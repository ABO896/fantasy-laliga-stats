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


def test_players_carry_the_live_inputs_fields(session, client):
    """Task 7: every row gets the compact inputs fields beside score_fields,
    whatever their values — the keys must always be there."""
    ids = _seed(session)
    rows = {r["playerId"]: r for r in client.get("/api/players").json()["players"]}
    row = rows[ids[0]]
    for key in (
        "powerRank", "reliabilityClass", "pStart", "pointsValuePct",
        "outlookPct", "outlookDirection", "dropRisk", "xptsWindow",
    ):
        assert key in row, key
    # This seed gives every player a snapshot, so reliability always computes.
    assert row["reliabilityClass"] is not None
    assert row["pStart"] is not None


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


def test_player_analytics_carries_the_live_inputs_blocks(session, client):
    """Task 7: reliability, evidence, points value, outlook and Power's
    position rank, added beside the existing ANALYTICS-05 blocks."""
    ids = _seed(session, n=3)
    body = client.get(f"/api/players/{ids[0]}/analytics").json()
    assert body["reliability"]["class"] in {"Nailed", "Regular", "Rotation", "Fringe"}
    assert isinstance(body["pointsValue"]["replacement"], (int, float)) or (
        body["pointsValue"]["replacement"] is None
    )
    # No market-v2 rows stored in this seed → no outlook to report.
    assert body["priceOutlook"] is None
    assert body["powerRank"]["of"] == 3
    assert "matchesWithMinutes" in body["evidence"]
    assert "inputsConfidence" in body
    assert "dataThrough" in body


def test_player_analytics_carries_ranks_and_the_xp_card(session, client):
    """Plan D Task 1: every metric gets a within-position rank, and the xP
    card gets its own block."""
    ids = _seed(session, n=5)
    body = client.get(f"/api/players/{ids[0]}/analytics").json()
    assert set(body["ranks"]) == {
        "power", "pointsValue", "outlook", "reliability", "xp", "form",
        "consistency", "momentum7",
    }
    assert body["ranks"]["power"]["of"] == 5
    assert body["ranks"]["power"]["position"] == "MED"
    assert body["ranks"]["reliability"]["position"] == "MED"
    # This seed stores no ExpectedPointsPrediction rows, so the xP card has
    # nothing to show yet, but the key must always be present.
    assert body["xp"] is None


def test_player_analytics_empty_payload_has_null_ranks_and_xp(session, client):
    now = datetime.now(UTC)
    p = Player(external_id="blank", name="Blank", team="T", position="DEF",
               created_at=now, updated_at=now)
    session.add(p)
    session.commit()
    session.refresh(p)

    body = client.get(f"/api/players/{p.id}/analytics").json()
    assert body["ranks"] is None
    assert body["xp"] is None


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


def test_market_track_record_version_param(client):
    assert client.get("/api/models/market/track-record").json()["modelVersion"] == "market-v1"

    v2 = client.get("/api/models/market/track-record?version=market-v2")
    assert v2.status_code == 200
    body = v2.json()
    assert body["modelVersion"] == "market-v2"
    assert "naive" in body and "intervalCoverage" in body

    assert client.get("/api/models/market/track-record?version=bogus").status_code == 422
