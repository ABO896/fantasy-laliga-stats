"""The refresh stores expected points for the next jornada after every
dataset it depends on — and an xP failure never fails the scrape."""

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import Session, func, select

from scraper.run import run_daily_refresh
from storage.db import set_engine
from storage.models import DatasetRun, ExpectedPointsPrediction, PlayerSnapshot

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "puja-ideal-page1.html"
PHASE7 = Path(__file__).resolve().parent.parent / "fixtures" / "phase7"


@pytest.fixture(autouse=True)
def _stub_every_fetch(monkeypatch):
    def fixture(name):
        return lambda *a, **k: (PHASE7 / name).read_text(encoding="utf-8")

    monkeypatch.setattr("scraper.run.fetch_jornada", fixture("jornada-2026-latest.html"))
    monkeypatch.setattr("scraper.run.fetch_season_stats", fixture("estadisticas-2025.html"))
    monkeypatch.setattr("scraper.run.fetch_points_predictions", fixture("predicciones.html"))
    monkeypatch.setattr(
        "scraper.run.fetch_market_predictions", fixture("prediccion-de-mercado.html")
    )
    monkeypatch.setattr(
        "scraper.run.fetch_calendar",
        lambda *a, **k: (PHASE7.parent / "calendario-predictor.html").read_text(encoding="utf-8"),
    )
    external = PHASE7.parent / "external"
    season_csv = (external / "football-data-SP1-2627.csv").read_text(encoding="utf-8")
    fixtures_csv = (external / "football-data-fixtures-with-sp1.csv").read_text(encoding="utf-8")
    monkeypatch.setattr("scraper.external_ingest.fetch_season_csv", lambda *a, **k: season_csv)
    monkeypatch.setattr("scraper.external_ingest.fetch_fixtures_csv", lambda *a, **k: fixtures_csv)


def _xp_run(engine) -> DatasetRun:
    with Session(engine) as s:
        return s.exec(select(DatasetRun).where(DatasetRun.dataset == "expected_points")).one()


def test_a_refresh_stores_one_prediction_per_snapshot_player(engine):
    set_engine(engine)
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    with patch("scraper.run.fetch_pages", return_value=[html]):
        result = run_daily_refresh()

    assert result.status == "success"
    with Session(engine) as s:
        snapshots = s.exec(select(func.count()).select_from(PlayerSnapshot)).one()
        preds = s.exec(select(ExpectedPointsPrediction)).all()
    assert len(preds) == snapshots > 0
    assert len({p.jornada for p in preds}) == 1
    assert {p.basis for p in preds} <= {
        "form", "form+starter", "form+odds", "form+starter+odds", "no_fixture",
    }
    assert _xp_run(engine).status == "success"


def test_an_xp_failure_is_recorded_but_never_fails_the_scrape(engine):
    set_engine(engine)
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    with (
        patch("scraper.run.fetch_pages", return_value=[html]),
        patch("scraper.run.refresh_expected_points", side_effect=RuntimeError("boom")),
    ):
        result = run_daily_refresh()

    assert result.status == "success"
    xp_run = _xp_run(engine)
    assert xp_run.status == "failed"
    assert "RuntimeError: boom" in xp_run.errors
