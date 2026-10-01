"""Phase 10 endpoints, and the two score fields added to the browser and
squad payloads."""

from datetime import UTC, date, datetime

from core import expected_points as xp
from storage.models import Player, PlayerGameweekPoints, PlayerSnapshot, ScrapeRun, SquadMember
from storage.our_models import refresh_market_predictions


def _v2_score(history, position):
    a, c = xp.RATE_ONLY[position]
    return round(100 * max(0.0, a * xp.points_rate(history, None, position).value + c) / 10, 1)


def _seed(session, n=20):
    now = datetime.now(UTC)
    run = ScrapeRun(started_at=now, status="success")
    session.add(run)
    session.commit()
    ids = []
    for i in range(n):
        p = Player(external_id=f"p{i}", name=f"P{i}", team="T", position="MED",
                   created_at=now, updated_at=now)
        session.add(p)
        session.commit()
        session.refresh(p)
        ids.append(p.id)
        for day, pct in [(date(2026, 9, 1), -1.0), (date(2026, 9, 2), 0.6)]:
            session.add(PlayerSnapshot(
                as_of=day, player_id=p.id, market_value=1_000_000 * (i + 1),
                price_change_pct=pct, points=0, availability_status="available",
                raw_fields="{}", scrape_run_id=run.id,
            ))
        for week in range(1, 11):
            session.add(PlayerGameweekPoints(season_year=2026, week=week, player_id=p.id,
                                             points=1 + i % 5, scrape_run_id=run.id))
    session.commit()
    return ids


def test_players_carry_power_and_economy(session, client):
    ids = _seed(session)
    rows = {r["playerId"]: r for r in client.get("/api/players").json()["players"]}
    # Steady 5s → shrunk toward the MED prior and calibrated (Power v2).
    assert rows[ids[4]]["powerScore"] == _v2_score([5] * 10, "MED")
    assert 0 <= rows[ids[4]]["economyScore"] <= 100


def test_squad_members_carry_power_and_economy(session, client):
    ids = _seed(session)
    session.add(SquadMember(player_id=ids[0], purchase_price=1, acquired_on=date(2026, 9, 1)))
    session.commit()
    [member] = client.get("/api/squad").json()["members"]
    assert member["powerScore"] == _v2_score([1] * 10, "MED")
    assert "economyScore" in member


def test_player_analytics_shows_inputs_and_windows(session, client):
    ids = _seed(session)
    body = client.get(f"/api/players/{ids[3]}/analytics?windows=1,30").json()
    assert body["form"]["window"] == 5
    assert body["consistency"]["points"] == [4] * 10
    assert [m["windowDays"] for m in body["momentum"]] == [1, 30]
    assert body["momentum"][0]["days"] == 1
    assert body["momentum"][1]["pct"] is None
    assert body["power"]["referencePpg"] == 10.0
    assert body["power"]["rateMatches"] == 10
    assert body["power"]["calibration"] == {"a": xp.RATE_ONLY["MED"][0],
                                            "c": xp.RATE_ONLY["MED"][1]}
    assert body["valuation"]["fit"]["n"] == 20


def test_player_analytics_404_and_bad_windows(session, client):
    ids = _seed(session, n=1)
    assert client.get("/api/players/999/analytics").status_code == 404
    assert client.get(f"/api/players/{ids[0]}/analytics?windows=abc").status_code == 422
    assert client.get(f"/api/players/{ids[0]}/analytics?windows=0").status_code == 422


def test_market_endpoints(session, client):
    _seed(session, n=3)
    refresh_market_predictions(session, today=date(2026, 9, 20),
                               now=datetime(2026, 9, 20, tzinfo=UTC))
    preds = client.get("/api/models/market/predictions").json()
    assert preds["madeOn"] == "2026-09-02"
    assert len(preds["predictions"]) == 3
    assert preds["predictions"][0]["confidence"] in {"strong", "moderate", "weak"}

    record = client.get("/api/models/market/track-record").json()
    assert record["ours"]["retroactive"]["scored"] == 3
    assert record["ours"]["retroactive"]["byScoring"]["exact"]["scored"] == 3

    div = client.get("/api/models/market/divergence").json()
    assert div == {"asOf": None, "rows": [], "agree": 0, "disagree": 0, "ourCallMissing": 0}

    older = client.get("/api/models/market/predictions?madeOn=2026-09-01").json()
    assert older["predictions"][0]["outcome"]["scoring"] == "exact"


def test_market_predictions_empty(client):
    body = client.get("/api/models/market/predictions").json()
    assert body["predictions"] == [] and body["madeOn"] is None
