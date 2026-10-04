"""Storage side of market-v2 (spec §4.4): assemble `core.market_v2.Row`s from
the DB, fit and predict walk-forward, persist one `MarketPrediction` per
`(player, day)`, score at 7 days, and the v2 track record.

Kept beside `storage/our_models.py` rather than inside it — this module is
owned by the market-v2 work and both are already large.
"""

import bisect
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, delete, select

from core import expected_points as xp
from core import jornadas as jr
from core import market_model as mm
from core import market_v2 as m2
from core import ranks as rk
from core import reliability as rel
from core.config import get_settings
from storage import our_models as om
from storage.db import as_utc
from storage.expected_points import last_season_means
from storage.models import (
    ExternalMatch,
    Fixture,
    MarketPrediction,
    Player,
    PlayerMarketDaily,
    PlayerMatchStats,
    PlayerSnapshot,
)

MODEL_VERSION = m2.MODEL_VERSION


@dataclass(frozen=True)
class RefreshSummary:
    generated: int
    scored: int


# --- schedule: every match date per club ------------------------------------------------


def load_schedule(session: Session, season: int) -> dict[str, list[date]]:
    """Per club, every match date this season: `ExternalMatch` ∪ `Fixture`,
    deduplicated on `(home, away)` with `ExternalMatch` winning. Shared with
    Task 6 and Plan C."""
    pairs: dict[tuple[str, str], date] = {}
    for home, away, kickoff in session.exec(
        select(Fixture.home_team, Fixture.away_team, Fixture.kickoff_utc)
        .where(Fixture.season_year == season)
    ).all():
        pairs[(home, away)] = as_utc(kickoff).date()
    for home, away, match_date in session.exec(
        select(ExternalMatch.home_team, ExternalMatch.away_team, ExternalMatch.match_date)
        .where(ExternalMatch.season_year == season)
    ).all():
        pairs[(home, away)] = match_date

    out: dict[str, set[date]] = defaultdict(set)
    for (home, away), day in pairs.items():
        out[home].add(day)
        out[away].add(day)
    return {team: sorted(days) for team, days in out.items()}


# --- features -----------------------------------------------------------------------------


def _pts_vs_exp(
    known_club_weeks: set[int],
    points: dict[int, int],
    last_season_mean: float | None,
    position: str,
) -> float:
    history = [points.get(w, 0) for w in sorted(known_club_weeks)]
    if len(history) < 3:
        return 0.0
    recent = statistics.fmean(history[-3:])
    rate = xp.points_rate(history, last_season_mean, position).value
    return recent - rate


def _minutes_trend(matches: list[rel.ClubMatch], known_club_weeks: set[int]) -> float:
    ms = sorted((m for m in matches if m.week in known_club_weeks), key=lambda m: m.week)
    trend = rel.reliability(ms, rel.DEFAULT_PRIOR, None, "available").minutes_trend
    return 0.0 if trend is None else trend


def _latest_at_or_before(dates: list[date], values: list, d: date):
    idx = bisect.bisect_right(dates, d) - 1
    return values[idx] if idx >= 0 else None


def _avail_change(dates: list[date], statuses: list[str], d: date) -> float:
    cur = _latest_at_or_before(dates, statuses, d)
    prev = _latest_at_or_before(dates, statuses, d - timedelta(days=7))
    if cur is None or prev is None:
        return 0.0
    if prev == "available" and cur in rel.UNAVAILABLE:
        return -1.0
    if prev in rel.UNAVAILABLE and cur == "available":
        return 1.0
    return 0.0


def _days_to_match(club_days: list[date], d: date, cap: float = 14.0) -> float:
    idx = bisect.bisect_right(club_days, d)
    if idx >= len(club_days):
        return cap
    return min(cap, float((club_days[idx] - d).days))


def build_rows(session: Session, season: int) -> list[m2.Row]:
    """One row per `(player, day)` in `PlayerMarketDaily` for the season,
    every feature built from data dated ≤ that day."""
    players = session.exec(select(Player)).all()
    player_by_id = {p.id: p for p in players}
    team_of = {p.id: p.team for p in players}

    daily = session.exec(
        select(PlayerMarketDaily.player_id, PlayerMarketDaily.day, PlayerMarketDaily.market_value)
        .where(PlayerMarketDaily.season_year == season)
    ).all()
    if not daily:
        return []
    values_by_player: dict[int, dict[date, int]] = defaultdict(dict)
    days_by_player: dict[int, list[date]] = defaultdict(list)
    values_by_day: dict[date, dict[int, int]] = defaultdict(dict)
    for pid, day, value in daily:
        values_by_player[pid][day] = value
        days_by_player[pid].append(day)
        values_by_day[day][pid] = value

    schedule = load_schedule(session, season)
    week_ends = jr.week_end_dates(schedule)

    gw_rows = om.load_gameweek_rows(session)
    club_weeks = om.team_played_weeks(gw_rows, team_of)
    points_by_player: dict[int, dict[int, int]] = defaultdict(dict)
    for r in gw_rows:
        if r.season_year == season:
            points_by_player[r.player_id][r.week] = r.points

    match_rows = session.exec(
        select(PlayerMatchStats.player_id, PlayerMatchStats.week, PlayerMatchStats.minutes,
               PlayerMatchStats.appearance)
        .where(PlayerMatchStats.season_year == season)
    ).all()
    matches_by_player: dict[int, list[rel.ClubMatch]] = defaultdict(list)
    for pid, week, minutes, appearance in match_rows:
        matches_by_player[pid].append(rel.ClubMatch(week=week, minutes=minutes,
                                                     appearance=appearance))

    snaps = session.exec(
        select(PlayerSnapshot.player_id, PlayerSnapshot.as_of, PlayerSnapshot.availability_status)
    ).all()
    avail_dates: dict[int, list[date]] = defaultdict(list)
    avail_status: dict[int, list[str]] = defaultdict(list)
    for pid, as_of, status in sorted(snaps, key=lambda r: (r[0], r[1])):
        avail_dates[pid].append(as_of)
        avail_status[pid].append(status)

    last_season_mean = last_season_means(session, season)

    # Cross-sectional percentile, per day, within position.
    percentile_by_day: dict[date, dict[int, float]] = {}
    for day, vals in values_by_day.items():
        positions = {pid: player_by_id[pid].position for pid in vals if pid in player_by_id}
        percentile_by_day[day] = {
            pid: r.percentile for pid, r in rk.position_ranks(vals, positions).items()
        }

    known_cache: dict[date, frozenset[int]] = {}
    # (player_id, frozenset(known club-played weeks)) -> (pts_vs_exp, minutes_trend)
    feature_cache: dict[tuple[int, frozenset[int]], tuple[float, float]] = {}

    rows_out: list[m2.Row] = []
    for pid, days in days_by_player.items():
        player = player_by_id.get(pid)
        if player is None:
            continue
        team = team_of.get(pid)
        values = values_by_player[pid]
        club_days = schedule.get(team, [])
        matches = matches_by_player.get(pid, [])
        own_points = points_by_player.get(pid, {})
        own_club_weeks = club_weeks.get(team, set())
        own_avail_dates = avail_dates.get(pid, [])
        own_avail_status = avail_status.get(pid, [])

        for d in sorted(set(days)):
            known = known_cache.get(d)
            if known is None:
                known = frozenset(jr.known_weeks(week_ends, d))
                known_cache[d] = known
            club_known_weeks = frozenset(w for w in known if (season, w) in own_club_weeks)

            cache_key = (pid, club_known_weeks)
            cached = feature_cache.get(cache_key)
            if cached is None:
                cached = (
                    _pts_vs_exp(club_known_weeks, own_points, last_season_mean.get(pid),
                                player.position),
                    _minutes_trend(matches, club_known_weeks),
                )
                feature_cache[cache_key] = cached
            pts_vs_exp, minutes_trend = cached

            target_day = d + timedelta(days=m2.OUTLOOK_DAYS)
            x = {
                "r1": m2.price_change_pct(values, d, 1) or 0.0,
                "r3": m2.price_change_pct(values, d, 3) or 0.0,
                "r7": m2.price_change_pct(values, d, 7) or 0.0,
                "pts_vs_exp": pts_vs_exp,
                "minutes_trend": minutes_trend,
                "avail_change": _avail_change(own_avail_dates, own_avail_status, d),
                "days_to_match": _days_to_match(club_days, d),
                "price_level": percentile_by_day.get(d, {}).get(pid, 50.0) / 100,
            }
            target = m2.price_change_pct(values, target_day, m2.OUTLOOK_DAYS)
            rows_out.append(m2.Row(pid, player.position, d, x, target, target_day))
    return rows_out


# --- generation, scoring -------------------------------------------------------------------


def _fit_date_for(fit_dates: list[date], d: date) -> date:
    idx = bisect.bisect_right(fit_dates, d) - 1
    return fit_dates[max(idx, 0)]


def _outcome_values(session: Session, season: int) -> dict[int, dict[date, int]]:
    out: dict[int, dict[date, int]] = defaultdict(dict)
    for pid, day, value in session.exec(
        select(PlayerMarketDaily.player_id, PlayerMarketDaily.day, PlayerMarketDaily.market_value)
        .where(PlayerMarketDaily.season_year == season)
    ).all():
        out[pid][day] = value
    return out


def _score_pending(session: Session, values: dict[int, dict[date, int]]) -> int:
    pending = session.exec(
        select(MarketPrediction)
        .where(MarketPrediction.model_version == MODEL_VERSION)
        .where(MarketPrediction.outcome_as_of.is_(None))
    ).all()
    scored = 0
    for p in pending:
        target_day = p.made_on + timedelta(days=m2.OUTLOOK_DAYS)
        actual_pct = m2.price_change_pct(values.get(p.player_id, {}), target_day, m2.OUTLOOK_DAYS)
        if actual_pct is None:
            continue
        actual_direction, hit = m2.score(p.direction, actual_pct)
        p.outcome_as_of = target_day
        p.outcome_gap_days = m2.OUTLOOK_DAYS
        p.actual_pct = actual_pct
        p.actual_direction = actual_direction
        p.scoring = "7d"
        p.hit = hit
        session.add(p)
        scored += 1
    session.commit()
    return scored


def refresh_market_v2(
    session: Session, today: date | None = None, now: datetime | None = None
) -> RefreshSummary:
    """Generate a `market-v2` prediction for every `(player, day)` with none,
    re-generating only the latest day when it equals `today` (same rule as
    v1: a day with a known outcome is never rewritten), then score every
    pending row whose 7-day outcome is now known."""
    today = today or date.today()
    now = now or datetime.now(UTC)
    season = get_settings().current_season_year
    rows = build_rows(session, season)
    if not rows:
        return RefreshSummary(0, 0)

    have = set(
        session.exec(
            select(MarketPrediction.player_id, MarketPrediction.made_on)
            .where(MarketPrediction.model_version == MODEL_VERSION)
        ).all()
    )
    latest_day = max(r.day for r in rows)
    if latest_day == today:
        session.exec(
            delete(MarketPrediction)
            .where(MarketPrediction.made_on == latest_day)
            .where(MarketPrediction.model_version == MODEL_VERSION)
        )
        have = {k for k in have if k[1] != latest_day}

    first_day = min(r.day for r in rows)
    fit_dates = m2.fit_dates(first_day, today)
    fit_cache: dict[date, dict[str, m2.Fit]] = {}

    generated = 0
    for row in rows:
        key = (row.player_id, row.day)
        if key in have:
            continue
        f = _fit_date_for(fit_dates, row.day)
        fits = fit_cache.get(f)
        if fits is None:
            fits = m2.fit_models(rows, f)
            fit_cache[f] = fits
        o = m2.predict(row, fits)
        session.add(
            MarketPrediction(
                made_on=row.day,
                player_id=row.player_id,
                model_version=MODEL_VERSION,
                predicted_pct=o.expected_pct,
                direction=o.direction,
                confidence=m2.confidence_for(o),
                inputs=json.dumps({
                    "lower": o.lower,
                    "upper": o.upper,
                    "dropRisk": o.drop_risk,
                    "basis": o.basis,
                    "terms": o.terms,
                    "features": row.x,
                    "horizonDays": m2.OUTLOOK_DAYS,
                }),
                generated_at=now,
                retroactive=now.date() > row.day,
            )
        )
        generated += 1
    session.commit()

    scored = _score_pending(session, _outcome_values(session, season))
    return RefreshSummary(generated, scored)


# --- read models -----------------------------------------------------------------------


def latest_outlooks(session: Session, on: date | None = None) -> dict[int, m2.Outlook]:
    """The stored predictions for the latest `made_on` ≤ `on` (default: the
    latest `made_on` stored)."""
    query = select(MarketPrediction).where(MarketPrediction.model_version == MODEL_VERSION)
    if on is not None:
        query = query.where(MarketPrediction.made_on <= on)
    rows = session.exec(query).all()
    if not rows:
        return {}
    made_on = max(r.made_on for r in rows)
    out: dict[int, m2.Outlook] = {}
    for r in rows:
        if r.made_on != made_on:
            continue
        inputs = json.loads(r.inputs)
        out[r.player_id] = m2.Outlook(
            expected_pct=r.predicted_pct,
            direction=r.direction,
            lower=inputs.get("lower", r.predicted_pct),
            upper=inputs.get("upper", r.predicted_pct),
            drop_risk=inputs.get("dropRisk", False),
            basis=inputs.get("basis", ""),
            terms=inputs.get("terms", {}),
        )
    return out


def v2_track_record(session: Session) -> dict:
    """market-v2's track record: our scored calls (MODEL-03's vocabulary),
    interval coverage and MAE, and the naive baseline ("next week repeats
    last week", i.e. predict `r7` itself)."""
    preds = session.exec(
        select(MarketPrediction).where(MarketPrediction.model_version == MODEL_VERSION)
    ).all()
    ours = mm.summarize(
        mm.ScoredCall(p.confidence, p.scoring, p.hit, p.retroactive, p.outcome_gap_days)
        for p in preds
    )

    scored = [p for p in preds if p.hit is not None]
    inside = 0
    errors: list[float] = []
    naive_hits = 0
    naive_errors: list[float] = []
    for p in scored:
        inputs = json.loads(p.inputs)
        lower, upper = inputs.get("lower"), inputs.get("upper")
        if lower is not None and upper is not None and lower <= p.actual_pct <= upper:
            inside += 1
        errors.append(abs(p.predicted_pct - p.actual_pct))
        r7 = inputs.get("features", {}).get("r7", 0.0)
        if m2.direction_of(r7) == p.actual_direction:
            naive_hits += 1
        naive_errors.append(abs(r7 - p.actual_pct))

    n = len(scored)
    return {
        "modelVersion": MODEL_VERSION,
        "ours": ours,
        "intervalCoverage": inside / n if n else None,
        "mae": statistics.fmean(errors) if errors else None,
        "naive": {
            "rule": "next week repeats last week",
            "hitRate": naive_hits / n if n else None,
            "mae": statistics.fmean(naive_errors) if naive_errors else None,
        },
    }
