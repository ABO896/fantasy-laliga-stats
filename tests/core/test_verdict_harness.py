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
