"""`core.fixture_difficulty` — pure, so every case is hand-built."""

from datetime import UTC, datetime, timedelta

import pytest

from core.fixture_difficulty import (
    HOME_ADVANTAGE,
    PRIOR_WEIGHT_WEEKS,
    FixtureView,
    fixture_difficulty,
    team_strength,
    upcoming_fixtures,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _fx(fixture_id, matchday, home, away, days=1, is_final=False) -> FixtureView:
    return FixtureView(
        fixture_id=fixture_id,
        matchday=matchday,
        kickoff_utc=NOW + timedelta(days=days),
        kickoff_confirmed=True,
        is_final=is_final,
        home_team=home,
        away_team=away,
    )


# --- upcoming_fixtures -----------------------------------------------------


def test_upcoming_excludes_finished_and_long_past_fixtures():
    fixtures = [
        _fx(1, 8, "A", "B", days=2),
        _fx(2, 6, "C", "D", days=-5, is_final=True),
        _fx(3, 6, "E", "F", days=-5),  # stale: never marked final, long past
        _fx(4, 8, "G", "H", days=-0.05),  # kicked off an hour ago: in play
    ]
    assert [f.fixture_id for f in upcoming_fixtures(fixtures, NOW)] == [4, 1]


def test_upcoming_is_in_kickoff_order_not_jornada_order():
    """A postponed fixture keeps its old jornada number."""
    fixtures = [_fx(1, 9, "A", "B", days=3), _fx(2, 6, "C", "D", days=10)]
    assert [f.fixture_id for f in upcoming_fixtures(fixtures, NOW)] == [1, 2]


# --- team_strength ---------------------------------------------------------


def test_strength_is_relative_to_the_league_mean():
    """With a long enough record the prior barely moves it: a team scoring
    twice the league-average per jornada rates close to 2x the weak one."""
    weeks = 400
    current = {"Strong": [60.0] * weeks, "Weak": [30.0] * weeks}
    ratings = team_strength(current)
    assert ratings["Strong"] == pytest.approx(60 / 45, rel=0.01)
    assert ratings["Weak"] == pytest.approx(30 / 45, rel=0.01)


def test_early_season_ratings_are_shrunk_toward_the_prior():
    """One jornada is noise; it moves a rating only 1/(1+k) of the way."""
    current = {"A": [60.0], "B": [30.0]}
    ratings = team_strength(current)
    raw = 60 / 45
    expected = (1 * raw + PRIOR_WEIGHT_WEEKS * 1.0) / (1 + PRIOR_WEIGHT_WEEKS)
    assert ratings["A"] == pytest.approx(expected)


def test_the_prior_is_last_seasons_relative_rating_when_there_is_one():
    current = {"A": [45.0], "B": [45.0]}
    previous = {"A": [80.0], "B": [40.0]}  # A was 4/3 of last season's mean
    ratings = team_strength(current, previous)
    expected_a = (1 * 1.0 + PRIOR_WEIGHT_WEEKS * (80 / 60)) / (1 + PRIOR_WEIGHT_WEEKS)
    assert ratings["A"] == pytest.approx(expected_a)


def test_a_team_with_no_current_weeks_rates_at_its_prior():
    ratings = team_strength({"A": [50.0]}, {"A": [50.0], "Promoted": []}, teams=["Promoted", "Z"])
    assert ratings["Z"] == 1.0
    assert ratings["Promoted"] == 1.0


def test_no_data_at_all_rates_everyone_average():
    assert team_strength({}, teams=["A", "B"]) == {"A": 1.0, "B": 1.0}


# --- fixture_difficulty ----------------------------------------------------


def test_difficulty_is_opponent_strength_adjusted_for_venue():
    strength = {"A": 1.0, "B": 1.2}
    [a, b] = sorted(fixture_difficulty([_fx(1, 8, "A", "B")], strength, n=1), key=lambda t: t.team)
    # A hosts B: facing a 1.2 side, made easier by playing at home.
    assert a.fixtures[0].difficulty == pytest.approx(1.2 * (1 - HOME_ADVANTAGE))
    assert a.fixtures[0].is_home
    assert a.fixtures[0].opponent == "B"
    # B travels to A: an average side, made harder by being away.
    assert b.fixtures[0].difficulty == pytest.approx(1.0 * (1 + HOME_ADVANTAGE))
    assert not b.fixtures[0].is_home


def test_the_window_is_the_next_n_jornadas_by_kickoff():
    fixtures = [
        _fx(1, 8, "A", "B", days=1),
        _fx(2, 9, "B", "A", days=8),
        _fx(3, 10, "A", "B", days=15),
    ]
    teams = {t.team: t for t in fixture_difficulty(fixtures, {}, n=2)}
    assert [f.matchday for f in teams["A"].fixtures] == [8, 9]
    assert teams["A"].fixture_count == 2


def test_a_team_with_two_fixtures_in_the_window_has_both_averaged():
    """A postponed match played inside the window is a real extra fixture."""
    fixtures = [
        _fx(1, 8, "A", "B", days=1),
        _fx(2, 6, "A", "C", days=2),  # postponed jornada-6 match
        _fx(3, 8, "C", "D", days=1),
    ]
    strength = {"B": 1.0, "C": 1.4, "D": 1.0, "A": 1.0}
    teams = {t.team: t for t in fixture_difficulty(fixtures, strength, n=2)}
    a = teams["A"]
    assert a.fixture_count == 2
    home = 1 - HOME_ADVANTAGE
    assert a.average_difficulty == pytest.approx((1.0 * home + 1.4 * home) / 2)


def test_a_team_without_a_fixture_is_listed_last_with_no_average():
    fixtures = [_fx(1, 8, "A", "B"), _fx(2, 9, "C", "D", days=30)]
    result = fixture_difficulty(fixtures, {"B": 1.5, "A": 0.5}, n=1)
    assert [t.team for t in result] == ["B", "A", "C", "D"]
    assert result[-1].average_difficulty is None
    assert result[-1].fixture_count == 0


def test_teams_are_ranked_easiest_first():
    fixtures = [_fx(1, 8, "A", "B"), _fx(2, 8, "C", "D")]
    strength = {"A": 1.5, "B": 0.6, "C": 1.0, "D": 1.0}
    assert [t.team for t in fixture_difficulty(fixtures, strength, n=1)][0] == "A"


def test_n_must_be_positive():
    with pytest.raises(ValueError):
        fixture_difficulty([], {}, n=0)
