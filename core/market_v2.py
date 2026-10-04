"""market-v2 — expected % change in market value over the next 7 days
(spec §4.4). Pure.

Per-position linear model with ridge shrinkage on standardized features,
refit weekly, walk-forward: a fit made on day F only ever sees rows whose
7-day outcome was known by F. Features (as of the prediction day):

    r1, r3, r7      the last 1/3/7-day % changes of his value
    pts_vs_exp      recent points per match minus his shrunk rate
    minutes_trend   minutes per match, last 3 club matches vs the 5 before
    avail_change    +1 back from injury/suspension, −1 newly out, 0 otherwise
    days_to_match   days until his club's next match (market updates left)
    price_level     his price's percentile within his position, 0–1

The interval is the fit's residual 10th/90th percentiles around the
prediction; *drop risk* is a lower bound under −3 %. With too little
history it falls back to persistence (half the last week's move), which is
labelled as such. Every number here is a starting value; the track record
publishes the naive baseline beside it (lesson 7).
"""

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

MODEL_VERSION = "market-v2"
OUTLOOK_DAYS = 7
FLAT_BAND_PCT = 0.5
DROP_RISK_PCT = -3.0
RIDGE_LAMBDA = 10.0
MIN_TRAIN_ROWS = 300
REFIT_EVERY_DAYS = 7
PERSISTENCE_SHRINK = 0.5
PERSISTENCE_HALF_WIDTH = 4.0
INTERVAL_QUANTILES = (0.1, 0.9)
FEATURES = (
    "r1", "r3", "r7", "pts_vs_exp", "minutes_trend", "avail_change", "days_to_match",
    "price_level",
)


@dataclass(frozen=True)
class Row:
    player_id: int
    position: str
    day: date
    x: dict[str, float]
    target: float | None
    target_day: date


@dataclass(frozen=True)
class Fit:
    position: str
    pooled: bool
    means: dict[str, float]
    scales: dict[str, float]
    coef: dict[str, float]
    intercept: float
    q_low: float
    q_high: float
    n: int


@dataclass(frozen=True)
class Outlook:
    expected_pct: float
    direction: str  # rise | flat | fall
    lower: float
    upper: float
    drop_risk: bool
    basis: str  # ridge | ridge-pooled | persistence
    terms: dict[str, float]
    #: The day the prediction was made, when a caller knows it (storage
    #: reconstructs it from the stored row); `None` from a bare `predict()`
    #: call, which has no notion of "when" — core stays clockless.
    made_on: date | None = None


def price_change_pct(values: Mapping[date, int], day: date, days: int) -> float | None:
    then = values.get(day - timedelta(days=days))
    now = values.get(day)
    if not then or now is None:
        return None
    return (now - then) / then * 100


def direction_of(pct: float) -> str:
    if abs(pct) < FLAT_BAND_PCT:
        return "flat"
    return "rise" if pct > 0 else "fall"


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting; `a` is small and SPD."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r != col and m[col][col]:
                f = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] if m[i][i] else 0.0 for i in range(n)]


def _quantile(values: Sequence[float], q: float) -> float:
    s = sorted(values)
    idx = q * (len(s) - 1)
    lo, hi = math.floor(idx), math.ceil(idx)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _fit(rows: Sequence[Row], position: str, pooled: bool) -> Fit:
    means = {f: statistics.fmean(r.x[f] for r in rows) for f in FEATURES}
    scales = {}
    for f in FEATURES:
        sd = statistics.pstdev(r.x[f] for r in rows)
        scales[f] = sd if sd > 1e-9 else 1.0
    z = [[(r.x[f] - means[f]) / scales[f] for f in FEATURES] for r in rows]
    y = [r.target for r in rows]
    y_mean = statistics.fmean(y)
    k = len(FEATURES)
    xtx = [[sum(zi[a] * zi[b] for zi in z) + (RIDGE_LAMBDA if a == b else 0.0)
            for b in range(k)] for a in range(k)]
    xty = [sum(zi[a] * (yi - y_mean) for zi, yi in zip(z, y, strict=True)) for a in range(k)]
    beta = _solve(xtx, xty)
    coef = dict(zip(FEATURES, beta, strict=True))
    resid = [yi - (y_mean + sum(b * v for b, v in zip(beta, zi, strict=True)))
             for zi, yi in zip(z, y, strict=True)]
    lo, hi = INTERVAL_QUANTILES
    return Fit(position, pooled, means, scales, coef, y_mean,
               _quantile(resid, lo), _quantile(resid, hi), len(rows))


def fit_models(rows: Sequence[Row], fit_date: date) -> dict[str, Fit]:
    matured = [r for r in rows if r.target is not None and r.target_day <= fit_date]
    pooled = _fit(matured, "ALL", True) if len(matured) >= MIN_TRAIN_ROWS else None
    out: dict[str, Fit] = {}
    for position in ("POR", "DEF", "MED", "DEL"):
        group = [r for r in matured if r.position == position]
        if len(group) >= MIN_TRAIN_ROWS:
            out[position] = _fit(group, position, False)
        elif pooled is not None:
            out[position] = pooled
    return out


def predict(row: Row, fits: Mapping[str, Fit]) -> Outlook:
    fit = fits.get(row.position)
    if fit is None:
        pct = PERSISTENCE_SHRINK * row.x.get("r7", 0.0)
        lower, upper = pct - PERSISTENCE_HALF_WIDTH, pct + PERSISTENCE_HALF_WIDTH
        return Outlook(pct, direction_of(pct), lower, upper, lower < DROP_RISK_PCT,
                       "persistence", {"r7": pct})
    terms = {f: fit.coef[f] * (row.x[f] - fit.means[f]) / fit.scales[f] for f in FEATURES}
    pct = fit.intercept + sum(terms.values())
    lower, upper = pct + fit.q_low, pct + fit.q_high
    return Outlook(pct, direction_of(pct), lower, upper, lower < DROP_RISK_PCT,
                   "ridge-pooled" if fit.pooled else "ridge",
                   {"intercept": fit.intercept} | terms)


def confidence_for(o: Outlook) -> str:
    if o.lower > 0 or o.upper < 0:
        return "strong"
    return "moderate" if abs(o.expected_pct) >= FLAT_BAND_PCT else "weak"


def score(predicted_direction: str, actual_pct: float) -> tuple[str, bool]:
    actual = direction_of(actual_pct)
    return actual, actual == predicted_direction


def fit_dates(first: date, last: date) -> list[date]:
    out, d = [], first
    while d <= last:
        out.append(d)
        d += timedelta(days=REFIT_EVERY_DAYS)
    return out
