"""GET /api/players/{id}/verdict and GET /api/models/verdict/validation —
Plan C's verdict and personal-line surface (Task 5)."""

from fastapi import APIRouter, HTTPException, Query

from api.deps import SessionDep
from storage.verdict import player_verdict_payload, validation_report

router = APIRouter()


@router.get("/players/{player_id}/verdict")
def get_player_verdict(
    player_id: int,
    session: SessionDep,
    max: int | None = Query(None, ge=0),  # noqa: A002 — BROWSE-05's own param name
):
    payload = player_verdict_payload(session, player_id, max)
    if payload is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return payload


@router.get("/models/verdict/validation")
def get_verdict_validation(session: SessionDep):
    return validation_report(session)
