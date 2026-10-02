from datetime import UTC, date, datetime

from core.player_pages import Candidate, appearance, expected_last_day, needs_fetch, select_players

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


def test_appearance_from_minutes():
    assert [appearance(m) for m in (0, 1, 59, 60, 90)] == ["dnp", "sub", "sub", "start", "start"]


def test_expected_last_day_respects_the_update_hour():
    assert expected_last_day(datetime(2026, 10, 2, 7, 59), 8) == date(2026, 10, 1)
    assert expected_last_day(datetime(2026, 10, 2, 8, 0), 8) == date(2026, 10, 2)


def test_a_player_is_fetched_for_each_kind_of_gap():
    fresh = datetime(2026, 10, 2, 9, tzinfo=UTC)
    ok = Candidate(1, date(2026, 10, 2), frozenset(), fresh)
    assert not needs_fetch(ok, date(2026, 10, 2), NOW, 7)
    assert needs_fetch(Candidate(2, None, frozenset(), None), date(2026, 10, 2), NOW, 7)
    never_caught_up = Candidate(3, date(2026, 9, 30), frozenset(), fresh)
    assert needs_fetch(never_caught_up, date(2026, 10, 2), NOW, 7)
    has_gap = Candidate(4, date(2026, 10, 2), frozenset({6}), fresh)
    assert needs_fetch(has_gap, date(2026, 10, 2), NOW, 7)
    stale = datetime(2026, 9, 24, tzinfo=UTC)
    overdue_sweep = Candidate(5, date(2026, 10, 2), frozenset(), stale)
    assert needs_fetch(overdue_sweep, date(2026, 10, 2), NOW, 7)


def test_never_fetched_and_oldest_fetch_come_first():
    cs = [
        Candidate(1, None, frozenset(), datetime(2026, 10, 1, tzinfo=UTC)),
        Candidate(2, None, frozenset(), None),
        Candidate(3, None, frozenset(), datetime(2026, 9, 1, tzinfo=UTC)),
    ]
    assert select_players(cs, date(2026, 10, 2), NOW, 7, budget=None) == [2, 3, 1]
    assert select_players(cs, date(2026, 10, 2), NOW, 7, budget=2) == [2, 3]
