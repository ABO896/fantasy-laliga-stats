"""A database behind the code says so, instead of failing page by page.

On 2026-10-11 the live DB sat at 0018 under code needing 0019: the verdict,
settings and transfers endpoints returned bare 500s. (The same happened for
13 days at 0008 in September.)"""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from api.app import app
from api.deps import get_db_session
from storage.db import set_engine
from storage.schema import schema_status
from tests.conftest import PROJECT_ROOT


def _engine_at(revision: str):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    with eng.connect() as connection:
        cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, revision)
    return eng


@pytest.fixture()
def behind():
    eng = _engine_at("0018")
    set_engine(eng)

    def override():
        with Session(eng) as s:
            yield s

    app.dependency_overrides[get_db_session] = override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, eng
    app.dependency_overrides.clear()
    eng.dispose()


def test_schema_status_at_head(engine):
    status = schema_status(engine)
    assert status.up_to_date is True
    assert status.current == status.head


def test_schema_status_behind():
    status = schema_status(_engine_at("0018"))
    assert status.up_to_date is False
    assert status.current == "0018"


def test_health_reports_the_schema_and_still_answers(behind):
    client, _ = behind
    body = client.get("/api/health").json()
    assert body["schema"] == {"current": "0018", "head": schema_status_head(), "upToDate": False}


def test_a_failing_endpoint_names_the_fix(behind):
    client, _ = behind
    r = client.get("/api/league-settings")
    assert r.status_code == 503
    assert "alembic upgrade head" in r.json()["detail"]


def test_the_cli_refuses_to_refresh_a_database_behind_the_code(behind, monkeypatch):
    from scraper import run as run_mod

    called = []
    monkeypatch.setattr(run_mod, "run_daily_refresh", lambda **k: called.append(k))
    assert run_mod.main([]) == 3
    assert called == []


def schema_status_head() -> str:
    from storage.schema import head_revision

    return head_revision()
