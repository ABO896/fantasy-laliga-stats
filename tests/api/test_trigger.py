"""POST /api/scrape/trigger — schedules the shared `run_daily_refresh`
pipeline via FastAPI BackgroundTasks, and refuses to start a second
concurrent scrape while one is already `running` (T-05-01, this plan's
flagged concurrency assumption)."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from sqlmodel import select

from storage.db import set_engine
from storage.models import ScrapeRun

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "puja-ideal-page1.html"
PHASE7_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "phase7"


def _phase7(name: str) -> str:
    return (PHASE7_FIXTURES / name).read_text(encoding="utf-8")


def test_trigger_schedules_run(client, session, engine):
    # `run_daily_refresh` also calls the four deep-ingestion fetchers
    # unconditionally now (Task 8) — stub them from committed fixtures so
    # this test, which runs the pipeline via BackgroundTasks, stays
    # offline exactly as it always was. See
    # tests/integration/test_scrape_pipeline.py's `_stub_deep_ingestion_fetchers`
    # for the same pattern.
    set_engine(engine)
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    with (
        patch("scraper.run.fetch_pages", return_value=[html]),
        patch("scraper.run.fetch_jornada", return_value=_phase7("jornada-2026-latest.html")),
        patch("scraper.run.fetch_season_stats", return_value=_phase7("estadisticas-2025.html")),
        patch("scraper.run.fetch_points_predictions", return_value=_phase7("predicciones.html")),
        patch(
            "scraper.run.fetch_market_predictions",
            return_value=_phase7("prediccion-de-mercado.html"),
        ),
        patch(
            "scraper.run.fetch_calendar",
            return_value=(PHASE7_FIXTURES.parent / "calendario-predictor.html").read_text(
                encoding="utf-8"
            ),
        ),
        patch("scraper.external_ingest.fetch_season_csv", return_value="Div,Date\n"),
        patch("scraper.external_ingest.fetch_fixtures_csv", return_value="Div,Date\n"),
    ):
        response = client.post("/api/scrape/trigger")

    assert response.status_code == 202
    run_id = response.json()["scrapeRunId"]
    assert isinstance(run_id, int)

    # TestClient runs BackgroundTasks synchronously before returning, so
    # the run has already reached a terminal status.
    run = session.get(ScrapeRun, run_id)
    session.refresh(run)
    assert run.status in ("success", "rejected", "failed")


def test_trigger_with_mode_schedules_run_daily_refresh_with_that_mode(client, session):
    """`?mode=complete` is stored on the started run row and forwarded to
    `run_daily_refresh` — mocked here so the test only checks the wiring,
    not the pipeline itself (that's `test_trigger_schedules_run` above)."""
    with patch("api.routes.health.run_daily_refresh") as mock_refresh:
        response = client.post("/api/scrape/trigger", params={"mode": "complete"})

    assert response.status_code == 202
    run_id = response.json()["scrapeRunId"]
    mock_refresh.assert_called_once_with(run_id=run_id, mode="complete")

    run = session.get(ScrapeRun, run_id)
    session.refresh(run)
    assert run.mode == "complete"


def test_trigger_rejects_unknown_mode(client):
    response = client.post("/api/scrape/trigger", params={"mode": "bogus"})
    assert response.status_code == 422


def test_trigger_is_single_flight(client, session):
    running = ScrapeRun(started_at=datetime.now(UTC), status="running")
    session.add(running)
    session.commit()
    session.refresh(running)

    response = client.post("/api/scrape/trigger")

    assert response.status_code == 409
    assert "detail" in response.json()

    # No second run was started — the only running run is still the one
    # seeded above.
    all_runs = session.exec(select(ScrapeRun)).all()
    assert len(all_runs) == 1
