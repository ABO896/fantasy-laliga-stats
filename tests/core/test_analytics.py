"""ANALYTICS-01…07 — pure functions over already-loaded rows."""

import math
from datetime import date

import pytest

from core import expected_points as xp
from core.analytics import (
    AVAILABILITY_FACTOR,
    GameweekRow,
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


def test_timeline_keeps_a_flagged_top_week_the_calendar_says_is_final():
    data = rows(1, 2026, {1: 1, 2: 2}, provisional=(2,))
    assert build_timeline(data) == [(2026, 1)]
    assert build_timeline(data, final_weeks={(2026, 2)}) == [(2026, 1), (2026, 2)]


def test_series_skips_a_week_his_team_did_not_play():
    # League played weeks 1-3; his club's week-2 match was postponed.
    data = rows(1, 2026, {1: 6, 3: 4}) + rows(2, 2026, {1: 1, 2: 1, 3: 1})
    timeline = build_timeline(data)
    mine = [r for r in data if r.player_id == 1]
    assert player_series(timeline, mine, n=10) == [6, 0, 4]
    assert player_series(timeline, mine, n=10, team_weeks={(2026, 1), (2026, 3)}) == [6, 4]


def test_series_still_zeroes_a_week_his_team_played_without_him():
    data = rows(1, 2026, {1: 6, 3: 4}) + rows(2, 2026, {1: 1, 2: 1, 3: 1})
    timeline = build_timeline(data)
    mine = [r for r in data if r.player_id == 1]
    played = {(2026, 1), (2026, 2), (2026, 3)}
    assert player_series(timeline, mine, n=10, team_weeks=played) == [6, 0, 4]


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


def test_power_with_no_history_is_the_prior():
    inp = power_inputs([0], [], None, "MED", "available")
    res = power_score(inp)
    a, c = xp.RATE_ONLY["MED"]
    assert res.quality_ppg == pytest.approx(max(0.0, a * xp.POSITION_PRIOR["MED"] + c))
    assert 0 <= res.score <= 100


def test_power_is_shrunk_toward_the_prior_for_one_big_match():
    one = power_score(power_inputs([20], [20], None, "DEL", "available"))
    many = power_score(power_inputs([20] * 10, [20] * 10, None, "DEL", "available"))
    assert one.quality_ppg < many.quality_ppg


def test_injured_player_is_charged_by_availability():
    fit = power_score(power_inputs([8] * 6, [8] * 6, 6.0, "DEL", "available"))
    hurt = power_score(power_inputs([8] * 6, [8] * 6, 6.0, "DEL", "injured"))
    assert hurt.quality_ppg == fit.quality_ppg
    assert hurt.power_ppg == pytest.approx(fit.power_ppg * AVAILABILITY_FACTOR["injured"])


def test_rising_from_negative_to_zero_is_not_rewarded():
    # Audit: Beitia — recent avg 0 after a negative baseline scored Economy 96.9.
    res = power_score(power_inputs([-3, -2, -2, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0], None, "DEF",
                                   "available"))
    zero = power_score(power_inputs([0] * 8, [0] * 5, None, "DEF", "available"))
    assert res.quality_ppg == pytest.approx(zero.quality_ppg)


def test_power_without_series_is_none():
    assert power_inputs([], [], None, "DEF", "available") is None


# --- valuation and economy -------------------------------------------------


def _market(position, pairs, start_id=1):
    return [
        ValuationInput(player_id=start_id + i, position=position, quality_ppg=ppg, market_value=mv,
                       recent_jornadas=10, starter_probability=70.0)
        for i, (ppg, mv) in enumerate(pairs)
    ]


def test_fit_recovers_an_exact_log_log_curve():
    pairs = [(p, int(math.exp(14 + 0.5 * math.log(p)))) for p in range(1, 21)]
    fits = fit_fair_value(_market("DEF", pairs))
    assert fits["DEF"].intercept == pytest.approx(14, abs=1e-3)
    assert fits["DEF"].slope == pytest.approx(0.5, abs=1e-3)
    assert fits["DEF"].pooled is False


def test_small_positions_fall_back_to_the_pooled_fit():
    data = _market("DEF", [(p, int(math.exp(14 + 0.5 * math.log(p)))) for p in range(1, 21)])
    data += _market("POR", [(1, 2_000_000), (2, 3_000_000)], start_id=100)
    fits = fit_fair_value(data)
    assert fits["POR"].pooled is True


def test_valuation_gap_and_economy_percentile():
    pairs = [(p, int(math.exp(14 + 0.5 * math.log(p)))) for p in range(1, 20)]
    data = _market("MED", pairs)
    fair_at_10 = math.exp(14 + 0.5 * math.log(10))
    cheap = ValuationInput(500, "MED", 10.0, int(fair_at_10 / 2), 10, 70.0)  # half its fair value
    dear = ValuationInput(501, "MED", 10.0, int(fair_at_10 * 2), 10, 70.0)
    result = valuations(data + [cheap, dear])
    assert result[500].gap == pytest.approx(1.0, rel=0.05)  # fair/actual - 1 = +100%
    assert result[501].gap == pytest.approx(-0.5, rel=0.05)
    econ = economy_scores(result)
    assert econ[500] == 100.0
    assert econ[501] == 0.0


def test_valuation_needs_evidence():
    data = _market("DEL", [(p, int(math.exp(14 + 0.5 * math.log(p)))) for p in range(1, 20)])
    idle = ValuationInput(900, "DEL", 0.0, 500_000, 10)
    newcomer = ValuationInput(901, "DEL", 5.0, 5_000_000, 2)
    result = valuations(data + [idle, newcomer])
    assert result[900].gap is None and result[900].reason == "no points in the recent window"
    assert result[901].gap is None and "jornadas" in result[901].reason
    assert 900 not in economy_scores(result)


def test_recent_avg_zero_gates_despite_shrunk_quality():
    """Power v2 shrinks quality toward a prior, so a player who scores
    nothing in his recent window still gets a small positive quality_ppg.
    recent_avg — the raw mean, uncorrected — is the real "didn't score"
    signal, and must still gate him out of the valuation."""
    data = _market("DEF", [(p, int(math.exp(14 + 0.5 * math.log(p)))) for p in range(1, 20)])
    shrunk = ValuationInput(777, "DEF", 1.5, 2_000_000, 10, 70.0, recent_avg=0.0)
    result = valuations(data + [shrunk])
    assert result[777].gap is None
    assert result[777].reason == "no points in the recent window"


def test_fair_value_is_log_log_and_does_not_explode_for_stars():
    data = [ValuationInput(i, "MED", ppg, int(1e6 * ppg ** 1.5), 10, 80)
            for i, ppg in enumerate([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], 1)]
    star = ValuationInput(99, "MED", 20.0, int(1e6 * 20 ** 1.5), 10, 90)
    res = valuations(data + [star])
    assert res[99].gap == pytest.approx(0.0, abs=0.05)


def test_starter_gate_excludes_fringe_players():
    base = [ValuationInput(i, "DEF", 3.0 + i / 10, int(2e6 + i * 1e5), 10, 70)
            for i in range(1, 20)]
    fringe = ValuationInput(50, "DEF", 2.0, 500_000, 5, 10)
    res = valuations(base + [fringe])
    assert res[50].gap is None
    assert "starter" in res[50].reason


def test_unknown_starter_probability_is_not_gated():
    base = [ValuationInput(i, "DEF", 3.0 + i / 10, int(2e6 + i * 1e5), 10, 70)
            for i in range(1, 20)]
    unknown = ValuationInput(51, "DEF", 3.0, 2_000_000, 5, None)
    assert valuations(base + [unknown])[51].gap is not None
