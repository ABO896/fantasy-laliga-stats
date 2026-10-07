"""Live inputs — load every table once, compute every verdict input for
today (Plan B Task 6).

`core.inputs.compute_inputs` (Task 5) is pure and takes an `InputsData`
bundle plus the day's context (known weeks, upcoming fixtures, market
outlooks, fixture multipliers). This module is the one place that loads
that bundle from SQLite and calls it for "now" — the live app and the
verdict validation harness both go through it, so what the app shows and
what gets backtested can never drift apart.

Kept beside `storage/our_models.py`, `storage/expected_points.py` and
`storage/transfers.py` rather than folded into any of them — those are each
owned by their own slice of work; this one belongs to the Plan B inputs
layer that sits on top of all three.
"""

from collections import defaultdict
from datetime import UTC, date, datetime

from sqlmodel import Session, func, select

from core import analytics as an
from core import market_v2 as m2
from core import transfers as tr
from core.config import get_settings
from core.fixture_difficulty import FixtureView
from core.freshness import madrid_date
from core.inputs import InputsData, PlayerBase, PlayerInputs, SnapshotState, UpcomingMatch
from core.inputs import compute_inputs as _compute_inputs
from core.ranks import Rank
from core.reliability import HALF_LIFE, PRIOR_WEIGHT, SOURCE_BLEND
from core.rules import load_rules
from storage.expected_points import ODDS_SOURCE, last_season_means, odds_probabilities
from storage.market_v2 import latest_outlooks
from storage.models import (
    Player,
    PlayerGameweekPoints,
    PlayerMarketDaily,
    PlayerMatchStats,
    PlayerPageFetch,
    PlayerSnapshot,
)
from storage.our_models import calendar_final_weeks, load_gameweek_rows
from storage.repository import get_fixtures
from storage.transfers import fixture_outlooks

#: Look-ahead jornadas for points, and the fixture window fed to the
#: fixture multiplier — spec §4, never restated.
LIVE_HORIZON = 3


# --- loading --------------------------------------------------------------------------


def load_inputs_data(session: Session, season: int) -> InputsData:
    """Every table `core.inputs.compute_inputs` reads, loaded once."""
    players = {
        p.id: PlayerBase(p.id, p.name, p.team, p.position)
        for p in session.exec(select(Player)).all()
    }
    gameweek_rows = load_gameweek_rows(session)

    match_lines: dict[int, dict[int, tuple[int, str]]] = defaultdict(dict)
    for pid, week, minutes, appearance in session.exec(
        select(PlayerMatchStats.player_id, PlayerMatchStats.week, PlayerMatchStats.minutes,
               PlayerMatchStats.appearance)
        .where(PlayerMatchStats.season_year == season)
    ).all():
        match_lines[pid][week] = (minutes, appearance)

    page_players = frozenset(
        session.exec(
            select(PlayerPageFetch.player_id)
            .where(PlayerPageFetch.weeks_checked_through.is_not(None))
        ).all()
    )

    prices: dict[int, dict[date, int]] = defaultdict(dict)
    for pid, day, value in session.exec(
        select(PlayerMarketDaily.player_id, PlayerMarketDaily.day,
               PlayerMarketDaily.market_value)
        .where(PlayerMarketDaily.season_year == season)
    ).all():
        prices[pid][day] = value

    snapshots: dict[int, list[SnapshotState]] = defaultdict(list)
    snap_rows = session.exec(
        select(PlayerSnapshot.player_id, PlayerSnapshot.as_of, PlayerSnapshot.market_value,
               PlayerSnapshot.availability_status, PlayerSnapshot.starter_probability)
        .order_by(PlayerSnapshot.as_of)
    ).all()
    for pid, as_of, market_value, availability, starter in snap_rows:
        snapshots[pid].append(SnapshotState(as_of, market_value, availability, starter))

    last_season_apps = dict(
        session.exec(
            select(PlayerGameweekPoints.player_id, func.count())
            .where(PlayerGameweekPoints.season_year == season - 1)
            .group_by(PlayerGameweekPoints.player_id)
        ).all()
    )

    return InputsData(
        season=season,
        players=players,
        gameweek_rows=gameweek_rows,
        match_lines=dict(match_lines),
        page_players=page_players,
        prices=dict(prices),
        snapshots=dict(snapshots),
        last_season_means=last_season_means(session, season),
        last_season_apps=last_season_apps,
        cash_per_point=load_rules().cash_per_point,
    )


def live_known_weeks(session: Session, season: int, now: datetime) -> set[int]:
    """This season's weeks on the shared points timeline, as of `now`."""
    timeline = an.build_timeline(
        load_gameweek_rows(session), calendar_final_weeks(session, season, now)
    )
    return {w for s, w in timeline if s == season}


def live_upcoming(
    session: Session, season: int, now: datetime, horizon: int = LIVE_HORIZON
) -> dict[str, list[UpcomingMatch]]:
    """Per club, the fixtures `core.transfers.select_window` chooses for the
    next `horizon` jornadas, with odds where `ExternalMatch` has the
    pairing. Every club the calendar has ever named this season gets a list
    — possibly empty, when it has nothing inside the window."""
    rows = get_fixtures(session, season)
    views = [
        FixtureView(r.fixture_id, r.matchday, r.kickoff_utc, r.kickoff_confirmed, r.is_final,
                    r.home_team, r.away_team)
        for r in rows
    ]
    _, weighed = tr.select_window(views, now, horizon)
    teams = {f.home_team for f in views} | {f.away_team for f in views}
    out: dict[str, list[UpcomingMatch]] = {team: [] for team in teams}
    for f in sorted(weighed, key=lambda f: (f.kickoff_utc, f.fixture_id)):
        for team, opponent, is_home in (
            (f.home_team, f.away_team, True), (f.away_team, f.home_team, False)
        ):
            if team not in out:
                continue
            team_goals, clean_sheet = odds_probabilities(
                session, season, f.home_team, f.away_team, team
            )
            odds_source = ODDS_SOURCE if team_goals is not None else None
            out[team].append(UpcomingMatch(opponent, is_home, team_goals, clean_sheet,
                                           odds_source))
    return out


# --- computing --------------------------------------------------------------------------


def compute_live_inputs(
    session: Session, now: datetime | None = None
) -> dict[int, PlayerInputs]:
    """Every verdict input for every player, as of today — one load of the
    database, then `core.inputs.compute_inputs` does the rest."""
    now = now or datetime.now(UTC)
    season = get_settings().current_season_year
    # The market's (Madrid) calendar date — the date every refresh stamps
    # its rows with — never the UTC date, which lags it after midnight.
    as_of = madrid_date(now)

    data = load_inputs_data(session, season)
    known_weeks = live_known_weeks(session, season, now)
    upcoming = live_upcoming(session, season, now, LIVE_HORIZON)
    outlooks = latest_outlooks(session, as_of)

    per_team, window, _ = fixture_outlooks(session, season, LIVE_HORIZON, now)
    spread = len(window) if window else LIVE_HORIZON
    fixture_multipliers = {
        team: tr.fixture_outlook(fixtures, spread).multiplier
        for team, fixtures in per_team.items()
    }

    return _compute_inputs(
        data, as_of, known_weeks, upcoming, outlooks, fixture_multipliers, horizon=LIVE_HORIZON
    )


# --- payload shaping -------------------------------------------------------------------


def _round(x: float | None, n: int = 3) -> float | None:
    return round(x, n) if x is not None else None


def _rank(r: Rank | None) -> dict | None:
    return {"rank": r.rank, "of": r.of, "percentile": round(r.percentile, 1)} if r else None


def inputs_fields(i: PlayerInputs | None) -> dict:
    """The compact fields the player list and squad payloads carry."""
    if i is None:
        return {
            "powerRank": None, "reliabilityClass": None, "pStart": None,
            "pointsValuePct": None, "outlookPct": None, "outlookDirection": None,
            "dropRisk": None, "xptsWindow": None,
        }
    power_rank = i.ranks.get("power")
    pv_rank = i.ranks.get("pointsValue")
    return {
        "powerRank": (
            {"rank": power_rank.rank, "of": power_rank.of} if power_rank else None
        ),
        "reliabilityClass": i.reliability.cls,
        "pStart": round(i.reliability.p_start_next, 3),
        "pointsValuePct": _round(pv_rank.percentile, 1) if pv_rank else None,
        "outlookPct": round(i.outlook.expected_pct, 2) if i.outlook else None,
        "outlookDirection": i.outlook.direction if i.outlook else None,
        "dropRisk": i.outlook.drop_risk if i.outlook else None,
        "xptsWindow": round(i.xpts.total, 2) if i.xpts else None,
    }


def inputs_payload(i: PlayerInputs) -> dict:
    """The player-page blocks (Plan B Task 7's shape). Every name this
    payload shows (e.g. a fixture's opponent club) already comes through
    `core.inputs.UpcomingMatch.opponent` as a club name, so unlike
    `score_fields`/`xp_fields` this needs no separate name lookup."""
    rel = i.reliability
    ev = i.evidence

    reliability = {
        "class": rel.cls,
        "pStart": round(rel.p_start_next, 3),
        "pPlay": round(rel.p_play_next, 3),
        "startShare": _round(rel.start_share),
        "playShare": _round(rel.play_share),
        "subShare": _round(rel.sub_share),
        "minutesShare": _round(rel.minutes_share),
        "shrunkStart": round(rel.shrunk_start, 3),
        "sourceStarter": _round(rel.source_starter),
        "sourceBlend": SOURCE_BLEND,
        "availability": rel.availability,
        "availabilityFactor": rel.availability_factor,
        "minutesTrend": _round(rel.minutes_trend, 1),
        "matches": rel.matches,
        "appearances": rel.appearances,
        "halfLife": HALF_LIFE,
        "priorWeight": PRIOR_WEIGHT,
        "prior": {"start": round(i.prior.start, 3), "play": round(i.prior.play, 3)},
        "confidence": rel.confidence,
        "basis": rel.basis,
        "rank": _rank(i.ranks.get("start")),
    }

    evidence = {
        "matchesWithMinutes": ev.matches_with_minutes,
        "lastSeasonApps": ev.last_season_apps,
        "ok": ev.ok,
        "reason": ev.reason,
    }

    points_value = {
        "value": _round(i.points_value, 2),
        "xpts": _round(i.xpts.total, 2) if i.xpts else None,
        "replacement": _round(i.replacement, 2),
        "price": i.price,
        "cashPerPoint": load_rules().cash_per_point,
        "horizon": LIVE_HORIZON,  # jornadas looked ahead (the copy's "next 3")
        "matchCount": len(i.xpts.matches) if i.xpts else 0,  # matches inside them
        "matches": (
            [{"opponent": o, "isHome": h, "xp": round(x, 2)} for o, h, x in i.xpts.matches]
            if i.xpts else []
        ),
        "reason": i.points_value_reason,
        "rank": _rank(i.ranks.get("pointsValue")),
    }

    outlook = i.outlook
    price_outlook = None
    if outlook is not None:
        price_outlook = {
            "expectedPct": round(outlook.expected_pct, 2),
            "direction": outlook.direction,
            "lower": round(outlook.lower, 2),
            "upper": round(outlook.upper, 2),
            "dropRisk": outlook.drop_risk,
            "basis": outlook.basis,
            "confidence": m2.confidence_for(outlook),
            "terms": outlook.terms,
            "madeOn": outlook.made_on.isoformat() if outlook.made_on else None,
            "rank": _rank(i.ranks.get("outlook")),
        }

    return {
        "powerRank": _rank(i.ranks.get("power")),
        "reliability": reliability,
        "evidence": evidence,
        "pointsValue": points_value,
        "priceOutlook": price_outlook,
        "expectedReturnEur": _round(i.expected_return_eur, 2),
        "inputsConfidence": i.confidence,
        "dataThrough": {
            "prices": i.price_as_of.isoformat() if i.price_as_of else None,
            "matches": rel.matches if rel.basis == "matches" else None,
        },
    }
