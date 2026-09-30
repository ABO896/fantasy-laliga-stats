"""GET /api/health — staleness derived at request time from the most
recent *successful* run, never persisted as a stored flag (RESEARCH.md
Pattern 3, T-05-04).

Reworked 2026-08-22: staleness is now measured against the market's 00:15
Madrid update rather than a 30-hour elapsed threshold. The boundary cases
live in `tests/core/test_freshness.py`, which owns that rule; these tests
check the endpoint delegates to it and reports it, not the rule itself.
"""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from core.freshness import last_market_update
from storage.models import ScrapeRun


def _utc(moment):
    """SQLite drops `tzinfo`, so whatever is written is what comes back —
    naive, and read as UTC. Production only ever writes `datetime.now(UTC)`
    (`storage.repository.start_run`); storing a Madrid-aware value here would
    silently persist a Madrid wall clock and shift every assertion two hours
    in summer. Normalising in the helper keeps the convention impossible to
    break from a test."""
    return moment.astimezone(UTC) if moment is not None else None


def _make_run(session: Session, *, status: str, started_at, finished_at=None, row_count=0):
    run = ScrapeRun(
        started_at=_utc(started_at),
        finished_at=_utc(finished_at),
        status=status,
        row_count=row_count,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def test_stale_when_the_last_scrape_predates_the_market_update(client, session):
    """The case the old elapsed-hours threshold got wrong: a scrape only
    hours old, but from before the market moved."""
    before_update = last_market_update(datetime.now(UTC)) - timedelta(minutes=1)
    _make_run(
        session,
        status="success",
        started_at=before_update,
        finished_at=before_update + timedelta(minutes=5),
        row_count=342,
    )
    assert client.get("/api/health").json()["isStale"] is True


def test_fresh_when_the_last_scrape_followed_the_market_update(client, session):
    after_update = last_market_update(datetime.now(UTC)) + timedelta(minutes=1)
    _make_run(
        session,
        status="success",
        started_at=after_update,
        finished_at=after_update + timedelta(minutes=5),
        row_count=342,
    )
    assert client.get("/api/health").json()["isStale"] is False


def test_reports_the_market_update_it_judged_against(client, session):
    """The UI says *why* data is stale, so the instant has to be on the wire
    rather than recomputed in the browser against a different clock."""
    body = client.get("/api/health").json()
    assert body["marketUpdatedAt"] == last_market_update(datetime.now(UTC)).isoformat()


def test_elapsed_hours_is_reported_but_never_decides(client, session):
    """A scrape from well over a day ago that still follows the most recent
    update is fresh — proof that `hoursSinceLastSuccess` is display only."""
    after_update = last_market_update(datetime.now(UTC)) + timedelta(minutes=1)
    _make_run(
        session,
        status="success",
        started_at=after_update,
        finished_at=after_update + timedelta(minutes=5),
        row_count=342,
    )
    body = client.get("/api/health").json()
    assert body["isStale"] is False
    assert body["hoursSinceLastSuccess"] is not None


def test_no_successful_run_is_stale(client):
    body = client.get("/api/health").json()
    assert body["isStale"] is True
    assert body["lastSuccessfulRun"] is None
    assert body["hoursSinceLastSuccess"] is None


def test_last_successful_ignores_later_failures(client, session):
    now = datetime.now(UTC)
    success = _make_run(
        session,
        status="success",
        started_at=now - timedelta(hours=5, minutes=5),
        finished_at=now - timedelta(hours=5),
        row_count=342,
    )
    rejected = _make_run(
        session,
        status="rejected",
        started_at=now - timedelta(hours=1, minutes=5),
        finished_at=now - timedelta(hours=1),
        row_count=10,
    )

    body = client.get("/api/health").json()

    assert body["lastSuccessfulRun"]["id"] == success.id
    assert body["recentRuns"][0]["id"] == rejected.id


def test_recent_runs_ordering_and_limit(client, session):
    now = datetime.now(UTC)
    runs = [
        _make_run(
            session,
            status="success",
            started_at=now - timedelta(hours=i),
            finished_at=now - timedelta(hours=i) + timedelta(minutes=1),
            row_count=342,
        )
        for i in range(12)
    ]

    body = client.get("/api/health").json()

    assert len(body["recentRuns"]) == 10
    expected_ids = [run.id for run in runs[:10]]
    assert [r["id"] for r in body["recentRuns"]] == expected_ids


def test_no_stored_staleness_flag(client, session):
    after_update = last_market_update(datetime.now(UTC)) + timedelta(minutes=1)
    run = _make_run(
        session,
        status="success",
        started_at=after_update,
        finished_at=after_update + timedelta(minutes=5),
        row_count=342,
    )

    assert client.get("/api/health").json()["isStale"] is False

    # No is_stale column exists to flip — move the same run's `started_at`
    # back across the market update and the response follows, derived fresh
    # on every request.
    run.started_at = _utc(last_market_update(datetime.now(UTC)) - timedelta(minutes=1))
    session.add(run)
    session.commit()

    assert client.get("/api/health").json()["isStale"] is True
