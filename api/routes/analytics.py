"""GET /api/players/{player_id}/analytics — ANALYTICS-01…07 for one player,
each metric with its inputs and its window (ANALYTICS-05).

Its own endpoint rather than a field on GET /api/players/{id}: the player
page's main payload is shared with other work, and momentum windows are a
query parameter that payload has no reason to carry.
"""

from fastapi import APIRouter, HTTPException, Query

from api.deps import SessionDep
from core.analytics import DEFAULT_MOMENTUM_WINDOWS
from storage.our_models import player_analytics_payload
from storage.repository import get_player

router = APIRouter()

MAX_WINDOWS = 6
MAX_WINDOW_DAYS = 365

_EMPTY = {
    "form": None,
    "consistency": None,
    "momentum": [],
    "power": None,
    "valuation": None,
    "economy": None,
    "marketPrediction": None,
    # Plan B Task 7.
    "powerRank": None,
    "reliability": None,
    "evidence": None,
    "pointsValue": None,
    "priceOutlook": None,
    "expectedReturnEur": None,
    "inputsConfidence": None,
    "dataThrough": None,
}


def parse_windows(raw: str | None) -> list[int]:
    if not raw:
        return list(DEFAULT_MOMENTUM_WINDOWS)
    try:
        windows = sorted({int(part) for part in raw.split(",") if part.strip()})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="windows must be comma-separated days") from exc
    if (
        not windows
        or len(windows) > MAX_WINDOWS
        or not all(1 <= w <= MAX_WINDOW_DAYS for w in windows)
    ):
        raise HTTPException(
            status_code=422,
            detail=f"between 1 and {MAX_WINDOWS} windows, each 1–{MAX_WINDOW_DAYS} days",
        )
    return windows


@router.get("/players/{player_id}/analytics")
def get_player_analytics(player_id: int, session: SessionDep, windows: str | None = Query(None)):
    if get_player(session, player_id) is None:
        raise HTTPException(status_code=404, detail="Player not found")
    parsed = parse_windows(windows)
    payload = player_analytics_payload(session, player_id, parsed)
    return payload if payload is not None else {"playerId": player_id, **_EMPTY}
