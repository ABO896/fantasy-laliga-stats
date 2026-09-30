"""GET /api/squad/history — SQUAD-04's value and points series.

Kept off the main GET /api/squad payload deliberately: that route is
refetched on every pitch rearrangement, and this one's aggregation has no
reason to run that often.
"""

from datetime import UTC, date, datetime

import pytest

from storage.models import Player, PlayerGameweekPoints, PlayerSnapshot, ScrapeRun
from storage.repository import add_squad_member


@pytest.fixture()
def a_player(session):
    seed_player(session, 1, "Galactico", "DEL")
    return session.get(Player, 1)


def seed_player(session, player_id: int, name: str, position: str) -> None:
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
    session.commit()


def seed_snapshot(session, player_id: int, as_of: date, market_value: int) -> None:
    run = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(run)
    session.commit()
    session.add(
        PlayerSnapshot(
            as_of=as_of,
            player_id=player_id,
            market_value=market_value,
            points=0,
            availability_status="available",
            raw_fields="{}",
            scrape_run_id=run.id,
        )
    )
    session.commit()


def seed_gameweek_points(session, player_id: int, season_year: int, week: int, points: int) -> None:
    run = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(run)
    session.commit()
    session.add(
        PlayerGameweekPoints(
            season_year=season_year,
            week=week,
            player_id=player_id,
            points=points,
            scrape_run_id=run.id,
        )
    )
    session.commit()


def test_empty_squad_returns_an_empty_history(client):
    body = client.get("/api/squad/history").json()
    assert body == {"valueHistory": [], "pointsHistory": [], "seasonWeekRanges": {}}


def test_history_reports_squad_value_and_points(session, client, a_player):
    # `add_squad_member` stamps `acquired_on` as today — the snapshot must
    # land on the same date, or the member reads as not-yet-held on it.
    today = date.today()
    seed_snapshot(session, a_player.id, today, 5_000_000)
    seed_gameweek_points(session, a_player.id, 2026, 1, 8)
    add_squad_member(session, player_id=a_player.id, purchase_price=4_500_000)

    body = client.get("/api/squad/history").json()

    assert body["valueHistory"] == [{"asOf": today.isoformat(), "squadValue": 5_000_000}]
    assert body["pointsHistory"] == [
        {"seasonYear": 2026, "week": 1, "points": 8, "isProvisional": False}
    ]
    assert body["seasonWeekRanges"] == {"2026": 1}
