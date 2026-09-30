"""The league's Premium toggles.

Two independent settings (LN-29), not one master switch — a league admin
turns each on separately, and this app mirrors that rather than simplifying
it into something the owner would have to mentally translate.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import SessionDep
from storage.repository import get_league_settings, set_league_settings

router = APIRouter()


class LeagueSettingsRequest(BaseModel):
    """Both flags are required. Making them optional would let a client that
    knows about one feature silently switch off another it has never heard
    of — the settings form always submits the full set."""

    premiumFormationsEnabled: bool
    premiumBenchEnabled: bool


def _serialize(settings) -> dict:
    return {
        "premiumFormationsEnabled": settings.premium_formations_enabled,
        "premiumBenchEnabled": settings.premium_bench_enabled,
    }


@router.get("/league-settings")
def read_league_settings(session: SessionDep):
    return _serialize(get_league_settings(session))


@router.put("/league-settings")
def update_league_settings(payload: LeagueSettingsRequest, session: SessionDep):
    return _serialize(
        set_league_settings(
            session,
            premium_formations_enabled=payload.premiumFormationsEnabled,
            premium_bench_enabled=payload.premiumBenchEnabled,
        )
    )
