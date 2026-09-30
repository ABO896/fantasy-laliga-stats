"""MODEL-02 — our expected fantasy points, and their track record (MODEL-03).

- `GET /api/expected-points?jornada=&season=` — every stored prediction for
  one jornada (default: the latest stored, i.e. the next one), highest first,
  each with its basis and every input.
- `GET /api/expected-points/track-record` — stored predictions scored
  against final per-jornada points, beside the naive season average.
- `GET /api/players/{player_id}/expected-points` — one player's latest.
"""

from fastapi import APIRouter, HTTPException, Query

from api.deps import SessionDep
from storage.expected_points import (
    expected_points_payload,
    prediction_payload,
    stored_predictions,
    track_record_payload,
)
from storage.repository import get_player

router = APIRouter()


@router.get("/expected-points")
def list_expected_points(
    session: SessionDep,
    jornada: int | None = Query(None, ge=1, le=38),
    season: int | None = Query(None, ge=2000, le=2100),
):
    return expected_points_payload(session, jornada=jornada, season=season)


@router.get("/expected-points/track-record")
def expected_points_track_record(session: SessionDep):
    return track_record_payload(session)


@router.get("/players/{player_id}/expected-points")
def player_expected_points(player_id: int, session: SessionDep):
    if get_player(session, player_id) is None:
        raise HTTPException(status_code=404, detail="Player not found")
    _, _, rows = stored_predictions(session, player_id=player_id)
    return {
        "playerId": player_id,
        "prediction": prediction_payload(rows[0][0]) if rows else None,
    }
