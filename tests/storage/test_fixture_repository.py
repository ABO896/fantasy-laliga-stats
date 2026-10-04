from datetime import UTC, datetime

from scraper.sources.analiticafantasy_calendar import FixtureRecord
from storage.models import Player, PlayerGameweekPoints, ScrapeRun
from storage.repository import get_fixtures, get_team_week_points, upsert_fixtures


def _record(fixture_id: int, **overrides) -> FixtureRecord:
    defaults = dict(
        fixture_id=fixture_id,
        matchday=8,
        season_year=2026,
        kickoff_utc=datetime(2026, 10, 9, 19, 0, tzinfo=UTC),
        kickoff_confirmed=True,
        is_final=False,
        home_team="Barcelona",
        away_team="Athletic Club",
        home_team_id=529,
        away_team_id=531,
        home_difficulty="easy",
        away_difficulty="very_hard",
    )
    defaults.update(overrides)
    return FixtureRecord(**defaults)


def test_upsert_inserts_new_fixtures(session):
    assert upsert_fixtures(session, [_record(1), _record(2)]) == 2
    assert len(get_fixtures(session)) == 2


def test_upsert_updates_an_existing_fixture_in_place(session):
    upsert_fixtures(session, [_record(1)])
    upsert_fixtures(
        session,
        [_record(1, kickoff_utc=datetime(2026, 10, 10, 19, 0, tzinfo=UTC), is_final=True)],
    )
    stored = get_fixtures(session)
    assert len(stored) == 1
    assert stored[0].kickoff_utc == datetime(2026, 10, 10, 19, 0, tzinfo=UTC)
    assert stored[0].is_final


def test_a_fixture_outside_the_current_window_is_never_discarded(session):
    """The source shows five jornadas at a time. A refresh that no longer
    mentions jornada 6 must not delete jornada 6 — it is history, which is
    exactly what an expected-points model trains on."""
    upsert_fixtures(session, [_record(1, matchday=6)])
    upsert_fixtures(session, [_record(99, matchday=12)])
    assert {f.fixture_id for f in get_fixtures(session)} == {1, 99}


def test_get_fixtures_returns_aware_kickoffs(session):
    upsert_fixtures(session, [_record(1)])
    assert get_fixtures(session)[0].kickoff_utc.tzinfo is not None


def _player(session, slug, team):
    now = datetime.now(UTC)
    p = Player(
        external_id=slug, name=slug, team=team, position="DEL", created_at=now, updated_at=now
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_team_week_points_sums_final_weeks_per_team(session):
    run = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(run)
    session.commit()
    # 5 players per club — MIN_TEAM_ROWS — so every week counts as played.
    a1, a2, a3, a4, a5 = (_player(session, f"a{i}", "A") for i in range(1, 6))
    b1, b2, b3, b4, b5 = (_player(session, f"b{i}", "B") for i in range(1, 6))

    def gw(week, player, points, provisional=False, season=2026):
        return PlayerGameweekPoints(
            season_year=season, week=week, player_id=player.id, points=points,
            is_provisional=provisional, scrape_run_id=run.id,
        )

    session.add_all([
        gw(1, a1, 5), gw(1, a2, 3), gw(1, a3, 0), gw(1, a4, 0), gw(1, a5, 0),
        gw(1, b1, 2), gw(1, b2, 0), gw(1, b3, 0), gw(1, b4, 0), gw(1, b5, 0),
        gw(2, a1, 4), gw(2, a2, 0), gw(2, a3, 0), gw(2, a4, 0), gw(2, a5, 0),
        gw(2, b1, 6), gw(2, b2, 0), gw(2, b3, 0), gw(2, b4, 0), gw(2, b5, 0),
        gw(3, a1, 50, provisional=True),  # still moving — excluded
        gw(1, b1, 99, season=2025),  # another season — excluded
    ])
    session.commit()

    assert get_team_week_points(session, 2026) == {"A": [8.0, 4.0], "B": [2.0, 6.0]}


def test_team_week_points_keep_a_stale_flagged_week(session):
    """Week 2 is flagged but finished (a stale ingest flag); week 3 is the
    actual active jornada. Only week 3 — the season's highest flagged
    week — is excluded."""
    run = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(run)
    session.commit()
    players = [_player(session, f"a{i}", "A") for i in range(1, 6)]

    def gw(week, player, points, provisional=False):
        return PlayerGameweekPoints(
            season_year=2026, week=week, player_id=player.id, points=points,
            is_provisional=provisional, scrape_run_id=run.id,
        )

    for week, provisional in ((1, False), (2, True), (3, True)):
        session.add_all([gw(week, p, 2, provisional=provisional) for p in players])
    session.commit()

    assert get_team_week_points(session, 2026)["A"] == [10.0, 10.0]


def test_team_week_points_drops_a_club_that_did_not_play(session):
    """A club-week with fewer than MIN_TEAM_ROWS rows is left out entirely,
    not read as a low-scoring week."""
    run = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(run)
    session.commit()
    players = [_player(session, f"a{i}", "A") for i in range(1, 6)]

    def gw(week, player, points):
        return PlayerGameweekPoints(
            season_year=2026, week=week, player_id=player.id, points=points,
            scrape_run_id=run.id,
        )

    session.add_all([gw(1, p, 2) for p in players])
    # Week 2: only 2 of the 5 players have a row — club didn't play (or
    # wasn't captured) that week.
    session.add_all([gw(2, players[0], 9), gw(2, players[1], 9)])
    session.commit()

    assert get_team_week_points(session, 2026)["A"] == [10.0]
