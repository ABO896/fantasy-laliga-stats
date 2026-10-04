"""Route contracts for the squad surface.

The 409 body shape is load-bearing: spec D-05 requires a refusal to carry the
rule, the numbers, and a remedy — the UI renders `detail.message` directly.
"""

from datetime import UTC, date, datetime

import pytest

from core.rules import load_rules
from storage.models import Player, PlayerSnapshot, ScrapeRun


@pytest.fixture()
def a_player(session):
    seed_player(session, 1, "Galactico", "DEL", 5_000_000)
    return session.get(Player, 1)


def seed_player(session, player_id: int, name: str, position: str, value: int) -> None:
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
            availability_status="available",
            raw_fields="{}",
            scrape_run_id=run.id,
        )
    )
    session.commit()


def test_empty_squad_returns_a_usable_summary(client):
    body = client.get("/api/squad").json()
    assert body["members"] == []
    assert body["summary"]["squadSize"] == 0
    assert body["summary"]["maxSquadSize"] == 24
    assert body["summary"]["isLegal"] is True
    assert body["summary"]["canFieldXi"] is False
    assert body["summary"]["violations"] == []


def test_add_returns_201(client, session):
    seed_player(session, 1, "Keeper", "POR", 5_000_000)
    response = client.post("/api/squad/players", json={"playerId": 1, "purchasePrice": 4_500_000})
    assert response.status_code == 201
    body = response.json()
    assert body["summary"]["squadSize"] == 1
    assert body["summary"]["memberPlayerIds"] == [1]


def test_add_uses_the_submitted_purchase_price_not_market_value(client, session):
    seed_player(session, 1, "Keeper", "POR", 5_000_000)
    client.post("/api/squad/players", json={"playerId": 1, "purchasePrice": 7_000_000})
    member = client.get("/api/squad").json()["members"][0]
    assert member["purchasePrice"] == 7_000_000
    assert member["marketValue"] == 5_000_000


def test_add_of_an_unknown_player_returns_404(client):
    assert (
        client.post("/api/squad/players", json={"playerId": 999, "purchasePrice": 1}).status_code
        == 404
    )


def test_duplicate_add_returns_409_already_owned(client, session):
    seed_player(session, 1, "Keeper", "POR", 1_000_000)
    client.post("/api/squad/players", json={"playerId": 1, "purchasePrice": 1_000_000})
    response = client.post("/api/squad/players", json={"playerId": 1, "purchasePrice": 1_000_000})
    assert response.status_code == 409
    assert response.json()["detail"]["rule"] == "already_owned"


def test_remove_with_a_sale_price_succeeds(client, session):
    seed_player(session, 1, "Keeper", "POR", 1_000_000)
    client.post("/api/squad/players", json={"playerId": 1, "purchasePrice": 1_000_000})

    response = client.request("DELETE", "/api/squad/players/1", params={"salePrice": 1_200_000})
    assert response.status_code == 200
    assert response.json()["summary"]["squadSize"] == 0


def test_remove_of_a_player_not_in_the_squad_returns_404(client):
    assert client.delete("/api/squad/players/1").status_code == 404


def test_negative_sale_price_returns_409_with_a_structured_violation(client, session):
    seed_player(session, 1, "Keeper", "POR", 1_000_000)
    client.post("/api/squad/players", json={"playerId": 1, "purchasePrice": 1_000_000})

    response = client.request("DELETE", "/api/squad/players/1", params={"salePrice": -5})
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["rule"] == "sale_price"
    assert detail["actual"] == -5
    assert detail["limit"] == 0


def test_the_old_confirm_endpoint_is_gone(client):
    """Removed, not deprecated — two endpoints for one gesture is exactly what
    the spec cut, and one of them erased the gap."""
    assert client.post("/api/squad/balance/confirm", json={"amount": 1}).status_code == 404


def test_summary_reports_feasible_formations_and_what_is_missing(client, session):
    for player_id, position in enumerate(
        ["POR"] + ["DEF"] * 3 + ["MED"] * 4 + ["DEL"] * 3, start=1
    ):
        seed_player(session, player_id, f"P{player_id}", position, 1_000_000)
        client.post("/api/squad/players", json={"playerId": player_id, "purchasePrice": 1_000_000})

    summary = client.get("/api/squad").json()["summary"]
    assert summary["canFieldXi"] is True
    assert summary["feasibleFormations"] == ["3-4-3"]
    assert summary["missingForXi"] == {}
    assert summary["positionCounts"] == {"POR": 1, "DEF": 3, "MED": 4, "DEL": 3}


def test_rules_endpoint_exposes_the_league_narrowed_rules(client):
    body = client.get("/api/squad/rules").json()
    assert body["maxSquadSize"] == 24
    assert body["retrievedOn"] == "2026-08-07"
    assert body["premiumFormationsEnabled"] is False
    assert len(body["formations"]) == 7
    assert "4-6-0" not in {f["name"] for f in body["formations"]}
    # Pinned against the versioned rules data itself (not a re-typed literal)
    # so a typo'd key, a swap to the wrong `Rules` attribute, or the line
    # being dropped would all fail here rather than passing silently — this
    # assertion pins the rules-data projection this endpoint serves, not any
    # particular client (the frontend that once consumed cashPerPoint,
    # LedgerPage, was deleted with the budget ledger on 2026-08-21).
    assert body["cashPerPoint"] == load_rules().cash_per_point


def test_squad_returns_no_balance(client):
    body = client.get("/api/squad").json()

    assert "balance" not in body
    assert "cashBalance" not in body["summary"]
    assert "spendingPower" not in body["summary"]
    assert "inDebt" not in body["summary"]
    # The squad's own facts survive intact.
    assert "squadValue" in body["summary"]
    assert "feasibleFormations" in body["summary"]


def test_the_ledger_endpoints_are_gone(client):
    for method, path in [
        ("post", "/api/squad/balance/reconcile"),
        ("post", "/api/squad/ledger/points-income"),
        ("get", "/api/squad/ledger"),
        ("post", "/api/squad/ledger/entries/1/reverse"),
        ("post", "/api/squad/ledger/entries/1/replace"),
    ]:
        kwargs = {"json": {}} if method == "post" else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404, f"{method.upper()} {path} still routes"


def test_the_lineup_endpoints_are_gone(client):
    """Removed, not deprecated. The `lineup` table never held a row in twelve
    days and two deadlines; see the 2026-08-22 spec."""
    for method, path in [
        ("get", "/api/lineups"),
        ("get", "/api/lineups/1"),
        ("put", "/api/lineups/1"),
        ("delete", "/api/lineups/1"),
    ]:
        kwargs = {"json": {"formation": "4-4-2", "starterIds": []}} if method == "put" else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404, f"{method.upper()} {path} still routes"


def test_an_expensive_player_can_still_be_added(client, a_player):
    # The refusal that used to fire here needed a cash balance. There is no
    # cash balance, so there is no refusal — the owner decides.
    response = client.post(
        "/api/squad/players", json={"playerId": a_player.id, "purchasePrice": 99_000_000}
    )
    assert response.status_code == 201


def seed_squad(
    client, session, shape=("POR", "DEF", "DEF", "DEF", "DEF", "MED", "DEL")
) -> list[int]:
    """Seed and buy one player per entry, returning their ids in order."""
    ids = []
    for player_id, position in enumerate(shape, start=1):
        seed_player(session, player_id, f"P{player_id}", position, 1_000_000)
        client.post("/api/squad/players", json={"playerId": player_id, "purchasePrice": 1_000_000})
        ids.append(player_id)
    return ids


def enable_bench(client):
    client.put(
        "/api/league-settings",
        json={"premiumFormationsEnabled": False, "premiumBenchEnabled": True},
    )


def test_the_squad_starts_in_a_standard_formation_with_everyone_in_the_rail(client, session):
    seed_squad(client, session)
    body = client.get("/api/squad").json()

    assert body["summary"]["formation"] == "4-4-2"
    assert body["summary"]["formationShape"] == {"POR": 1, "DEF": 4, "MED": 4, "DEL": 2}
    assert body["summary"]["formationAvailable"] is True
    assert body["summary"]["benchEnabled"] is False
    assert len(body["summary"]["allowedFormations"]) == 7
    assert body["summary"]["formationShapes"]["4-4-2"] == {"POR": 1, "DEF": 4, "MED": 4, "DEL": 2}
    assert {m["role"] for m in body["members"]} == {"reserve"}


def test_every_member_carries_an_availability(client, session):
    seed_squad(client, session, shape=("POR",))
    member = client.get("/api/squad").json()["members"][0]
    assert member["availability"] == "available"


def test_every_member_carries_the_live_inputs_fields(client, session):
    """Task 7: the squad cards get the same compact inputs fields as the
    browser table — comparing same-position members' reliability and Power
    rank is the "who should I start" answer."""
    seed_squad(client, session, shape=("POR",))
    member = client.get("/api/squad").json()["members"][0]
    for key in (
        "powerRank", "reliabilityClass", "pStart", "pointsValuePct",
        "outlookPct", "outlookDirection", "dropRisk", "xptsWindow",
    ):
        assert key in member, key


def test_saving_an_xi_persists_the_roles_and_the_formation(client, session):
    ids = seed_squad(client, session)
    response = client.put(
        "/api/squad/lineup",
        json={"formation": "5-3-2", "starterIds": ids[:5], "benchIds": []},
    )
    assert response.status_code == 200

    body = client.get("/api/squad").json()
    assert body["summary"]["formation"] == "5-3-2"
    roles = {m["playerId"]: m["role"] for m in body["members"]}
    assert [roles[i] for i in ids[:5]] == ["starter"] * 5
    assert roles[ids[5]] == "reserve"


def test_an_incomplete_xi_is_saved_not_refused(client, session):
    ids = seed_squad(client, session)
    response = client.put(
        "/api/squad/lineup", json={"formation": "4-4-2", "starterIds": ids[:2], "benchIds": []}
    )
    assert response.status_code == 200
    assert response.json()["summary"]["formation"] == "4-4-2"


def test_an_over_filled_position_is_refused_with_a_structured_violation(client, session):
    ids = seed_squad(client, session)
    response = client.put(
        "/api/squad/lineup",
        json={"formation": "3-4-3", "starterIds": ids[1:5], "benchIds": []},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["rule"] == "formation_shape"
    assert detail["actual"] == 4
    assert detail["limit"] == 3
    assert "defender" in detail["message"]


def test_a_refused_save_changes_nothing(client, session):
    ids = seed_squad(client, session)
    client.put("/api/squad/lineup", json={"formation": "4-4-2", "starterIds": ids[:1]})

    client.put("/api/squad/lineup", json={"formation": "3-4-3", "starterIds": ids[1:5]})

    body = client.get("/api/squad").json()
    assert body["summary"]["formation"] == "4-4-2"
    roles = {m["playerId"]: m["role"] for m in body["members"]}
    assert roles[ids[0]] == "starter"
    assert roles[ids[1]] == "reserve"


def test_a_premium_formation_is_refused_while_the_league_is_standard(client, session):
    seed_squad(client, session)
    response = client.put("/api/squad/lineup", json={"formation": "4-6-0", "starterIds": []})
    assert response.status_code == 409
    assert response.json()["detail"]["rule"] == "formation_unavailable"


def test_a_player_outside_the_squad_is_refused(client, session):
    seed_squad(client, session, shape=("POR",))
    response = client.put("/api/squad/lineup", json={"formation": "4-4-2", "starterIds": [999]})
    assert response.status_code == 409
    assert response.json()["detail"]["rule"] == "not_in_squad"


def test_a_bench_pick_is_refused_while_the_bench_is_off(client, session):
    ids = seed_squad(client, session)
    response = client.put(
        "/api/squad/lineup",
        json={"formation": "4-4-2", "starterIds": ids[:1], "benchIds": [ids[1]]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["rule"] == "bench_disabled"


def test_a_bench_pick_is_accepted_once_the_league_enables_it(client, session):
    ids = seed_squad(client, session)
    enable_bench(client)
    response = client.put(
        "/api/squad/lineup",
        json={"formation": "4-4-2", "starterIds": ids[:1], "benchIds": [ids[1]]},
    )
    assert response.status_code == 200
    roles = {m["playerId"]: m["role"] for m in response.json()["members"]}
    assert roles[ids[1]] == "bench"
    assert response.json()["summary"]["benchEnabled"] is True


def test_removing_a_starter_puts_them_back_in_the_rail(client, session):
    ids = seed_squad(client, session)
    client.put("/api/squad/lineup", json={"formation": "4-4-2", "starterIds": ids[:3]})

    client.delete(f"/api/squad/players/{ids[0]}")

    body = client.get("/api/squad").json()
    assert ids[0] not in {m["playerId"] for m in body["members"]}
    # And re-adding does not restore the slot.
    client.post("/api/squad/players", json={"playerId": ids[0], "purchasePrice": 1_000_000})
    roles = {m["playerId"]: m["role"] for m in client.get("/api/squad").json()["members"]}
    assert roles[ids[0]] == "reserve"


def test_a_bench_member_stranded_by_the_league_switching_the_bench_off(client, session):
    """The server's half of the contract: a role stored while the bench was on
    survives the feature being switched off, and the API still reports it.
    The client is what must stop re-sending it — see SquadPage's `commit`."""
    ids = seed_squad(client, session)
    enable_bench(client)
    client.put(
        "/api/squad/lineup",
        json={"formation": "4-4-2", "starterIds": ids[:1], "benchIds": [ids[1]]},
    )

    client.put(
        "/api/league-settings",
        json={"premiumFormationsEnabled": False, "premiumBenchEnabled": False},
    )

    body = client.get("/api/squad").json()
    assert body["summary"]["benchEnabled"] is False
    roles = {m["playerId"]: m["role"] for m in body["members"]}
    assert roles[ids[1]] == "bench", "the stored role is not rewritten by a settings change"

    # And re-sending it is exactly what the server refuses.
    refused = client.put(
        "/api/squad/lineup",
        json={"formation": "4-4-2", "starterIds": ids[:1], "benchIds": [ids[1]]},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["rule"] == "bench_disabled"


def test_a_stored_formation_the_league_no_longer_allows_still_renders(client, session):
    """The pitch must draw the shape it is standing in and say it is no
    longer available, rather than silently reshuffling the team."""
    seed_squad(client, session)
    client.put(
        "/api/league-settings",
        json={"premiumFormationsEnabled": True, "premiumBenchEnabled": False},
    )
    client.put("/api/squad/lineup", json={"formation": "4-6-0", "starterIds": []})

    client.put(
        "/api/league-settings",
        json={"premiumFormationsEnabled": False, "premiumBenchEnabled": False},
    )
    summary = client.get("/api/squad").json()["summary"]

    assert summary["formation"] == "4-6-0"
    assert summary["formationShape"] == {"POR": 1, "DEF": 4, "MED": 6, "DEL": 0}
    assert summary["formationAvailable"] is False
