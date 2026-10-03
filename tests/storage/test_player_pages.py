"""storage/player_pages.py — tables, upsert and candidate selection for the
player-page scraper (per-player daily market values and per-jornada match
stats)."""

import json
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlmodel import select

from scraper.sources.af_player_page import DailyValue, MatchRow, PlayerPage
from storage.models import (
    Player,
    PlayerGameweekPoints,
    PlayerMarketDaily,
    PlayerMatchStats,
    PlayerSnapshot,
    ScrapeRun,
    SquadMember,
)
from storage.player_pages import (
    build_candidates,
    coverage,
    my_player_ids,
    record_fetch,
    upsert_player_page,
)
from storage.repository import add_to_watchlist
from tests.storage.helpers import seed_fixture

SEASON = 2026


def make_player(session, player_id: int, team: str = "Sevilla FC") -> Player:
    now = datetime.now(UTC)
    p = Player(
        id=player_id, external_id=f"ext-{player_id}", name=f"Player {player_id}",
        team=team, position="DEL", created_at=now, updated_at=now,
    )
    session.add(p)
    session.commit()
    return p


def make_run(session) -> ScrapeRun:
    r = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def test_upsert_is_idempotent_and_overwrites_values(session):
    make_player(session, 1)
    run = make_run(session)
    page = PlayerPage(
        market=[DailyValue(day=date(2026, 9, 1), market_value=1_000_000, delta=None)],
        matches=[],
    )
    upsert_player_page(session, SEASON, 1, page, run.id)

    updated = PlayerPage(
        market=[DailyValue(day=date(2026, 9, 1), market_value=1_200_000, delta=200_000)],
        matches=[],
    )
    days_written, matches_written = upsert_player_page(session, SEASON, 1, updated, run.id)

    rows = session.exec(select(PlayerMarketDaily)).all()
    assert len(rows) == 1
    assert rows[0].market_value == 1_200_000
    assert rows[0].delta == 200_000
    assert days_written == 1
    assert matches_written == 0


def test_upsert_never_deletes_existing_days(session):
    make_player(session, 1)
    run = make_run(session)
    full = PlayerPage(
        market=[
            DailyValue(day=date(2026, 9, 1), market_value=1_000_000, delta=None),
            DailyValue(day=date(2026, 9, 2), market_value=1_010_000, delta=10_000),
            DailyValue(day=date(2026, 9, 3), market_value=1_020_000, delta=10_000),
        ],
        matches=[],
    )
    upsert_player_page(session, SEASON, 1, full, run.id)

    partial = PlayerPage(
        market=[
            DailyValue(day=date(2026, 9, 2), market_value=1_015_000, delta=5_000),
            DailyValue(day=date(2026, 9, 3), market_value=1_025_000, delta=5_000),
        ],
        matches=[],
    )
    upsert_player_page(session, SEASON, 1, partial, run.id)

    rows = session.exec(select(PlayerMarketDaily)).all()
    assert len(rows) == 3
    by_day = {r.day: r.market_value for r in rows}
    assert by_day[date(2026, 9, 1)] == 1_000_000
    assert by_day[date(2026, 9, 2)] == 1_015_000
    assert by_day[date(2026, 9, 3)] == 1_025_000


def test_match_rows_record_appearance(session):
    make_player(session, 1)
    run = make_run(session)
    page = PlayerPage(
        market=[],
        matches=[
            MatchRow(week=1, minutes=90, points=10, components={"goals": 1}),
            MatchRow(week=2, minutes=30, points=2, components={}),
            MatchRow(week=3, minutes=0, points=0, components={}),
        ],
    )
    days_written, matches_written = upsert_player_page(session, SEASON, 1, page, run.id)

    rows = {r.week: r for r in session.exec(select(PlayerMatchStats)).all()}
    assert rows[1].appearance == "start"
    assert rows[2].appearance == "sub"
    assert rows[3].appearance == "dnp"
    assert json.loads(rows[1].components) == {"goals": 1}
    assert days_written == 0
    assert matches_written == 3


def test_candidates_flag_a_missing_finished_week(session):
    run = make_run(session)
    for pid in range(1, 6):
        make_player(session, pid, team="Sevilla FC")

    for pid in range(1, 6):
        session.add(
            PlayerGameweekPoints(
                season_year=SEASON, week=1, player_id=pid, points=5,
                is_provisional=False, scrape_run_id=run.id,
            )
        )
    session.commit()

    # Week 1's calendar is over: >= MIN_FINAL_FIXTURES final fixtures, none live.
    for fid in range(1, 9):
        seed_fixture(
            session, fid, matchday=1, kickoff=datetime(2026, 8, 20, tzinfo=UTC),
            final=True, season_year=SEASON,
        )

    now = datetime(2026, 9, 1, tzinfo=UTC)
    candidates = build_candidates(session, SEASON, now, [1])
    assert len(candidates) == 1
    assert candidates[0].player_id == 1
    assert candidates[0].missing_weeks == frozenset({1})


def _snapshot(session, run, pid, as_of):
    session.add(
        PlayerSnapshot(
            as_of=as_of, player_id=pid, market_value=1_000_000, points=0,
            availability_status="available", raw_fields="{}", scrape_run_id=run.id,
        )
    )


def _daily(session, run, pid, day):
    session.add(
        PlayerMarketDaily(
            season_year=SEASON, day=day, player_id=pid, market_value=1_000_000,
            delta=None, scrape_run_id=run.id,
        )
    )


def test_coverage_counts_complete_and_gapped(session):
    """One player complete (fresh day, no gap), one with a stale last day,
    one fresh but missing a finished week — only the first counts as
    complete; the weekly-sweep interval plays no part in either."""
    run = make_run(session)
    expected = date(2026, 9, 5)
    now = datetime(2026, 9, 10, tzinfo=UTC)

    make_player(session, 1, team="Getafe")  # complete
    make_player(session, 2, team="Getafe")  # stale last day
    make_player(session, 3, team="Sevilla FC")  # missing finished week
    for pid in (4, 5, 6, 7):
        make_player(session, pid, team="Sevilla FC")

    latest_as_of = date(2026, 9, 7)
    for pid in (1, 2, 3):
        _snapshot(session, run, pid, latest_as_of)
    session.commit()

    _daily(session, run, 1, date(2026, 9, 5))  # == expected: fresh
    _daily(session, run, 2, date(2026, 9, 1))  # < expected: stale
    _daily(session, run, 3, date(2026, 9, 6))  # > expected: fresh
    session.commit()

    # Sevilla FC's week 1 is covered by >= MIN_TEAM_ROWS players (3..7), so
    # the club "played" it, but player 3 never got a PlayerMatchStats row.
    for pid in (3, 4, 5, 6, 7):
        session.add(
            PlayerGameweekPoints(
                season_year=SEASON, week=1, player_id=pid, points=5,
                is_provisional=False, scrape_run_id=run.id,
            )
        )
    session.commit()

    for fid in range(1, 9):
        seed_fixture(
            session, fid, matchday=1, kickoff=datetime(2026, 8, 20, tzinfo=UTC),
            final=True, season_year=SEASON,
        )

    result = coverage(session, SEASON, expected, now)
    assert result == {
        "players": 3,
        "complete": 1,
        "withGaps": 2,
        "oldestLastDay": date(2026, 9, 1),
    }


def test_my_player_ids_is_squad_plus_watchlist(session):
    make_player(session, 1)
    make_player(session, 2)
    make_player(session, 3)
    session.add(SquadMember(player_id=1, purchase_price=1_000_000, acquired_on=date(2026, 8, 1)))
    session.add(
        SquadMember(
            player_id=2, purchase_price=1_000_000, acquired_on=date(2026, 8, 1),
            sold_at=datetime(2026, 8, 10, tzinfo=UTC), sale_price=1_100_000,
        )
    )
    session.commit()
    add_to_watchlist(session, 3)

    assert set(my_player_ids(session)) == {1, 3}


def test_record_fetch_round_trips_status_and_error(session):
    make_player(session, 1)
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    record_fetch(session, 1, now, "ok")

    from storage.models import PlayerPageFetch

    stored = session.get(PlayerPageFetch, 1)
    assert stored.status == "ok"
    assert stored.error is None

    later = datetime(2026, 9, 2, 12, tzinfo=UTC)
    record_fetch(session, 1, later, "gap", error="no statsRows")
    session.expire_all()
    stored = session.get(PlayerPageFetch, 1)
    assert stored.status == "gap"
    assert stored.error == "no statsRows"
    assert stored.fetched_at.replace(tzinfo=UTC) == later


def test_migration_matches_the_models(engine):
    market_cols = {c["name"] for c in sa.inspect(engine).get_columns("playermarketdaily")}
    assert market_cols == set(PlayerMarketDaily.model_fields)
    match_cols = {c["name"] for c in sa.inspect(engine).get_columns("playermatchstats")}
    assert match_cols == set(PlayerMatchStats.model_fields)
    run_cols = {c["name"] for c in sa.inspect(engine).get_columns("scraperun")}
    assert "mode" in run_cols
