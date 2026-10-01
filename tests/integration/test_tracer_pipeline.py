"""End-to-end tracer: fixture -> parse -> transform -> append -> GET /api/players.

Runs entirely offline against the captured fixture (`tests/fixtures/`) —
never against the live site, per `PITFALLS.md`'s "develop against fixtures,
not live requests" guidance.
"""

import json
from datetime import date
from pathlib import Path

from core.transform import to_snapshot
from scraper.sources.analiticafantasy import parse_page
from storage.repository import append_snapshots, get_latest_players, upsert_players

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "puja-ideal-page1.html"


def _load_records() -> list[dict]:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    return parse_page(html)


def _load_fixture_into(session, as_of: date, records: list[dict] | None = None):
    records = records if records is not None else _load_records()
    player_ids = upsert_players(session, records)
    snapshots = [
        to_snapshot(record, player_ids[record["external_id"]], as_of, scrape_run_id=1)
        for record in records
    ]
    append_snapshots(session, snapshots)
    return records, player_ids


def test_end_to_end_from_fixture(session, client):
    _load_fixture_into(session, date(2026, 8, 6))

    response = client.get("/api/players")
    assert response.status_code == 200

    body = response.json()
    assert body["as_of"] == "2026-08-06"
    assert len(body["players"]) >= 10

    for row in body["players"]:
        assert row["name"]
        assert row["team"]
        assert row["position"]
        assert row["marketValue"] is not None
        assert row["points"] is not None


def test_second_day_appends_not_overwrites(session):
    # Load the same fixture under two different `as_of` dates — simulating
    # the scraper running on two different calendar days. Day two's values
    # are deliberately changed so an overwrite bug (day one's row mutated
    # in place) would be caught by the market_value assertion below, not
    # masked by both days coincidentally holding identical values.
    records, player_ids = _load_fixture_into(session, date(2026, 8, 5))

    day_two_records = [dict(r, market_value=r["market_value"] + 1_000_000) for r in records]
    _load_fixture_into(session, date(2026, 8, 6), records=day_two_records)

    first_player = records[0]
    original_market_value = first_player["market_value"]
    player_id = player_ids[first_player["external_id"]]

    from sqlmodel import select

    from storage.models import PlayerSnapshot

    both_days = session.exec(
        select(PlayerSnapshot)
        .where(PlayerSnapshot.player_id == player_id)
        .order_by(PlayerSnapshot.as_of)
    ).all()
    assert len(both_days) == 2
    assert both_days[0].as_of == date(2026, 8, 5)
    assert both_days[1].as_of == date(2026, 8, 6)

    # Yesterday's market_value is still readable — it was never overwritten.
    assert both_days[0].market_value == original_market_value
    assert both_days[1].market_value == original_market_value + 1_000_000

    rows = get_latest_players(session)
    assert len(rows) >= 10
    latest_snapshot = next(s for s, p in rows if p.id == player_id)
    assert latest_snapshot.as_of == date(2026, 8, 6)
    assert latest_snapshot.market_value == original_market_value + 1_000_000


def test_snapshot_keeps_starter_market_updates_and_fixture_id(session):
    # F15: these three columns used to not exist at all — the parser kept
    # a subset of the source payload and the rest, including isStarter /
    # mercadosProximoPartido / nextFixture.fixtureId, was discarded before
    # it ever reached to_snapshot. This fixture predates those keys in the
    # embedded JSON, so the values are None here; the point is that
    # to_snapshot actually passes them through onto the model rather than
    # dropping them.
    records, player_ids = _load_fixture_into(session, date(2026, 8, 6))
    first_record = records[0]
    snapshot = to_snapshot(
        first_record, player_ids[first_record["external_id"]], date(2026, 8, 6), scrape_run_id=1
    )
    assert snapshot.is_starter == first_record.get("is_starter")
    assert snapshot.market_updates_to_next_match == first_record.get(
        "market_updates_to_next_match"
    )
    assert snapshot.next_fixture_id == first_record.get("next_fixture_id")


def test_raw_fields_roundtrip(session):
    records, _ = _load_fixture_into(session, date(2026, 8, 6))
    rows = get_latest_players(session)

    first_record = records[0]
    snapshot = next(
        s for s, p in rows if p.external_id == first_record["external_id"]
    )
    stored = json.loads(snapshot.raw_fields)

    for key in first_record:
        assert key in stored
        assert stored[key] == first_record[key]
