"""Verdict harness maths — outcomes, signed claims, a player-clustered
bootstrap (Plan C, Task 3). Pure: no database, no clock, stdlib only
(`random.Random(seed)`, no numpy) so the backtest is reproducible without
extra dependencies.

Each label that makes a forward claim (`CLAIMS`) is scored against what an
*average same-position player did on the same day* — never an absolute
threshold, since "good" moves with the season. `sign` is `+1` when the
label claims "more than the position" (Elite's points, Bargain's points
per €, Rising's price move) and `-1` when it claims "less" (Sell high's
price move, Overpriced's points per €, Avoid's points, Rotation risk's
minutes).

The point estimate (`mean_diff`) is a plain mean over every qualifying
observation. The confidence interval around it is not: observations from
the same player are correlated (a hot streak shows up as several
"wins" from one player, not independent evidence), so the bootstrap
resamples *players*, not observations, pooling whichever players are
drawn and taking the mean of everything they contributed. A label beats
chance only when the low end of that interval still clears zero.

The "position" baseline is **eligible** observations only — available (not
injured/suspended) and past the evidence floor on the day — the players a
label could actually have been given. Injured, unproven and zero-minute
players would otherwise drag the same-day mean down and flatter every label.

The two price labels also carry a **momentum baseline** (`MOMENTUM`): the
same claim measured over a naive selection — the eligible players whose
7-day price move was in the top (Rising) or bottom (Sell high) 15% of their
position that day. A price label that does not beat plain momentum adds
nothing a sorted column would not.

Labels with no forward claim (`Unavailable`, `Unproven`, `Fair price`) are
reported with a count only — they are not claims to validate.
"""

import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

#: What each label claims, and how the claim is measured over the following
#: 3 jornadas / 7 days. sign +1: the label says "more than the position";
#: -1: "less".
CLAIMS: dict[str, tuple[str, int]] = {
    "Elite": ("points", +1),
    "Bargain": ("points_per_m", +1),
    "Rising": ("price_pct", +1),
    "Sell high": ("price_pct", -1),
    "Overpriced": ("points_per_m", -1),
    "Avoid": ("points", -1),
    "Rotation risk": ("minutes", -1),
}


#: The naive momentum rule each price label is compared against: +1 picks the
#: top `MOMENTUM_SHARE` of the position's 7-day movers that day, -1 the bottom.
MOMENTUM: dict[str, int] = {"Rising": +1, "Sell high": -1}
MOMENTUM_SHARE = 0.15


@dataclass(frozen=True)
class Observation:
    day: date
    player_id: int
    position: str
    label: str
    outcomes: dict[str, float | None]  # keys: points, points_per_m, price_pct, minutes
    #: Available and past the evidence floor on `day` — part of the baseline.
    eligible: bool = True
    #: The 7-day price move up to `day` (%), for the momentum baseline.
    momentum: float | None = None


@dataclass(frozen=True)
class MomentumBaseline:
    n: int
    hit_rate: float | None
    mean_diff: float | None


@dataclass(frozen=True)
class LabelReport:
    label: str
    metric: str
    n: int  # observations with the outcome
    players: int
    hit_rate: float | None  # share beating the same-day position mean in the claimed direction
    base_rate: float | None  # the same share over every observation of those positions/days
    mean_diff: float | None  # mean of sign x (outcome - same-day position mean)
    ci_low: float | None  # 90% clustered-bootstrap interval of mean_diff
    ci_high: float | None
    beats_chance: bool  # ci_low > 0
    #: The same claim over the naive momentum selection (price labels only).
    momentum: MomentumBaseline | None = None


def _percentile(values: Sequence[float], pct: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def bootstrap_ci(
    values_by_player: Mapping[int, Sequence[float]], resamples: int, seed: int,
    level: float = 0.9,
) -> tuple[float, float] | None:
    """Resample players with replacement, pool whichever are drawn, take the
    mean; repeat `resamples` times and report the `level` interval of those
    means. `None` with fewer than 5 players — too thin to bootstrap."""
    players = list(values_by_player.keys())
    if len(players) < 5:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        chosen = [rng.choice(players) for _ in range(len(players))]
        pooled = [v for p in chosen for v in values_by_player[p]]
        if pooled:
            means.append(statistics.fmean(pooled))
    if not means:
        return None
    alpha = (1 - level) / 2
    return _percentile(means, alpha * 100), _percentile(means, (1 - alpha) * 100)


def _group_means(
    obs: Sequence[Observation],
) -> dict[str, dict[tuple[date, str], float]]:
    """Per metric, the mean outcome within each (day, position) — over every
    eligible observation that day with that outcome, whatever its label."""
    groups: dict[str, dict[tuple[date, str], list[float]]] = {}
    for o in obs:
        if not o.eligible:
            continue
        for metric, value in o.outcomes.items():
            if value is None:
                continue
            groups.setdefault(metric, {}).setdefault((o.day, o.position), []).append(value)
    return {
        metric: {key: statistics.fmean(values) for key, values in by_key.items()}
        for metric, by_key in groups.items()
    }


def _unclaimed_report(label: str, label_obs: Sequence[Observation]) -> LabelReport:
    return LabelReport(
        label=label, metric="", n=len(label_obs),
        players=len({o.player_id for o in label_obs}),
        hit_rate=None, base_rate=None, mean_diff=None, ci_low=None, ci_high=None,
        beats_chance=False,
    )


def label_reports(
    obs: Sequence[Observation], resamples: int = 1000, seed: int = 7,
) -> list[LabelReport]:
    means = _group_means(obs)
    reports: list[LabelReport] = []
    for label in sorted({o.label for o in obs}):
        label_obs = [o for o in obs if o.label == label]
        if label not in CLAIMS:
            reports.append(_unclaimed_report(label, label_obs))
            continue

        metric, sign = CLAIMS[label]
        by_key = means.get(metric, {})
        qualifying = [o for o in label_obs if o.outcomes.get(metric) is not None]

        diffs_by_player: dict[int, list[float]] = {}
        diffs: list[float] = []
        hits = 0
        keys_seen: set[tuple[date, str]] = set()
        for o in qualifying:
            key = (o.day, o.position)
            if key not in by_key:  # no eligible peer that day: nothing to compare to
                continue
            keys_seen.add(key)
            d = sign * (o.outcomes[metric] - by_key[key])
            diffs.append(d)
            diffs_by_player.setdefault(o.player_id, []).append(d)
            if d > 0:
                hits += 1
        if not diffs:
            reports.append(LabelReport(label, metric, 0, 0, None, None, None, None, None,
                                       False))
            continue
        n = len(diffs)
        players = len(diffs_by_player)
        hit_rate = hits / n

        base_total = 0
        base_hits = 0
        for o in obs:
            value = o.outcomes.get(metric)
            key = (o.day, o.position)
            if not o.eligible or value is None or key not in keys_seen:
                continue
            d = sign * (value - by_key[key])
            base_total += 1
            if d > 0:
                base_hits += 1
        base_rate = base_hits / base_total if base_total else None

        mean_diff = statistics.fmean(diffs)
        ci = bootstrap_ci(diffs_by_player, resamples, seed)
        ci_low, ci_high = ci if ci is not None else (None, None)
        beats_chance = ci_low is not None and ci_low > 0

        reports.append(LabelReport(
            label=label, metric=metric, n=n, players=players, hit_rate=hit_rate,
            base_rate=base_rate, mean_diff=mean_diff, ci_low=ci_low, ci_high=ci_high,
            beats_chance=beats_chance,
            momentum=(
                momentum_baseline(obs, metric, MOMENTUM[label], by_key)
                if label in MOMENTUM else None
            ),
        ))
    return reports


def _momentum_rank(value: float, others: Sequence[float]) -> float:
    """Share of the day's movers strictly below `value`, over `n - 1`."""
    return sum(v < value for v in others) / max(len(others) - 1, 1)


def momentum_baseline(
    obs: Sequence[Observation], metric: str, sign: int,
    by_key: Mapping[tuple[date, str], float],
) -> MomentumBaseline:
    """The claim `sign` on `metric`, measured over the naive momentum pick:
    eligible observations whose `momentum` is in the top (`sign` +1) or
    bottom (-1) `MOMENTUM_SHARE` of their (day, position). Same hit and
    diff definitions as the label itself."""
    movers: dict[tuple[date, str], list[float]] = {}
    for o in obs:
        if o.eligible and o.momentum is not None and o.outcomes.get(metric) is not None:
            movers.setdefault((o.day, o.position), []).append(o.momentum)

    diffs: list[float] = []
    for o in obs:
        key = (o.day, o.position)
        value = o.outcomes.get(metric)
        if not o.eligible or o.momentum is None or value is None or key not in by_key:
            continue
        rank = _momentum_rank(o.momentum, movers[key])
        picked = rank >= 1 - MOMENTUM_SHARE if sign > 0 else rank <= MOMENTUM_SHARE
        if picked:
            diffs.append(sign * (value - by_key[key]))
    if not diffs:
        return MomentumBaseline(0, None, None)
    return MomentumBaseline(
        n=len(diffs),
        hit_rate=sum(d > 0 for d in diffs) / len(diffs),
        mean_diff=statistics.fmean(diffs),
    )
