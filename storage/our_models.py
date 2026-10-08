"""Storage side of Phase 10's own models: load rows for `core.analytics` and
`core.market_model`, persist and score market predictions, and assemble the
read-models the API serves.

Kept out of `storage/repository.py` deliberately — that module is shared by
every feature and edited in parallel; this one is owned by the models work.
It is still storage, so it is still one of the only places that talks SQL.
"""

import bisect
import json
import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlmodel import Session, delete, func, select

from core import analytics as an
from core import market_model as mm
from core import market_v2 as m2
from core.analytics import team_played_weeks  # lives in core; storage callers import it here
from core.config import get_settings
from core.ranks import Rank, position_ranks
from storage.db import as_utc
from storage.expected_points import last_season_means, latest_expected_points, stored_predictions
from storage.models import (
    Fixture,
    MarketPrediction,
    Player,
    PlayerGameweekPoints,
    PlayerMarketDaily,
    PlayerSnapshot,
    SourcePrediction,
)

#: A calendar jornada counts as over once this many of its fixtures are final
#: and none that has kicked off is still live.
MIN_FINAL_FIXTURES = 8

# --- loading ------------------------------------------------------------------------


def load_gameweek_rows(session: Session) -> list[an.GameweekRow]:
    rows = session.exec(
        select(
            PlayerGameweekPoints.season_year,
            PlayerGameweekPoints.week,
            PlayerGameweekPoints.player_id,
            PlayerGameweekPoints.points,
            PlayerGameweekPoints.is_provisional,
        )
    ).all()
    return [an.GameweekRow(*r) for r in rows]


def _latest_as_of(session: Session) -> date | None:
    return session.exec(select(func.max(PlayerSnapshot.as_of))).one()


def load_snapshot_points(
    session: Session, player_ids: list[int] | None = None
) -> dict[int, list[mm.SnapshotPoint]]:
    """Every captured snapshot per player, oldest first."""
    query = select(
        PlayerSnapshot.player_id,
        PlayerSnapshot.as_of,
        PlayerSnapshot.market_value,
        PlayerSnapshot.price_change_pct,
        PlayerSnapshot.starter_probability,
        PlayerSnapshot.availability_status,
        PlayerSnapshot.points,
    ).order_by(PlayerSnapshot.as_of)
    if player_ids is not None:
        query = query.where(PlayerSnapshot.player_id.in_(player_ids))
    out: dict[int, list[mm.SnapshotPoint]] = defaultdict(list)
    for pid, *fields in session.exec(query).all():
        out[pid].append(mm.SnapshotPoint(*fields))
    return out


def _momentum7_values(
    session: Session, season: int, player_ids: Iterable[int]
) -> dict[int, float | None]:
    """7-day price momentum per player, for position-ranking only
    (Plan D Task 1): the daily series' change (`PlayerMarketDaily`, Plan A)
    where it exists, else the snapshot series' change for players the
    daily table hasn't captured yet (`core.analytics.value_momentum`)."""
    daily = session.exec(
        select(PlayerMarketDaily.player_id, PlayerMarketDaily.day,
               PlayerMarketDaily.market_value)
        .where(PlayerMarketDaily.season_year == season)
    ).all()
    by_player: dict[int, dict[date, int]] = defaultdict(dict)
    for pid, day, value in daily:
        by_player[pid][day] = value

    out: dict[int, float | None] = {}
    for pid in player_ids:
        values = by_player.get(pid)
        out[pid] = m2.price_change_pct(values, max(values), 7) if values else None

    missing = [pid for pid, pct in out.items() if pct is None]
    if missing:
        snaps = load_snapshot_points(session, missing)
        for pid in missing:
            history = [(s.as_of, s.market_value) for s in snaps.get(pid, [])]
            out[pid] = an.value_momentum(history, [7])[0].pct
    return out


def calendar_final_weeks(session: Session, season: int, now: datetime) -> set[tuple[int, int]]:
    """Current-season jornadas the calendar says are over: at least
    `MIN_FINAL_FIXTURES` final, and every fixture that has kicked off final
    (a postponed match still in the future does not hold the week open)."""
    by_day: dict[int, list[Fixture]] = defaultdict(list)
    for f in session.exec(select(Fixture).where(Fixture.season_year == season)).all():
        by_day[f.matchday].append(f)
    out = set()
    for day, fixtures in by_day.items():
        finals = sum(1 for f in fixtures if f.is_final)
        live = any(not f.is_final and as_utc(f.kickoff_utc) <= now for f in fixtures)
        if finals >= MIN_FINAL_FIXTURES and not live:
            out.add((season, day))
    return out


# --- ANALYTICS: per-player scores ---------------------------------------------------


@dataclass(frozen=True)
class PlayerAnalytics:
    player_id: int
    series: list[int]
    form: an.FormResult
    consistency: an.ConsistencyResult
    power_inputs: an.PowerInputs | None
    power: an.PowerResult | None
    valuation: an.ValuationResult | None
    economy: float | None
    market_value: int | None


def compute_player_analytics(
    session: Session,
    now: datetime | None = None,
    season: int | None = None,
) -> dict[int, PlayerAnalytics]:
    """Power, Economy and their components for every player in the latest
    snapshot.

    Power v2 reads his current-season points per team match, shrunk toward
    last season's mean (`core.analytics.power_score`). Expected points for the
    next fixture are deliberately not blended in — they are their own number.
    """
    now = now or datetime.now(UTC)
    season = season or get_settings().current_season_year
    latest = _latest_as_of(session)
    if latest is None:
        return {}
    market = session.exec(
        select(PlayerSnapshot.player_id, PlayerSnapshot.market_value, Player.position,
               PlayerSnapshot.availability_status, PlayerSnapshot.starter_probability)
        .join(Player, Player.id == PlayerSnapshot.player_id)
        .where(PlayerSnapshot.as_of == latest)
    ).all()

    team_of = dict(session.exec(select(Player.id, Player.team)).all())
    gw_rows = load_gameweek_rows(session)
    timeline = an.build_timeline(gw_rows, calendar_final_weeks(session, season, now))
    played = team_played_weeks(gw_rows, team_of)
    by_player: dict[int, list[an.GameweekRow]] = defaultdict(list)
    for r in gw_rows:
        by_player[r.player_id].append(r)
    prior = last_season_means(session, season)
    season_timeline = [k for k in timeline if k[0] == season]

    window = an.FORM_WINDOW + an.BASELINE_WINDOW
    partial = {}
    val_inputs = []
    for pid, market_value, position, availability, starter in market:
        team_weeks = played.get(team_of.get(pid), set())
        rows_p = by_player.get(pid, [])
        series = an.player_series(timeline, rows_p, n=window, team_weeks=team_weeks)
        history = an.player_series(season_timeline, rows_p, n=len(season_timeline),
                                   team_weeks=team_weeks)
        inputs = an.power_inputs(series, history, prior.get(pid), position, availability)
        power = an.power_score(inputs) if inputs else None
        partial[pid] = (series, inputs, power, market_value)
        if power is not None:
            recent_avg = statistics.fmean(series[-an.RECENT_WINDOW:])
            val_inputs.append(an.ValuationInput(pid, position, power.quality_ppg, market_value,
                                                inputs.recent_jornadas, starter, recent_avg,
                                                current_matches=inputs.rate_matches,
                                                availability=availability))

    vals = an.valuations(val_inputs)
    econ = an.economy_scores(vals)
    return {
        pid: PlayerAnalytics(
            player_id=pid,
            series=series,
            form=an.form(series),
            consistency=an.consistency(series),
            power_inputs=inputs,
            power=power,
            valuation=vals.get(pid),
            economy=econ.get(pid),
            market_value=market_value,
        )
        for pid, (series, inputs, power, market_value) in partial.items()
    }


def score_fields(a: PlayerAnalytics | None) -> dict:
    """The two headline numbers, as the browser and squad payloads carry them."""
    return {
        "powerScore": round(a.power.score, 1) if a and a.power else None,
        "economyScore": round(a.economy, 1) if a and a.economy is not None else None,
    }


def _round(x: float | None, n: int = 2) -> float | None:
    return round(x, n) if x is not None else None


#: `player_analytics_payload`'s Plan B Task 7 blocks when the player has no
#: live inputs (no snapshot and no price at all) — the same null shape
#: `api.routes.analytics._EMPTY` serves when the player has nothing else
#: either.
_EMPTY_INPUTS = {
    "powerRank": None,
    "reliability": None,
    "evidence": None,
    "pointsValue": None,
    "priceOutlook": None,
    "expectedReturnEur": None,
    "inputsConfidence": None,
    "dataThrough": None,
}


def _rank_entry(r: Rank | None, position: str | None) -> dict | None:
    return (
        {"rank": r.rank, "of": r.of, "percentile": round(r.percentile, 1), "position": position}
        if r and position else None
    )


def _ranks_block(session: Session, all_analytics: dict, player_id: int, live_inputs) -> dict:
    """Plan D Task 1: a within-position rank for every metric card.

    `power`/`pointsValue`/`outlook`/`reliability` are read straight off
    `compute_live_inputs`' own `PlayerInputs.ranks` (Plan B) — they are
    already computed once for every player there. `form`/`consistency`
    rank among players with a value from `compute_player_analytics`; `xp`
    ranks the latest stored jornada's expected points
    (`storage.expected_points.latest_expected_points`), leaving `no_fixture`
    blanks unranked; `momentum7` ranks the 7-day price move."""
    season = get_settings().current_season_year
    positions = dict(session.exec(select(Player.id, Player.position)).all())
    player_position = positions.get(player_id)

    form_values = {pid: pa.form.value for pid, pa in all_analytics.items()}
    consistency_values = {pid: pa.consistency.value for pid, pa in all_analytics.items()}
    xp_latest = latest_expected_points(session, season)
    xp_values = {pid: v for pid, (v, basis) in xp_latest.items() if basis != "no_fixture"}
    momentum7_values = _momentum7_values(session, season, positions)

    form_ranks = position_ranks(form_values, positions)
    consistency_ranks = position_ranks(consistency_values, positions)
    xp_ranks = position_ranks(xp_values, positions)
    momentum7_ranks = position_ranks(momentum7_values, positions)

    def _r(r: Rank | None) -> dict | None:
        return _rank_entry(r, player_position)

    live_ranks = live_inputs.ranks if live_inputs else {}
    return {
        "power": _r(live_ranks.get("power")),
        "pointsValue": _r(live_ranks.get("pointsValue")),
        "outlook": _r(live_ranks.get("outlook")),
        "reliability": _r(live_ranks.get("start")),
        "xp": _r(xp_ranks.get(player_id)),
        "form": _r(form_ranks.get(player_id)),
        "consistency": _r(consistency_ranks.get(player_id)),
        "momentum7": _r(momentum7_ranks.get(player_id)),
    }


def _xp_card(session: Session, player_id: int) -> dict | None:
    """Plan D Task 1's xP card: the latest stored jornada's prediction for
    this one player — one request (`storage.expected_points.
    stored_predictions`), its terms/coefficients/rate read straight off the
    stored `inputs` JSON (`core.expected_points.expected_points`)."""
    _, _, rows = stored_predictions(session, player_id=player_id)
    if not rows:
        return None
    row, _player = rows[0]
    row_inputs = json.loads(row.inputs)
    return {
        "value": round(row.predicted, 2),
        "basis": row.basis,
        "jornada": row.jornada,
        "opponent": row.opponent,
        "isHome": row.is_home,
        "terms": row_inputs.get("terms"),
        "coefficients": row_inputs.get("coefficients"),
        "rate": row_inputs.get("rate"),
    }


def player_analytics_payload(
    session: Session, player_id: int, windows: list[int]
) -> dict | None:
    """ANALYTICS-05: every metric with its inputs and its window."""
    # Imported here, not at module level: `storage.inputs` itself imports
    # `calendar_final_weeks`/`load_gameweek_rows` from this module, so a
    # top-level import the other way would be a cycle.
    from storage.inputs import compute_live_inputs, inputs_payload

    all_analytics = compute_player_analytics(session)
    a = all_analytics.get(player_id)
    history = [
        (s.as_of, s.market_value) for s in load_snapshot_points(session, [player_id])[player_id]
    ]
    if a is None and not history:
        return None
    momentum = an.value_momentum(history, windows)
    prediction = session.exec(
        select(MarketPrediction)
        .where(MarketPrediction.player_id == player_id)
        .where(MarketPrediction.model_version == mm.MODEL_VERSION)
        .order_by(MarketPrediction.made_on.desc())
    ).first()

    # Plan B Task 7: reliability, points value, outlook and Power's position
    # rank — computed once for every player, same as the browser table.
    all_live_inputs = compute_live_inputs(session)
    live_inputs = all_live_inputs.get(player_id)
    inputs = inputs_payload(live_inputs) if live_inputs is not None else _EMPTY_INPUTS

    ranks = _ranks_block(session, all_analytics, player_id, live_inputs)
    xp_block = _xp_card(session, player_id)

    recent = a.series[-an.RECENT_WINDOW:] if a else []
    fit = a.valuation.fit if a and a.valuation else None
    return {
        "playerId": player_id,
        "form": a and {
            "value": _round(a.form.value),
            "formAvg": _round(a.form.form_avg),
            "baselineAvg": _round(a.form.baseline_avg),
            "window": a.form.window,
            "baselineWindow": a.form.baseline_window,
            "formJornadas": a.form.form_jornadas,
            "baselineJornadas": a.form.baseline_jornadas,
            "recentPoints": a.series[-an.FORM_WINDOW:],
        },
        "consistency": a and {
            "value": _round(a.consistency.value, 1),
            "mean": _round(a.consistency.mean),
            "sd": _round(a.consistency.sd),
            "window": a.consistency.window,
            "jornadas": a.consistency.jornadas,
            "points": recent,
        },
        "momentum": [
            {
                "windowDays": m.window_days,
                "fromDate": m.from_date.isoformat() if m.from_date else None,
                "toDate": m.to_date.isoformat() if m.to_date else None,
                "fromValue": m.from_value,
                "toValue": m.to_value,
                "days": m.days,
                "pct": _round(m.pct),
                "ratePerDay": _round(m.rate_per_day, 3),
                "direction": m.direction,
            }
            for m in momentum
        ],
        "power": a and a.power and {
            "score": _round(a.power.score, 1),
            "powerPpg": _round(a.power.power_ppg),
            "qualityPpg": _round(a.power.quality_ppg),
            "rate": _round(a.power_inputs.rate),
            "rateMatches": a.power_inputs.rate_matches,
            "prior": _round(a.power_inputs.prior),
            "priorSource": a.power_inputs.prior_source,
            "calibration": {"a": a.power.calibration[0], "c": a.power.calibration[1]},
            "availability": a.power_inputs.availability,
            "availabilityFactor": a.power.availability_factor,
            "recentJornadas": a.power_inputs.recent_jornadas,
            "referencePpg": an.POWER_REFERENCE_PPG,
        },
        "valuation": a and a.valuation and {
            "marketValue": a.market_value,
            "fairValue": a.valuation.fair_value,
            "gapPct": _round(a.valuation.gap * 100, 1) if a.valuation.gap is not None else None,
            "reason": a.valuation.reason,
            "fit": fit and {
                "intercept": _round(fit.intercept, 4),
                "slope": _round(fit.slope, 4),
                "n": fit.n,
                "rSquared": _round(fit.r_squared, 3),
                "pooled": fit.pooled,
            },
        },
        "economy": a and {
            "score": _round(a.economy, 1),
            "basis": "percentile of the log-log valuation gap among valued players "
                     "(starter > 30%, ≥ 3 matches this season, available)",
        },
        "marketPrediction": prediction and _prediction_payload(prediction),
        "ranks": ranks,
        "xp": xp_block,
        **inputs,
    }


# --- MODEL-01 / MODEL-03: generate, persist, score --------------------------------


@dataclass(frozen=True)
class RefreshSummary:
    generated: int
    scored: int


def _prediction_payload(p: MarketPrediction) -> dict:
    return {
        "madeOn": p.made_on.isoformat(),
        "modelVersion": p.model_version,
        "predictedPct": _round(p.predicted_pct, 3),
        "direction": p.direction,
        "confidence": p.confidence,
        "inputs": json.loads(p.inputs),
        "retroactive": p.retroactive,
        "outcome": (
            {
                "asOf": p.outcome_as_of.isoformat(),
                "gapDays": p.outcome_gap_days,
                "actualPct": _round(p.actual_pct, 3),
                "actualDirection": p.actual_direction,
                "scoring": p.scoring,
                "hit": p.hit,
            }
            if p.outcome_as_of
            else None
        ),
    }


def _previous(points: list[mm.SnapshotPoint], i: int) -> mm.SnapshotPoint | None:
    return points[i - 1] if i > 0 else None


def refresh_market_predictions(session: Session, today: date | None = None,
                               now: datetime | None = None) -> RefreshSummary:
    """Generate predictions for every snapshot date that has none, replace
    today's when today's snapshots were re-captured, then score.

    A date that already has predictions is never regenerated unless it is
    today and the latest snapshot date — so a prediction whose outcome is
    known can never be rewritten, and a refresh on a later day whose market
    scrape failed cannot overwrite live calls with retroactive ones.
    """
    today = today or date.today()
    now = now or datetime.now(UTC)
    snapshots = load_snapshot_points(session)
    dates = sorted({p.as_of for pts in snapshots.values() for p in pts})
    if not dates:
        return RefreshSummary(0, 0)
    have = set(
        session.exec(
            select(MarketPrediction.made_on)
            .where(MarketPrediction.model_version == mm.MODEL_VERSION)
            .distinct()
        ).all()
    )
    latest = dates[-1]
    targets = [d for d in dates if d not in have]
    if latest == today and latest in have:
        session.exec(
            delete(MarketPrediction)
            .where(MarketPrediction.made_on == latest)
            .where(MarketPrediction.model_version == mm.MODEL_VERSION)
        )
        targets.append(latest)
    targets_set = set(targets)

    generated = 0
    for pid, points in snapshots.items():
        for i, point in enumerate(points):
            if point.as_of not in targets_set:
                continue
            p = mm.predict(point, _previous(points, i))
            session.add(
                MarketPrediction(
                    made_on=point.as_of,
                    player_id=pid,
                    model_version=mm.MODEL_VERSION,
                    predicted_pct=p.predicted_pct,
                    direction=p.direction,
                    confidence=p.confidence,
                    inputs=json.dumps(p.inputs),
                    generated_at=now,
                    retroactive=now.date() > point.as_of,
                )
            )
            generated += 1
    session.commit()
    scored = score_market_predictions(session, snapshots, latest)
    return RefreshSummary(generated, scored)


def _next_point(points: list[mm.SnapshotPoint], made_on: date):
    dates = [p.as_of for p in points]
    i = bisect.bisect_right(dates, made_on)
    if i == 0 or points[i - 1].as_of != made_on or i >= len(points):
        return None, None
    return points[i - 1], points[i]


def score_market_predictions(
    session: Session,
    snapshots: dict[int, list[mm.SnapshotPoint]] | None = None,
    latest: date | None = None,
) -> int:
    """Score every pending prediction, and re-score any scored against the
    latest date (a same-day re-run may have replaced that snapshot)."""
    snapshots = snapshots if snapshots is not None else load_snapshot_points(session)
    latest = latest or _latest_as_of(session)
    pending = session.exec(
        select(MarketPrediction).where(
            (MarketPrediction.outcome_as_of.is_(None))
            | (MarketPrediction.outcome_as_of == latest)
        )
    ).all()
    scored = 0
    for p in pending:
        made_from, nxt = _next_point(snapshots.get(p.player_id, []), p.made_on)
        if nxt is None:
            continue
        o = mm.score(made_from, p.direction, nxt)
        p.outcome_as_of = o.outcome_as_of
        p.outcome_gap_days = o.gap_days
        p.actual_pct = o.actual_pct
        p.actual_direction = o.actual_direction
        p.scoring = o.scoring
        p.hit = o.hit
        session.add(p)
        scored += 1
    session.commit()
    return scored


# --- read models: predictions, track record, divergence -------------------------------


def _players(session: Session, ids) -> dict[int, Player]:
    ids = list(ids)
    if not ids:
        return {}
    return {p.id: p for p in session.exec(select(Player).where(Player.id.in_(ids))).all()}


def market_predictions_payload(session: Session, made_on: date | None = None) -> dict:
    made_on = made_on or session.exec(
        select(func.max(MarketPrediction.made_on)).where(
            MarketPrediction.model_version == mm.MODEL_VERSION
        )
    ).one()
    if made_on is None:
        return {"madeOn": None, "modelVersion": mm.MODEL_VERSION, "predictions": []}
    rows = session.exec(
        select(MarketPrediction)
        .where(MarketPrediction.made_on == made_on)
        .where(MarketPrediction.model_version == mm.MODEL_VERSION)
    ).all()
    players = _players(session, (r.player_id for r in rows))
    mv = dict(
        session.exec(
            select(PlayerSnapshot.player_id, PlayerSnapshot.market_value).where(
                PlayerSnapshot.as_of == made_on
            )
        ).all()
    )
    out = []
    for r in sorted(rows, key=lambda r: -r.predicted_pct):
        pl = players.get(r.player_id)
        out.append(
            {
                "playerId": r.player_id,
                "name": pl.name if pl else None,
                "team": pl.team if pl else None,
                "position": pl.position if pl else None,
                "marketValue": mv.get(r.player_id),
                **_prediction_payload(r),
            }
        )
    return {"madeOn": made_on.isoformat(), "modelVersion": mm.MODEL_VERSION, "predictions": out}


def _source_market_rows(session: Session):
    return [
        r
        for r in session.exec(select(SourcePrediction)).all()
        if mm.source_direction(r.source) is not None
    ]


def track_record_payload(session: Session, model_version: str = mm.MODEL_VERSION) -> dict:
    if model_version == "market-v2":
        from storage.market_v2 import v2_track_record

        return v2_track_record(session)
    if model_version != mm.MODEL_VERSION:
        raise ValueError(
            f"unknown model_version {model_version!r}; expected "
            f"{mm.MODEL_VERSION!r} or 'market-v2'"
        )
    preds = session.exec(
        select(MarketPrediction).where(MarketPrediction.model_version == model_version)
    ).all()
    ours = mm.summarize(
        mm.ScoredCall(p.confidence, p.scoring, p.hit, p.retroactive, p.outcome_gap_days)
        for p in preds
    )

    by_day: dict[date, list[MarketPrediction]] = defaultdict(list)
    for p in preds:
        by_day[p.made_on].append(p)
    days = []
    for d in sorted(by_day):
        group = by_day[d]
        scored = [p for p in group if p.hit is not None]
        hits = sum(1 for p in scored if p.hit)
        days.append(
            {
                "madeOn": d.isoformat(),
                "predictions": len(group),
                "scored": len(scored),
                "hits": hits,
                "hitRate": hits / len(scored) if scored else None,
                "scoring": scored[0].scoring if scored else None,
                "gapDays": scored[0].outcome_gap_days if scored else None,
                "retroactive": all(p.retroactive for p in group),
            }
        )

    # The source's lists, scored by exactly the same rule, beside ours on
    # the same player-days — the only like-for-like comparison available.
    snapshots = load_snapshot_points(session)
    ours_by_key = {(p.made_on, p.player_id): p for p in preds}
    src_scored = src_hits = same_scored = same_hits = 0
    for r in _source_market_rows(session):
        made_from, nxt = _next_point(snapshots.get(r.player_id, []), r.as_of)
        if nxt is None:
            continue
        o = mm.score(made_from, mm.source_direction(r.source), nxt)
        src_scored += 1
        src_hits += o.hit
        mine = ours_by_key.get((r.as_of, r.player_id))
        if mine is not None and mine.hit is not None:
            same_scored += 1
            same_hits += mine.hit
    return {
        "modelVersion": mm.MODEL_VERSION,
        "ours": ours,
        "days": days,
        "source": {
            "scored": src_scored,
            "hits": src_hits,
            "hitRate": src_hits / src_scored if src_scored else None,
            "oursOnSamePlayers": {
                "scored": same_scored,
                "hits": same_hits,
                "hitRate": same_hits / same_scored if same_scored else None,
            },
        },
    }


def divergence_payload(session: Session) -> dict:
    """MODEL-04 — the latest day the source published market lists, every
    player they listed, both calls side by side, disagreements first."""
    rows = _source_market_rows(session)
    if not rows:
        return {"asOf": None, "rows": [], "agree": 0, "disagree": 0, "ourCallMissing": 0}
    as_of = max(r.as_of for r in rows)
    today_rows = [r for r in rows if r.as_of == as_of]
    ours = {
        p.player_id: p
        for p in session.exec(
            select(MarketPrediction)
            .where(MarketPrediction.made_on == as_of)
            .where(MarketPrediction.model_version == mm.MODEL_VERSION)
        ).all()
    }
    players = _players(session, (r.player_id for r in today_rows))
    out = []
    for r in today_rows:
        mine = ours.get(r.player_id)
        theirs = mm.source_direction(r.source)
        status = (
            "no-call" if mine is None
            else "agree" if mine.direction == theirs
            else "disagree"
        )
        pl = players.get(r.player_id)
        out.append(
            {
                "playerId": r.player_id,
                "name": pl.name if pl else None,
                "team": pl.team if pl else None,
                "position": pl.position if pl else None,
                "sourceList": r.source,
                "sourceDirection": theirs,
                "status": status,
                "ours": mine and _prediction_payload(mine),
            }
        )
    order = {"disagree": 0, "agree": 1, "no-call": 2}
    out.sort(key=lambda x: (order[x["status"]], x["name"] or ""))
    return {
        "asOf": as_of.isoformat(),
        "rows": out,
        "agree": sum(1 for x in out if x["status"] == "agree"),
        "disagree": sum(1 for x in out if x["status"] == "disagree"),
        "ourCallMissing": sum(1 for x in out if x["status"] == "no-call"),
    }
