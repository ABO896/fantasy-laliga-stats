"""GET /api/players — the latest snapshot joined to player identity."""

from fastapi import APIRouter

from api.deps import SessionDep
from storage.expected_points import latest_expected_points, xp_fields
from storage.our_models import compute_player_analytics, score_fields
from storage.repository import get_latest_players

router = APIRouter()


@router.get("/players")
def list_players(session: SessionDep):
    rows = get_latest_players(session)
    latest_xp = latest_expected_points(session)
    # MODEL-02 feeds Power (ANALYTICS-06); blank jornadas stay out of the blend.
    analytics = compute_player_analytics(
        session,
        expected_points={
            pid: v for pid, (v, basis) in latest_xp.items() if basis != "no_fixture"
        },
    )

    as_of = rows[0][0].as_of.isoformat() if rows else None
    players = [
        {
            "playerId": player.id,
            "externalId": player.external_id,
            "name": player.name,
            "team": player.team,
            "position": player.position,
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
            # ANALYTICS-06/07 — our own scores, sortable in the browser.
            **score_fields(analytics.get(player.id)),
            # MODEL-02 — expected points next jornada, and what it was built from.
            **xp_fields(latest_xp, player.id),
        }
        for snapshot, player in rows
    ]

    return {"as_of": as_of, "players": players}
