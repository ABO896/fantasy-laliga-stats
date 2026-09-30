"""ANALYTICS-01…07 — pure functions over already-loaded rows."""

import math
from datetime import date

import pytest

from core.analytics import (
    EXPECTED_POINTS_WEIGHT,
    GameweekRow,
    PowerInputs,
    ValuationInput,
    build_timeline,
    consistency,
    economy_scores,
    fit_fair_value,
    form,
    player_series,
    power_inputs,
    power_score,
    valuations,
    value_momentum,
)


def rows(player_id, season, points_by_week, provisional=()):
    return [
        GameweekRow(season, week, player_id, pts, week in provisional)
        for week, pts in points_by_week.items()
    ]


# --- timeline -------------------------------------------------------------


def test_timeline_drops_weeks_nobody_has_and_orders_across_seasons():
    data = rows(1, 2025, {1: 3, 2: 4, 4: 5}) + rows(1, 2026, {1: 6})
    assert build_timeline(data) == [(2025, 1), (2025, 2), (2025, 4), (2026, 1)]


def test_timeline_excludes_only_the_provisional_top_week_of_a_season():
    # Week 2 carries a stale provisional flag but weeks after it exist — it is final.
    data = rows(1, 2026, {1: 1, 2: 2, 3: 3, 4: 4}, provisional=(2, 4))
    assert build_timeline(data) == [(2026, 1), (2026, 2), (2026, 3)]


def test_series_counts_a_missing_week_as_zero_only_after_first_appearance():
    data = rows(1, 2026, {1: 5, 2: 5, 3: 5, 4: 5}) + rows(2, 2026, {3: 8})
    timeline = build_timeline(data)
    by_player = {}
    for r in data:
        by_player.setdefault(r.player_id, []).append(r)
    # Player 2 joined in week 3 and missed week 4: 8, 0 — not 0, 0, 8, 0.
    assert player_series(timeline, by_player[2], n=10) == [8, 0]
    assert player_series(timeline, by_player[1], n=2) == [5, 5]


def test_series_restarts_first_appearance_per_season():
    data = rows(1, 2025, {1: 4, 2: 4}) + rows(9, 2026, {1: 1, 2: 1, 3: 1}) + rows(1, 2026, {3: 7})
    timeline = build_timeline(data)
    mine = [r for r in data if r.player_id == 1]
    # 2026 weeks 1-2 predate his first 2026 row: not charged.
    assert player_series(timeline, mine, n=10) == [4, 4, 7]


# --- form -----------------------------------------------------------------


def test_form_is_recent_average_minus_trailing_baseline():
    series = [2] * 10 + [8] * 5
    result = form(series, window=5, baseline_window=38)
    assert result.value == pytest.approx(6.0)
    assert result.form_avg == pytest.approx(8.0)
    assert result.baseline_avg == pytest.approx(2.0)
    assert result.window == 5 and result.baseline_jornadas == 10


def test_form_is_none_without_a_baseline():
    assert form([5, 5, 5], window=5, baseline_window=38).value is None


# --- consistency ----------------------------------------------------------


def test_consistency_separates_two_big_weeks_from_steady_scoring():
    lumpy = consistency([20, 20, 0, 0, 0, 0, 0, 0, 0, 0], window=10)
    steady = consistency([4] * 10, window=10)
    assert steady.value == pytest.approx(100.0)
    assert lumpy.value == pytest.approx(100 * 4 / (4 + 8))
    assert lumpy.sd == pytest.approx(8.0)


def test_consistency_is_zero_when_mean_is_not_positive_and_none_when_empty():
    assert consistency([0, -1, 1], window=10).value == 0.0
    assert consistency([], window=10).value is None


# --- momentum -------------------------------------------------------------


def test_momentum_uses_latest_snapshot_at_or_before_window_start_and_actual_days():
    history = [
        (date(2026, 9, 1), 10_000_000),
        (date(2026, 9, 5), 11_000_000),
        (date(2026, 9, 16), 12_100_000),
    ]
    [w7, w30] = value_momentum(history, windows=[7, 30])
    # 16 - 7 = 9th -> latest at/before is the 5th, 11 days back.
    assert w7.from_date == date(2026, 9, 5)
    assert w7.days == 11
    assert w7.pct == pytest.approx(10.0)
    assert w7.rate_per_day == pytest.approx(10.0 / 11)
    assert w7.direction == "up"
    # Nothing at/before Aug 17: window not covered, so no number.
    assert w30.pct is None and w30.direction is None


def test_momentum_flat_threshold():
    history = [(date(2026, 9, 15), 10_000_000), (date(2026, 9, 16), 10_010_000)]
    [w1] = value_momentum(history, windows=[1])
    assert w1.direction == "flat"


# --- power ----------------------------------------------------------------


def test_power_inputs_and_score():
    series = [4] * 43  # 38 baseline + 5 form, perfectly steady
    inputs = power_inputs(series)
    assert inputs.recent_avg == pytest.approx(4.0)
    assert inputs.form == pytest.approx(0.0)
    assert inputs.consistency == pytest.approx(100.0)
    result = power_score(inputs)
    assert result.power_ppg == pytest.approx(4.0)
    assert result.score == pytest.approx(40.0)
    assert result.expected_points_used is False


def test_power_penalises_inconsistency_and_rewards_form():
    base = PowerInputs(recent_avg=5, recent_jornadas=10, form=0, consistency=100)
    shaky = PowerInputs(recent_avg=5, recent_jornadas=10, form=0, consistency=0)
    rising = PowerInputs(recent_avg=5, recent_jornadas=10, form=2, consistency=100)
    assert power_score(shaky).score < power_score(base).score < power_score(rising).score
    assert power_score(shaky).power_ppg == pytest.approx(4.0)


def test_power_clamps_to_0_100():
    assert power_score(PowerInputs(30, 10, 0, 100)).score == 100.0
    assert power_score(PowerInputs(-3, 10, 0, 0)).score == 0.0


def test_power_form_missing_counts_as_zero_tilt():
    assert power_score(PowerInputs(5, 10, None, 100)).power_ppg == pytest.approx(5.0)


def test_power_is_none_without_recent_points():
    assert power_inputs([]) is None


def test_expected_points_hook_blends_when_given():
    inputs = PowerInputs(recent_avg=4, recent_jornadas=10, form=0, consistency=100)
    result = power_score(inputs, expected_points=8.0)
    expected = (1 - EXPECTED_POINTS_WEIGHT) * 4 + EXPECTED_POINTS_WEIGHT * 8
    assert result.power_ppg == pytest.approx(expected)
    assert result.expected_points_used is True


# --- valuation and economy -------------------------------------------------


def _market(position, pairs, start_id=1):
    return [
        ValuationInput(player_id=start_id + i, position=position, power_ppg=ppg, market_value=mv,
                       recent_jornadas=10)
        for i, (ppg, mv) in enumerate(pairs)
    ]


def test_fit_recovers_an_exact_log_linear_curve():
    pairs = [(p, int(math.exp(14 + 0.5 * p))) for p in range(0, 20)]
    fits = fit_fair_value(_market("DEF", pairs))
    assert fits["DEF"].intercept == pytest.approx(14, abs=1e-3)
    assert fits["DEF"].slope == pytest.approx(0.5, abs=1e-3)
    assert fits["DEF"].pooled is False


def test_small_positions_fall_back_to_the_pooled_fit():
    data = _market("DEF", [(p, int(math.exp(14 + 0.5 * p))) for p in range(20)])
    data += _market("POR", [(1, 2_000_000), (2, 3_000_000)], start_id=100)
    fits = fit_fair_value(data)
    assert fits["POR"].pooled is True


def test_valuation_gap_and_economy_percentile():
    pairs = [(p, int(math.exp(14 + 0.5 * p))) for p in range(1, 20)]
    data = _market("MED", pairs)
    cheap = ValuationInput(500, "MED", 10.0, int(math.exp(14 + 5) / 2), 10)  # half its fair value
    dear = ValuationInput(501, "MED", 10.0, int(math.exp(14 + 5) * 2), 10)
    result = valuations(data + [cheap, dear])
    assert result[500].gap == pytest.approx(1.0, rel=0.05)  # fair/actual - 1 = +100%
    assert result[501].gap == pytest.approx(-0.5, rel=0.05)
    econ = economy_scores(result)
    assert econ[500] == 100.0
    assert econ[501] == 0.0


def test_valuation_needs_evidence():
    data = _market("DEL", [(p, int(math.exp(14 + 0.5 * p))) for p in range(1, 20)])
    idle = ValuationInput(900, "DEL", 0.0, 500_000, 10)
    newcomer = ValuationInput(901, "DEL", 5.0, 5_000_000, 2)
    result = valuations(data + [idle, newcomer])
    assert result[900].gap is None and result[900].reason == "no points in the recent window"
    assert result[901].gap is None and "jornadas" in result[901].reason
    assert 900 not in economy_scores(result)
