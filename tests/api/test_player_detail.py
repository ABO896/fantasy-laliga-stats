"""GET /api/players/{player_id} — everything one player's page needs.

The sparse cases here are not hypothetical: on 2026-08-27 the live database
has 283 of 642 players with no last-season statistics row, 628 of 642 not in
the squad, and 23 of the market's 518 with no stored prediction.
"""

from datetime import UTC, date, datetime

from storage.models import (
    Player,
    PlayerGameweekPoints,
    PlayerSnapshot,
    ScrapeRun,
    SourcePrediction,
    SquadMember,
)


def _seed_player(session, slug="p-1", name="Player One"):
    now = datetime.now(UTC)
    p = Player(
        external_id=slug, name=name, team="Team A", position="DEL", created_at=now, updated_at=now
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _seed_run(session):
    r = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def test_an_unknown_player_is_a_404(client):
    assert client.get("/api/players/999").status_code == 404


def test_the_payload_carries_identity_and_the_latest_snapshot(session, client):
    p = _seed_player(session)
    run = _seed_run(session)
    for as_of, value, points in [(date(2026, 8, 6), 100, 0), (date(2026, 8, 7), 120, 5)]:
        session.add(
            PlayerSnapshot(
                as_of=as_of,
                player_id=p.id,
                market_value=value,
                points=points,
                price_per_point=None,
                starter_probability=0.9,
                availability_status="available",
                next_opponent="GET",
                raw_fields="{}",
                scrape_run_id=run.id,
            )
        )
    session.commit()

    body = client.get(f"/api/players/{p.id}").json()

    assert body["asOf"] == "2026-08-07"
    assert body["player"]["name"] == "Player One"
    assert body["player"]["position"] == "DEL"
    assert body["latest"]["marketValue"] == 120
    assert body["latest"]["starterProbability"] == 0.9
    assert [v["marketValue"] for v in body["valueHistory"]] == [100, 120]


def test_a_player_with_no_snapshot_still_renders(session, client):
    """`asOf` and `latest` are null rather than absent — the page decides."""
    p = _seed_player(session)

    body = client.get(f"/api/players/{p.id}").json()

    assert body["asOf"] is None
    assert body["latest"] is None
    assert body["valueHistory"] == []


def test_gameweek_points_carry_season_week_and_provisional(session, client):
    p = _seed_player(session)
    run = _seed_run(session)
    session.add(
        PlayerGameweekPoints(
            season_year=2026,
            week=2,
            player_id=p.id,
            points=7,
            is_provisional=True,
            scrape_run_id=run.id,
        )
    )
    session.commit()

    body = client.get(f"/api/players/{p.id}").json()

    assert body["gameweekPoints"] == [
        {"seasonYear": 2026, "week": 2, "points": 7, "isProvisional": True}
    ]
    assert body["seasonWeekRanges"] == {"2026": 2}


def test_the_stats_map_covers_every_pair_in_the_schema(session, client, season_stats_row):
    """The schema is the single source of truth; a statistic added there must
    reach the API with no route change. This is the guard for that."""
    from core.season_stats_schema import STAT_PAIRS

    p = _seed_player(session)
    run = _seed_run(session)
    session.add(
        season_stats_row(
            season_year=2025, player_id=p.id, scrape_run_id=run.id, goals=18, goals_pts=72
        )
    )
    session.commit()

    body = client.get(f"/api/players/{p.id}").json()
    stats = body["seasonStats"][0]["stats"]

    assert set(stats) == {counter for counter, _ in STAT_PAIRS}
    assert stats["goals"] == {"count": 18, "points": 72}


def test_a_player_with_no_last_season_returns_one_season(session, client, season_stats_row):
    p = _seed_player(session)
    run = _seed_run(session)
    session.add(season_stats_row(season_year=2026, player_id=p.id, scrape_run_id=run.id))
    session.commit()

    body = client.get(f"/api/players/{p.id}").json()

    assert [s["seasonYear"] for s in body["seasonStats"]] == [2026]


def test_squad_membership_is_null_when_not_owned(session, client):
    p = _seed_player(session)
    assert client.get(f"/api/players/{p.id}").json()["squad"] is None


def test_squad_membership_reports_the_purchase(session, client):
    p = _seed_player(session)
    session.add(
        SquadMember(player_id=p.id, purchase_price=17_900_000, acquired_on=date(2026, 8, 12))
    )
    session.commit()

    assert client.get(f"/api/players/{p.id}").json()["squad"] == {
        "purchasePrice": 17_900_000,
        "acquiredOn": "2026-08-12",
    }


def test_a_missing_prediction_is_an_empty_map_not_a_zero(session, client):
    p = _seed_player(session)
    assert client.get(f"/api/players/{p.id}").json()["predictions"] == {}


def test_a_stored_prediction_is_returned(session, client):
    p = _seed_player(session)
    run = _seed_run(session)
    session.add(
        SourcePrediction(
            as_of=date(2026, 8, 27),
            source="points",
            player_id=p.id,
            value=4.2,
            raw_fields="{}",
            scrape_run_id=run.id,
        )
    )
    session.commit()

    assert client.get(f"/api/players/{p.id}").json()["predictions"] == {"points": 4.2}
