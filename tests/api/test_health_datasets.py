"""`/api/health` reports each dataset's own outcome (INGEST Task 10).

One refresh now covers five datasets that fail independently. A single
run-level status is how a partial failure becomes invisible — the exact
condition that let the 2026-08-10 outage run eleven days unnoticed.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from core.config import get_settings
from core.player_pages import expected_last_day
from storage.models import Player, PlayerMarketDaily, PlayerSnapshot, ScrapeRun
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


def _player(session, external_id="p1"):
    now = datetime.now(UTC)
    p = Player(
        external_id=external_id,
        name="Test Player",
        team="RMA",
        position="DEL",
        created_at=now,
        updated_at=now,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_health_suggests_complete_refresh_on_an_empty_db(client):
    """No complete run has ever succeeded, so there is nothing to trust —
    `suggestComplete` must say so even though there are zero tracked
    players yet (T-05 interface)."""
    body = client.get("/api/health").json()
    assert body["lastCompleteRun"] is None
    assert body["suggestComplete"] is True
    assert body["playerPages"] == {
        "players": 0,
        "complete": 0,
        "withGaps": 0,
        "oldestLastDay": None,
    }


def test_health_does_not_suggest_complete_after_a_recent_full_coverage_run(session, client):
    """A `complete` run that just finished, with every tracked player's
    page already current, means there is nothing more a complete refresh
    would fix right now."""
    settings = get_settings()
    now = datetime.now(UTC)
    complete_run = ScrapeRun(
        started_at=now - timedelta(minutes=5),
        finished_at=now - timedelta(minutes=1),
        status="success",
        mode="complete",
    )
    session.add(complete_run)
    session.commit()
    session.refresh(complete_run)

    player = _player(session)
    today = now.date()
    session.add(
        PlayerSnapshot(
            as_of=today,
            player_id=player.id,
            market_value=1_000_000,
            points=0,
            availability_status="available",
            raw_fields="{}",
            scrape_run_id=complete_run.id,
        )
    )
    now_local = now.astimezone(ZoneInfo("Europe/Madrid"))
    expected = expected_last_day(now_local, settings.market_update_hour)
    session.add(
        PlayerMarketDaily(
            season_year=settings.current_season_year,
            day=expected,
            player_id=player.id,
            market_value=1_000_000,
            scrape_run_id=complete_run.id,
        )
    )
    session.commit()

    body = client.get("/api/health").json()
    assert body["lastCompleteRun"]["id"] == complete_run.id
    assert body["lastCompleteRun"]["mode"] == "complete"
    assert body["playerPages"] == {
        "players": 1,
        "complete": 1,
        "withGaps": 0,
        "oldestLastDay": expected.isoformat(),
    }
    assert body["suggestComplete"] is False
