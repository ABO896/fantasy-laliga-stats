"""Repository-level tests for the league-wide stats surfaces (STATS-01…04).

Each query is a pure read-model over `PlayerGameweekPoints` /
`PlayerSeasonStats` joined to `Player` — no new tables, no scraping.
"""

from datetime import UTC, date, datetime

from storage.models import Player, PlayerGameweekPoints, PlayerSnapshot, ScrapeRun
from storage.repository import (
    get_jornada_point_records,
    get_jornada_scores,
    get_season_leaderboard,
    get_season_stat_records,
    get_stats_seasons,
    get_streak_leaderboard,
    get_team_jornada_summary,
)


def _player(session, slug: str, name: str, team: str = "Team A", position: str = "DEL") -> Player:
    now = datetime.now(UTC)
    p = Player(
        external_id=slug, name=name, team=team, position=position, created_at=now, updated_at=now
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _run(session) -> ScrapeRun:
    r = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _gw(season_year, week, player_id, points, run_id, is_provisional=False):
    return PlayerGameweekPoints(
        season_year=season_year,
        week=week,
        player_id=player_id,
        points=points,
        is_provisional=is_provisional,
        scrape_run_id=run_id,
    )


def test_get_stats_seasons_is_distinct_and_descending(session):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add_all([_gw(2025, 10, p.id, 5, run.id), _gw(2026, 3, p.id, 7, run.id)])
    session.commit()

    assert get_stats_seasons(session) == [2026, 2025]


def test_get_stats_seasons_is_empty_with_no_gameweek_rows(session):
    assert get_stats_seasons(session) == []


def test_get_jornada_scores_returns_one_row_per_player_that_week(session):
    p1 = _player(session, "p1", "Player One", team="Team A", position="DEL")
    p2 = _player(session, "p2", "Player Two", team="Team B", position="MED")
    run = _run(session)
    session.add_all(
        [
            _gw(2026, 3, p1.id, 9, run.id),
            _gw(2026, 3, p2.id, 4, run.id),
            _gw(2026, 4, p1.id, 2, run.id),  # a different week — must not appear
        ]
    )
    session.commit()

    rows = get_jornada_scores(session, 2026, 3)

    assert [(r.name, r.team, r.position, r.week, r.points) for r in rows] == [
        ("Player One", "Team A", "DEL", 3, 9),
        ("Player Two", "Team B", "MED", 3, 4),
    ]


def test_get_jornada_scores_carries_is_provisional(session):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add(_gw(2026, 3, p.id, 9, run.id, is_provisional=True))
    session.commit()

    assert get_jornada_scores(session, 2026, 3)[0].is_provisional is True


def test_get_jornada_scores_is_empty_for_an_unplayed_week(session):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add(_gw(2026, 3, p.id, 9, run.id))
    session.commit()

    assert get_jornada_scores(session, 2026, 99) == []


def test_get_jornada_scores_carries_market_value_and_price_per_point_from_the_latest_snapshot(
    session,
):
    """The Scores tab's context columns: current market value and season
    price/point, joined from the latest `PlayerSnapshot` — not this
    jornada's own points, which would be a different, noisier ratio."""
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add(_gw(2026, 3, p.id, 9, run.id))
    session.add_all(
        [
            PlayerSnapshot(
                as_of=date(2026, 9, 1),
                player_id=p.id,
                market_value=1_000_000,
                points=5,
                price_per_point=200_000.0,
                availability_status="available",
                raw_fields="{}",
                scrape_run_id=run.id,
            ),
            PlayerSnapshot(
                as_of=date(2026, 9, 8),
                player_id=p.id,
                market_value=1_500_000,
                points=8,
                price_per_point=187_500.0,
                availability_status="available",
                raw_fields="{}",
                scrape_run_id=run.id,
            ),
        ]
    )
    session.commit()

    row = get_jornada_scores(session, 2026, 3)[0]

    assert (row.market_value, row.price_per_point) == (1_500_000, 187_500.0)


def test_get_jornada_scores_market_value_and_price_per_point_are_none_without_a_snapshot(session):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add(_gw(2026, 3, p.id, 9, run.id))
    session.commit()

    row = get_jornada_scores(session, 2026, 3)[0]

    assert (row.market_value, row.price_per_point) == (None, None)


def test_get_team_jornada_summary_aggregates_per_team_ordered_by_total(session):
    a1 = _player(session, "a1", "A One", team="Team A")
    a2 = _player(session, "a2", "A Two", team="Team A")
    b1 = _player(session, "b1", "B One", team="Team B")
    run = _run(session)
    session.add_all(
        [
            _gw(2026, 3, a1.id, 4, run.id),
            _gw(2026, 3, a2.id, 2, run.id),
            _gw(2026, 3, b1.id, 9, run.id),
        ]
    )
    session.commit()

    rows = get_team_jornada_summary(session, 2026, 3)

    assert [(r.team, r.total_points, r.player_count, r.average_points) for r in rows] == [
        ("Team B", 9, 1, 9.0),
        ("Team A", 6, 2, 3.0),
    ]


def test_get_team_jornada_summary_is_empty_for_an_unplayed_week(session):
    assert get_team_jornada_summary(session, 2026, 99) == []


def test_get_streak_leaderboard_sums_the_window_and_orders_by_total(session):
    p1 = _player(session, "p1", "Player One")
    p2 = _player(session, "p2", "Player Two")
    run = _run(session)
    session.add_all(
        [
            _gw(2026, 1, p1.id, 3, run.id),
            _gw(2026, 2, p1.id, 4, run.id),
            _gw(2026, 3, p1.id, 2, run.id),
            _gw(2026, 1, p2.id, 10, run.id),
            _gw(2026, 2, p2.id, 1, run.id),
            _gw(2026, 3, p2.id, 1, run.id),
        ]
    )
    session.commit()

    rows = get_streak_leaderboard(session, 2026, end_week=3, window=3)

    assert [(r.name, r.total_points, r.weeks_counted) for r in rows] == [
        ("Player Two", 12, 3),
        ("Player One", 9, 3),
    ]


def test_get_streak_leaderboard_shortens_the_window_at_season_start(session):
    """Week 1 with a 5-week window: only one week exists to sum, and
    `weeks_counted` must say so rather than silently treating the missing
    four weeks as zeros."""
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add(_gw(2026, 1, p.id, 6, run.id))
    session.commit()

    rows = get_streak_leaderboard(session, 2026, end_week=1, window=5)

    assert (rows[0].total_points, rows[0].weeks_counted) == (6, 1)


def test_get_streak_leaderboard_excludes_weeks_outside_the_window(session):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add_all([_gw(2026, 1, p.id, 100, run.id), _gw(2026, 5, p.id, 3, run.id)])
    session.commit()

    rows = get_streak_leaderboard(session, 2026, end_week=5, window=2)

    assert (rows[0].total_points, rows[0].weeks_counted) == (3, 1)


def test_get_jornada_point_records_orders_by_points_desc_across_all_weeks(session):
    p1 = _player(session, "p1", "Player One")
    p2 = _player(session, "p2", "Player Two")
    run = _run(session)
    session.add_all(
        [
            _gw(2026, 1, p1.id, 12, run.id),
            _gw(2026, 2, p2.id, 15, run.id),
            _gw(2026, 3, p1.id, 8, run.id),
        ]
    )
    session.commit()

    rows = get_jornada_point_records(session, 2026)

    assert [(r.name, r.week, r.points) for r in rows] == [
        ("Player Two", 2, 15),
        ("Player One", 1, 12),
        ("Player One", 3, 8),
    ]


def test_get_jornada_point_records_respects_the_limit(session):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add_all([_gw(2026, w, p.id, w, run.id) for w in range(1, 6)])
    session.commit()

    assert len(get_jornada_point_records(session, 2026, limit=2)) == 2


def test_get_jornada_point_records_breaks_ties_by_week_then_player_id(session):
    p1 = _player(session, "p1", "Player One")
    p2 = _player(session, "p2", "Player Two")
    run = _run(session)
    session.add_all([_gw(2026, 2, p2.id, 10, run.id), _gw(2026, 1, p1.id, 10, run.id)])
    session.commit()

    rows = get_jornada_point_records(session, 2026)

    assert [(r.week, r.player_id) for r in rows] == sorted(
        [(r.week, r.player_id) for r in rows]
    )
    assert rows[0].week == 1  # earlier week wins the tie


def test_get_season_stat_records_returns_the_leader_per_field(session, season_stats_row):
    p1 = _player(session, "p1", "Player One", team="Team A")
    p2 = _player(session, "p2", "Player Two", team="Team B")
    run = _run(session)
    session.add_all(
        [
            season_stats_row(season_year=2026, player_id=p1.id, scrape_run_id=run.id, goals=10),
            season_stats_row(season_year=2026, player_id=p2.id, scrape_run_id=run.id, goals=4),
        ]
    )
    session.commit()

    records = {r.field: r for r in get_season_stat_records(session, 2026)}

    assert (records["goals"].name, records["goals"].team, records["goals"].value) == (
        "Player One",
        "Team A",
        10,
    )


def test_get_season_stat_records_skips_a_field_with_no_qualifying_data(session, season_stats_row):
    p = _player(session, "p1", "Player One")
    run = _run(session)
    session.add(season_stats_row(season_year=2026, player_id=p.id, scrape_run_id=run.id, goals=0))
    session.commit()

    fields = {r.field for r in get_season_stat_records(session, 2026)}

    assert "goals" not in fields


def test_get_season_stat_records_breaks_a_tie_by_player_id_ascending(session, season_stats_row):
    p_high = _player(session, "p-high", "Higher Id")
    p_low = _player(session, "p-low", "Lower Id")
    run = _run(session)
    session.add_all(
        [
            season_stats_row(season_year=2026, player_id=p_high.id, scrape_run_id=run.id, saves=5),
            season_stats_row(season_year=2026, player_id=p_low.id, scrape_run_id=run.id, saves=5),
        ]
    )
    session.commit()

    winner_id = min(p_high.id, p_low.id)
    records = {r.field: r for r in get_season_stat_records(session, 2026)}

    assert records["saves"].player_id == winner_id


def test_get_season_leaderboard_orders_by_stat_desc(session, season_stats_row):
    p1 = _player(session, "p1", "Player One")
    p2 = _player(session, "p2", "Player Two")
    run = _run(session)
    session.add_all(
        [
            season_stats_row(season_year=2026, player_id=p1.id, scrape_run_id=run.id, goals=3),
            season_stats_row(season_year=2026, player_id=p2.id, scrape_run_id=run.id, goals=9),
        ]
    )
    session.commit()

    rows = get_season_leaderboard(session, 2026, "goals")

    assert [(r.name, r.value) for r in rows] == [("Player Two", 9), ("Player One", 3)]


def test_get_season_leaderboard_filters_by_position_and_team(session, season_stats_row):
    p_del = _player(session, "p-del", "Del Player", team="Team A", position="DEL")
    p_med = _player(session, "p-med", "Med Player", team="Team A", position="MED")
    p_other_team = _player(session, "p-other", "Other Team", team="Team B", position="DEL")
    run = _run(session)
    session.add_all(
        [
            season_stats_row(season_year=2026, player_id=p_del.id, scrape_run_id=run.id, goals=5),
            season_stats_row(season_year=2026, player_id=p_med.id, scrape_run_id=run.id, goals=5),
            season_stats_row(
                season_year=2026, player_id=p_other_team.id, scrape_run_id=run.id, goals=5
            ),
        ]
    )
    session.commit()

    rows = get_season_leaderboard(session, 2026, "goals", position="DEL", team="Team A")

    assert [r.name for r in rows] == ["Del Player"]


def test_get_season_leaderboard_excludes_null_but_not_zero(session, season_stats_row):
    """A stored `0` is a real observation (the player played and did not
    score); it must sort, never be treated as missing the way `None` is."""
    p_zero = _player(session, "p-zero", "Zero Player")
    p_null = _player(session, "p-null", "Null Player")
    run = _run(session)
    zero_row = season_stats_row(
        season_year=2026, player_id=p_zero.id, scrape_run_id=run.id, goals=0
    )
    null_row = season_stats_row(
        season_year=2026, player_id=p_null.id, scrape_run_id=run.id, goals=0
    )
    null_row.goals = None
    session.add_all([zero_row, null_row])
    session.commit()

    rows = get_season_leaderboard(session, 2026, "goals")

    assert [r.name for r in rows] == ["Zero Player"]


def test_get_season_leaderboard_ties_break_by_total_points_then_name(session, season_stats_row):
    p_low_points = _player(session, "p-a", "Alpha")
    p_high_points = _player(session, "p-b", "Beta")
    run = _run(session)
    session.add_all(
        [
            season_stats_row(
                season_year=2026, player_id=p_low_points.id, scrape_run_id=run.id, goals=5,
                total_points=10,
            ),
            season_stats_row(
                season_year=2026, player_id=p_high_points.id, scrape_run_id=run.id, goals=5,
                total_points=20,
            ),
        ]
    )
    session.commit()

    rows = get_season_leaderboard(session, 2026, "goals")

    assert [r.name for r in rows] == ["Beta", "Alpha"]
