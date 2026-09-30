"""GET /api/fixtures/odds — LaLiga fixtures with raw odds and the
probabilities derived from them (INGEST-10), for Phase 10 to consume."""

from datetime import UTC, date, datetime

import pytest

from storage.external_repository import upsert_external_matches
from storage.models import ScrapeRun


def _record(home, away, status="scheduled", **overrides) -> dict:
    record = {
        "season_year": 2026,
        "match_date": date(2026, 10, 3),
        "kickoff_at": datetime(2026, 10, 3, 14, 0, tzinfo=UTC),
        "home_team": home,
        "away_team": away,
        "source_home_team": home,
        "source_away_team": away,
        "status": status,
        "odds_home": 2.33,
        "odds_draw": 2.82,
        "odds_away": 3.62,
        "odds_over25": 3.08,
        "odds_under25": 1.35,
        "raw_fields": {},
    }
    record.update(overrides)
    return record


@pytest.fixture()
def seeded(session):
    run = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(run)
    session.commit()
    upsert_external_matches(
        session,
        [
            _record("Barcelona", "Sevilla"),
            _record(
                "Getafe",
                "Elche",
                status="played",
                match_date=date(2026, 9, 20),
                home_goals=1,
                away_goals=0,
                home_xg=1.4,
                away_xg=0.6,
                closing_odds_home=2.0,
                closing_odds_draw=3.2,
                closing_odds_away=4.0,
            ),
            _record("Alaves", "Levante", odds_home=None),
            _record("Alaves", "Getafe", season_year=2025, match_date=date(2025, 10, 1)),
        ],
        run.id,
    )


def test_empty_database_is_an_empty_list(client):
    body = client.get("/api/fixtures/odds").json()
    assert body["fixtures"] == []
    assert body["source"] == "football-data"


def test_fixtures_carry_odds_and_derived_probabilities(client, seeded):
    body = client.get("/api/fixtures/odds", params={"season": 2026}).json()
    assert [(f["homeTeam"], f["awayTeam"]) for f in body["fixtures"]] == [
        ("Getafe", "Elche"),
        ("Alaves", "Levante"),
        ("Barcelona", "Sevilla"),
    ]
    barca = body["fixtures"][2]
    assert barca["odds"] == {
        "home": 2.33,
        "draw": 2.82,
        "away": 3.62,
        "over25": 3.08,
        "under25": 1.35,
    }
    p = barca["probabilities"]
    assert p["basis"] == "pre-match"
    assert p["home"] + p["draw"] + p["away"] == pytest.approx(1.0)
    assert 0 < p["cleanSheetHome"] < 1
    assert p["expectedGoalsHome"] > p["expectedGoalsAway"]
    assert p["goalsFit"] == "1x2+ou"


def test_a_played_match_prefers_closing_odds(client, seeded):
    body = client.get("/api/fixtures/odds", params={"status": "played"}).json()
    [getafe] = body["fixtures"]
    assert getafe["probabilities"]["basis"] == "closing"
    assert getafe["result"] == {"home": 1, "away": 0}
    assert getafe["teamStats"]["xgHome"] == 1.4


def test_an_incomplete_book_has_no_probabilities_rather_than_a_guess(client, seeded):
    body = client.get("/api/fixtures/odds", params={"season": 2026}).json()
    [levante] = [f for f in body["fixtures"] if f["awayTeam"] == "Levante"]
    assert levante["probabilities"] is None


def test_filters(client, seeded):
    upcoming = client.get("/api/fixtures/odds", params={"status": "scheduled", "season": 2026})
    assert len(upcoming.json()["fixtures"]) == 2
    since = client.get("/api/fixtures/odds", params={"from": "2026-10-01"})
    assert len(since.json()["fixtures"]) == 2
    power = client.get("/api/fixtures/odds", params={"method": "power", "season": 2026})
    assert power.json()["fixtures"][2]["probabilities"]["method"] == "power"


def test_bad_parameters_are_refused(client):
    assert client.get("/api/fixtures/odds", params={"status": "maybe"}).status_code == 422
    assert client.get("/api/fixtures/odds", params={"method": "magic"}).status_code == 422
