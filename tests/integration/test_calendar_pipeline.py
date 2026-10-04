"""The calendar dataset of the refresh, end to end over the saved capture —
fetch (stubbed), parse, validate, write — without touching the network."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from scraper.errors import ScrapeBlocked, ScrapeNotPublished
from scraper.run import ingest_fixtures, run_daily_refresh
from scraper.sources.analiticafantasy_calendar import FixtureRecord
from storage.db import set_engine
from storage.models import PlayerSnapshot, ScrapeRun
from storage.repository import get_dataset_runs, get_fixtures, upsert_fixtures

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURE_PATH = FIXTURES / "calendario-predictor.html"
PUJA_PATH = FIXTURES / "puja-ideal-page1.html"


def _record(fixture_id: int) -> FixtureRecord:
    return FixtureRecord(
        fixture_id=fixture_id,
        matchday=8,
        season_year=2026,
        kickoff_utc=datetime(2026, 10, 9, 19, 0, tzinfo=UTC),
        kickoff_confirmed=True,
        is_final=False,
        home_team="Barcelona",
        away_team="Athletic Club",
        home_team_id=529,
        away_team_id=531,
        home_difficulty="easy",
        away_difficulty="very_hard",
    )


@pytest.fixture()
def offline_deep_datasets(monkeypatch):
    """Stub the four deep-ingestion fetchers from committed captures so a
    full `run_daily_refresh` stays offline."""

    def _fixture(name: str):
        text = (FIXTURES / "phase7" / name).read_text(encoding="utf-8")
        return lambda *a, **k: text

    monkeypatch.setattr("scraper.run.fetch_jornada", _fixture("jornada-2026-latest.html"))
    monkeypatch.setattr("scraper.run.fetch_season_stats", _fixture("estadisticas-2025.html"))
    monkeypatch.setattr("scraper.run.fetch_points_predictions", _fixture("predicciones.html"))
    monkeypatch.setattr(
        "scraper.run.fetch_market_predictions", _fixture("prediccion-de-mercado.html")
    )


def _run(session) -> ScrapeRun:
    r = ScrapeRun(started_at=datetime.now(UTC), status="running")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _datasets(session, run):
    return {d.dataset: d for d in get_dataset_runs(session, run.id)}


def test_a_good_capture_is_written(session, monkeypatch):
    monkeypatch.setattr(
        "scraper.run.fetch_calendar", lambda *a, **k: FIXTURE_PATH.read_text(encoding="utf-8")
    )
    run = _run(session)
    ingest_fixtures(session, run, None)

    assert len(get_fixtures(session)) == 50
    dataset = _datasets(session, run)["fixtures"]
    assert dataset.status == "success"
    assert dataset.row_count == 50


def test_a_malformed_capture_fails_the_dataset_and_writes_nothing(session, monkeypatch):
    monkeypatch.setattr(
        "scraper.run.fetch_calendar", lambda *a, **k: "<html><body>no fixtures</body></html>"
    )
    run = _run(session)
    ingest_fixtures(session, run, None)

    assert get_fixtures(session) == []
    dataset = _datasets(session, run)["fixtures"]
    assert dataset.status == "failed"
    assert "ValueError" in dataset.errors


def test_a_rejected_window_leaves_stored_fixtures_untouched(session, monkeypatch):
    """INGEST-02 applies to this source too: a too-small window is rejected
    loudly, and history already stored survives."""
    upsert_fixtures(session, [_record(1)])
    monkeypatch.setattr("scraper.run.parse_calendar", lambda html: [_record(2)])
    monkeypatch.setattr("scraper.run.fetch_calendar", lambda *a, **k: "<html></html>")
    run = _run(session)
    ingest_fixtures(session, run, None)

    assert [f.fixture_id for f in get_fixtures(session)] == [1]
    dataset = _datasets(session, run)["fixtures"]
    assert dataset.status == "rejected"
    assert "below minimum" in dataset.errors


def test_a_blocked_calendar_still_leaves_the_market_scrape_written(
    session, engine, offline_deep_datasets
):
    """The calendar is a secondary dataset: its failure is recorded on its
    own `DatasetRun` (and turns the health page red, like any other failed
    dataset) but never costs the day's player snapshots, which cannot be
    backfilled."""
    set_engine(engine)
    html = PUJA_PATH.read_text(encoding="utf-8")
    with (
        patch("scraper.run.fetch_pages", return_value=[html]),
        patch("scraper.run.fetch_calendar", side_effect=ScrapeBlocked("429")),
    ):
        result = run_daily_refresh()

    assert session.query(PlayerSnapshot).count() > 0
    datasets = _datasets(session, result)
    assert datasets["market"].status == "success"
    assert datasets["fixtures"].status == "failed"
    assert datasets["season_stats"].status == "success"


def test_a_not_published_calendar_is_a_state_not_a_failure(
    session, engine, offline_deep_datasets
):
    set_engine(engine)
    html = PUJA_PATH.read_text(encoding="utf-8")
    with (
        patch("scraper.run.fetch_pages", return_value=[html]),
        patch("scraper.run.fetch_calendar", side_effect=ScrapeNotPublished("404")),
    ):
        result = run_daily_refresh()

    assert result.status == "success"
    assert _datasets(session, result)["fixtures"].status == "not_published"
