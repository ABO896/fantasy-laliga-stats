"""Shared pytest fixtures.

Schema creation goes through Alembic migrations — never a direct SQLModel
table-creation call — so the same migration path used in production is
exercised on every test run. A single in-memory SQLite connection is shared
(via `StaticPool`) between the migration run and the test session/client so
the tables created by `alembic upgrade head` are visible to the rest of the
test.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from api.app import app
from api.deps import get_db_session

PROJECT_ROOT = Path(__file__).resolve().parent.parent

FIXTURES_DIR = (Path(__file__).parent / "fixtures").resolve()


def _missing_fixture(exc: BaseException | None) -> str | None:
    """The missing file's path if `exc` (or anything it chains from) is a
    `FileNotFoundError` for a file under `tests/fixtures/`, else `None`."""
    while exc is not None:
        if isinstance(exc, FileNotFoundError) and exc.filename:
            path = Path(exc.filename).resolve()
            if path.is_relative_to(FIXTURES_DIR):
                return str(path.relative_to(FIXTURES_DIR))
        exc = exc.__cause__ or exc.__context__
    return None


def _skip_on_missing_fixture():
    try:
        return (yield)
    except Exception as exc:
        missing = _missing_fixture(exc)
        if missing is not None:
            pytest.skip(
                f"captured page tests/fixtures/{missing} is not in the repo "
                "— see tests/fixtures/README.md"
            )
        raise


# Captured third-party pages are not redistributed with the repo, so a fresh
# clone lacks them. A test that needs one is skipped with the reason rather
# than erroring; a local install with the pages captured runs everything.
@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    return (yield from _skip_on_missing_fixture())


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    return (yield from _skip_on_missing_fixture())


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.connect() as connection:
        alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture()
def client(engine):
    def override_get_db_session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def season_stats_row():
    """Factory for a `PlayerSeasonStats` with every statistic column zeroed.

    Pass only the fields the test cares about, plus the three that have no
    sensible default: `season_year`, `player_id`, `scrape_run_id`.
    """
    from core.season_stats_schema import STAT_PAIRS, column_name
    from storage.models import PlayerSeasonStats

    def _make(**overrides) -> PlayerSeasonStats:
        fields: dict = {
            "matches_played": 0,
            "total_points": 0,
            "average_points": 0.0,
            "market_value": 0,
            "raw_fields": "{}",
        }
        for counter, points_field in STAT_PAIRS:
            fields[column_name(counter)] = 0
            fields[column_name(points_field)] = 0
        fields.update(overrides)
        return PlayerSeasonStats(**fields)

    return _make


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Fail loudly if any test reaches the network.

    The suite fetches nothing: scrapers are stubbed and parsers run against
    committed fixtures. Without this guard, forgetting one stub means a test
    silently hits the live site instead of failing — which is exactly how
    five pipeline tests would have started scraping production the moment
    the refresh grew from one dataset to five.
    """

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "A test attempted a real network request. Stub the fetcher instead "
            "— see tests/integration/test_multi_dataset_refresh.py for the pattern."
        )

    # Two patches cover the two ways this codebase ever leaves the process —
    # this is NOT "the whole real-egress surface" from `httpx.get` alone;
    # an earlier version of this docstring claimed that and was wrong.
    #
    # 1. `httpx.get` — `scraper/http.py`'s `_get` is the only httpx-based
    #    production call site (verified: no other `httpx.Client`/`AsyncClient`
    #    use anywhere in this codebase), and `httpx.get()` itself opens an
    #    ephemeral `Client` and calls `Client.request` internally, so this one
    #    patch already covers it. Patching `httpx.Client.request` directly, as
    #    an earlier draft of this guard did, also intercepts FastAPI's
    #    `TestClient` — it subclasses `httpx.Client` and never overrides
    #    `request`, so every `client.get(...)` call in the API test suite
    #    (in-process ASGI transport, no socket ever opened) was caught by the
    #    same patch and failed with this same "real network request" message.
    #    That broke 50 previously-passing tests across tests/api/ and
    #    test_tracer_pipeline.py — a false positive, not a network reach, so
    #    only `httpx.get` is patched here.
    # 2. `scraper.sources.analiticafantasy.sync_playwright` — the market
    #    fetcher (`fetch_pages`, the very path that motivated this guard)
    #    does not use httpx at all; it drives a real Chromium via
    #    `sync_playwright()` (see `scraper/http.py`'s own docstring: "The
    #    Playwright path ... keeps its own `_goto` because a browser
    #    navigation is a different operation"). Patched in
    #    `analiticafantasy`'s own namespace, not `playwright.sync_api`'s,
    #    because it's a module-level `from ... import` there — patching the
    #    origin module wouldn't rebind the name already imported into
    #    `analiticafantasy`.
    monkeypatch.setattr("httpx.get", _blocked)
    monkeypatch.setattr("scraper.sources.analiticafantasy.sync_playwright", _blocked)
