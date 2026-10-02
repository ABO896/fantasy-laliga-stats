"""GET /api/fixtures and GET /api/fixtures/difficulty — the restored
fixture calendar (INGEST-04) and this project's own fixture difficulty
(TRANSFER-03). The formula lives in `core/fixture_difficulty.py`."""

from datetime import UTC, datetime

from fastapi import APIRouter, Query

from api.deps import SessionDep, SettingsDep
from core.fixture_difficulty import (
    HOME_ADVANTAGE,
    PRIOR_WEIGHT_WEEKS,
    FixtureView,
    fixture_difficulty,
    team_strength,
    upcoming_fixtures,
    window_jornadas,
)
from storage.models import Fixture
from storage.repository import get_fixtures, get_team_week_points

router = APIRouter()

#: A season is 38 jornadas; the source's window only ever holds five, so a
#: larger `n` simply returns fewer jornadas than asked for.
MAX_WINDOW = 38


def _view(row: Fixture) -> FixtureView:
    return FixtureView(
        fixture_id=row.fixture_id,
        matchday=row.matchday,
        kickoff_utc=row.kickoff_utc,
        kickoff_confirmed=row.kickoff_confirmed,
        is_final=row.is_final,
        home_team=row.home_team,
        away_team=row.away_team,
    )


def _upcoming(session, season: int) -> tuple[list[FixtureView], dict[int, Fixture]]:
    rows = get_fixtures(session, season)
    by_id = {row.fixture_id: row for row in rows}
    return upcoming_fixtures([_view(r) for r in rows], datetime.now(UTC)), by_id


@router.get("/fixtures")
def list_fixtures(session: SessionDep, settings: SettingsDep):
    upcoming, by_id = _upcoming(session, settings.current_season_year)
    return {
        "serverTime": datetime.now(UTC).isoformat(),
        "fixtures": [
            {
                "fixtureId": f.fixture_id,
                "matchday": f.matchday,
                "kickoffUtc": f.kickoff_utc.isoformat(),
                "kickoffConfirmed": f.kickoff_confirmed,
                "isFinal": f.is_final,
                "homeTeam": f.home_team,
                "awayTeam": f.away_team,
                "homeTeamId": by_id[f.fixture_id].home_team_id,
                "awayTeamId": by_id[f.fixture_id].away_team_id,
                # The source's own per-side label — reference only; this
                # app's own difficulty is /api/fixtures/difficulty.
                "sourceHomeDifficulty": by_id[f.fixture_id].home_difficulty,
                "sourceAwayDifficulty": by_id[f.fixture_id].away_difficulty,
            }
            for f in upcoming
        ],
    }


@router.get("/fixtures/difficulty")
def difficulty(
    session: SessionDep,
    settings: SettingsDep,
    n: int = Query(3, ge=1, le=MAX_WINDOW),
):
    season = settings.current_season_year
    upcoming, _ = _upcoming(session, season)
    current = get_team_week_points(session, season)
    previous = get_team_week_points(session, season - 1)
    teams_in_play = {f.home_team for f in upcoming} | {f.away_team for f in upcoming}
    strength = team_strength(current, previous, teams=teams_in_play)
    ranked = fixture_difficulty(upcoming, strength, n)

    return {
        "serverTime": datetime.now(UTC).isoformat(),
        "n": n,
        "jornadas": window_jornadas(upcoming, n),
        "homeAdvantage": HOME_ADVANTAGE,
        "strengthBasis": {
            "season": season,
            "priorSeason": season - 1,
            "priorWeightWeeks": PRIOR_WEIGHT_WEEKS,
            "weeksCounted": max((len(w) for w in current.values()), default=0),
        },
        "teams": [
            {
                "team": t.team,
                "strength": strength.get(t.team, 1.0),
                "averageDifficulty": t.average_difficulty,
                "fixtureCount": t.fixture_count,
                "fixtures": [
                    {
                        "fixtureId": tf.fixture_id,
                        "matchday": tf.matchday,
                        "kickoffUtc": tf.kickoff_utc.isoformat(),
                        "kickoffConfirmed": tf.kickoff_confirmed,
                        "opponent": tf.opponent,
                        "isHome": tf.is_home,
                        "opponentStrength": tf.opponent_strength,
                        "difficulty": tf.difficulty,
                    }
                    for tf in t.fixtures
                ],
            }
            for t in ranked
        ],
    }
