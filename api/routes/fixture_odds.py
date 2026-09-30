"""GET /api/fixtures/odds — LaLiga fixtures from external sources, with the
raw odds as published and the probabilities `core/odds.py` derives from
them (INGEST-10). Phase 10's points model is the intended consumer.

Probabilities are computed on read, never stored, so a better
de-margining method needs no backfill. The basis is the **closing** book
when one exists (played matches — the market's final, best-informed view)
and the pre-match book otherwise; `basis` says which. An incomplete 1X2
book yields `probabilities: null` — absent, never guessed.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from api.deps import SessionDep
from core.odds import match_probabilities
from storage.db import as_utc
from storage.external_repository import get_external_matches
from storage.models import ExternalMatch

router = APIRouter()

SOURCE = "football-data"


def _book(m: ExternalMatch, prefix: str) -> dict:
    return {
        "home": getattr(m, f"{prefix}home"),
        "draw": getattr(m, f"{prefix}draw"),
        "away": getattr(m, f"{prefix}away"),
        "over25": getattr(m, f"{prefix}over25"),
        "under25": getattr(m, f"{prefix}under25"),
    }


def _probabilities(m: ExternalMatch, method: str) -> dict | None:
    closing, pre = _book(m, "closing_odds_"), _book(m, "odds_")
    has_closing = all(closing[k] is not None for k in ("home", "draw", "away"))
    book, basis = (closing, "closing") if has_closing else (pre, "pre-match")
    p = match_probabilities(
        book["home"], book["draw"], book["away"], book["over25"], book["under25"], method
    )
    if p is None:
        return None
    return {
        "basis": basis,
        "method": p.method,
        "home": p.p_home,
        "draw": p.p_draw,
        "away": p.p_away,
        "over25": p.p_over25,
        "under25": p.p_under25,
        "expectedGoalsHome": p.exp_goals_home,
        "expectedGoalsAway": p.exp_goals_away,
        "cleanSheetHome": p.p_clean_sheet_home,
        "cleanSheetAway": p.p_clean_sheet_away,
        "overround1x2": p.overround_1x2,
        "overroundOverUnder": p.overround_ou,
        "goalsFit": p.goals_fit,
    }


def _to_dto(m: ExternalMatch, method: str) -> dict:
    played = m.status == "played"
    return {
        "seasonYear": m.season_year,
        "matchDate": m.match_date.isoformat(),
        "kickoffAt": as_utc(m.kickoff_at).isoformat() if m.kickoff_at else None,
        "status": m.status,
        "homeTeam": m.home_team,
        "awayTeam": m.away_team,
        "sourceHomeTeam": m.source_home_team,
        "sourceAwayTeam": m.source_away_team,
        "result": {"home": m.home_goals, "away": m.away_goals} if played else None,
        "teamStats": {
            "xgHome": m.home_xg,
            "xgAway": m.away_xg,
            "shotsHome": m.home_shots,
            "shotsAway": m.away_shots,
            "shotsOnTargetHome": m.home_shots_on_target,
            "shotsOnTargetAway": m.away_shots_on_target,
        },
        "odds": _book(m, "odds_"),
        "closingOdds": _book(m, "closing_odds_"),
        "probabilities": _probabilities(m, method),
        "updatedAt": as_utc(m.updated_at).isoformat(),
    }


@router.get("/fixtures/odds")
def get_fixture_odds(
    session: SessionDep,
    season: int | None = None,
    status: Literal["scheduled", "played"] | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    method: Literal["proportional", "power"] = "proportional",
):
    matches = get_external_matches(
        session,
        season_year=season,
        status=status,
        from_date=from_date,
        to_date=to_date,
        source=SOURCE,
    )
    return {"source": SOURCE, "fixtures": [_to_dto(m, method) for m in matches]}
