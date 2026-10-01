"""core/expected_points.py — MODEL-02's pure model."""

import math

import pytest

from core import expected_points as xp
from core.expected_points import UNAVAILABLE_STARTER_CAP, XpInputs, _starter_fraction

UNIT = xp.Coefficients(
    rate_only={p: (1.0, 0.0) for p in ("POR", "DEF", "MED", "DEL")},
    with_starter={p: (0.0, 1.0, 0.0) for p in ("POR", "DEF", "MED", "DEL")},
    fixture={p: (0.0, 0.0) for p in ("POR", "DEF", "MED", "DEL")},
)


def test_rate_with_no_history_is_the_prior():
    r = xp.points_rate([], 5.0, "DEL")
    assert r.value == pytest.approx(5.0 * xp.PRIOR_SEASON_SCALE)
    assert r.prior_source == "last_season"
    assert r.matches == 0


def test_rate_falls_back_to_position_prior_without_last_season():
    r = xp.points_rate([], None, "DEF")
    assert r.value == pytest.approx(xp.POSITION_PRIOR["DEF"])
    assert r.prior_source == "position"


def test_rate_weights_recent_matches_more():
    rising = xp.points_rate([0, 0, 0, 10, 10], None, "MED").value
    falling = xp.points_rate([10, 10, 0, 0, 0], None, "MED").value
    assert rising > falling


def test_rate_moves_toward_history_as_matches_accumulate():
    few = xp.points_rate([10] * 2, None, "MED").value
    many = xp.points_rate([10] * 20, None, "MED").value
    assert few < many < 10


def test_no_fixture_is_zero_and_says_so():
    r = xp.expected_points(xp.XpInputs("DEL", [8, 8], None, 90, has_fixture=False))
    assert r.value == 0
    assert r.basis == "no_fixture"


def test_basis_names_every_input_used():
    fixture = xp.FixtureContext("Real Madrid", True, team_goals=1.8, clean_sheet=0.35,
                                odds_source="football-data")
    assert xp.expected_points(xp.XpInputs("MED", [4], None)).basis == "form"
    assert xp.expected_points(xp.XpInputs("MED", [4], None, 70)).basis == "form+starter"
    assert xp.expected_points(xp.XpInputs("MED", [4], None, fixture=fixture)).basis == "form+odds"
    assert (
        xp.expected_points(xp.XpInputs("MED", [4], None, 70, fixture=fixture)).basis
        == "form+starter+odds"
    )


def test_a_fixture_without_prices_degrades_to_no_odds():
    unpriced = xp.FixtureContext("Getafe", False)
    r = xp.expected_points(xp.XpInputs("DEF", [2], None, 50, fixture=unpriced))
    assert r.basis == "form+starter"
    assert r.inputs["fixture"]["opponent"] == "Getafe"
    assert "cleanSheet" not in r.inputs["terms"]


def test_starter_probability_scales_the_base():
    hi = xp.expected_points(xp.XpInputs("DEL", [6] * 5, None, 90), UNIT).value
    lo = xp.expected_points(xp.XpInputs("DEL", [6] * 5, None, 10), UNIT).value
    assert hi == pytest.approx(9 * lo)


def test_injured_without_starter_probability_reads_as_not_playing():
    r = xp.expected_points(xp.XpInputs("DEL", [6] * 5, None, None, "injured"), UNIT)
    assert r.value == 0
    assert r.basis == "form+starter"


def test_better_odds_raise_xp_for_a_defender():
    k = xp.Coefficients(UNIT.rate_only, UNIT.with_starter, {"DEF": (0.1, 5.0)})
    easy = xp.FixtureContext("A", True, team_goals=2.2, clean_sheet=0.5)
    hard = xp.FixtureContext("B", False, team_goals=0.8, clean_sheet=0.1)
    e = xp.expected_points(xp.XpInputs("DEF", [3] * 5, None, 80, fixture=easy), k)
    h = xp.expected_points(xp.XpInputs("DEF", [3] * 5, None, 80, fixture=hard), k)
    assert e.value > h.value
    assert e.inputs["terms"]["cleanSheet"] > 0 > h.inputs["terms"]["cleanSheet"]


def test_terms_add_up_to_the_value():
    fixture = xp.FixtureContext("X", True, team_goals=1.9, clean_sheet=0.4)
    r = xp.expected_points(xp.XpInputs("DEL", [2, 9, 5], 4.0, 60, fixture=fixture))
    assert sum(r.inputs["terms"].values()) == pytest.approx(r.value, abs=0.01)
    assert r.inputs["rate"]["matches"] == 3
    assert r.inputs["modelVersion"] == xp.MODEL_VERSION


def test_value_is_never_negative():
    k = xp.Coefficients({"POR": (1.0, -50.0)}, UNIT.with_starter, UNIT.fixture)
    assert xp.expected_points(xp.XpInputs("POR", [0], None), k).value == 0


def test_fitted_coefficients_cover_every_position():
    for table in (xp.RATE_ONLY, xp.WITH_STARTER, xp.FIXTURE):
        assert set(table) == {"POR", "DEF", "MED", "DEL"}


def test_a_regular_starter_outscores_a_fringe_player_with_the_shipped_coefficients():
    """Sanity on the fitted constants, not on exact values."""
    starter = xp.expected_points(xp.XpInputs("DEL", [8, 6, 9, 7], 7.0, 90)).value
    fringe = xp.expected_points(xp.XpInputs("DEL", [0, 1, 0, 2], 2.0, 10)).value
    assert starter > 4 > fringe


def test_summarize_errors():
    s = xp.summarize_errors([xp.ScoredPair(4, 2, "form"), xp.ScoredPair(1, 3, "form")])
    assert s.n == 2
    assert s.mae == 2
    assert s.rmse == 2
    assert s.bias == 0
    assert xp.summarize_errors([]).mae is None
    assert math.isclose(xp.summarize_errors([xp.ScoredPair(3, 0, "x")]).bias, 3)


def test_injured_status_caps_the_published_chance():
    s = _starter_fraction(XpInputs("DEL", [8, 9], None, starter_probability=50,
                                   availability="injured"))
    assert s == UNAVAILABLE_STARTER_CAP


def test_doubtful_keeps_the_published_chance():
    s = _starter_fraction(XpInputs("DEL", [8, 9], None, starter_probability=50,
                                   availability="doubtful"))
    assert s == 0.5
