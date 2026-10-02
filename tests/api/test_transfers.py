"""Phase 11 endpoints — /api/transfers/*. Legality, ceiling, staleness and
fixtures exercised end to end through the real rules engine."""

from datetime import UTC, date, datetime, timedelta

import pytest

from core.config import get_settings
from core.rules import load_rules
from scraper.sources.analiticafantasy_calendar import FixtureRecord
from storage.models import (
    DatasetRun,
    Player,
    PlayerGameweekPoints,
    PlayerSnapshot,
    ScrapeRun,
    SquadMember,
)
from storage.repository import upsert_fixtures
from storage.transfers import build_context

SEASON = get_settings().current_season_year
RULES = load_rules().for_league(False)
SQUAD_POSITIONS = ["POR"] + ["DEF"] * 8 + ["MED"] * 8 + ["DEL"] * 7


def _run(session, started_at, datasets=("jornada_points", "fixtures")):
    run = ScrapeRun(started_at=started_at, status="success")
    session.add(run)
    session.commit()
    session.refresh(run)
    for d in datasets:
        session.add(DatasetRun(scrape_run_id=run.id, dataset=d, status="success",
                               started_at=started_at))
    session.commit()
    return run


def _player(session, run, key, position, team, mv, weekly, availability="available"):
    now = datetime.now(UTC)
    p = Player(external_id=key, name=key, team=team, position=position,
               created_at=now, updated_at=now)
    session.add(p)
    session.commit()
    session.refresh(p)
    session.add(PlayerSnapshot(
        as_of=date(2026, 9, 16), player_id=p.id, market_value=mv, ideal_bid=mv, max_bid=mv,
        points=0, availability_status=availability, raw_fields="{}", scrape_run_id=run.id,
    ))
    for week in range(1, 11):
        session.add(PlayerGameweekPoints(season_year=SEASON, week=week, player_id=p.id,
                                         points=weekly, scrape_run_id=run.id))
    session.commit()
    return p.id


@pytest.fixture()
def world(session):
    """A full squad of weak players (one goalkeeper), and a market of
    stronger ones in every position at a range of prices."""
    run = _run(session, datetime.now(UTC))
    squad = []
    for i, pos in enumerate(SQUAD_POSITIONS):
        pid = _player(session, run, f"own{i}", pos, "Home", 2_000_000, 1)
        session.add(SquadMember(player_id=pid, purchase_price=2_000_000,
                                acquired_on=date(2026, 9, 1)))
        squad.append(pid)
    goalkeeper = squad[0]
    market = {}
    for pos in ("POR", "DEF", "MED", "DEL"):
        market[(pos, "cheap")] = _player(session, run, f"{pos}-cheap", pos, "Away", 3_000_000, 5)
        market[(pos, "star")] = _player(session, run, f"{pos}-star", pos, "Away", 60_000_000, 9)
    # Enough filler per position for the price curves to fit.
    for pos in ("POR", "DEF", "MED", "DEL"):
        for j in range(15):
            _player(session, run, f"{pos}-fill{j}", pos, "Other", 1_000_000 * (j + 1), 1 + j % 4)
    session.commit()
    return {"squad": squad, "goalkeeper": goalkeeper, "market": market, "run": run}


def test_every_suggested_move_is_legal_and_explained(world, client):
    body = client.get("/api/transfers/suggestions").json()
    assert body["squadSize"] == RULES.max_squad_size
    assert body["moves"], "a weak full squad should have upgrades"
    owned = set(world["squad"])
    for m in body["moves"]:
        assert m["kind"] == "swap"
        assert m["sell"]["playerId"] in owned
        assert m["buy"]["playerId"] not in owned
        assert m["feasibleFormations"], "no move may leave the squad unable to field an XI"
        assert m["signals"][0]["name"] in {"points", "value"}
        if m["sell"]["playerId"] == world["goalkeeper"]:
            assert m["buy"]["position"] == "POR"
    sells = [m["sell"]["playerId"] for m in body["moves"]]
    assert len(sells) == len(set(sells))


def test_the_ceiling_is_respected_on_the_chosen_basis(world, client):
    body = client.get("/api/transfers/suggestions?max=5000000&basis=marketValue").json()
    assert body["ceiling"] == {"max": 5_000_000, "basis": "marketValue"}
    assert body["moves"]
    assert all(m["buy"]["marketValue"] <= 5_000_000 for m in body["moves"])
    stars = {v for (pos, kind), v in world["market"].items() if kind == "star"}
    assert not stars & {m["buy"]["playerId"] for m in body["moves"]}


def test_bad_basis_is_rejected(world, client):
    assert client.get("/api/transfers/suggestions?max=1&basis=cash").status_code == 422


def test_stale_market_lowers_confidence_and_says_why(world, session, client):
    fresh = client.get("/api/transfers/suggestions").json()
    run = world["run"]
    run.started_at = datetime.now(UTC) - timedelta(days=5)
    session.add(run)
    session.commit()
    stale = client.get("/api/transfers/suggestions").json()
    assert stale["freshness"]["confidence"] < fresh["freshness"]["confidence"]
    assert any("market update" in r for r in stale["freshness"]["reasons"])
    assert stale["moves"][0]["confidence"] < fresh["moves"][0]["confidence"]
    assert any("market update" in r for r in stale["moves"][0]["confidenceReasons"])


def test_no_fixtures_is_said_and_neutral(world, client):
    body = client.get("/api/transfers/suggestions").json()
    assert any("fixture" in r.lower() for r in body["freshness"]["reasons"])
    assert body["moves"][0]["buy"]["fixtureDataAvailable"] is False
    assert body["moves"][0]["buy"]["fixtureMultiplier"] == 1.0


def test_fixture_difficulty_is_weighted_and_its_opponent_visible(world, session, client):
    now = datetime.now(UTC)

    def rec(fid, md, home, away, days):
        return FixtureRecord(fixture_id=fid, matchday=md, season_year=SEASON,
                             kickoff_utc=now + timedelta(days=days),
                             kickoff_confirmed=True, is_final=False, home_team=home,
                             away_team=away, home_team_id=None, away_team_id=None,
                             home_difficulty=None, away_difficulty=None)

    upsert_fixtures(session, [rec(1, 8, "Away", "Other", 2), rec(2, 8, "Home", "Weak", 2.1)])
    body = client.get("/api/transfers/suggestions?n=1").json()
    assert body["jornadas"]["window"] == [8]
    buy = body["moves"][0]["buy"]
    assert buy["fixtureDataAvailable"] is True
    assert buy["fixtureDriver"]["opponent"] == "Other"
    assert any(s["name"] == "fixtures" and "Other" in s["text"]
               for s in body["moves"][0]["signals"])


def test_best_by_position_budget_toggle(world, client):
    no_ceiling = client.get("/api/transfers/best?position=DEL").json()
    assert no_ceiling["ceilingMissing"] is True
    assert no_ceiling["players"][0]["playerId"] == world["market"][("DEL", "star")]

    within = client.get("/api/transfers/best?position=DEL&max=5000000").json()
    assert within["affordableOnly"] is True
    assert within["players"][0]["playerId"] == world["market"][("DEL", "cheap")]
    assert all(p["marketValue"] <= 5_000_000 for p in within["players"])

    regardless = client.get(
        "/api/transfers/best?position=DEL&max=5000000&affordableOnly=false"
    ).json()
    assert regardless["players"][0]["playerId"] == world["market"][("DEL", "star")]
    assert all(p["position"] == "DEL" for p in regardless["players"])


def test_bargains_and_bids(world, client):
    bargains = client.get("/api/transfers/bargains").json()
    assert bargains["players"]
    assert all(p["forwardGapPct"] > 0 for p in bargains["players"])
    cheap = {v for (pos, kind), v in world["market"].items() if kind == "cheap"}
    assert cheap & {p["playerId"] for p in bargains["players"]}

    bids = client.get("/api/transfers/bids?limit=5").json()
    assert len(bids["players"]) == 5
    row = bids["players"][0]
    assert row["ourIdeal"] >= row["marketValue"]
    assert row["ourMax"] >= row["ourIdeal"]

    one = client.get(f"/api/transfers/bids/{world['market'][('MED', 'cheap')]}").json()
    assert one["ourIdeal"] == 3_000_000
    assert client.get("/api/transfers/bids/99999").status_code == 404


def test_expected_points_flow_through_when_supplied(world, session):
    star = world["market"][("MED", "cheap")]
    now = datetime.now(UTC)
    without = build_context(session, RULES, SEASON, 3, now)
    with_xp = build_context(session, RULES, SEASON, 3, now, expected_points={star: 20.0})
    assert without.expected_points_used is False
    assert with_xp.expected_points_used is True
    assert with_xp.assessments[star].expected_return > without.assessments[star].expected_return
    # Odds become a confidence input once expected points use them — and
    # this world has never fetched odds.
    assert with_xp.freshness.factor < without.freshness.factor


def test_empty_database_is_not_an_error(client):
    body = client.get("/api/transfers/suggestions").json()
    assert body["moves"] == []
    assert body["freshness"]["label"] == "low"
    assert client.get("/api/transfers/best?position=POR").json()["players"] == []
    assert client.get("/api/transfers/bargains").json()["players"] == []
