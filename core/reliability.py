"""Reliability — how much a player plays (spec §4.2). Pure.

From his club's matches this season (weeks his club did not play are not
passed in, so a postponement is never a "did not play"), recency-weighted
with a 5-match half-life:

    start share, play share (any minutes), sub share = play − start,
    minutes share (of 90)

shrunk toward a position prior with 3 pseudo-matches, blended with the
source's starter probability at weight 0.3, and only then multiplied by
availability (injured/suspended → 0, doubtful × 0.6). The class reads the
final start probability: Nailed ≥ 0.8, Regular ≥ 0.55, Rotation ≥ 0.25,
else Fringe. Every threshold is a starting value the verdict harness tunes.

Starts are inferred from minutes (≥ 60) because the source has no start
flag: an early injury substitution reads as a sub — accepted (spec §10).
"""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

HALF_LIFE = 5.0
PRIOR_WEIGHT = 3.0
SOURCE_BLEND = 0.3
DOUBTFUL_FACTOR = 0.6
CLASS_THRESHOLDS = (("Nailed", 0.8), ("Regular", 0.55), ("Rotation", 0.25))
RELIABLE_CLASSES = frozenset({"Nailed", "Regular"})
TREND_RECENT = 3
TREND_BEFORE = 5
#: Club matches for medium / high confidence.
MEDIUM_MATCHES = 3
HIGH_MATCHES = 6
#: Evidence floor (spec §5.1).
MIN_MATCHES = 3
MIN_LAST_SEASON_APPS = 10
UNAVAILABLE = frozenset({"injured", "suspended"})


@dataclass(frozen=True)
class ClubMatch:
    week: int
    minutes: int
    appearance: str  # start | sub | dnp


@dataclass(frozen=True)
class Prior:
    start: float
    play: float


DEFAULT_PRIOR = Prior(0.45, 0.6)


@dataclass(frozen=True)
class Reliability:
    p_play_next: float
    p_start_next: float
    start_share: float | None
    play_share: float | None
    sub_share: float | None
    minutes_share: float | None
    shrunk_start: float
    shrunk_play: float
    source_starter: float | None  # 0–1
    availability: str
    availability_factor: float
    minutes_trend: float | None  # minutes per match, last 3 minus the 5 before
    matches: int  # club matches observed
    appearances: int  # of which he played any minutes
    cls: str
    confidence: str
    basis: str  # matches | source-only


def _weights(n: int) -> list[float]:
    return [0.5 ** ((n - 1 - i) / HALF_LIFE) for i in range(n)]


def _shares(ms: Sequence[ClubMatch]) -> tuple[float, float, float, int] | None:
    if not ms:
        return None
    w = _weights(len(ms))
    total = sum(w)
    start = sum(wi for wi, m in zip(w, ms, strict=True) if m.appearance == "start") / total
    play = sum(wi for wi, m in zip(w, ms, strict=True) if m.minutes > 0) / total
    minutes = sum(wi * min(m.minutes, 90) / 90 for wi, m in zip(w, ms, strict=True)) / total
    # Shrinkage strength is the raw match count (pseudo-count semantics), not
    # the recency-decayed sum of weights used to compute the shares above —
    # the latter caps out below the 3-pseudo-match prior weight could ever
    # overcome, so an ever-present starter would never reach "Nailed".
    return start, play, minutes, len(ms)


def _class(p_start: float) -> str:
    for name, threshold in CLASS_THRESHOLDS:
        if p_start >= threshold:
            return name
    return "Fringe"


def _trend(ms: Sequence[ClubMatch]) -> float | None:
    if len(ms) < TREND_RECENT + 1:
        return None
    recent = [m.minutes for m in ms[-TREND_RECENT:]]
    before = [m.minutes for m in ms[:-TREND_RECENT][-TREND_BEFORE:]]
    return statistics.fmean(recent) - statistics.fmean(before)


def reliability(
    matches: Sequence[ClubMatch] | None,
    prior: Prior,
    source_starter_pct: float | None,
    availability: str,
) -> Reliability:
    ms = sorted(matches or [], key=lambda m: m.week)
    shares = _shares(ms)
    if shares is None:
        start = play = minutes = None
        weight = 0.0
    else:
        start, play, minutes, weight = shares
    shrunk_start = ((start or 0) * weight + PRIOR_WEIGHT * prior.start) / (weight + PRIOR_WEIGHT)
    shrunk_play = ((play or 0) * weight + PRIOR_WEIGHT * prior.play) / (weight + PRIOR_WEIGHT)

    s = None if source_starter_pct is None else max(0.0, min(1.0, source_starter_pct / 100))
    p_start = shrunk_start if s is None else (1 - SOURCE_BLEND) * shrunk_start + SOURCE_BLEND * s
    p_play = max(shrunk_play, p_start)

    if availability in UNAVAILABLE:
        factor = 0.0
    elif availability == "doubtful":
        factor = DOUBTFUL_FACTOR
    else:
        factor = 1.0
    p_start *= factor
    p_play *= factor

    n = len(ms)
    basis = "source-only" if matches is None else "matches"
    confidence = (
        "high" if n >= HIGH_MATCHES else "medium" if n >= MEDIUM_MATCHES else "low"
    )
    if basis == "source-only":
        confidence = "low"
    return Reliability(
        p_play_next=p_play,
        p_start_next=p_start,
        start_share=start,
        play_share=play,
        sub_share=None if start is None else play - start,
        minutes_share=minutes,
        shrunk_start=shrunk_start,
        shrunk_play=shrunk_play,
        source_starter=s,
        availability=availability,
        availability_factor=factor,
        minutes_trend=_trend(ms),
        matches=n,
        appearances=sum(1 for m in ms if m.minutes > 0),
        cls=_class(p_start),
        confidence=confidence,
        basis=basis,
    )


def position_priors(per_player: Mapping[int, tuple[str, Sequence[ClubMatch]]]) -> dict[str, Prior]:
    starts: dict[str, list[float]] = {}
    plays: dict[str, list[float]] = {}
    for position, ms in per_player.values():
        if len(ms) < MEDIUM_MATCHES:
            continue
        shares = _shares(sorted(ms, key=lambda m: m.week))
        starts.setdefault(position, []).append(shares[0])
        plays.setdefault(position, []).append(shares[1])
    out = {pos: DEFAULT_PRIOR for pos in ("POR", "DEF", "MED", "DEL")}
    for pos in starts:
        out[pos] = Prior(statistics.fmean(starts[pos]), statistics.fmean(plays[pos]))
    return out


@dataclass(frozen=True)
class Evidence:
    matches_with_minutes: int
    last_season_apps: int
    ok: bool
    level: str  # high | medium | low
    reason: str | None


def evidence(matches_with_minutes: int, last_season_apps: int) -> Evidence:
    ok = matches_with_minutes >= MIN_MATCHES or (
        last_season_apps >= MIN_LAST_SEASON_APPS and matches_with_minutes >= 1
    )
    level = (
        "high" if matches_with_minutes >= HIGH_MATCHES
        else "medium" if ok
        else "low"
    )
    reason = None if ok else (
        f"{matches_with_minutes} match{'es' if matches_with_minutes != 1 else ''} with minutes "
        f"this season (needs {MIN_MATCHES}, or {MIN_LAST_SEASON_APPS} last season and 1 now)"
    )
    return Evidence(matches_with_minutes, last_season_apps, ok, level, reason)
