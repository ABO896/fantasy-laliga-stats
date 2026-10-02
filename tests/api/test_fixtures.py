"""GET /api/fixtures and GET /api/fixtures/difficulty (INGEST-04 / TRANSFER-03).

Kickoffs are relative to the real clock because the routes read it."""

from datetime import UTC, datetime, timedelta

import pytest

from core.config import get_settings
from core.fixture_difficulty import HOME_ADVANTAGE
from core.xp_backtest import MIN_TEAM_ROWS
from scraper.sources.analiticafantasy_calendar import FixtureRecord
from storage.models import Player, PlayerGameweekPoints, ScrapeRun
from storage.repository import upsert_fixtures

SEASON = get_settings().current_season_year


def _rec(fixture_id, matchday, home, away, days, is_final=False) -> FixtureRecord:
    return FixtureRecord(
        fixture_id=fixture_id,
        matchday=matchday,
        season_year=SEASON,
        kickoff_utc=datetime.now(UTC) + timedelta(days=days),
        kickoff_confirmed=True,
        is_final=is_final,
        home_team=home,
        away_team=away,
        home_team_id=None,
        away_team_id=None,
        home_difficulty="easy",
        away_difficulty="hard",
    )


@pytest.fixture()
def calendar(session):
    upsert_fixtures(
        session,
        [
            _rec(1, 6, "A", "B", days=-4, is_final=True),
            _rec(2, 8, "A", "B", days=2),
            _rec(3, 8, "C", "D", days=2.1),
            _rec(4, 9, "B", "C", days=9),
            _rec(5, 9, "D", "A", days=9.1),
        ],
    )


def _points(session, team_totals: dict[str, list[int]], season=SEASON):
    """Seed `MIN_TEAM_ROWS` players per team so every week clears the
    minimum-rows floor — one carries the real total, the rest are 0-point
    fillers (the sum, and the team-strength ranking it drives, is unchanged)."""
    run = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(run)
    session.commit()
    now = datetime.now(UTC)
    for team, weeks in team_totals.items():
        players = []
        for i in range(MIN_TEAM_ROWS):
            p = Player(
                external_id=f"p{i}-{team}-{season}", name=f"{team}{i}", team=team,
                position="DEL", created_at=now, updated_at=now,
            )
            session.add(p)
            session.commit()
            session.refresh(p)
            players.append(p)
        for week, points in enumerate(weeks, start=1):
            session.add(
                PlayerGameweekPoints(
                    season_year=season, week=week, player_id=players[0].id, points=points,
                    scrape_run_id=run.id,
                )
            )
            for filler in players[1:]:
                session.add(
                    PlayerGameweekPoints(
                        season_year=season, week=week, player_id=filler.id, points=0,
                        scrape_run_id=run.id,
                    )
                )
    session.commit()


def test_fixtures_lists_only_upcoming_in_kickoff_order(client, calendar):
    body = client.get("/api/fixtures").json()
    assert [f["fixtureId"] for f in body["fixtures"]] == [2, 3, 4, 5]
    first = body["fixtures"][0]
    assert first["matchday"] == 8
    assert first["homeTeam"] == "A"
    assert first["awayTeam"] == "B"
    assert first["isFinal"] is False
    assert first["kickoffConfirmed"] is True
    # The source's own label, surfaced as reference only.
    assert first["sourceHomeDifficulty"] == "easy"
    assert first["kickoffUtc"].endswith("+00:00")


def test_fixtures_is_empty_without_a_calendar(client):
    assert client.get("/api/fixtures").json()["fixtures"] == []


def test_difficulty_uses_the_next_n_jornadas_with_home_and_away(client, session, calendar):
    _points(session, {"A": [40, 40], "B": [80, 80], "C": [40, 40], "D": [40, 40]})

    body = client.get("/api/fixtures/difficulty?n=1").json()

    assert body["n"] == 1
    assert body["jornadas"] == [8]
    assert body["homeAdvantage"] == HOME_ADVANTAGE
    teams = {t["team"]: t for t in body["teams"]}
    a = teams["A"]
    assert a["fixtureCount"] == 1
    [fx] = a["fixtures"]
    assert fx["opponent"] == "B"
    assert fx["isHome"] is True
    assert fx["matchday"] == 8
    # B is the strongest side, so A (at home to B) has a harder fixture
    # than C (at home to an average D).
    assert fx["difficulty"] > teams["C"]["fixtures"][0]["difficulty"]
    assert teams["B"]["fixtures"][0]["isHome"] is False


def test_difficulty_defaults_to_three_jornadas_and_ranks_easiest_first(client, calendar):
    body = client.get("/api/fixtures/difficulty").json()
    assert body["n"] == 3
    assert body["jornadas"] == [8, 9]  # only two upcoming
    averages = [t["averageDifficulty"] for t in body["teams"]]
    assert averages == sorted(averages)


@pytest.mark.parametrize("n", [0, 39])
def test_difficulty_rejects_an_out_of_range_n(client, n):
    assert client.get(f"/api/fixtures/difficulty?n={n}").status_code == 422


def test_difficulty_with_no_calendar_is_empty_not_an_error(client):
    body = client.get("/api/fixtures/difficulty").json()
    assert body["teams"] == []
    assert body["jornadas"] == []
