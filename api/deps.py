"""Shared FastAPI dependencies."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from core.config import Settings, get_settings
from core.lineup_rules import LeagueFeatures
from core.rules import Rules, load_rules
from storage.db import get_engine
from storage.repository import get_league_settings


def get_db_session():
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@dataclass(frozen=True)
class LeagueContext:
    """Everything about the owner's league that a route needs, resolved once
    per request from the `leaguesettings` row.

    Bundling the narrowed rules with the feature flags is deliberate: they
    come from the same row and are always needed together, and the four
    call sites this replaces were already two near-duplicate `_rules()`
    helpers plus two inline reads that could drift apart.
    """

    rules: Rules
    features: LeagueFeatures


def resolve_league_context(session: Session) -> LeagueContext:
    settings = get_league_settings(session)
    return LeagueContext(
        rules=load_rules().for_league(settings.premium_formations_enabled),
        features=LeagueFeatures(bench_enabled=settings.premium_bench_enabled),
    )


def get_league_context(session: SessionDep) -> LeagueContext:
    return resolve_league_context(session)


LeagueContextDep = Annotated[LeagueContext, Depends(get_league_context)]
