"""Integration proof of the invariants a bad scrape must satisfy: a
classified `ScrapeError` (blocked/structure-changed/network, Task 2) and a
`validate_scrape()` rejection (Task 3) must both leave `player_snapshots`
untouched — yesterday's data stays the current "latest" either way. The
distinction between `failed` and `rejected` is only how far the run got,
never whether existing history survives (docs/SCRAPING-POLICY.md,
01-03-PLAN.md prohibitions).

Also proves the flagged same-day-idempotency assumption (T-03-05): running
`run_daily_refresh` twice on one calendar date replaces that date's
snapshot set rather than duplicating/erroring, and that replace is
strictly bounded to the current date — earlier dates survive byte-identical.
"""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import func, select

from core.transform import to_snapshot
from scraper.errors import ScrapeBlocked, ScrapeNotPublished
from scraper.run import run_daily_refresh
from scraper.sources.analiticafantasy import parse_page
from storage.db import set_engine
from storage.external_repository import get_external_matches
from storage.models import PlayerSnapshot, ScrapeRun
from storage.repository import (
    append_snapshots,
    get_dataset_runs,
    get_latest_players,
    upsert_players,
)

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "puja-ideal-page1.html"
PHASE7_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "phase7"


@pytest.fixture(autouse=True)
def _stub_deep_ingestion_fetchers(monkeypatch):
    """These tests assert market-pipeline behaviour only. Once the refresh
    grew from one dataset to five, `run_daily_refresh` also calls the four
    deep-ingestion fetchers unconditionally — stub them from committed
    fixtures so every test in this file stays offline, exactly as it
    always was. Every test here calls `run_daily_refresh`, so this is
    autouse rather than threaded through each signature.
    """

    def _fixture(name: str):
        text = (PHASE7_FIXTURES / name).read_text(encoding="utf-8")
        return lambda *a, **k: text

    monkeypatch.setattr("scraper.run.fetch_jornada", _fixture("jornada-2026-latest.html"))
    monkeypatch.setattr("scraper.run.fetch_season_stats", _fixture("estadisticas-2025.html"))
    monkeypatch.setattr("scraper.run.fetch_points_predictions", _fixture("predicciones.html"))
    monkeypatch.setattr(
        "scraper.run.fetch_market_predictions", _fixture("prediccion-de-mercado.html")
    )
    calendar = (PHASE7_FIXTURES.parent / "calendario-predictor.html").read_text(encoding="utf-8")
    monkeypatch.setattr("scraper.run.fetch_calendar", lambda *a, **k: calendar)
    external = PHASE7_FIXTURES.parent / "external"
    season_csv = (external / "football-data-SP1-2627.csv").read_text(encoding="utf-8")
    fixtures_csv = (external / "football-data-fixtures-with-sp1.csv").read_text(encoding="utf-8")
    monkeypatch.setattr("scraper.external_ingest.fetch_season_csv", lambda *a, **k: season_csv)
    monkeypatch.setattr("scraper.external_ingest.fetch_fixtures_csv", lambda *a, **k: fixtures_csv)


def _load_records() -> list[dict]:
    return parse_page(FIXTURE_PATH.read_text(encoding="utf-8"))


def _seed_one_day(session, as_of: date, records: list[dict] | None = None):
    records = records if records is not None else _load_records()
    player_ids = upsert_players(session, records)
    snapshots = [
        to_snapshot(r, player_ids[r["external_id"]], as_of, scrape_run_id=1) for r in records
    ]
    append_snapshots(session, snapshots)
    return records, player_ids


def test_blocked_run_leaves_snapshots_untouched(session, engine):
    set_engine(engine)
    _seed_one_day(session, date(2026, 8, 5))

    before_rows = get_latest_players(session)
    before_count = len(before_rows)
    before_as_of = before_rows[0][0].as_of

    with patch("scraper.run.fetch_pages", side_effect=ScrapeBlocked("HTTP 403")):
        result = run_daily_refresh()

    assert result.status == "failed"
    assert result.validation_errors is not None
    assert "ScrapeBlocked" in result.validation_errors

    after_rows = get_latest_players(session)
    assert len(after_rows) == before_count
    assert after_rows[0][0].as_of == before_as_of


def test_reject_does_not_write(session, engine):
    set_engine(engine)
    _seed_one_day(session, date(2026, 8, 5))

    before_rows = get_latest_players(session)
    before_count = len(before_rows)
    before_as_of = before_rows[0][0].as_of

    # A batch far below `min_row_count` (default 300) — must be rejected
    # by `validate_scrape()` before ever reaching `upsert_players`/
    # `replace_snapshots`.
    truncated_records = [
        {
            "external_id": f"truncated-{i}",
            "name": f"Player {i}",
            "team": "Test FC",
            "position": "DEF",
            "points": 1,
            "market_value": 1_000_000,
            "availability_status": "available",
        }
        for i in range(5)
    ]

    with (
        patch("scraper.run.fetch_pages", return_value=["<html></html>"]),
        patch("scraper.run.parse_page", return_value=truncated_records),
    ):
        result = run_daily_refresh()

    assert result.status == "rejected"
    assert result.validation_errors
    reasons = json.loads(result.validation_errors)
    assert any("row_count" in r for r in reasons)

    after_rows = get_latest_players(session)
    assert len(after_rows) == before_count
    assert after_rows[0][0].as_of == before_as_of


def test_same_day_rerun_replaces_only_today(session, engine):
    set_engine(engine)
    day1_records, _ = _seed_one_day(session, date(2026, 8, 4))
    day2_records, _ = _seed_one_day(session, date(2026, 8, 5))

    html = FIXTURE_PATH.read_text(encoding="utf-8")

    with patch("scraper.run.fetch_pages", return_value=[html]):
        first_result = run_daily_refresh()
        second_result = run_daily_refresh()

    assert first_result.status == "success"
    assert second_result.status == "success"

    today = date.today()
    today_count = session.exec(
        select(func.count()).select_from(PlayerSnapshot).where(PlayerSnapshot.as_of == today)
    ).one()
    # Exactly one snapshot per player for today after two runs — the
    # second run replaced, rather than duplicated, today's set. Without
    # `replace_snapshots`, the second run's inserts would have raised a
    # composite-PK (as_of, player_id) violation instead.
    assert today_count == first_result.row_count

    day1_rows = session.exec(
        select(PlayerSnapshot).where(PlayerSnapshot.as_of == date(2026, 8, 4))
    ).all()
    day2_rows = session.exec(
        select(PlayerSnapshot).where(PlayerSnapshot.as_of == date(2026, 8, 5))
    ).all()
    assert len(day1_rows) == len(day1_records)
    assert len(day2_rows) == len(day2_records)
    # Byte-identical: the replace touched only today, never these dates.
    assert {r.market_value for r in day1_rows} == {rec["market_value"] for rec in day1_records}
    assert {r.market_value for r in day2_rows} == {rec["market_value"] for rec in day2_records}


def test_an_unclassified_failure_still_records_why(session, engine):
    # An *unclassified* exception (a genuine bug, not a classified
    # `ScrapeError`) must still leave a readable reason on the run before
    # it re-raises. Without one, `/health` shows a bare "failed" with an
    # empty `validation_errors`, and the operator has nothing to act on —
    # which is exactly how a fortnight of failed daily scrapes went
    # unnoticed. Fail-loud is preserved: the exception still propagates.
    set_engine(engine)

    with patch("scraper.run.fetch_pages", side_effect=RuntimeError("kaboom")):
        with pytest.raises(RuntimeError):
            run_daily_refresh()

    run = session.exec(select(ScrapeRun).order_by(ScrapeRun.id.desc())).first()
    assert run.status == "failed"
    assert run.validation_errors is not None, "an unclassified failure recorded no reason"
    assert "RuntimeError" in run.validation_errors
    assert "kaboom" in run.validation_errors


def test_the_refresh_fetches_the_player_pages_once_and_stores_the_calendar(session, engine):
    """The calendar is back as a dataset of the refresh (INGEST-04, restored
    2026-09-27): one player-page fetch, and the fixture window stored under
    its own `DatasetRun`."""
    set_engine(engine)
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    with patch("scraper.run.fetch_pages", return_value=[html]) as fetch:
        result = run_daily_refresh()

    assert result.status == "success"
    assert fetch.call_count == 1
    fixtures = next(d for d in get_dataset_runs(session, result.id) if d.dataset == "fixtures")
    assert fixtures.status == "success"
    assert fixtures.row_count == 50


def test_a_failed_dataset_degrades_the_overall_run_to_failed(session, engine):
    """The status-derivation branch itself had zero coverage: every other
    test here produces all-success datasets. A classified failure in one
    dataset (jornada_points here) must downgrade the otherwise-successful
    `ScrapeRun.status` from "success" to "failed" — this is the mechanism
    the whole health-page constraint rests on."""
    set_engine(engine)
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    with (
        patch("scraper.run.fetch_pages", return_value=[html]),
        patch("scraper.run.fetch_jornada", side_effect=ScrapeBlocked("429")),
    ):
        result = run_daily_refresh()

    assert result.status == "failed"


def test_a_not_published_dataset_leaves_the_overall_run_green(session, engine):
    """The other direction of the same mechanism, and the one the spec
    cares about more: `not_published` is a state, not a failure, and must
    not turn a normal quiet day's health page red — that is exactly the
    silent-for-eleven-days failure mode this whole task exists to prevent."""
    set_engine(engine)
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    with (
        patch("scraper.run.fetch_pages", return_value=[html]),
        patch("scraper.run.fetch_jornada", side_effect=ScrapeNotPublished("404")),
    ):
        result = run_daily_refresh()

    assert result.status == "success"


def test_an_unclassified_dataset_failure_still_records_why_and_reraises(session, engine):
    """The regression this round's review caught: `ingest_*` only catches
    `ScrapeNotPublished` and `(ScrapeError, ValueError)`. Anything else —
    a genuine bug, or an upstream data collision like the two real ones
    this task's own fixtures surfaced — must not leave the run looking
    like a quiet success, and must still fail loud rather than being
    silently absorbed."""
    set_engine(engine)
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    with (
        patch("scraper.run.fetch_pages", return_value=[html]),
        patch("scraper.run.fetch_jornada", side_effect=RuntimeError("kaboom in jornada")),
    ):
        with pytest.raises(RuntimeError):
            run_daily_refresh()

    run = session.exec(select(ScrapeRun).order_by(ScrapeRun.id.desc())).first()
    assert run.status == "failed"
    assert run.validation_errors is not None
    assert "RuntimeError" in run.validation_errors
    assert "kaboom in jornada" in run.validation_errors


def test_an_external_source_failing_never_fails_the_refresh(session, engine):
    """INGEST-09/10's contract: an external source degrades to absent. A
    block, and even a bug, in football-data leaves the refresh `success`
    and is recorded on its own dataset row."""
    set_engine(engine)
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    for failure in (ScrapeBlocked("HTTP 403"), RuntimeError("bug in the csv path")):
        with (
            patch("scraper.run.fetch_pages", return_value=[html]),
            patch("scraper.external_ingest.fetch_season_csv", side_effect=failure),
            patch("scraper.external_ingest.fetch_fixtures_csv", side_effect=failure),
        ):
            result = run_daily_refresh()

        assert result.status == "success"
        external = [
            d for d in get_dataset_runs(session, result.id) if d.dataset == "football_data"
        ]
        assert [d.status for d in external] == ["failed"]


def test_a_healthy_refresh_stores_external_matches(session, engine):
    set_engine(engine)
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    with patch("scraper.run.fetch_pages", return_value=[html]):
        result = run_daily_refresh()
    assert result.status == "success"
    assert len(get_external_matches(session)) == 72
