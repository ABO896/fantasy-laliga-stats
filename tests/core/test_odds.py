import math

import pytest

from core.odds import (
    fit_poisson_goals,
    match_probabilities,
    overround,
    remove_overround,
    score_matrix_probabilities,
)


def test_overround_of_a_fair_book_is_zero():
    assert overround([2.0, 2.0]) == pytest.approx(0.0)


def test_overround_of_a_real_1x2_book():
    # Alaves v Getafe, 2026-08-15, market average pre-match odds.
    assert overround([2.33, 2.82, 3.62]) == pytest.approx(1 / 2.33 + 1 / 2.82 + 1 / 3.62 - 1)


def test_proportional_removal_sums_to_one_and_keeps_ratios():
    probs = remove_overround([2.33, 2.82, 3.62], method="proportional")
    assert sum(probs) == pytest.approx(1.0)
    raw = [1 / 2.33, 1 / 2.82, 1 / 3.62]
    assert probs[0] / probs[2] == pytest.approx(raw[0] / raw[2])


def test_power_removal_sums_to_one_and_shades_the_longshot_more():
    prop = remove_overround([1.30, 5.50, 11.0], method="proportional")
    power = remove_overround([1.30, 5.50, 11.0], method="power")
    assert sum(power) == pytest.approx(1.0)
    # The favourite-longshot bias: the power method takes more margin off
    # the longshot than proportional scaling does.
    assert power[2] < prop[2]
    assert power[0] > prop[0]


def test_removal_of_a_fair_book_is_identity():
    assert remove_overround([2.0, 4.0, 4.0]) == pytest.approx([0.5, 0.25, 0.25])


@pytest.mark.parametrize("bad", [[1.0, 2.0], [0.0, 3.0], [-2.0, 2.0], [2.0]])
def test_removal_refuses_invalid_books(bad):
    with pytest.raises(ValueError):
        remove_overround(bad)


def test_unknown_method_is_refused():
    with pytest.raises(ValueError):
        remove_overround([2.0, 2.0], method="shin-ish")


def test_score_matrix_probabilities_are_consistent():
    p = score_matrix_probabilities(1.5, 1.1)
    assert p.home + p.draw + p.away == pytest.approx(1.0, abs=1e-9)
    # Sum of independent Poissons is Poisson(2.6).
    lam = 2.6
    under = sum(math.exp(-lam) * lam**k / math.factorial(k) for k in range(3))
    assert p.over25 == pytest.approx(1 - under, abs=1e-9)


def test_fit_recovers_known_rates():
    truth = score_matrix_probabilities(1.8, 0.9)
    fit = fit_poisson_goals(truth.home, truth.draw, truth.away, truth.over25)
    assert fit.home == pytest.approx(1.8, abs=1e-4)
    assert fit.away == pytest.approx(0.9, abs=1e-4)


def test_fit_without_over_under_uses_the_draw():
    truth = score_matrix_probabilities(1.2, 1.4)
    fit = fit_poisson_goals(truth.home, truth.draw, truth.away, None)
    assert fit.home == pytest.approx(1.2, abs=1e-3)
    assert fit.away == pytest.approx(1.4, abs=1e-3)


def test_fit_handles_a_heavy_favourite():
    truth = score_matrix_probabilities(3.2, 0.35)
    fit = fit_poisson_goals(truth.home, truth.draw, truth.away, truth.over25)
    assert fit.home == pytest.approx(3.2, abs=1e-3)
    assert fit.away == pytest.approx(0.35, abs=1e-3)


def test_match_probabilities_from_a_real_row():
    # Alaves v Getafe, 2026-08-15, market averages: 1X2 and over/under 2.5.
    m = match_probabilities(2.33, 2.82, 3.62, 3.08, 1.35)
    assert m.p_home + m.p_draw + m.p_away == pytest.approx(1.0)
    assert m.p_over25 + m.p_under25 == pytest.approx(1.0)
    assert m.p_home > m.p_away > 0
    assert m.p_under25 > m.p_over25  # a low-scoring market
    assert m.exp_goals_home > m.exp_goals_away
    assert m.exp_goals_home + m.exp_goals_away < 2.5
    assert m.p_clean_sheet_home == pytest.approx(math.exp(-m.exp_goals_away))
    assert m.p_clean_sheet_away == pytest.approx(math.exp(-m.exp_goals_home))
    assert m.overround_1x2 > 0
    assert m.overround_ou > 0


def test_match_probabilities_without_over_under():
    m = match_probabilities(2.33, 2.82, 3.62, None, None)
    assert m.p_over25 is not None  # derived from the fitted rates instead
    assert m.overround_ou is None
    assert m.goals_fit == "1x2"


def test_match_probabilities_needs_a_complete_1x2():
    assert match_probabilities(None, 2.82, 3.62, 3.08, 1.35) is None
