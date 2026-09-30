"""GET /api/stats/* — league-wide read-models over PlayerGameweekPoints and
PlayerSeasonStats (STATS-01…04): who's doing well across the whole league,
not just this one player. No new scraping, no new table; every route here
is a query composed from repository functions already tested in isolation.
"""

from fastapi import APIRouter, HTTPException

from api.deps import SessionDep
from core.season_stats_schema import SEASON_RECORD_FIELDS
from storage.repository import (
    JornadaScoreRow,
    get_jornada_point_records,
    get_jornada_scores,
    get_season_leaderboard,
    get_season_stat_records,
    get_season_week_ranges,
    get_stats_seasons,
    get_streak_leaderboard,
    get_team_jornada_summary,
)

router = APIRouter()

#: Fixed, always all five rendered even at zero count (spec: Tiers table).
#: `(label, min_inclusive, max_inclusive)`, `None` meaning unbounded.
_TIER_BOUNDS: tuple[tuple[str, int | None, int | None], ...] = (
    ("≤0", None, 0),
    ("1–3", 1, 3),
    ("4–6", 4, 6),
    ("7–9", 7, 9),
    ("10+", 10, None),
)


def _bucket_tiers(scores: list[JornadaScoreRow]) -> list[dict]:
    tiers = []
    for label, lo, hi in _TIER_BOUNDS:
        count = sum(
            1
            for s in scores
            if (lo is None or s.points >= lo) and (hi is None or s.points <= hi)
        )
        tiers.append({"label": label, "min": lo, "max": hi, "count": count})
    return tiers


@router.get("/stats/seasons")
def stats_seasons(session: SessionDep):
    return {
        "seasons": get_stats_seasons(session),
        "seasonWeekRanges": get_season_week_ranges(session),
    }


@router.get("/stats/scores")
def stats_scores(season: int, week: int, session: SessionDep):
    if season not in get_stats_seasons(session):
        raise HTTPException(status_code=404, detail="Season not found")

    scores = get_jornada_scores(session, season, week)
    teams = get_team_jornada_summary(session, season, week)
    is_provisional = any(s.is_provisional for s in scores)

    return {
        "week": week,
        "isProvisional": is_provisional,
        "tiers": _bucket_tiers(scores),
        "scores": [
            {
                "playerId": s.player_id,
                "name": s.name,
                "team": s.team,
                "position": s.position,
                "points": s.points,
                "marketValue": s.market_value,
                "pricePerPoint": s.price_per_point,
            }
            for s in scores
        ],
        "teams": [
            {
                "team": t.team,
                "totalPoints": t.total_points,
                "playerCount": t.player_count,
                "averagePoints": t.average_points,
            }
            for t in teams
        ],
    }


@router.get("/stats/streaks")
def stats_streaks(season: int, session: SessionDep, end_week: int | None = None, window: int = 5):
    if season not in get_stats_seasons(session):
        raise HTTPException(status_code=404, detail="Season not found")

    max_week = get_season_week_ranges(session).get(season, 0)
    resolved_end_week = end_week if end_week is not None else max_week
    clamped_window = max(1, min(window, max_week))

    players = get_streak_leaderboard(session, season, resolved_end_week, clamped_window)

    return {
        "endWeek": resolved_end_week,
        "window": clamped_window,
        "players": [
            {
                "playerId": p.player_id,
                "name": p.name,
                "team": p.team,
                "position": p.position,
                "totalPoints": p.total_points,
                "weeksCounted": p.weeks_counted,
            }
            for p in players
        ],
    }


@router.get("/stats/records")
def stats_records(season: int, session: SessionDep):
    if season not in get_stats_seasons(session):
        raise HTTPException(status_code=404, detail="Season not found")

    return {
        "jornadaRecords": [
            {
                "playerId": r.player_id,
                "name": r.name,
                "team": r.team,
                "week": r.week,
                "points": r.points,
            }
            for r in get_jornada_point_records(session, season)
        ],
        "seasonRecords": [
            {
                "field": r.field,
                "playerId": r.player_id,
                "name": r.name,
                "team": r.team,
                "value": r.value,
            }
            for r in get_season_stat_records(session, season)
        ],
    }


@router.get("/stats/leaderboard")
def stats_leaderboard(
    season: int,
    stat: str,
    session: SessionDep,
    position: str | None = None,
    team: str | None = None,
):
    if stat not in SEASON_RECORD_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unknown stat '{stat}'")
    if season not in get_stats_seasons(session):
        raise HTTPException(status_code=404, detail="Season not found")

    players = get_season_leaderboard(session, season, stat, position, team)
    return {
        "stat": stat,
        "players": [
            {
                "playerId": p.player_id,
                "name": p.name,
                "team": p.team,
                "position": p.position,
                "value": p.value,
                "totalPoints": p.total_points,
            }
            for p in players
        ],
    }
