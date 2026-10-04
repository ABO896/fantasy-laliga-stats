"""`/api/health` reports each dataset's own outcome (INGEST Task 10).

One refresh now covers five datasets that fail independently. A single
run-level status is how a partial failure becomes invisible — the exact
condition that let the 2026-08-10 outage run eleven days unnoticed.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import select

from core.config import get_settings
from core.player_pages import expected_last_day
from storage.models import (
    Player,
    PlayerMarketDaily,
    PlayerPageFetch,
    PlayerSnapshot,
    ScrapeRun,
)
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
        "withMatchGaps": 0,
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
    session.add(PlayerPageFetch(player_id=player.id, fetched_at=now, status="ok"))
    session.commit()

    body = client.get("/api/health").json()
    assert body["lastCompleteRun"]["id"] == complete_run.id
    assert body["lastCompleteRun"]["mode"] == "complete"
    assert body["playerPages"] == {
        "players": 1,
        "complete": 1,
        "withGaps": 0,
        "withMatchGaps": 0,
        "oldestLastDay": expected.isoformat(),
    }
    assert body["suggestComplete"] is False


def _recent_complete_run_with_one_player(session, last_day, fetched: bool):
    now = datetime.now(UTC)
    run = ScrapeRun(
        started_at=now - timedelta(minutes=5), finished_at=now - timedelta(minutes=1),
        status="success", mode="complete",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    player = _player(session)
    session.add(
        PlayerSnapshot(
            as_of=now.date(), player_id=player.id, market_value=1_000_000, points=0,
            availability_status="available", raw_fields="{}", scrape_run_id=run.id,
        )
    )
    session.add(
        PlayerMarketDaily(
            season_year=get_settings().current_season_year, day=last_day,
            player_id=player.id, market_value=1_000_000, scrape_run_id=run.id,
        )
    )
    if fetched:
        session.add(PlayerPageFetch(player_id=player.id, fetched_at=now, status="ok"))
    session.commit()


def _after_update_hour(monkeypatch):
    """Pin the market update hour to midnight so it is always past it:
    `expected` is today (Madrid) and yesterday is a one-day lag."""
    settings = get_settings().model_copy(update={"market_update_hour": 0})
    monkeypatch.setattr("api.routes.health.get_settings", lambda: settings)
    return datetime.now(UTC).astimezone(ZoneInfo("Europe/Madrid")).date()


def test_a_one_day_price_lag_alone_does_not_suggest_complete(session, client, monkeypatch):
    """Every morning after the market update each player is one day behind
    until the next fetch. That lag shows in `withGaps` but must not nag:
    with a recent complete run and no match gaps, no suggestion."""
    today = _after_update_hour(monkeypatch)
    _recent_complete_run_with_one_player(session, today - timedelta(days=1), fetched=True)

    body = client.get("/api/health").json()
    assert body["playerPages"]["withGaps"] == 1
    assert body["playerPages"]["withMatchGaps"] == 0
    assert body["suggestComplete"] is False


def test_a_never_fetched_player_suggests_complete(session, client, monkeypatch):
    today = _after_update_hour(monkeypatch)
    _recent_complete_run_with_one_player(session, today, fetched=False)

    body = client.get("/api/health").json()
    assert body["playerPages"]["withMatchGaps"] == 1
    assert body["suggestComplete"] is True


def test_an_old_complete_run_suggests_complete(session, client, monkeypatch):
    today = _after_update_hour(monkeypatch)
    _recent_complete_run_with_one_player(session, today, fetched=True)
    old = session.exec(select(ScrapeRun)).one()
    old.started_at = datetime.now(UTC) - timedelta(
        days=get_settings().complete_refresh_stale_days + 1
    )
    session.add(old)
    session.commit()

    body = client.get("/api/health").json()
    assert body["playerPages"]["withMatchGaps"] == 0
    assert body["suggestComplete"] is True
