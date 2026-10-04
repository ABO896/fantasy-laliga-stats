"""GET /api/health — scrape freshness derived at request time from the
most recent *successful* `ScrapeRun`, never a stored flag (RESEARCH.md
Pattern 3). A stored or startup-computed value would be a second source
of truth that can drift from `ScrapeRun`, and a long-running server would
otherwise keep serving a staleness verdict computed hours earlier.

POST /api/scrape/trigger schedules `run_daily_refresh` (`scraper/run.py`)
via FastAPI `BackgroundTasks` — the same entrypoint `python -m scraper.run`
calls, never a duplicated pipeline. Since Phase 13 removed the scheduled
agent, this and `make scrape` are the *only* ways a scrape starts.

`has_running_run` guards it so a click while a run is already `running`
refuses with 409 rather than starting a second concurrent scrape (T-05-01).
That guard is about concurrency, not frequency: `docs/SCRAPING-POLICY.md`
dropped its once-per-day limit on 2026-08-22, and requests stay sequential
within a run.

`mode` (`?mode=quick|mine|complete`, default `quick`) is stamped on the
started run row before scheduling, so `ScrapeRun.mode` always reflects what
was actually requested even though the pipeline runs in the background.
`GET /api/health`'s `playerPages` (from `storage.player_pages.coverage`)
and `suggestComplete` let the owner judge whether a `complete` refresh is
worth running, without having to reason about `ScrapeRun`/mode history
themselves.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.deps import SessionDep
from core.config import get_settings
from core.freshness import is_stale, last_market_update
from core.player_pages import expected_last_day
from scraper.run import run_daily_refresh
from storage.db import as_utc
from storage.models import DatasetRun, ScrapeRun
from storage.player_pages import coverage
from storage.repository import (
    get_last_successful_run,
    get_recent_runs,
    has_running_run,
    latest_dataset_runs,
    start_run,
)

router = APIRouter()

MADRID = ZoneInfo("Europe/Madrid")


def _run_to_dto(run: ScrapeRun) -> dict:
    errors = json.loads(run.validation_errors) if run.validation_errors else []
    return {
        "id": run.id,
        "startedAt": run.started_at.isoformat(),
        "finishedAt": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "rowCount": run.row_count,
        "validationErrors": errors,
        "mode": run.mode,
    }


def _dataset_to_dto(dataset_run: DatasetRun) -> dict:
    """One dataset's own outcome. `errors` is `None` when there is nothing
    to act on — `not_published` is a state, not a failure — and flattens to
    `[]` rather than `null` so the panel has one shape to render."""
    errors = json.loads(dataset_run.errors) if dataset_run.errors else []
    return {
        "dataset": dataset_run.dataset,
        "status": dataset_run.status,
        "rowCount": dataset_run.row_count,
        "skippedCount": dataset_run.skipped_count,
        "seasonYear": dataset_run.season_year,
        "finishedAt": dataset_run.finished_at.isoformat() if dataset_run.finished_at else None,
        "errors": errors,
    }


@router.get("/health")
def get_health(session: SessionDep):
    settings = get_settings()
    last_success = get_last_successful_run(session)
    last_complete_run = get_last_successful_run(session, mode="complete")
    recent_runs = get_recent_runs(session, limit=10)

    now = datetime.now(UTC)
    market_updated_at = last_market_update(now)

    # Staleness is the market's question, not the clock's — see
    # `core.freshness`. `hours_since_last_success` stays purely as something
    # to show the owner; nothing branches on it.
    stale = is_stale(last_success.started_at if last_success else None, now)

    hours_since_last_success = None
    if last_success is not None and last_success.finished_at is not None:
        finished_at = as_utc(last_success.finished_at)
        hours_since_last_success = (now - finished_at).total_seconds() / 3600

    now_local = now.astimezone(MADRID)
    expected = expected_last_day(now_local, settings.market_update_hour)
    page_coverage = coverage(session, settings.current_season_year, expected, now)
    player_pages = {
        **page_coverage,
        "oldestLastDay": (
            page_coverage["oldestLastDay"].isoformat()
            if page_coverage["oldestLastDay"] is not None
            else None
        ),
    }

    # Nothing to trust yet, the last complete run is too old to still
    # reflect reality, or some player was never fetched or is missing a
    # finished week's match — any one is reason enough to suggest a complete
    # refresh. `withGaps` deliberately plays no part: it also counts the
    # ordinary one-day price lag every morning, which a complete refresh
    # is not needed for and must not nag about.
    stale_complete = last_complete_run is None or as_utc(
        last_complete_run.started_at
    ) < now - timedelta(days=settings.complete_refresh_stale_days)
    suggest_complete = stale_complete or page_coverage["withMatchGaps"] > 0

    return {
        "lastSuccessfulRun": _run_to_dto(last_success) if last_success else None,
        "lastCompleteRun": _run_to_dto(last_complete_run) if last_complete_run else None,
        "isStale": stale,
        "hoursSinceLastSuccess": hours_since_last_success,
        "marketUpdatedAt": market_updated_at.isoformat(),
        "recentRuns": [_run_to_dto(run) for run in recent_runs],
        "datasets": [_dataset_to_dto(d) for d in latest_dataset_runs(session).values()],
        "playerPages": player_pages,
        "suggestComplete": suggest_complete,
    }


@router.post("/scrape/trigger", status_code=202)
def trigger_scrape(
    session: SessionDep,
    background_tasks: BackgroundTasks,
    mode: Literal["quick", "mine", "complete"] = "quick",
):
    if has_running_run(session):
        raise HTTPException(status_code=409, detail="A scrape is already running")

    run = start_run(session)
    run.mode = mode
    session.add(run)
    session.commit()
    background_tasks.add_task(run_daily_refresh, run_id=run.id, mode=mode)
    return {"scrapeRunId": run.id}
