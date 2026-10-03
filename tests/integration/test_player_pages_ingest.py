"""`ingest_player_pages` — the per-player page dataset in each refresh mode.

The fetcher is always stubbed (`scraper.run.fetch_player_page`) with
synthetic HTML from `tests/scraper/player_page_html.py`; nothing here
reaches the network.
"""

from datetime import UTC, date, datetime, timedelta

from sqlmodel import select

from core.config import Settings
from scraper.errors import ScrapeBlocked, ScrapeNotPublished
from scraper.run import ingest_player_pages
from storage.models import (
    Player,
    PlayerMarketDaily,
    PlayerMatchStats,
    PlayerPageFetch,
    PlayerSnapshot,
    ScrapeRun,
    SquadMember,
)
from storage.repository import add_to_watchlist, get_dataset_runs
from tests.scraper.player_page_html import minimal_player_page

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)  # 14:00 Madrid, after the 08:00 update
SETTINGS = Settings(current_season_year=2026)


def _seed(session, n: int = 3) -> ScrapeRun:
    """`n` players, all in the latest market snapshot, none ever fetched."""
    run = ScrapeRun(started_at=NOW, status="running")
    session.add(run)
    session.commit()
    session.refresh(run)
    for pid in range(1, n + 1):
        session.add(
            Player(
                id=pid, external_id=f"player-{pid}", name=f"Player {pid}",
                team="Sevilla FC", position="DEL", created_at=NOW, updated_at=NOW,
            )
        )
    session.commit()
    for pid in range(1, n + 1):
        session.add(
            PlayerSnapshot(
                as_of=date(2026, 9, 2), player_id=pid, market_value=1_000_000, points=0,
                availability_status="available", raw_fields="{}", scrape_run_id=run.id,
            )
        )
    session.commit()
    return run


class _Fetcher:
    """Counts calls; `fail` maps a slug to the exception to raise for it."""

    def __init__(self, fail: dict | None = None):
        self.calls: list[str] = []
        self.fail = fail or {}

    def __call__(self, slug, settings=None):
        self.calls.append(slug)
        if slug in self.fail:
            raise self.fail[slug]
        return minimal_player_page(day="2026-09-02")


def _dataset(session, run):
    runs = [d for d in get_dataset_runs(session, run.id) if d.dataset == "player_pages"]
    return runs[0] if runs else None


def test_quick_mode_fetches_no_player_pages(session, monkeypatch):
    run = _seed(session)
    fetch = _Fetcher()
    monkeypatch.setattr("scraper.run.fetch_player_page", fetch)

    ingest_player_pages(session, run, SETTINGS, mode="quick", now=NOW)

    assert fetch.calls == []
    assert _dataset(session, run) is None


def test_mine_mode_fetches_only_squad_and_watchlist(session, monkeypatch):
    run = _seed(session)
    session.add(SquadMember(player_id=1, purchase_price=1_000_000, acquired_on=date(2026, 8, 1)))
    session.commit()
    add_to_watchlist(session, 3)
    fetch = _Fetcher()
    monkeypatch.setattr("scraper.run.fetch_player_page", fetch)

    ingest_player_pages(session, run, SETTINGS, mode="mine", now=NOW)

    assert sorted(fetch.calls) == ["player-1", "player-3"]
    assert _dataset(session, run).status == "success"


def test_mine_mode_with_no_squad_or_watchlist_is_an_empty_success(session, monkeypatch):
    run = _seed(session)
    fetch = _Fetcher()
    monkeypatch.setattr("scraper.run.fetch_player_page", fetch)

    ingest_player_pages(session, run, SETTINGS, mode="mine", now=NOW)

    assert fetch.calls == []
    ds = _dataset(session, run)
    assert ds.status == "success"
    assert ds.row_count == 0
    assert "no squad or watchlist players" in ds.errors


def test_complete_mode_fills_every_gap(session, monkeypatch):
    run = _seed(session)
    fetch = _Fetcher()
    monkeypatch.setattr("scraper.run.fetch_player_page", fetch)

    ingest_player_pages(session, run, SETTINGS, mode="complete", now=NOW)

    assert len(fetch.calls) == 3
    assert len(session.exec(select(PlayerMarketDaily)).all()) == 3
    assert len(session.exec(select(PlayerMatchStats)).all()) == 3
    fetches = session.exec(select(PlayerPageFetch)).all()
    assert len(fetches) == 3 and all(f.status == "ok" for f in fetches)
    ds = _dataset(session, run)
    assert ds.status == "success"
    assert ds.row_count == 6
    assert ds.season_year == 2026
    assert "fetched 3 of 3 due" in ds.errors


def test_a_bad_page_is_a_gap_not_a_failure(session, monkeypatch):
    run = _seed(session)
    fetch = _Fetcher(fail={"player-2": ScrapeNotPublished("404")})
    monkeypatch.setattr("scraper.run.fetch_player_page", fetch)

    ingest_player_pages(session, run, SETTINGS, mode="complete", now=NOW)

    assert len(fetch.calls) == 3
    ds = _dataset(session, run)
    assert ds.status == "success"
    assert ds.skipped_count == 1
    assert "player-2" in ds.errors
    assert session.get(PlayerPageFetch, 2).status == "gap"
    assert "ScrapeNotPublished" in session.get(PlayerPageFetch, 2).error


def test_an_unparseable_page_is_a_gap(session, monkeypatch):
    run = _seed(session, n=1)
    monkeypatch.setattr(
        "scraper.run.fetch_player_page", lambda slug, settings=None: "<html></html>"
    )

    ingest_player_pages(session, run, SETTINGS, mode="complete", now=NOW)

    ds = _dataset(session, run)
    assert ds.status == "success"
    assert ds.skipped_count == 1
    assert session.get(PlayerPageFetch, 1).status == "gap"


def test_blocked_stops_the_dataset(session, monkeypatch):
    run = _seed(session)
    fetch = _Fetcher(fail={"player-2": ScrapeBlocked("429")})
    monkeypatch.setattr("scraper.run.fetch_player_page", fetch)

    ingest_player_pages(session, run, SETTINGS, mode="complete", now=NOW)

    assert fetch.calls == ["player-1", "player-2"]
    ds = _dataset(session, run)
    assert ds.status == "failed"
    assert "ScrapeBlocked" in ds.errors
    assert ds.row_count == 2  # player 1's one day + one match
    assert {r.player_id for r in session.exec(select(PlayerMarketDaily)).all()} == {1}
    # The blocked player is not logged as fetched, so he stays first in line.
    assert session.get(PlayerPageFetch, 2) is None


def test_budget_stops_and_records_a_note(session, monkeypatch):
    run = _seed(session)
    fetch = _Fetcher()
    monkeypatch.setattr("scraper.run.fetch_player_page", fetch)
    capped = Settings(current_season_year=2026, player_pages_max_requests=2)

    ingest_player_pages(session, run, capped, mode="complete", now=NOW)

    assert fetch.calls == ["player-1", "player-2"]
    ds = _dataset(session, run)
    assert ds.status == "success"
    assert "budget reached" in ds.errors
    assert "fetched 2 of 3 due" in ds.errors

    fetch.calls.clear()
    ingest_player_pages(session, run, capped, mode="complete", now=NOW + timedelta(minutes=5))

    assert fetch.calls[0] == "player-3"


def _offline_refresh(monkeypatch, tmp_path) -> list[str]:
    """Stub every step of `run_daily_refresh` except the run bookkeeping;
    returns the list the stubbed `ingest_player_pages` appends its mode to."""
    seen: list[str] = []
    monkeypatch.setattr(
        "scraper.run.get_settings", lambda: Settings(raw_snapshot_root=str(tmp_path))
    )
    monkeypatch.setattr(
        "scraper.run.fetch_pages", lambda *a, **k: (_ for _ in ()).throw(ScrapeBlocked("403"))
    )
    for name in (
        "ingest_fixtures", "ingest_jornada_points", "ingest_season_stats",
        "ingest_points_predictions", "ingest_market_predictions", "ingest_football_data",
        "run_our_models", "run_expected_points",
    ):
        monkeypatch.setattr(f"scraper.run.{name}", lambda *a, **k: None)
    monkeypatch.setattr(
        "scraper.run.ingest_player_pages", lambda s, r, st, mode, now=None: seen.append(mode)
    )
    return seen


def test_refresh_stamps_its_mode_on_a_new_run(session, engine, monkeypatch, tmp_path):
    from scraper.run import run_daily_refresh
    from storage.db import set_engine

    set_engine(engine)
    seen = _offline_refresh(monkeypatch, tmp_path)

    result = run_daily_refresh(mode="complete")

    assert result.mode == "complete"
    assert seen == ["complete"]


def test_refresh_stamps_its_mode_on_a_reused_run(session, engine, monkeypatch, tmp_path):
    from scraper.run import run_daily_refresh
    from storage.db import set_engine

    set_engine(engine)
    seen = _offline_refresh(monkeypatch, tmp_path)
    started = ScrapeRun(started_at=NOW, status="running")
    session.add(started)
    session.commit()
    session.refresh(started)

    run_daily_refresh(run_id=started.id, mode="mine")

    session.expire_all()
    assert session.get(ScrapeRun, started.id).mode == "mine"
    assert seen == ["mine"]
