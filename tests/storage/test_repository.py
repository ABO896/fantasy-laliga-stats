"""Tests for `purge_old_raw_scrapes` — the one deletion this system
performs, scoped to staging `RawScrape` data (DB rows + on-disk HTML)
only. Must never reference `player_snapshots`.
"""

from datetime import UTC, date, datetime, timedelta

from core.config import Settings
from storage.models import (
    Player,
    PlayerGameweekPoints,
    PlayerSnapshot,
    RawScrape,
    ScrapeRun,
    SourcePrediction,
    SquadMember,
)
from storage.repository import (
    get_gameweek_points,
    get_latest_predictions,
    get_player,
    get_season_stats,
    get_season_week_ranges,
    get_snapshot_history,
    get_squad_membership,
    purge_old_raw_scrapes,
)


def _seed_run_with_raw_scrape(session, tmp_path, *, days_old: int) -> tuple[ScrapeRun, RawScrape]:
    fetched_at = datetime.now(UTC) - timedelta(days=days_old)

    run = ScrapeRun(
        started_at=fetched_at,
        finished_at=fetched_at,
        status="success",
        row_count=1,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    run_dir = tmp_path / f"run_{run.id}"
    run_dir.mkdir()
    (run_dir / "page_1.html").write_text("<html></html>", encoding="utf-8")
    run.raw_snapshot_dir = str(run_dir)
    session.add(run)
    session.commit()

    raw_scrape = RawScrape(
        scrape_run_id=run.id,
        page_number=1,
        fetched_at=fetched_at,
        html="<html></html>",
    )
    session.add(raw_scrape)
    session.commit()
    session.refresh(raw_scrape)
    return run, raw_scrape


def test_purge_deletes_rows_and_dirs_past_retention_window(session, tmp_path):
    settings = Settings(raw_retention_days=7)

    old_run, old_scrape = _seed_run_with_raw_scrape(session, tmp_path, days_old=8)
    recent_run, recent_scrape = _seed_run_with_raw_scrape(session, tmp_path, days_old=6)

    deleted_count = purge_old_raw_scrapes(session, settings)

    assert deleted_count == 1
    assert session.get(RawScrape, old_scrape.id) is None
    assert session.get(RawScrape, recent_scrape.id) is not None

    assert not (tmp_path / f"run_{old_run.id}").exists()
    assert (tmp_path / f"run_{recent_run.id}").exists()


def test_purge_retains_recent_and_is_a_noop_when_nothing_is_stale(session, tmp_path):
    settings = Settings(raw_retention_days=7)
    _seed_run_with_raw_scrape(session, tmp_path, days_old=1)

    deleted_count = purge_old_raw_scrapes(session, settings)

    assert deleted_count == 0


def _detail_player(session, slug="p-1"):
    now = datetime.now(UTC)
    p = Player(
        external_id=slug, name=slug, team="T", position="MED", created_at=now, updated_at=now
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _detail_run(session):
    r = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _snapshot(session, player_id, run_id, as_of, market_value):
    session.add(
        PlayerSnapshot(
            as_of=as_of,
            player_id=player_id,
            market_value=market_value,
            points=0,
            availability_status="available",
            raw_fields="{}",
            scrape_run_id=run_id,
        )
    )
    session.commit()


def test_get_player_returns_none_for_an_unknown_id(session):
    assert get_player(session, 999) is None


def test_snapshot_history_is_ascending_by_date(session):
    p = _detail_player(session)
    run = _detail_run(session)
    _snapshot(session, p.id, run.id, date(2026, 8, 8), 200)
    _snapshot(session, p.id, run.id, date(2026, 8, 6), 100)

    history = get_snapshot_history(session, p.id)

    assert [s.as_of for s in history] == [date(2026, 8, 6), date(2026, 8, 8)]


def test_snapshot_history_excludes_other_players(session):
    a = _detail_player(session, "a")
    b = _detail_player(session, "b")
    run = _detail_run(session)
    _snapshot(session, a.id, run.id, date(2026, 8, 6), 100)
    _snapshot(session, b.id, run.id, date(2026, 8, 6), 999)

    assert [s.market_value for s in get_snapshot_history(session, a.id)] == [100]


def test_gameweek_points_are_ordered_by_season_then_week(session):
    p = _detail_player(session)
    run = _detail_run(session)
    for season, week in [(2026, 2), (2025, 38), (2026, 1), (2025, 1)]:
        session.add(
            PlayerGameweekPoints(
                season_year=season, week=week, player_id=p.id, points=1, scrape_run_id=run.id
            )
        )
    session.commit()

    rows = get_gameweek_points(session, p.id)

    assert [(r.season_year, r.week) for r in rows] == [(2025, 1), (2025, 38), (2026, 1), (2026, 2)]


def test_season_stats_are_ordered_by_season(session, season_stats_row):
    p = _detail_player(session)
    run = _detail_run(session)
    for season in (2026, 2025):
        session.add(season_stats_row(season_year=season, player_id=p.id, scrape_run_id=run.id))
    session.commit()

    assert [r.season_year for r in get_season_stats(session, p.id)] == [2025, 2026]


def test_a_sold_member_is_not_current_membership(session):
    p = _detail_player(session)
    session.add(
        SquadMember(
            player_id=p.id,
            purchase_price=100,
            acquired_on=date(2026, 8, 6),
            sale_price=150,
            sold_at=datetime.now(UTC),
        )
    )
    session.commit()

    assert get_squad_membership(session, p.id) is None


def test_an_unsold_member_is_current_membership(session):
    p = _detail_player(session)
    session.add(SquadMember(player_id=p.id, purchase_price=100, acquired_on=date(2026, 8, 6)))
    session.commit()

    assert get_squad_membership(session, p.id).purchase_price == 100


def test_predictions_take_the_latest_date_per_source(session):
    p = _detail_player(session)
    run = _detail_run(session)
    for as_of, value in [(date(2026, 8, 26), 1.0), (date(2026, 8, 27), 2.0)]:
        session.add(
            SourcePrediction(
                as_of=as_of,
                source="points",
                player_id=p.id,
                value=value,
                raw_fields="{}",
                scrape_run_id=run.id,
            )
        )
    session.commit()

    assert get_latest_predictions(session, p.id) == {"points": 2.0}


def test_predictions_are_empty_when_the_player_has_none(session):
    p = _detail_player(session)
    assert get_latest_predictions(session, p.id) == {}


def test_season_week_ranges_report_the_highest_week_per_season(session):
    p = _detail_player(session)
    run = _detail_run(session)
    for season, week in [(2025, 1), (2025, 38), (2026, 1), (2026, 2)]:
        session.add(
            PlayerGameweekPoints(
                season_year=season, week=week, player_id=p.id, points=1, scrape_run_id=run.id
            )
        )
    session.commit()

    assert get_season_week_ranges(session) == {2025: 38, 2026: 2}
