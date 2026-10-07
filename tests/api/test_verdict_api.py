"""Route contracts for the verdict surface (Plan C, Task 5): the label on
every player-list row, a player's own verdict + personal line, and the
stored validation report.
"""

import json
from datetime import UTC, date, datetime

from core.verdict import LABELS
from storage.models import ModelReport, Player, PlayerSnapshot, ScrapeRun
from storage.verdict_backtest import REPORT_NAME


def seed_player(
    session, player_id: int, name: str, position: str, value: int,
    availability: str = "available",
) -> None:
    now = datetime.now(UTC)
    session.add(
        Player(
            id=player_id,
            external_id=f"ext-{player_id}",
            name=name,
            team="Team",
            position=position,
            created_at=now,
            updated_at=now,
        )
    )
    run = ScrapeRun(started_at=now, status="success")
    session.add(run)
    session.commit()
    session.add(
        PlayerSnapshot(
            as_of=date(2026, 8, 6),
            player_id=player_id,
            market_value=value,
            points=0,
            availability_status=availability,
            raw_fields="{}",
            scrape_run_id=run.id,
        )
    )
    session.commit()


def test_player_list_rows_carry_a_verdict_label_from_the_vocabulary(client, session):
    seed_player(session, 1, "Galactico", "DEL", 5_000_000)
    body = client.get("/api/players").json()
    row = body["players"][0]
    assert row["verdict"]["label"] in LABELS
    assert isinstance(row["verdict"]["tags"], list)


def test_player_verdict_endpoint_returns_the_documented_shape(client, session):
    seed_player(session, 1, "Galactico", "DEL", 5_000_000)
    body = client.get("/api/players/1/verdict").json()
    assert body["playerId"] == 1
    assert body["label"] in LABELS
    assert isinstance(body["tags"], list)
    assert isinstance(body["reason"], str) and body["reason"]
    assert body["confidence"] in {"high", "medium", "low"}
    assert isinstance(body["deciding"], dict)
    assert body["disabledLabels"] == ["Rotation risk"]
    # No squad owns this player — the personal line is null.
    assert body["personal"] is None
    # No stored validation report yet.
    assert body["validation"] is None


def test_an_injured_player_is_unavailable_with_a_reason_that_says_so(client, session):
    seed_player(session, 1, "Hurt", "DEF", 3_000_000, availability="injured")
    body = client.get("/api/players/1/verdict").json()
    assert body["label"] == "Unavailable"
    assert body["reason"].startswith("Injured")


def test_an_unknown_player_returns_404(client):
    assert client.get("/api/players/999/verdict").status_code == 404


def test_validation_endpoint_without_a_stored_report_returns_the_empty_shape(client):
    body = client.get("/api/models/verdict/validation").json()
    assert body == {"generatedAt": None, "labels": []}


def test_validation_endpoint_returns_the_stored_report(client, session):
    payload = {
        "generatedAt": "2026-10-01T00:00:00+00:00",
        "season": 2026,
        "dates": [],
        "thresholds": {},
        "disabled": [],
        "labels": [
            {"label": "Bargain", "metric": "points_per_m", "n": 120, "players": 40,
             "hitRate": 0.61, "baseRate": 0.5, "meanDiff": 0.05, "ciLow": 0.01,
             "ciHigh": 0.09, "beatsChance": True},
        ],
        "notes": [],
    }
    session.add(ModelReport(
        name=REPORT_NAME,
        generated_at=datetime.fromisoformat(payload["generatedAt"]),
        payload=json.dumps(payload),
    ))
    session.commit()

    body = client.get("/api/models/verdict/validation").json()
    assert body == payload


def test_a_players_verdict_carries_its_validation_entry_when_one_is_stored(client, session):
    """`Fair price` is the vocabulary's fallback, so a freshly seeded player
    with no evidence lands on `Unproven` instead — seed a report entry for
    that label and confirm the player's own verdict surfaces it."""
    seed_player(session, 1, "Nobody", "DEF", 1_000_000)
    label = client.get("/api/players/1/verdict").json()["label"]

    payload = {
        "generatedAt": "2026-10-01T00:00:00+00:00", "season": 2026, "dates": [],
        "thresholds": {}, "disabled": [],
        "labels": [
            {"label": label, "metric": None, "n": 50, "players": 20, "hitRate": 0.4,
             "baseRate": 0.4, "meanDiff": None, "ciLow": None, "ciHigh": None,
             "beatsChance": False},
        ],
        "notes": [],
    }
    session.add(ModelReport(
        name=REPORT_NAME,
        generated_at=datetime.fromisoformat(payload["generatedAt"]),
        payload=json.dumps(payload),
    ))
    session.commit()

    body = client.get("/api/players/1/verdict").json()
    assert body["validation"] == {
        "label": label, "beatsChance": False, "hitRate": 0.4, "n": 50,
    }
