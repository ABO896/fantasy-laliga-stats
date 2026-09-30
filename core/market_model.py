"""MODEL-01 — predict the next market update, and MODEL-03's scoring rules.

Pure functions only. Market prediction is inference under partial
observation: the demand side (who is buying) is unobservable, so the model
works from proxies — the last published movement, its acceleration,
starter-probability and availability changes, and fresh points. The backtest
(spec §4) found the market overwhelmingly persistent; this model is
persistence plus a nudge, and its real contribution is a calibrated
confidence tier rather than accuracy. Say so wherever it is shown.

The confidence words below belong to the *market* model only. MODEL-02
(expected points) must not reuse them — the roadmap is explicit that the two
problems are differently conditioned and must not share a vocabulary.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

MODEL_VERSION = "market-v1"

ACCELERATION_WEIGHT = 0.5
STARTER_WEIGHT = 0.01  # % per percentage point of starter probability
NEWLY_UNAVAILABLE_SHIFT = -1.0
BACK_AVAILABLE_SHIFT = 0.5
FRESH_POINTS_WEIGHT = 0.15
FRESH_POINTS_PIVOT = 2
FRESH_POINTS_MAX_GAP_DAYS = 2

STRONG_MIN = 1.0
MODERATE_MIN = 0.5
CONFIDENCE_TIERS = ("strong", "moderate", "weak")
#: What to call when there is no signal at all: roughly 72% of players fall
#: on any given market update (backtest, 2026-08-06…09-16).
BASE_RATE_DIRECTION = "fall"

UNAVAILABLE = frozenset({"injured", "doubtful", "suspended"})

_SOURCE_DIRECTIONS = {
    "market_top_risers": "rise",
    "market_possible_risers": "rise",
    "market_top_fallers": "fall",
    "market_possible_fallers": "fall",
}


@dataclass(frozen=True)
class SnapshotPoint:
    as_of: date
    market_value: int
    price_change_pct: float | None
    starter_probability: float | None
    availability_status: str
    points: int


@dataclass(frozen=True)
class Prediction:
    predicted_pct: float
    direction: str  # rise | fall | flat
    confidence: str  # strong | moderate | weak
    inputs: dict


@dataclass(frozen=True)
class Outcome:
    outcome_as_of: date
    gap_days: int
    actual_pct: float
    actual_direction: str
    scoring: str  # exact | interval
    hit: bool


def direction_of(pct: float) -> str:
    return "rise" if pct > 0 else "fall" if pct < 0 else "flat"


def confidence_for(predicted_pct: float) -> str:
    magnitude = abs(predicted_pct)
    if magnitude >= STRONG_MIN:
        return "strong"
    if magnitude >= MODERATE_MIN:
        return "moderate"
    return "weak"


def predict(current: SnapshotPoint, previous: SnapshotPoint | None) -> Prediction:
    """Predict the update after `current`. `previous` is the player's latest
    earlier captured snapshot, whatever its age — each term checks whether
    that age makes it usable."""
    last = current.price_change_pct or 0.0
    gap = (current.as_of - previous.as_of).days if previous else None

    acceleration = None
    if previous is not None and gap == 1 and previous.price_change_pct is not None:
        acceleration = ACCELERATION_WEIGHT * (last - previous.price_change_pct)

    starter = None
    if (
        previous is not None
        and current.starter_probability is not None
        and previous.starter_probability is not None
    ):
        starter = STARTER_WEIGHT * (current.starter_probability - previous.starter_probability)

    availability_change = None
    availability_term = None
    if previous is not None and previous.availability_status != current.availability_status:
        availability_change = f"{previous.availability_status} → {current.availability_status}"
        if previous.availability_status == "available" and current.availability_status in (
            UNAVAILABLE
        ):
            availability_term = NEWLY_UNAVAILABLE_SHIFT
        elif (
            previous.availability_status in UNAVAILABLE
            and current.availability_status == "available"
        ):
            availability_term = BACK_AVAILABLE_SHIFT

    fresh_points = None
    fresh_term = None
    if previous is not None and gap is not None and gap <= FRESH_POINTS_MAX_GAP_DAYS:
        fresh_points = current.points - previous.points
        if fresh_points != 0:
            fresh_term = FRESH_POINTS_WEIGHT * (fresh_points - FRESH_POINTS_PIVOT)

    x = last + sum(t for t in (acceleration, starter, availability_term, fresh_term) if t)
    # No signal at all (a new player, or a zero move with nothing else
    # known). "Flat" is almost never what happens — 33 of 34 such cases in
    # the backtest fell — so fall back to the market's base rate: most
    # players fall on any given day. Always weak, and flagged in the inputs.
    base_rate_fallback = x == 0
    direction = BASE_RATE_DIRECTION if base_rate_fallback else direction_of(x)
    inputs = {
        "asOf": current.as_of.isoformat(),
        "lastMovePct": current.price_change_pct,
        "previousSnapshot": previous.as_of.isoformat() if previous else None,
        "previousMovePct": previous.price_change_pct if previous and gap == 1 else None,
        "accelerationTerm": acceleration,
        "starterProbability": current.starter_probability,
        "previousStarterProbability": previous.starter_probability if previous else None,
        "starterTerm": starter,
        "availabilityChange": availability_change,
        "availabilityTerm": availability_term,
        "freshPoints": fresh_points,
        "freshPointsTerm": fresh_term,
        "baseRateFallback": base_rate_fallback,
    }
    return Prediction(x, direction, confidence_for(x), inputs)


def score(made_from: SnapshotPoint, predicted_direction: str, nxt: SnapshotPoint) -> Outcome:
    """Score against the next *captured* snapshot, whatever the gap.

    One day later, that snapshot's own published move *is* the predicted
    update — an exact label. Any later, only the cumulative change across the
    gap is knowable, which can hide a reversal inside it; it is scored on
    direction and labelled `interval` so the track record can keep the two
    apart.
    """
    gap = (nxt.as_of - made_from.as_of).days
    if gap == 1 and nxt.price_change_pct is not None:
        actual, scoring = nxt.price_change_pct, "exact"
    else:
        actual = (nxt.market_value - made_from.market_value) / made_from.market_value * 100
        scoring = "interval"
    actual_direction = direction_of(actual)
    return Outcome(
        nxt.as_of, gap, actual, actual_direction, scoring, predicted_direction == actual_direction
    )


def source_direction(source: str) -> str | None:
    """The direction a source market list asserts. `None` for non-market
    sources (the points predictions)."""
    return _SOURCE_DIRECTIONS.get(source)


@dataclass(frozen=True)
class ScoredCall:
    confidence: str
    scoring: str | None
    hit: bool | None
    retroactive: bool
    gap_days: int | None


def _rate(hits: int, n: int) -> float | None:
    return hits / n if n else None


def _bucket(calls: list[ScoredCall]) -> dict:
    scored = [c for c in calls if c.hit is not None]
    hits = sum(1 for c in scored if c.hit)
    by_conf = {}
    for tier in CONFIDENCE_TIERS:
        group = [c for c in scored if c.confidence == tier]
        h = sum(1 for c in group if c.hit)
        by_conf[tier] = {"scored": len(group), "hits": h, "hitRate": _rate(h, len(group))}
    by_scoring = {}
    for mode in ("exact", "interval"):
        group = [c for c in scored if c.scoring == mode]
        h = sum(1 for c in group if c.hit)
        by_scoring[mode] = {"scored": len(group), "hits": h, "hitRate": _rate(h, len(group))}
    return {
        "scored": len(scored),
        "pending": len(calls) - len(scored),
        "hits": hits,
        "hitRate": _rate(hits, len(scored)),
        "byConfidence": by_conf,
        "byScoring": by_scoring,
    }


def summarize(calls: Iterable[ScoredCall]) -> dict:
    """Live and retroactive records, never merged: a backtest computed after
    the fact must not be able to inflate the record of calls made in time."""
    calls = list(calls)
    return {
        "live": _bucket([c for c in calls if not c.retroactive]),
        "retroactive": _bucket([c for c in calls if c.retroactive]),
    }
