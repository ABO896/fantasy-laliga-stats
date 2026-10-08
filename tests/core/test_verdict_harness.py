import statistics
from datetime import date, timedelta

from core.verdict_harness import Observation, bootstrap_ci, label_reports


def test_mean_diff_is_signed_by_claim():
    day1 = date(2026, 1, 1)
    day2 = date(2026, 1, 2)
    obs = [
        Observation(day1, 1, "DEF", "Bargain", {"points_per_m": 3.0}),
        Observation(day1, 2, "DEF", "Fair price", {"points_per_m": 1.0}),
        Observation(day2, 3, "DEF", "Overpriced", {"points_per_m": 1.0}),
        Observation(day2, 4, "DEF", "Fair price", {"points_per_m": 3.0}),
    ]
    reports = {r.label: r for r in label_reports(obs)}

    bargain = reports["Bargain"]
    assert bargain.mean_diff == 1.0
    assert bargain.hit_rate == 1.0

    overpriced = reports["Overpriced"]
    assert overpriced.mean_diff == 1.0


def test_bootstrap_is_clustered_by_player():
    obs = []
    # Player 1: 40 "wins" (points 10 vs a same-day filler at 0 -> mean 5,
    # diff = +1 * (10 - 5) = +5), each on its own day.
    for i in range(40):
        day = date(2026, 1, 1) + timedelta(days=i)
        obs.append(Observation(day, 1, "DEF", "Elite", {"points": 10.0}))
        obs.append(Observation(day, 100 + i, "DEF", "Fair price", {"points": 0.0}))
    # Players 2-10: one "loss" each (points 0 vs a same-day filler at 10 ->
    # mean 5, diff = +1 * (0 - 5) = -5), each on its own day.
    for j in range(2, 11):
        day = date(2026, 6, 1) + timedelta(days=j)
        obs.append(Observation(day, j, "DEF", "Elite", {"points": 0.0}))
        obs.append(Observation(day, 200 + j, "DEF", "Fair price", {"points": 10.0}))

    report = next(r for r in label_reports(obs) if r.label == "Elite")

    naive_mean = statistics.fmean(
        5.0 if o.player_id == 1 else -5.0
        for o in obs if o.label == "Elite"
    )
    assert naive_mean > 0

    assert report.ci_low is not None
    assert report.ci_low <= 0
    assert report.beats_chance is False


def test_too_few_players_has_no_interval():
    obs = [
        Observation(date(2026, 1, i + 1), i, "DEF", "Elite", {"points": 10.0})
        for i in range(3)
    ]
    report = next(r for r in label_reports(obs) if r.label == "Elite")
    assert report.ci_low is None
    assert report.beats_chance is False

    # bootstrap_ci itself, directly, with fewer than 5 players.
    assert bootstrap_ci({1: [1.0], 2: [1.0], 3: [1.0]}, resamples=100, seed=7) is None


def test_unclaimed_labels_report_counts_only():
    obs = [
        Observation(date(2026, 1, 1), 1, "DEF", "Unproven", {"points": None}),
        Observation(date(2026, 1, 2), 2, "DEF", "Unproven", {"points": None}),
    ]
    report = next(r for r in label_reports(obs) if r.label == "Unproven")
    assert report.n == 2
    assert report.players == 2
    assert report.hit_rate is None
    assert report.mean_diff is None
    assert report.ci_low is None
    assert report.beats_chance is False


# --- the baseline is eligible players only (final review #3) ----------------------------


def test_baseline_excludes_ineligible_observations():
    """An injured / unproven / zero-minute player must not drag the
    same-day position mean down and flatter every label."""
    day = date(2026, 1, 1)
    obs = [
        Observation(day, 1, "DEF", "Elite", {"points": 10.0}),
        Observation(day, 2, "DEF", "Fair price", {"points": 10.0}),
        Observation(day, 3, "DEF", "Unavailable", {"points": 0.0}, eligible=False),
        Observation(day, 4, "DEF", "Unproven", {"points": 0.0}, eligible=False),
    ]
    elite = next(r for r in label_reports(obs) if r.label == "Elite")
    assert elite.mean_diff == 0.0  # vs eligible mean 10, not the all-player mean 5
    assert elite.base_rate == 0.0  # neither eligible observation beats the eligible mean


def test_observation_is_eligible_by_default():
    assert Observation(date(2026, 1, 1), 1, "DEF", "Elite", {}).eligible is True


# --- the momentum baseline for the price labels (final review #2) -----------------------


def _momentum_day(day, label_pid, label, momentum_outcomes):
    """Ten DEFs on `day`: (momentum, price_pct) pairs; `label_pid` carries `label`."""
    return [
        Observation(day, pid, "DEF", label if pid == label_pid else "Fair price",
                    {"price_pct": outcome}, momentum=momentum)
        for pid, (momentum, outcome) in enumerate(momentum_outcomes)
    ]


def test_rising_carries_a_momentum_baseline_over_the_top_15_percent():
    obs = []
    for i in range(6):
        day = date(2026, 1, 1) + timedelta(days=i)
        # momentum 0..9; the top mover (momentum 9) rises +10, everyone else 0.
        pairs = [(float(m), 10.0 if m == 9 else 0.0) for m in range(10)]
        obs += _momentum_day(day, 0, "Rising", pairs)  # the label picks player 0
    reports = {r.label: r for r in label_reports(obs)}

    momentum = reports["Rising"].momentum
    assert momentum is not None
    # Top 15%: share of the day's movers strictly below >= 0.85 — momentum 9
    # (9/9) and 8 (8/9), each day. Diffs vs the same-day mean of 1: +9, -1.
    assert momentum.n == 12
    assert momentum.hit_rate == 0.5
    assert momentum.mean_diff == 4.0
    assert reports["Rising"].mean_diff == -1.0  # the label lost to momentum


def test_sell_high_momentum_baseline_is_the_bottom_15_percent_signed_down():
    day = date(2026, 1, 1)
    pairs = [(float(m), -10.0 if m == 0 else 0.0) for m in range(10)]
    obs = _momentum_day(day, 5, "Sell high", pairs)
    momentum = next(r for r in label_reports(obs) if r.label == "Sell high").momentum
    # Bottom 15%: momentum 0 (0/9) and 1 (1/9). Diffs, signed down, vs the
    # same-day mean of -1: -(-10 + 1) = +9 and -(0 + 1) = -1.
    assert momentum.n == 2
    assert momentum.mean_diff == 4.0


def test_non_price_labels_have_no_momentum_baseline():
    day = date(2026, 1, 1)
    obs = [Observation(day, i, "DEF", "Elite" if i == 0 else "Fair price",
                       {"points": float(i)}, momentum=float(i)) for i in range(10)]
    assert next(r for r in label_reports(obs) if r.label == "Elite").momentum is None
