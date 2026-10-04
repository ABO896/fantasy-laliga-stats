"""Every verdict input for every player, as of a date (spec §4). Pure.

One function, `compute_inputs`, and every caller uses it — the live app and
the verdict validation harness alike — so what the app shows and what the
backtest scores can never drift apart. Everything is filtered to `as_of`:
the snapshot state is the latest at or before it, the price the latest daily
price at or before it, and current-season points only the jornadas in
`known_weeks` (those knowable at `as_of`; earlier seasons are used in full).

Power is `storage.our_models.compute_player_analytics`' recipe exactly, on
the visible rows. Reliability, evidence, xP over the next `horizon` jornadas,
a within-position replacement level and points value, the market outlook and
within-position ranks are layered on top.

**Recorded deviation from spec §4.3:** xP over the window is fed
reliability's `p_start_next` as its starter probability, not `p_play_next`.
xP's `WITH_STARTER` coefficients were fitted on the source's *starter*
probability; a play probability counts sub cameos and would overstate every
rotation player. `p_play_next` is still computed and shown.

Missing inputs are `None`, with a reason where the verdict needs one — never
a silent default (spec §8).
"""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date

from core import analytics as an
from core import expected_points as xp
from core.market_v2 import Outlook
from core.ranks import Rank, position_ranks
from core.reliability import (
    DEFAULT_PRIOR,
    RELIABLE_CLASSES,
    ClubMatch,
    Evidence,
    Prior,
    Reliability,
    evidence,
    position_priors,
    reliability,
)

#: Replacement level: the median xP of players priced at or below this
#: percentile of their position's prices.
REPLACEMENT_PRICE_PCT = 30
#: Fewer reliable players than this in the cheap pool → use every cheap player.
MIN_REPLACEMENT_POOL = 3
#: Recent team matches compared against the Power rate for points_vs_expected.
VS_EXPECTED_MATCHES = 3
CONFIDENCE_ORDER = ("low", "medium", "high")


@dataclass(frozen=True)
class PlayerBase:
    player_id: int
    name: str
    team: str
    position: str


@dataclass(frozen=True)
class SnapshotState:
    as_of: date
    market_value: int
    availability: str
    starter_probability: float | None


@dataclass(frozen=True)
class UpcomingMatch:
    opponent: str
    is_home: bool
    team_goals: float | None
    clean_sheet: float | None
    odds_source: str | None = None


@dataclass(frozen=True)
class InputsData:
    season: int
    players: dict[int, PlayerBase]
    gameweek_rows: list[an.GameweekRow]  # every season
    match_lines: dict[int, dict[int, tuple[int, str]]]  # pid -> week -> (minutes, appearance)
    page_players: frozenset[int]  # players with an ok player-page fetch
    prices: dict[int, dict[date, int]]  # PlayerMarketDaily, this season
    snapshots: dict[int, list[SnapshotState]]  # oldest first
    last_season_means: dict[int, float]
    last_season_apps: dict[int, int]
    cash_per_point: int


@dataclass(frozen=True)
class WindowXp:
    total: float
    matches: list[tuple[str, bool, float]]  # (opponent, is_home, xP)
    basis: str  # e.g. "form+starter+odds"; "blank" when no match in the window


@dataclass(frozen=True)
class PlayerInputs:
    player_id: int
    position: str
    team: str
    price: int | None
    price_as_of: date | None  # the date the price was captured/published
    availability: str
    power_inputs: an.PowerInputs | None
    power: an.PowerResult | None
    reliability: Reliability
    prior: Prior  # the position prior reliability shrunk toward
    evidence: Evidence
    xpts: WindowXp | None
    replacement: float | None
    points_value: float | None
    points_value_reason: str | None
    points_vs_expected: float | None
    outlook: Outlook | None
    expected_return_eur: float | None
    fixture_multiplier: float | None
    confidence: str  # high | medium | low
    ranks: dict[str, Rank]  # keys: power, pointsValue, outlook, xpts, start, price


def _state(
    data: InputsData, pid: int, as_of: date
) -> tuple[SnapshotState | None, int | None, date | None]:
    snap = None
    for s in data.snapshots.get(pid, []):
        if s.as_of <= as_of and (snap is None or s.as_of >= snap.as_of):
            snap = s
    days = [d for d in data.prices.get(pid, {}) if d <= as_of]
    if days:
        price_as_of = max(days)
        price = data.prices[pid][price_as_of]
    elif snap is not None:
        price, price_as_of = snap.market_value, snap.as_of
    else:
        price, price_as_of = None, None
    return snap, price, price_as_of


def _percentile(values: Sequence[float], pct: float) -> float:
    """Linear interpolation between closest ranks."""
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _window_xp(
    position: str,
    history: Sequence[int],
    prior_mean: float | None,
    rel: Reliability,
    availability: str,
    matches: Sequence[UpcomingMatch] | None,
    horizon: int,
) -> WindowXp | None:
    if matches is None:
        return None
    window = list(matches)[:horizon]
    if not window:
        return WindowXp(0.0, [], "blank")
    out, basis = [], None
    for m in window:
        r = xp.expected_points(xp.XpInputs(
            position=position,
            history=history,
            prior_season_mean=prior_mean,
            starter_probability=rel.p_start_next * 100,
            availability=availability,
            fixture=xp.FixtureContext(m.opponent, m.is_home, m.team_goals, m.clean_sheet,
                                      m.odds_source),
            has_fixture=True,
        ))
        basis = basis or r.basis
        out.append((m.opponent, m.is_home, r.value))
    return WindowXp(sum(v for _, _, v in out), out, basis)


def compute_inputs(
    data: InputsData,
    as_of: date,
    known_weeks: set[int],
    upcoming: Mapping[str, Sequence[UpcomingMatch]],
    outlooks: Mapping[int, Outlook],
    fixture_multipliers: Mapping[str, float] | None = None,
    horizon: int = 3,
) -> dict[int, PlayerInputs]:
    season = data.season
    rows = [
        r for r in data.gameweek_rows
        if r.season_year < season or (r.season_year == season and r.week in known_weeks)
    ]
    team_of = {pid: b.team for pid, b in data.players.items()}
    played = an.team_played_weeks(rows, team_of)
    timeline = sorted({(r.season_year, r.week) for r in rows})
    season_timeline = [k for k in timeline if k[0] == season]
    by_player: dict[int, list[an.GameweekRow]] = {}
    for r in rows:
        by_player.setdefault(r.player_id, []).append(r)

    # Club matches this season, per player with page data.
    club_matches: dict[int, list[ClubMatch]] = {}
    for pid in data.page_players:
        base = data.players.get(pid)
        if base is None:
            continue
        lines = data.match_lines.get(pid, {})
        weeks = sorted(
            w for s, w in played.get(base.team, set()) if s == season and w in known_weeks
        )
        club_matches[pid] = [
            ClubMatch(w, *lines[w]) if w in lines else ClubMatch(w, 0, "dnp") for w in weeks
        ]
    priors = position_priors(
        {pid: (data.players[pid].position, ms) for pid, ms in club_matches.items()}
    )

    window = an.FORM_WINDOW + an.BASELINE_WINDOW
    partial: dict[int, dict] = {}
    for pid, base in data.players.items():
        snap, price, price_as_of = _state(data, pid, as_of)
        if snap is None and price is None:
            continue
        availability = snap.availability if snap is not None else "available"
        starter = snap.starter_probability if snap is not None else None
        position = base.position
        team_weeks = played.get(base.team, set())
        rows_p = by_player.get(pid, [])
        series = an.player_series(timeline, rows_p, n=window, team_weeks=team_weeks)
        history = an.player_series(season_timeline, rows_p, n=len(season_timeline),
                                   team_weeks=team_weeks)
        prior_mean = data.last_season_means.get(pid)
        p_inputs = an.power_inputs(series, history, prior_mean, position, availability)
        power = an.power_score(p_inputs) if p_inputs else None

        prior = priors.get(position, DEFAULT_PRIOR)
        rel = reliability(club_matches.get(pid), prior, starter, availability)
        lines = data.match_lines.get(pid, {}) if pid in data.page_players else {}
        with_minutes = sum(1 for w, (mins, _) in lines.items() if w in known_weeks and mins > 0)
        ev = evidence(with_minutes, data.last_season_apps.get(pid, 0))

        xpts = _window_xp(position, history, prior_mean, rel, availability,
                          upcoming.get(base.team), horizon)
        vs_expected = (
            statistics.fmean(history[-VS_EXPECTED_MATCHES:]) - p_inputs.rate
            if p_inputs is not None and len(history) >= VS_EXPECTED_MATCHES
            else None
        )
        partial[pid] = dict(base=base, price=price, price_as_of=price_as_of,
                            availability=availability, p_inputs=p_inputs, power=power, rel=rel,
                            prior=prior, ev=ev, xpts=xpts, vs_expected=vs_expected)

    replacement = _replacement_levels(partial)

    out: dict[int, PlayerInputs] = {}
    for pid, p in partial.items():
        base, price, xpts, ev = p["base"], p["price"], p["xpts"], p["ev"]
        repl = replacement.get(base.position)
        if not ev.ok:
            value, reason = None, ev.reason
        elif xpts is None:
            value, reason = None, "no fixture data"
        elif repl is None:
            value, reason = None, "no replacement level"
        elif price is None or price <= 0:
            value, reason = None, "no price"
        else:
            value, reason = (xpts.total - repl) * data.cash_per_point / price, None
        outlook = outlooks.get(pid)
        expected_return = (
            xpts.total * data.cash_per_point + price * outlook.expected_pct / 100
            if xpts is not None and price is not None and outlook is not None
            else None
        )
        confidence = CONFIDENCE_ORDER[min(CONFIDENCE_ORDER.index(p["rel"].confidence),
                                          CONFIDENCE_ORDER.index(ev.level))]
        out[pid] = PlayerInputs(
            player_id=pid,
            position=base.position,
            team=base.team,
            price=price,
            price_as_of=p["price_as_of"],
            availability=p["availability"],
            power_inputs=p["p_inputs"],
            power=p["power"],
            reliability=p["rel"],
            prior=p["prior"],
            evidence=ev,
            xpts=xpts,
            replacement=repl,
            points_value=value,
            points_value_reason=reason,
            points_vs_expected=p["vs_expected"],
            outlook=outlook,
            expected_return_eur=expected_return,
            fixture_multiplier=(fixture_multipliers or {}).get(base.team),
            confidence=confidence,
            ranks={},
        )

    positions = {pid: i.position for pid, i in out.items()}
    metrics = {
        "power": {pid: i.power.power_ppg if i.power else None for pid, i in out.items()},
        "pointsValue": {pid: i.points_value for pid, i in out.items()},
        "outlook": {pid: i.outlook.expected_pct if i.outlook else None for pid, i in out.items()},
        "xpts": {pid: i.xpts.total if i.xpts else None for pid, i in out.items()},
        "start": {pid: i.reliability.p_start_next for pid, i in out.items()},
        "price": {pid: i.price for pid, i in out.items()},
    }
    ranked = {key: position_ranks(values, positions) for key, values in metrics.items()}
    return {
        pid: replace(i, ranks={key: r[pid] for key, r in ranked.items() if pid in r})
        for pid, i in out.items()
    }


def _replacement_levels(partial: Mapping[int, dict]) -> dict[str, float | None]:
    """Per position: the median xP over the window of players priced at or
    below the position's 30th-percentile price who are Nailed or Regular —
    or of every such cheap player when fewer than 3 are."""
    by_pos: dict[str, list[dict]] = {}
    for p in partial.values():
        if p["xpts"] is not None and p["price"] is not None:
            by_pos.setdefault(p["base"].position, []).append(p)
    out: dict[str, float | None] = {}
    for position, group in by_pos.items():
        cut = _percentile([p["price"] for p in group], REPLACEMENT_PRICE_PCT)
        cheap = [p for p in group if p["price"] <= cut]
        pool = [p for p in cheap if p["rel"].cls in RELIABLE_CLASSES]
        if len(pool) < MIN_REPLACEMENT_POOL:
            pool = cheap
        out[position] = statistics.median(p["xpts"].total for p in pool) if pool else None
    return out
