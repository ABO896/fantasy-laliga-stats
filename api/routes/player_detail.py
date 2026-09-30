"""GET /api/players/{player_id} — one player's whole page in one payload.

Everything the page renders arrives in a single round trip (spec D-04): one
loading state, one error state, and a page internally consistent as of one
read. At 8-12 KB for a local single-user app, splitting it would add round
trips and buy caching nothing needs.
"""

from fastapi import APIRouter, HTTPException

from api.deps import SessionDep
from core.season_stats_schema import STAT_PAIRS, column_name
from storage.models import PlayerSeasonStats, PlayerSnapshot
from storage.repository import (
    get_gameweek_points,
    get_latest_predictions,
    get_player,
    get_season_stats,
    get_season_week_ranges,
    get_snapshot_history,
    get_squad_membership,
)

router = APIRouter()


def _latest_fields(snapshot: PlayerSnapshot) -> dict:
    return {
        "marketValue": snapshot.market_value,
        "idealBid": snapshot.ideal_bid,
        "maxBid": snapshot.max_bid,
        "priceChangeAbs": snapshot.price_change_abs,
        "priceChangePct": snapshot.price_change_pct,
        "points": snapshot.points,
        "pricePerPoint": snapshot.price_per_point,
        "starterProbability": snapshot.starter_probability,
        "availabilityStatus": snapshot.availability_status,
        "nextOpponent": snapshot.next_opponent,
    }


def _stats_map(row: PlayerSeasonStats) -> dict[str, dict[str, int]]:
    """Built by iterating the schema, never by listing 42 fields by hand.

    `core/season_stats_schema.py` is already the one source of truth the
    parser and the table share, and `tests/storage/test_ingestion_schema.py`
    asserts it has not drifted from the table. Generating the payload from it
    extends that guarantee to the API: a statistic added to the schema
    surfaces on the page with no change here, and cannot silently go missing.
    """
    return {
        counter: {
            "count": getattr(row, column_name(counter)),
            "points": getattr(row, column_name(points_field)),
        }
        for counter, points_field in STAT_PAIRS
    }


@router.get("/players/{player_id}")
def get_player_detail(player_id: int, session: SessionDep):
    player = get_player(session, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    history = get_snapshot_history(session, player_id)
    latest = history[-1] if history else None
    membership = get_squad_membership(session, player_id)

    return {
        "asOf": latest.as_of.isoformat() if latest else None,
        "player": {
            "playerId": player.id,
            "externalId": player.external_id,
            "name": player.name,
            "team": player.team,
            "position": player.position,
        },
        "latest": _latest_fields(latest) if latest else None,
        "valueHistory": [
            {"asOf": s.as_of.isoformat(), "marketValue": s.market_value} for s in history
        ],
        "gameweekPoints": [
            {
                "seasonYear": row.season_year,
                "week": row.week,
                "points": row.points,
                "isProvisional": row.is_provisional,
            }
            for row in get_gameweek_points(session, player_id)
        ],
        "seasonWeekRanges": get_season_week_ranges(session),
        "seasonStats": [
            {
                "seasonYear": row.season_year,
                "matchesPlayed": row.matches_played,
                "totalPoints": row.total_points,
                "averagePoints": row.average_points,
                "marketValue": row.market_value,
                "idealFormationCount": row.ideal_formation_count,
                "stats": _stats_map(row),
            }
            for row in get_season_stats(session, player_id)
        ],
        "squad": (
            {
                "purchasePrice": membership.purchase_price,
                "acquiredOn": membership.acquired_on.isoformat(),
            }
            if membership
            else None
        ),
        "predictions": get_latest_predictions(session, player_id),
    }
