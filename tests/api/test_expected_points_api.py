"""MODEL-02 endpoints, and xP on the player list, squad and Power Score."""

from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session

from storage.expected_points import refresh_expected_points
from storage.models import (
    Fixture,
    Player,
    PlayerGameweekPoints,
    PlayerSnapshot,
    ScrapeRun,
)

NOW = datetime.now(UTC)


def _seed(engine):
    with Session(engine) as s:
        run = ScrapeRun(started_at=NOW, status="success")
        s.add(run)
        s.commit()
        s.refresh(run)
        ids = []
        for slug, team, pos in [("ace", "Home FC", "DEL"), ("idle", "Idle FC", "MED")]:
            p = Player(external_id=slug, name=slug.title(), team=team, position=pos,
                       created_at=NOW, updated_at=NOW)
            s.add(p)
            s.commit()
            s.refresh(p)
            ids.append(p.id)
            s.add(PlayerSnapshot(as_of=date.today(), player_id=p.id, market_value=5_000_000,
                                 points=20, starter_probability=90.0,
                                 availability_status="available", raw_fields="{}",
                                 scrape_run_id=run.id))
            for week in range(1, 6):
                s.add(PlayerGameweekPoints(season_year=2026, week=week, player_id=p.id,
                                           points=8, scrape_run_id=run.id))
        s.add(Fixture(fixture_id=1, matchday=7, kickoff_utc=NOW + timedelta(days=3),
                      kickoff_confirmed=True, home_team="Home FC", away_team="Other FC",
                      scraped_at=NOW))
        s.add(Fixture(fixture_id=2, matchday=6, kickoff_utc=NOW - timedelta(days=3),
                      kickoff_confirmed=True, is_final=True, home_team="Idle FC",
                      away_team="Home FC", scraped_at=NOW))
        s.commit()
        refresh_expected_points(s)
        return ids


def test_list_expected_points(client, engine):
    ace, idle = _seed(engine)
    body = client.get("/api/expected-points").json()
    assert body["jornada"] == 7
    first = body["predictions"][0]
    assert first["playerId"] == ace
    assert first["basis"] == "form+starter"
    assert first["opponent"] == "Other FC" and first["isHome"] is True
    assert first["inputs"]["terms"]  # every term exposed
    assert {p["playerId"]: p["basis"] for p in body["predictions"]}[idle] == "no_fixture"
    assert client.get("/api/expected-points?jornada=2").json()["predictions"] == []


def test_player_expected_points(client, engine):
    ace, _ = _seed(engine)
    body = client.get(f"/api/players/{ace}/expected-points").json()
    assert body["prediction"]["jornada"] == 7
    assert body["prediction"]["expectedPoints"] > 0
    assert client.get("/api/players/999999/expected-points").status_code == 404


def test_player_without_prediction(client, engine):
    with Session(engine) as s:
        p = Player(external_id="x", name="X", team="T", position="DEL",
                   created_at=NOW, updated_at=NOW)
        s.add(p)
        s.commit()
        s.refresh(p)
        pid = p.id
    assert client.get(f"/api/players/{pid}/expected-points").json() == {
        "playerId": pid, "prediction": None,
    }


def test_track_record_empty_then_counts(client, engine):
    body = client.get("/api/expected-points/track-record").json()
    assert body["counts"]["scored"] == 0 and body["overall"]["mae"] is None
    _seed(engine)
    body = client.get("/api/expected-points/track-record").json()
    assert body["counts"]["pending"] == 1 and body["counts"]["noFixture"] == 1


def test_player_list_carries_xp_and_power_blends_it(client, engine):
    ace, idle = _seed(engine)
    rows = {p["playerId"]: p for p in client.get("/api/players").json()["players"]}
    assert rows[ace]["expectedPoints"] > 0
    assert rows[ace]["expectedPointsBasis"] == "form+starter"
    assert rows[idle]["expectedPoints"] == 0
    assert rows[idle]["expectedPointsBasis"] == "no_fixture"

    power = client.get(f"/api/players/{ace}/analytics").json()["power"]
    assert power["expectedPointsUsed"] is True
    assert round(power["expectedPoints"], 2) == rows[ace]["expectedPoints"]
    idle_power = client.get(f"/api/players/{idle}/analytics").json()["power"]
    assert idle_power["expectedPointsUsed"] is False  # a blank never drags Power down


def test_squad_members_carry_xp(client, engine):
    ace, _ = _seed(engine)
    added = client.post("/api/squad/players", json={"playerId": ace, "purchasePrice": 5_000_000})
    assert added.status_code in (200, 201), added.text
    member = client.get("/api/squad").json()["members"][0]
    assert member["expectedPoints"] > 0
    assert member["expectedPointsBasis"] == "form+starter"
