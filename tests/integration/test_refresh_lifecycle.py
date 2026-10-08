"""A refresh's `ScrapeRun` stays `running` until its last step, so the
single-flight guard covers the whole pipeline — not just the market page —
and a run left `running` by a killed process does not block every later
refresh."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import Session

from scraper import run as run_mod
from scraper.errors import ScrapeBlocked
from storage.db import set_engine
from storage.models import DatasetRun, ScrapeRun
from storage.repository import close_stale_runs, has_running_run

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "puja-ideal-page1.html"

LATER_STEPS = (
    "ingest_fixtures",
    "ingest_jornada_points",
    "ingest_season_stats",
    "ingest_points_predictions",
    "ingest_market_predictions",
    "ingest_football_data",
    "run_our_models",
    "run_expected_points",
)


@pytest.fixture()
def quiet_later_steps(monkeypatch):
    """Every step after the market page is a no-op, so these tests watch
    only the run's lifecycle."""
    for name in LATER_STEPS:
        monkeypatch.setattr(run_mod, name, lambda *a, **k: None)


def _status(engine, run_id: int) -> str:
    with Session(engine) as s:
        return s.get(ScrapeRun, run_id).status


def test_the_run_is_running_while_later_datasets_ingest(engine, monkeypatch, quiet_later_steps):
    set_engine(engine)
    seen = {}

    def spy(session, run, settings, mode="quick"):
        seen["status"] = _status(engine, run.id)

    monkeypatch.setattr(run_mod, "ingest_player_pages", spy)
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    with patch("scraper.run.fetch_pages", return_value=[html]):
        result = run_mod.run_daily_refresh()

    assert seen["status"] == "running"
    assert result.status == "success"
    assert result.finished_at is not None


def test_a_market_block_still_ends_the_run_failed(engine, monkeypatch, quiet_later_steps):
    set_engine(engine)
    monkeypatch.setattr(run_mod, "ingest_player_pages", lambda *a, **k: None)

    def blocked(*a, **k):
        raise ScrapeBlocked("Blocked by target site: HTTP 200")

    with patch("scraper.run.fetch_pages", side_effect=blocked):
        result = run_mod.run_daily_refresh()

    assert result.status == "failed"
    assert result.finished_at is not None
    assert "ScrapeBlocked" in result.validation_errors


def test_the_finish_time_is_after_the_last_step(engine, monkeypatch, quiet_later_steps):
    set_engine(engine)
    stamps = {}
    monkeypatch.setattr(run_mod, "ingest_player_pages", lambda *a, **k: None)
    monkeypatch.setattr(
        run_mod, "run_expected_points", lambda *a, **k: stamps.setdefault("last", datetime.now(UTC))
    )
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    with patch("scraper.run.fetch_pages", return_value=[html]):
        result = run_mod.run_daily_refresh()

    finished = result.finished_at.replace(tzinfo=UTC)
    assert finished >= stamps["last"]


def test_a_stale_running_run_is_closed_and_does_not_block(session):
    old = ScrapeRun(started_at=datetime.now(UTC) - timedelta(hours=3), status="running")
    session.add(old)
    session.commit()
    session.add(DatasetRun(scrape_run_id=old.id, dataset="player_pages", status="running",
                           started_at=old.started_at))
    session.commit()

    assert has_running_run(session) is False
    session.refresh(old)
    assert old.status == "failed"
    assert "interrupted" in old.validation_errors
    assert old.finished_at is not None


def test_a_recent_running_run_still_blocks(session):
    session.add(ScrapeRun(started_at=datetime.now(UTC) - timedelta(minutes=20), status="running"))
    session.commit()
    assert has_running_run(session) is True


def test_close_stale_runs_closes_their_running_datasets(session):
    old = ScrapeRun(started_at=datetime.now(UTC) - timedelta(hours=3), status="running")
    session.add(old)
    session.commit()
    ds = DatasetRun(scrape_run_id=old.id, dataset="player_pages", status="running",
                    started_at=old.started_at)
    session.add(ds)
    session.commit()

    assert close_stale_runs(session, datetime.now(UTC)) == 1
    session.refresh(ds)
    assert ds.status == "failed"
    assert ds.finished_at is not None


def test_the_cli_refuses_while_a_run_is_going(engine, monkeypatch):
    set_engine(engine)
    with Session(engine) as s:
        s.add(ScrapeRun(started_at=datetime.now(UTC), status="running"))
        s.commit()
    called = []
    monkeypatch.setattr(run_mod, "run_daily_refresh", lambda **k: called.append(k))

    assert run_mod.main([]) == 2
    assert called == []


def test_a_running_dataset_of_a_finished_run_is_closed(session):
    done = ScrapeRun(started_at=datetime.now(UTC) - timedelta(days=4), status="success",
                     finished_at=datetime.now(UTC) - timedelta(days=4))
    session.add(done)
    session.commit()
    ds = DatasetRun(scrape_run_id=done.id, dataset="player_pages", status="running",
                    started_at=done.started_at)
    session.add(ds)
    session.commit()

    close_stale_runs(session, datetime.now(UTC))
    session.refresh(ds)
    assert ds.status == "failed"
