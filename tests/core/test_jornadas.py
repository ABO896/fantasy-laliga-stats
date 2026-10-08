from datetime import date

from core.jornadas import known_weeks, week_end_dates


def d(day):  # September 2026
    return date(2026, 9, day)


def test_week_end_is_the_last_date_near_the_median():
    team_dates = {
        "A": [d(1), d(8)],
        "B": [d(2), d(9)],
        "C": [d(3), d(20)],  # C's second match was postponed — far from the median
    }
    ends = week_end_dates(team_dates)
    assert ends == {1: d(3), 2: d(9)}


def test_known_weeks_are_strictly_before():
    ends = {1: d(3), 2: d(9)}
    assert known_weeks(ends, d(3)) == set()
    assert known_weeks(ends, d(4)) == {1}
    assert known_weeks(ends, d(30)) == {1, 2}
