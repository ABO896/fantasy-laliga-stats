"""The verdict — one label per player, first match wins (Plan C, Task 1). Pure.

Ten labels, in priority order (`q` = `ranks["power"].percentile`, `v` =
`ranks["pointsValue"].percentile`, `o` = `ranks["outlook"].percentile` — all
within-position, `core.ranks`, never compared across positions; a rule whose
input is `None`/absent never matches):

| # | Label | Rule |
|---|---|---|
| 1 | Unavailable | `availability in {"injured", "suspended"}` |
| 2 | Unproven | `not evidence.ok` |
| 3 | Sell high | `price >= median_price[pos]` and `outlook.direction == "fall"` and |
|   |           | `outlook.drop_risk` and (`minutes_trend < 0` or `points_vs_expected < 0`) |
| 4 | Elite | `q >= elite_quality` and `reliability.cls in RELIABLE_CLASSES` |
| 5 | Bargain | `v >= bargain_value` and `q >= bargain_quality` and `cls in RELIABLE_CLASSES` |
|   |         | and `confidence == "high"` |
| 6 | Rising | `o >= rising_outlook` and `outlook.direction == "rise"` and |
|   |        | `cls in RELIABLE_CLASSES` and not (rule 8 would match) |
| 7 | Rotation risk | `q >= rotation_quality` and `cls in {"Rotation", "Fringe"}` |
| 8 | Overpriced | `v <= overpriced_value` and `price >= median_price[pos]` |
| 9 | Avoid | `q <= avoid_quality` and (`outlook.direction == "fall"` or `cls == "Fringe"`) |
| 10 | Fair price | otherwise |

`Unavailable`, `Unproven` and `Fair price` can never be disabled (`DISABLED_LABELS`).
Rule 2 precedes every positive label, which is what enforces the app's one
hard guarantee: a player below the evidence floor is never `Bargain`,
`Elite` or `Rising`. Rules 4-6 also check `evidence.ok` explicitly — belt
and braces over rule 2, and tested directly.

A label in `DISABLED_LABELS` is skipped: a player it would otherwise have
matched falls through to the next rule, rather than silently keeping the
disabled label.

Every threshold is a starting value tuned on the harness
(`storage/verdict_backtest.py`).
"""

import statistics
from collections.abc import Mapping
from dataclasses import dataclass

from core.inputs import PlayerInputs
from core.reliability import RELIABLE_CLASSES

LABELS = (
    "Unavailable", "Unproven", "Sell high", "Elite", "Bargain", "Rising",
    "Rotation risk", "Overpriced", "Avoid", "Fair price",
)
#: Labels the harness could not show beat chance (spec §5.3: dropped or reworked).
#: Rotation risk — 2026-10-07 walk-forward run, 33 dates: mean minutes vs the
#: same-day position mean −26.6 (90% CI −39.4 … −14.4, n=993, 121 players); its
#: players played *more*. The baseline includes unproven and zero-minute players,
#: so rework it against comparable-quality players before re-enabling.
#: DEFAULT_THRESHOLDS unchanged: no coarse-grid neighbour beat the defaults
#: (Elite and Rising beat chance in all 81 combinations; Bargain had no scorable
#: outcome in any).
DISABLED_LABELS: frozenset[str] = frozenset({"Rotation risk"})
#: Never disabled: Unavailable/Unproven state a fact, Fair price is the fallback.
_ALWAYS_ON = frozenset({"Unavailable", "Unproven", "Fair price"})


@dataclass(frozen=True)
class Thresholds:
    elite_quality: float = 90.0
    bargain_value: float = 80.0
    bargain_quality: float = 50.0
    rising_outlook: float = 85.0
    rotation_quality: float = 50.0
    overpriced_value: float = 20.0
    avoid_quality: float = 25.0
    good_value: float = 60.0
    easy_fixtures: float = 1.08  # fixture multiplier at/above -> "easy next 3"
    tough_fixtures: float = 0.92
    minutes_trend: float = 15.0  # minutes per match


DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class Cutoffs:
    median_price: dict[str, float]  # per position


def position_cutoffs(inputs: Mapping[int, PlayerInputs]) -> Cutoffs:
    """The median price within each position, over every player with a price."""
    by_pos: dict[str, list[float]] = {}
    for i in inputs.values():
        if i.price is not None:
            by_pos.setdefault(i.position, []).append(i.price)
    return Cutoffs({pos: statistics.median(prices) for pos, prices in by_pos.items()})


@dataclass(frozen=True)
class Verdict:
    player_id: int
    label: str
    tags: tuple[str, ...]  # at most two
    reason: str
    confidence: str  # high | medium | low
    deciding: dict[str, float | str | None]  # the inputs the rule read, for the step table


def _pct(ranks: Mapping, key: str) -> float | None:
    r = ranks.get(key)
    return r.percentile if r else None


def _eur(x: float) -> str:
    if abs(x) >= 1_000_000:
        return f"€{x / 1_000_000:.1f}M"
    return f"€{round(x / 1000)}k"


def _overpriced_matches(v: float | None, price: int | None, median: float | None,
                        t: Thresholds) -> bool:
    return (
        v is not None and v <= t.overpriced_value
        and price is not None and median is not None and price >= median
    )


def _reason(i: PlayerInputs, label: str, median: float | None,
            q: float | None, v: float | None, o: float | None) -> str:
    pos = i.position
    cls = i.reliability.cls
    p_start = i.reliability.p_start_next
    if label == "Unavailable":
        word = "Injured" if i.availability == "injured" else "Suspended"
        return f"{word} — won't play the next match."
    if label == "Unproven":
        return f"Not enough evidence: {i.evidence.reason}."
    if label == "Sell high":
        pct = abs(i.outlook.expected_pct)
        minutes_dropping = (
            i.reliability.minutes_trend is not None and i.reliability.minutes_trend < 0
        )
        extra = ", minutes dropping" if minutes_dropping else " and scoring under his rate"
        return f"Priced above the {pos} median, expected to fall {pct:.1f}% this week{extra}."
    if label == "Elite":
        return f"Top-{100 - q:.0f}% {pos} output, {cls.lower()} starter ({p_start:.0%} to start)."
    if label == "Bargain":
        return (f"Top-{100 - v:.0f}% {pos} points per €, {cls.lower()} starter, "
                f"priced {_eur(i.price)}.")
    if label == "Rising":
        pct = abs(i.outlook.expected_pct)
        return f"Expected to rise {pct:.1f}% this week — top-{100 - o:.0f}% {pos} outlook."
    if label == "Rotation risk":
        return f"Good {pos} output (top-{100 - q:.0f}%), but only {p_start:.0%} to start."
    if label == "Overpriced":
        return (f"Bottom-{v:.0f}% {pos} points per € at {_eur(i.price)}, "
                f"above the position median.")
    if label == "Avoid":
        falling = i.outlook is not None and i.outlook.direction == "fall"
        word = "falling in price" if falling else "rarely plays"
        return f"Bottom-{q:.0f}% {pos} output and {word}."
    return "Priced about right for what he gives — no strong signal either way."


def _confidence(i: PlayerInputs, label: str) -> str:
    return "high" if label == "Unavailable" else i.confidence


def _tags(i: PlayerInputs, t: Thresholds, label: str) -> tuple[str, ...]:
    candidates: list[tuple[float, int, str]] = []
    if i.confidence == "low":
        candidates.append((10.0, 0, "low confidence"))
    if i.outlook is not None:
        pct = i.outlook.expected_pct
        if i.outlook.direction == "rise":
            candidates.append((abs(pct), 1, "price rising"))
        elif i.outlook.direction == "fall":
            candidates.append((abs(pct), 1, "price falling"))
    if i.fixture_multiplier is not None:
        if i.fixture_multiplier >= t.easy_fixtures:
            candidates.append((abs(i.fixture_multiplier - 1) / 0.08, 2, "easy next 3"))
        elif i.fixture_multiplier <= t.tough_fixtures:
            candidates.append((abs(i.fixture_multiplier - 1) / 0.08, 2, "tough next 3"))
    trend = i.reliability.minutes_trend
    if trend is not None and abs(trend) >= t.minutes_trend:
        name = "minutes up" if trend > 0 else "minutes down"
        candidates.append((abs(trend) / 15, 3, name))
    v = _pct(i.ranks, "pointsValue")
    if label == "Elite" and v is not None and v >= t.good_value:
        candidates.append(((v - 60) / 20 + 1, 4, "good value"))
    candidates.sort(key=lambda c: (-c[0], c[1]))
    return tuple(c[2] for c in candidates[:2])


def _deciding(i: PlayerInputs, median: float | None, q: float | None, v: float | None,
              o: float | None) -> dict[str, float | str | None]:
    return {
        "qualityPct": q,
        "valuePct": v,
        "outlookPct": o,
        "class": i.reliability.cls,
        "medianPrice": median,
        "price": i.price,
        "availability": i.availability,
        "confidence": i.confidence,
    }


def _build(i: PlayerInputs, label: str, t: Thresholds, median: float | None,
           q: float | None, v: float | None, o: float | None) -> Verdict:
    return Verdict(
        player_id=i.player_id,
        label=label,
        tags=_tags(i, t, label),
        reason=_reason(i, label, median, q, v, o),
        confidence=_confidence(i, label),
        deciding=_deciding(i, median, q, v, o),
    )


def verdict(
    i: PlayerInputs, cutoffs: Cutoffs, t: Thresholds = DEFAULT_THRESHOLDS,
    disabled: frozenset[str] = DISABLED_LABELS,
) -> Verdict:
    q = _pct(i.ranks, "power")
    v = _pct(i.ranks, "pointsValue")
    o = _pct(i.ranks, "outlook")
    median = cutoffs.median_price.get(i.position)
    cls = i.reliability.cls
    outlook = i.outlook

    def enabled(label: str) -> bool:
        return label in _ALWAYS_ON or label not in disabled

    if enabled("Unavailable") and i.availability in {"injured", "suspended"}:
        return _build(i, "Unavailable", t, median, q, v, o)

    if enabled("Unproven") and not i.evidence.ok:
        return _build(i, "Unproven", t, median, q, v, o)

    if enabled("Sell high") and (
        i.price is not None and median is not None and i.price >= median
        and outlook is not None and outlook.direction == "fall" and outlook.drop_risk
        and (
            (i.reliability.minutes_trend is not None and i.reliability.minutes_trend < 0)
            or (i.points_vs_expected is not None and i.points_vs_expected < 0)
        )
    ):
        return _build(i, "Sell high", t, median, q, v, o)

    if enabled("Elite") and (
        i.evidence.ok and q is not None and q >= t.elite_quality and cls in RELIABLE_CLASSES
    ):
        return _build(i, "Elite", t, median, q, v, o)

    if enabled("Bargain") and (
        i.evidence.ok and v is not None and v >= t.bargain_value
        and q is not None and q >= t.bargain_quality
        and cls in RELIABLE_CLASSES and i.confidence == "high"
    ):
        return _build(i, "Bargain", t, median, q, v, o)

    if enabled("Rising") and (
        i.evidence.ok and o is not None and o >= t.rising_outlook
        and outlook is not None and outlook.direction == "rise"
        and cls in RELIABLE_CLASSES
        and not _overpriced_matches(v, i.price, median, t)
    ):
        return _build(i, "Rising", t, median, q, v, o)

    if enabled("Rotation risk") and (
        q is not None and q >= t.rotation_quality and cls in {"Rotation", "Fringe"}
    ):
        return _build(i, "Rotation risk", t, median, q, v, o)

    if enabled("Overpriced") and _overpriced_matches(v, i.price, median, t):
        return _build(i, "Overpriced", t, median, q, v, o)

    if enabled("Avoid") and (
        q is not None and q <= t.avoid_quality
        and ((outlook is not None and outlook.direction == "fall") or cls == "Fringe")
    ):
        return _build(i, "Avoid", t, median, q, v, o)

    return _build(i, "Fair price", t, median, q, v, o)


def verdicts(
    inputs: Mapping[int, PlayerInputs], t: Thresholds = DEFAULT_THRESHOLDS,
    disabled: frozenset[str] = DISABLED_LABELS,
) -> dict[int, Verdict]:
    cutoffs = position_cutoffs(inputs)
    return {pid: verdict(i, cutoffs, t, disabled) for pid, i in inputs.items()}
