"""ANALYTICS-01…07 — our own player metrics, as pure functions.

Nothing here touches the database: callers load rows (see
`storage/our_models.py`) and pass plain values in. Every metric returns its
value together with the inputs and the window it used, because ANALYTICS-05
requires the page to show both, and a number whose derivation the page
cannot show is a number the owner has to take on trust.

Formulas, windows and the reasoning behind each constant are in
`docs/superpowers/specs/2026-09-27-analytics-and-market-model-design.md`.
"""

import math
import statistics
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import NamedTuple

from core import expected_points as xp

#: Last N timeline jornadas that make up "form".
FORM_WINDOW = 5
#: The trailing baseline form is compared against — one season's worth,
#: wherever it falls, because six jornadas into a season the season's own
#: average *is* the form window.
BASELINE_WINDOW = 38
#: Recent-points and consistency window.
RECENT_WINDOW = 10
#: Momentum windows in days, when the caller does not choose.
DEFAULT_MOMENTUM_WINDOWS = (1, 7, 14, 30)
#: |pct| below this reads as flat rather than as a direction.
FLAT_THRESHOLD_PCT = 0.25
#: power_ppg that maps to a Power Score of 100. Calibrated on 2026-09-16:
#: the 99th percentile of power_ppg across 473 players was 9.7.
POWER_REFERENCE_PPG = 10.0
#: Chance-of-playing multiplier by the source's availability status. Assumed;
#: unknown statuses read as available. Shared with the transfer engine.
AVAILABILITY_FACTOR = {"available": 1.0, "doubtful": 0.6, "suspended": 0.5, "injured": 0.15}
#: Minimum jornadas in the recent window before a valuation is attempted.
MIN_VALUATION_JORNADAS = 3
#: A position with fewer eligible players than this uses the pooled fit.
MIN_POSITION_FIT = 15
#: Below this published starter probability a player isn't valued: a
#: floor-priced fringe player with a few points otherwise reads as the best
#: value in the game (audit F6 — the top Economy quintile scored least).
MIN_VALUATION_STARTER = 30.0


class GameweekRow(NamedTuple):
    season_year: int
    week: int
    player_id: int
    points: int
    is_provisional: bool


# --- the shared points timeline -------------------------------------------------


def build_timeline(
    rows: Iterable[GameweekRow], final_weeks: Collection[tuple[int, int]] = ()
) -> list[tuple[int, int]]:
    """Every `(season, week)` the league has rows for, oldest first.

    A week nobody has a row for was not captured, so it is simply absent
    rather than a zero. The in-progress jornada is excluded — a week is in
    progress only if it is flagged *and* is its season's highest week (an
    older week can carry a stale flag while being final), *and* the
    calendar does not already say it is over (`final_weeks`: every fixture
    of it that has kicked off is final). Without that last check the latest
    complete jornada sat outside every score until the next one began.
    """
    weeks: set[tuple[int, int]] = set()
    flagged: set[tuple[int, int]] = set()
    top: dict[int, int] = {}
    for r in rows:
        weeks.add((r.season_year, r.week))
        top[r.season_year] = max(top.get(r.season_year, r.week), r.week)
        if r.is_provisional:
            flagged.add((r.season_year, r.week))
    done = set(final_weeks)
    in_progress = {(s, w) for s, w in flagged if top[s] == w and (s, w) not in done}
    return sorted(weeks - in_progress)


def player_series(
    timeline: Sequence[tuple[int, int]],
    rows: Iterable[GameweekRow],
    n: int,
    team_weeks: Collection[tuple[int, int]] | None = None,
) -> list[int]:
    """The player's last `n` jornadas on the league timeline, oldest first.

    A timeline week with no row for this player counts as 0 — he did not
    feature — but only from his first recorded week *of that season*, and,
    when `team_weeks` is given, only in weeks his club actually played. A
    postponed match, or a capture that missed his club, is absent, not a
    zero (audit F2).
    """
    points: dict[tuple[int, int], int] = {}
    first: dict[int, int] = {}
    for r in rows:
        points[(r.season_year, r.week)] = r.points
        first[r.season_year] = min(first.get(r.season_year, r.week), r.week)
    played = set(team_weeks) if team_weeks is not None else None
    out: list[int] = []
    for season, week in reversed(timeline):
        if len(out) == n:
            break
        if season not in first or week < first[season]:
            continue
        key = (season, week)
        if key in points:
            out.append(points[key])
        elif played is None or key in played:
            out.append(0)
    out.reverse()
    return out


# --- ANALYTICS-01 form ------------------------------------------------------------


@dataclass(frozen=True)
class FormResult:
    value: float | None
    form_avg: float | None
    baseline_avg: float | None
    window: int
    baseline_window: int
    form_jornadas: int
    baseline_jornadas: int


def form(
    series: Sequence[int], window: int = FORM_WINDOW, baseline_window: int = BASELINE_WINDOW
) -> FormResult:
    """Recent average minus the trailing baseline immediately before it."""
    recent = list(series[-window:])
    baseline = list(series[:-window][-baseline_window:]) if len(series) > window else []
    form_avg = statistics.fmean(recent) if recent else None
    baseline_avg = statistics.fmean(baseline) if baseline else None
    value = (
        form_avg - baseline_avg if form_avg is not None and baseline_avg is not None else None
    )
    return FormResult(
        value, form_avg, baseline_avg, window, baseline_window, len(recent), len(baseline)
    )


# --- ANALYTICS-03 consistency -----------------------------------------------------


@dataclass(frozen=True)
class ConsistencyResult:
    value: float | None
    mean: float | None
    sd: float | None
    window: int
    jornadas: int


def consistency(series: Sequence[int], window: int = RECENT_WINDOW) -> ConsistencyResult:
    """`100 · m / (m + sd)`, `m = max(mean, 0)` — bounded 0–100, 100 for a
    perfectly steady scorer. Forty points as two twenties and eight blanks
    scores 33; the same forty as ten fours scores 100."""
    recent = list(series[-window:])
    if not recent:
        return ConsistencyResult(None, None, None, window, 0)
    mean = statistics.fmean(recent)
    sd = statistics.pstdev(recent)
    m = max(mean, 0.0)
    value = 0.0 if m == 0 else 100 * m / (m + sd)
    return ConsistencyResult(value, mean, sd, window, len(recent))


# --- ANALYTICS-02 value momentum --------------------------------------------------


@dataclass(frozen=True)
class MomentumResult:
    window_days: int
    from_date: date | None
    to_date: date | None
    from_value: int | None
    to_value: int | None
    days: int | None
    pct: float | None
    rate_per_day: float | None
    direction: str | None  # up | down | flat, None when the window isn't covered


def value_momentum(
    history: Sequence[tuple[date, int]], windows: Sequence[int] = DEFAULT_MOMENTUM_WINDOWS
) -> list[MomentumResult]:
    """Per window: % change from the latest snapshot at or before
    `latest − window` to the latest. Snapshots are irregular, so the actual
    span is reported and the rate is divided by it, not by the nominal
    window. A window reaching before the first snapshot has no value."""
    ordered = sorted(history)
    results = []
    if not ordered:
        return [MomentumResult(w, None, None, None, None, None, None, None, None) for w in windows]
    to_date, to_value = ordered[-1]
    for w in windows:
        cutoff = to_date - timedelta(days=w)
        earlier = [(d, v) for d, v in ordered if d <= cutoff]
        if not earlier or earlier[-1][1] <= 0:
            results.append(MomentumResult(w, None, to_date, None, to_value, None, None, None, None))
            continue
        from_date, from_value = earlier[-1]
        days = (to_date - from_date).days
        pct = (to_value - from_value) / from_value * 100
        direction = "flat" if abs(pct) < FLAT_THRESHOLD_PCT else ("up" if pct > 0 else "down")
        results.append(
            MomentumResult(w, from_date, to_date, from_value, to_value, days, pct, pct / days,
                           direction)
        )
    return results


# --- ANALYTICS-06 Power Score -----------------------------------------------------


@dataclass(frozen=True)
class PowerInputs:
    position: str
    rate: float
    rate_matches: int
    prior: float
    prior_source: str
    availability: str | None
    recent_jornadas: int


@dataclass(frozen=True)
class PowerResult:
    score: float
    power_ppg: float
    quality_ppg: float
    availability_factor: float
    calibration: tuple[float, float]


def power_inputs(
    series: Sequence[int],
    season_history: Sequence[int],
    prior_season_mean: float | None,
    position: str,
    availability: str | None,
) -> PowerInputs | None:
    """`None` when the player has no jornada on the timeline at all.

    `series` (cross-season, Task 2 rules) only supplies the evidence count;
    the rate comes from `season_history` — his current-season points per
    team match — shrunk toward last season exactly as MODEL-02 does it."""
    if not series:
        return None
    rate = xp.points_rate(season_history, prior_season_mean, position)
    return PowerInputs(
        position=position,
        rate=rate.value,
        rate_matches=rate.matches,
        prior=rate.prior,
        prior_source=rate.prior_source,
        availability=availability,
        recent_jornadas=len(series[-RECENT_WINDOW:]),
    )


def power_score(inputs: PowerInputs) -> PowerResult:
    """Power v2 (audit 2026-09-30): expected points per team match *now*.

    `quality = a·rate + c` with MODEL-02's rate-only calibration per position
    — the shrunk, recency-weighted rate is what beat plain averages in the
    backtest, and the calibration fixes the old score's over-dispersion (its
    top decile predicted 7.4, scored 5.2). `power_ppg = quality · availability`.
    The old form tilt and consistency factor are gone: neither added
    predictive value, and the tilt rewarded a rise from negative to zero.
    Expected points for the next fixture are *not* blended in; they are their
    own number (MODEL-02)."""
    a, c = xp.RATE_ONLY.get(inputs.position, xp.RATE_ONLY["MED"])
    quality = max(0.0, a * inputs.rate + c)
    avail = AVAILABILITY_FACTOR.get(inputs.availability or "available", 1.0)
    ppg = quality * avail
    score = min(max(100 * ppg / POWER_REFERENCE_PPG, 0.0), 100.0)
    return PowerResult(score, ppg, quality, avail, (a, c))


# --- ANALYTICS-04 valuation and ANALYTICS-07 Economy Score ------------------------


@dataclass(frozen=True)
class ValuationInput:
    player_id: int
    position: str
    quality_ppg: float
    market_value: int
    recent_jornadas: int
    starter_probability: float | None = None
    #: Raw mean of his last `RECENT_WINDOW` series points, uncorrected by
    #: Power's shrinkage. `None` means not checked. Power v2's quality is
    #: shrunk toward a prior, so a player who scores nothing still gets a
    #: small positive `quality_ppg`; this is the real "didn't play" signal.
    recent_avg: float | None = None


@dataclass(frozen=True)
class FairValueFit:
    intercept: float
    slope: float
    n: int
    r_squared: float | None
    pooled: bool


@dataclass(frozen=True)
class ValuationResult:
    fair_value: int | None
    gap: float | None  # fair / market − 1; +0.3 = priced 30% under what the production costs
    fit: FairValueFit | None
    reason: str | None  # why there is no valuation, when there isn't


def _eligibility(v: ValuationInput) -> str | None:
    if v.recent_jornadas < MIN_VALUATION_JORNADAS:
        return f"fewer than {MIN_VALUATION_JORNADAS} jornadas in the recent window"
    if v.quality_ppg <= 0:
        return "no points in the recent window"
    if v.recent_avg is not None and v.recent_avg <= 0:
        return "no points in the recent window"
    if v.market_value <= 0:
        return "no market value"
    if v.starter_probability is not None and v.starter_probability < MIN_VALUATION_STARTER:
        return f"starter probability below {MIN_VALUATION_STARTER:.0f}%"
    return None


def _ols(points: Sequence[tuple[float, float]]) -> tuple[float, float, float | None] | None:
    if len(points) < 2:
        return None
    mx = statistics.fmean(x for x, _ in points)
    my = statistics.fmean(y for _, y in points)
    sxx = sum((x - mx) ** 2 for x, _ in points)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in points) / sxx
    intercept = my - slope * mx
    syy = sum((y - my) ** 2 for _, y in points)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    r2 = 1 - ss_res / syy if syy else None
    return intercept, slope, r2


def fit_fair_value(data: Iterable[ValuationInput]) -> dict[str, FairValueFit]:
    """`ln(market_value) = a + b·ln(quality_ppg)` per position, over the
    eligible players only. Log-log, not exponential: the exponential curve
    valued a top scorer at ~8x anything the market pays (audit F5) — the
    same reason MODEL-05's bargains moved to log-log. A position with too
    few players borrows the pooled fit."""
    eligible = [v for v in data if _eligibility(v) is None]
    pts = lambda vs: [(math.log(v.quality_ppg), math.log(v.market_value)) for v in vs]  # noqa: E731
    pooled = _ols(pts(eligible))
    fits: dict[str, FairValueFit] = {}
    for position in {v.position for v in eligible}:
        group = [v for v in eligible if v.position == position]
        own = _ols(pts(group)) if len(group) >= MIN_POSITION_FIT else None
        if own is not None:
            fits[position] = FairValueFit(own[0], own[1], len(group), own[2], False)
        elif pooled is not None:
            fits[position] = FairValueFit(pooled[0], pooled[1], len(eligible), pooled[2], True)
    return fits


def valuations(data: Sequence[ValuationInput]) -> dict[int, ValuationResult]:
    """ANALYTICS-04 — each player's price against what his quality points per
    match usually costs at his position. Built from market values and points
    only; the source's ideal/max bid numbers are deliberately not an input."""
    fits = fit_fair_value(data)
    out: dict[int, ValuationResult] = {}
    for v in data:
        reason = _eligibility(v)
        fit = fits.get(v.position)
        if reason is None and fit is None:
            reason = "not enough players to fit a price curve"
        if reason is not None:
            out[v.player_id] = ValuationResult(None, None, fit, reason)
            continue
        fair = math.exp(fit.intercept + fit.slope * math.log(v.quality_ppg))
        out[v.player_id] = ValuationResult(round(fair), fair / v.market_value - 1, fit, None)
    return out


def economy_scores(results: dict[int, ValuationResult]) -> dict[int, float]:
    """ANALYTICS-07 — the log-log valuation gap as a 0–100 percentile rank:
    100 is the player priced furthest below what his production costs.
    Economy adds price to Power and nothing else; it *is* ANALYTICS-04,
    re-expressed."""
    scored = {pid: math.log1p(r.gap) for pid, r in results.items() if r.gap is not None}
    if not scored:
        return {}
    if len(scored) == 1:
        return {pid: 50.0 for pid in scored}
    ordered = sorted(scored.values())
    n = len(ordered)
    out = {}
    for pid, value in scored.items():
        below = sum(1 for x in ordered if x < value)
        equal = sum(1 for x in ordered if x == value) - 1
        out[pid] = 100 * (below + equal / 2) / (n - 1)
    return out
