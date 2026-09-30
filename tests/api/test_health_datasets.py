"""`/api/health` reports each dataset's own outcome (INGEST Task 10).

One refresh now covers five datasets that fail independently. A single
run-level status is how a partial failure becomes invisible — the exact
condition that let the 2026-08-10 outage run eleven days unnoticed.
"""

from datetime import UTC, datetime

from storage.models import ScrapeRun
from storage.repository import finish_dataset_run, start_dataset_run


def _run(session):
    r = ScrapeRun(started_at=datetime.now(UTC), status="running")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def test_health_reports_each_dataset_separately(session, client):
    run = _run(session)
    ok = start_dataset_run(session, run.id, "season_stats")
    finish_dataset_run(session, ok, "success", row_count=702, skipped_count=17, season_year=2025)
    bad = start_dataset_run(session, run.id, "jornada_points")
    finish_dataset_run(session, bad, "failed", errors=["ScrapeBlocked: 429"])

    body = client.get("/api/health").json()
    datasets = {d["dataset"]: d for d in body["datasets"]}
    assert datasets["season_stats"]["status"] == "success"
    assert datasets["season_stats"]["seasonYear"] == 2025
    assert datasets["season_stats"]["skippedCount"] == 17
    assert datasets["jornada_points"]["status"] == "failed"
    assert datasets["jornada_points"]["errors"] == ["ScrapeBlocked: 429"]


def test_not_published_is_not_reported_as_a_failure(session, client):
    """A dataset the source has not published yet is a state, not an
    outage — it carries no errors to act on."""
    run = _run(session)
    d = start_dataset_run(session, run.id, "season_stats")
    finish_dataset_run(session, d, "not_published")

    body = client.get("/api/health").json()
    entry = next(x for x in body["datasets"] if x["dataset"] == "season_stats")
    assert entry["status"] == "not_published"
    assert entry["errors"] == []
