import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from core.config import Settings
from scraper.errors import ScrapeBlocked, ScrapeNotPublished
from scraper.external_ingest import backfill_football_data, ingest_football_data
from storage.external_repository import get_external_matches
from storage.models import Player, ScrapeRun
from storage.repository import get_dataset_runs

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "external"


def _read(name: str) -> str:
    path = FIXTURES / name
    if not path.exists():
        # `pytest.skip` raises a BaseException, so it passes through the
        # ingest's deliberately total `except Exception` — a FileNotFoundError
        # would be swallowed and recorded as a failed dataset instead.
        pytest.skip(f"captured file tests/fixtures/external/{name} is not in the repo")
    return path.read_text(encoding="utf-8")


def _run(session) -> ScrapeRun:
    r = ScrapeRun(started_at=datetime.now(UTC), status="running")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _raise(exc):
    def f(*a, **k):
        raise exc

    return f


def _stub(monkeypatch, season=None, fixtures=None):
    monkeypatch.setattr(
        "scraper.external_ingest.fetch_season_csv",
        season or (lambda *a, **k: _read("football-data-SP1-2627.csv")),
    )
    monkeypatch.setattr(
        "scraper.external_ingest.fetch_fixtures_csv",
        fixtures or (lambda *a, **k: _read("football-data-fixtures-with-sp1.csv")),
    )


def _dataset(session, run):
    [d] = [d for d in get_dataset_runs(session, run.id) if d.dataset == "football_data"]
    return d


def test_both_files_are_stored(session, monkeypatch):
    _stub(monkeypatch)
    run = _run(session)
    ingest_football_data(session, run, Settings(current_season_year=2026))

    d = _dataset(session, run)
    assert d.status == "success"
    assert d.row_count == 72
    assert d.season_year == 2026
    assert len(get_external_matches(session, season_year=2026, status="scheduled")) == 3
    assert len(get_external_matches(session, season_year=2026, status="played")) == 69


def test_one_failing_file_keeps_the_other(session, monkeypatch):
    _stub(monkeypatch, fixtures=_raise(ScrapeBlocked("HTTP 429")))
    run = _run(session)
    ingest_football_data(session, run, Settings(current_season_year=2026))

    d = _dataset(session, run)
    assert d.status == "failed"
    assert d.row_count == 69
    assert "ScrapeBlocked" in d.errors


def test_an_unpublished_season_file_is_a_state_not_a_failure(session, monkeypatch):
    _stub(
        monkeypatch,
        season=_raise(ScrapeNotPublished("404")),
        fixtures=lambda *a, **k: _read("football-data-fixtures-no-sp1.csv"),
    )
    run = _run(session)
    ingest_football_data(session, run, Settings(current_season_year=2026))
    assert _dataset(session, run).status == "success"
    assert get_external_matches(session) == []


def test_a_bug_is_recorded_and_never_raised(session, monkeypatch):
    _stub(monkeypatch, season=_raise(KeyError("surprise")))
    run = _run(session)
    ingest_football_data(session, run, Settings(current_season_year=2026))  # must not raise
    d = _dataset(session, run)
    assert d.status == "failed"
    assert "unclassified KeyError" in d.errors


def test_disabled_source_is_skipped_without_a_request(session, monkeypatch):
    _stub(monkeypatch, season=_raise(AssertionError("fetched")), fixtures=_raise(AssertionError()))
    run = _run(session)
    ingest_football_data(session, run, Settings(football_data_enabled=False))
    assert _dataset(session, run).status == "skipped"


def test_clubs_outside_the_roster_are_reported(session, monkeypatch):
    now = datetime.now(UTC)
    session.add(
        Player(
            external_id="x", name="X", team="Getafe", position="DEF", created_at=now, updated_at=now
        )
    )
    session.commit()
    _stub(monkeypatch)
    run = _run(session)
    ingest_football_data(session, run, Settings(current_season_year=2026))
    errors = json.loads(_dataset(session, run).errors)
    assert any(e.startswith("clubs not in the fantasy roster") and "Alaves" in e for e in errors)


def test_backfill_stores_one_past_season_and_is_not_a_refresh(session, monkeypatch):
    calls = []

    def season(season_year, settings=None):
        calls.append(season_year)
        return _read("football-data-SP1-2526.csv")

    _stub(monkeypatch, season=season, fixtures=_raise(AssertionError("no fixtures in backfill")))
    run = backfill_football_data(session, 2025, Settings(current_season_year=2026))
    assert calls == [2025]
    assert run.status == "backfill"
    assert len(get_external_matches(session, season_year=2025)) == 380


def test_the_wrong_season_file_is_rejected_not_stored(session, monkeypatch):
    _stub(monkeypatch, season=lambda *a, **k: _read("football-data-SP1-2526.csv"))
    run = _run(session)
    ingest_football_data(session, run, Settings(current_season_year=2026))
    d = _dataset(session, run)
    assert d.status == "failed"
    assert get_external_matches(session, season_year=2025) == []


def test_requests_use_this_sources_own_pace(monkeypatch):
    """The source's pacing comes from its own setting, not the fantasy
    site's defaults — asserted at the HTTP seam, never over the network."""
    from scraper.sources.football_data import fetch_fixtures_csv

    sleeps, urls = [], []
    monkeypatch.setattr("scraper.http.time.sleep", sleeps.append)

    def fake_get(url, **kwargs):
        urls.append((url, kwargs["headers"]["User-Agent"]))
        return httpx.Response(200, text="Div,Date,Time,HomeTeam,AwayTeam\n")

    monkeypatch.setattr("scraper.http.httpx.get", fake_get)
    fetch_fixtures_csv(Settings(football_data_min_delay_seconds=3.0))
    assert sleeps and 3.0 <= sleeps[0] <= 6.0
    assert urls[0][0] == "https://football-data.co.uk/fixtures.csv"
    assert "FantasyLaLigaStats" in urls[0][1]


@pytest.mark.parametrize("status", [403, 429])
def test_a_block_is_terminal(monkeypatch, status):
    from scraper.sources.football_data import fetch_fixtures_csv

    calls = []
    monkeypatch.setattr("scraper.http.time.sleep", lambda _: None)

    def fake_get(url, **kwargs):
        calls.append(url)
        return httpx.Response(status, text="no")

    monkeypatch.setattr("scraper.http.httpx.get", fake_get)
    with pytest.raises(ScrapeBlocked):
        fetch_fixtures_csv(Settings())
    assert len(calls) == 1


def test_backfill_cli_flag(engine, monkeypatch, capsys):
    from scraper import backfill
    from storage.db import set_engine

    set_engine(engine)
    _stub(monkeypatch, season=lambda *a, **k: _read("football-data-SP1-2526.csv"))
    monkeypatch.setattr("sys.argv", ["backfill", "--season", "2025", "--football-data"])
    assert backfill.main() == 0
    assert "football-data 2025: success, 380 matches" in capsys.readouterr().out
