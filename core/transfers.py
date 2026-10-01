"""MODEL-05 and TRANSFER-01…05 — our own bids, bargains and transfer moves.

Pure: no database, no clock (callers pass `now`), no HTTP type. The storage
layer (`storage/transfers.py`) loads rows and hands plain values in. Every
constant below is an assumption or a calibration and is argued in
`docs/superpowers/specs/2026-09-27-bargains-and-transfers-design.md`.

Built on Phase 10, not beside it:

* **Expected return** starts from `PowerResult.quality_ppg` (ANALYTICS-06),
  weights it by fixture difficulty (`core.fixture_difficulty`, TRANSFER-03)
  and by the chance of playing, and — once MODEL-02 lands — blends in
  expected points at `EXPECTED_POINTS_WEIGHT`. Without expected
  points it degrades to the backward-looking form, not to nothing.
* **Bids** use our fair value (ANALYTICS-04) and our next-update prediction
  (MODEL-01), never the source's bid numbers.
* **Legality** is `core.squad_rules`, untouched: a move is `evaluate_add` on
  the squad minus the sold player, plus an XI-feasibility check that
  `evaluate_add` deliberately does not make.

Rule values (squad cap, formations, cash per point) come from `core.rules`
and are never restated here.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from core import analytics as an
from core.fixture_difficulty import FixtureView, TeamFixture, upcoming_fixtures
from core.freshness import _as_aware, is_stale, last_market_update
from core.rules import Rules, Violation
from core.squad_rules import SquadMember, evaluate_add, evaluate_squad

# --- constants ------------------------------------------------------------------------

#: Default look-ahead, in jornadas.
DEFAULT_JORNADAS = 3
#: How strongly fixture difficulty moves expected points. Per fixture the
#: multiplier is `1 + FIXTURE_WEIGHT · (1 − difficulty)`: an average opponent
#: at a neutral venue (1.0) is neutral; the strongest side away (~1.8) costs
#: ~24%, the weakest at home (~0.4) adds ~18%. Assumed, not fitted.
FIXTURE_WEIGHT = 0.3
#: Bounds on one fixture's multiplier, so an extreme strength rating can
#: never zero out or double a player.
FIXTURE_TERM_BOUNDS = (0.5, 1.5)
#: Chance-of-playing multiplier by the source's availability status — shared
#: with Power (`core.analytics`).
AVAILABILITY_FACTOR = an.AVAILABILITY_FACTOR
#: xP's share of expected return; assumed — Plan 3 replaces the blend.
EXPECTED_POINTS_WEIGHT = 0.5
#: Below this availability factor a player is never a suggested buy.
MIN_BUYABLE_AVAILABILITY = 0.5
#: Share of expected points that depends on starting: `STARTER_FLOOR +
#: (1 − STARTER_FLOOR) · p/100`. A floor because backward points already
#: reflect how often the player usually starts.
STARTER_FLOOR = 0.5
#: How many market updates of the predicted move a maximum bid may price in.
#: The market is overwhelmingly persistent (Phase 10 backtest: 95% of moves
#: keep their sign), so a rise tends to continue for a few updates.
MAX_BID_HORIZON_UPDATES = 3
#: Share of the valuation gap (fair / market − 1, when positive) worth
#: paying over market value. The gap is capped at `MAX_GAP_COUNTED` first:
#: not because ANALYTICS-04's log-log curve explodes (it no longer does),
#: but because the gap itself is noisy enough that an uncapped one would
#: let a single outlier dominate the bid.
SURPLUS_SHARE = 0.10
MAX_GAP_COUNTED = 1.0
#: A maximum bid never exceeds market value by more than this.
MAX_BID_PREMIUM = 0.25
#: Below this gain (points-equivalent) a swap is not worth suggesting.
MIN_GAIN = 0.5
#: Buy candidates kept per position before pairing — bounds the pair count.
CANDIDATES_PER_POSITION = 15
#: Jornada points older than this read as stale (one jornada a week).
JORNADA_STALE_DAYS = 7
#: The fixture window older than this reads as stale.
FIXTURES_STALE_DAYS = 7
#: Odds older than this read as stale (only once expected points use them).
ODDS_STALE_DAYS = 7
#: Per missed market update, confidence is multiplied by this.
MARKET_STALE_FACTOR = 0.8
#: Missed updates beyond this cost nothing more — confidence is already low.
MAX_MISSED_UPDATES_CHARGED = 4
#: Evidence: confidence scales from this floor to 1 as a player's recent
#: window fills.
EVIDENCE_FLOOR = 0.6
#: A bargain's expected return is at least this percentile of his position.
BARGAIN_MIN_PERCENTILE = 0.75
#: Confidence label thresholds.
HIGH_CONFIDENCE = 0.75
MEDIUM_CONFIDENCE = 0.5

#: The price a ceiling is compared against. The first three are BROWSE-05's
#: bases (the source's numbers); the last two are ours (MODEL-05).
PRICE_BASES = ("marketValue", "idealBid", "maxBid", "ourIdealBid", "ourMaxBid")

Ceiling = tuple[int, str]  # (maximum price in euros, basis)


# --- inputs -----------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayerInput:
    """Everything this module reads about one player, as plain values."""

    player_id: int
    name: str
    team: str
    position: str
    market_value: int
    source_ideal_bid: int | None
    source_max_bid: int | None
    availability: str
    starter_probability: float | None  # 0–100
    backward_ppg: float | None  # PowerResult.quality_ppg; None without a timeline
    recent_jornadas: int
    expected_points: float | None  # MODEL-02, next jornada; None until it lands
    fair_value: int | None  # ANALYTICS-04
    valuation_gap: float | None  # ANALYTICS-04, fair/market − 1
    economy: float | None  # ANALYTICS-07
    power_score: float | None  # ANALYTICS-06
    predicted_pct: float | None  # MODEL-01, next update
    prediction_confidence: str | None  # MODEL-01's own vocabulary


# --- MODEL-05: our bids ---------------------------------------------------------------


@dataclass(frozen=True)
class Bids:
    ideal: int
    maximum: int
    inputs: dict


def _unavailable(status: str) -> bool:
    return AVAILABILITY_FACTOR.get(status, 1.0) < MIN_BUYABLE_AVAILABILITY


def compute_bids(p: PlayerInput) -> Bids:
    """Our ideal and maximum bid.

    * **Ideal** = the value we predict the player will have after the next
      update: `mv · (1 + max(predicted %, 0)/100)`. A faller's ideal bid is
      market value — the official rules forbid bidding below it.
    * **Maximum** = `mv · (1 + H · max(predicted %, 0)/100
      + SURPLUS_SHARE · min(max(gap, 0), MAX_GAP_COUNTED))`, clamped between
      the ideal bid and `mv · (1 + MAX_BID_PREMIUM)`. No surplus for a player who is
      injured: his fair value describes a player who is playing.
    """
    mv = p.market_value
    rise = max(p.predicted_pct or 0.0, 0.0) / 100
    ideal = round(mv * (1 + rise))
    surplus = 0.0
    if p.valuation_gap is not None and not _unavailable(p.availability):
        surplus = mv * SURPLUS_SHARE * min(max(p.valuation_gap, 0.0), MAX_GAP_COUNTED)
    momentum = mv * (1 + MAX_BID_HORIZON_UPDATES * rise)
    cap = max(round(mv * (1 + MAX_BID_PREMIUM)), ideal)
    maximum = min(max(round(momentum + surplus), ideal), cap)
    return Bids(
        ideal=ideal,
        maximum=maximum,
        inputs={
            "marketValue": mv,
            "predictedPct": p.predicted_pct,
            "predictionConfidence": p.prediction_confidence,
            "fairValue": p.fair_value,
            "surplusCounted": round(surplus),
            "horizonUpdates": MAX_BID_HORIZON_UPDATES,
            "valuationGap": p.valuation_gap,
            "surplusShare": SURPLUS_SHARE,
            "maxGapCounted": MAX_GAP_COUNTED,
            "maxPremium": MAX_BID_PREMIUM,
        },
    )


# --- TRANSFER-03: fixture outlook -------------------------------------------------------


@dataclass(frozen=True)
class FixtureOutlook:
    multiplier: float
    available: bool  # False: no fixture data for this team, multiplier neutral
    jornadas: int
    fixtures: list[TeamFixture] = field(default_factory=list)
    driver: TeamFixture | None = None  # the fixture furthest from average


def _fixture_term(difficulty: float) -> float:
    lo, hi = FIXTURE_TERM_BOUNDS
    return min(max(1 + FIXTURE_WEIGHT * (1 - difficulty), lo), hi)


def fixture_outlook(fixtures: Sequence[TeamFixture] | None, jornadas: int) -> FixtureOutlook:
    """Average per-jornada fixture multiplier over the window.

    `None` means no fixture data for the team: neutral, and said so. An
    empty list means the data exists and the team has no match in the
    window — a blank, which genuinely costs points. Two matches in the
    window (a postponed one) count twice, for the same reason.
    """
    if fixtures is None or jornadas < 1:
        return FixtureOutlook(1.0, False, jornadas)
    total = sum(_fixture_term(f.difficulty) for f in fixtures)
    driver = max(fixtures, key=lambda f: abs(f.difficulty - 1), default=None)
    return FixtureOutlook(total / jornadas, True, jornadas, list(fixtures), driver)


def select_window(
    fixtures: Sequence[FixtureView], now: datetime, n: int
) -> tuple[list[int], list[FixtureView]]:
    """The next `n` *full* jornadas, plus any catch-up fixtures inside them.

    `fixture_difficulty.window_jornadas` places each jornada at its earliest
    *upcoming* kickoff, so a jornada that is mostly played but has a
    postponed match left reads as the very next jornada — and every team
    that already played it would be charged a blank. Here a jornada counts
    toward the window only while at least half its fixtures are still to
    come; a postponed fixture of an otherwise-played jornada that kicks off
    before the window ends is kept as an extra fixture for its two teams
    (which is what it is). Returns the window's full jornadas, in kickoff
    order, and every fixture to weigh.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    upcoming = upcoming_fixtures(fixtures, now)
    total: dict[int, int] = {}
    for f in fixtures:
        total[f.matchday] = total.get(f.matchday, 0) + 1
    remaining: dict[int, list[FixtureView]] = {}
    for f in upcoming:
        remaining.setdefault(f.matchday, []).append(f)
    full = [m for m, fs in remaining.items() if 2 * len(fs) >= total[m]]
    full.sort(key=lambda m: (min(f.kickoff_utc for f in remaining[m]), m))
    chosen = full[:n]
    if not chosen:
        return [], []
    end = max(f.kickoff_utc for m in chosen for f in remaining[m])
    weighed = [
        f for f in upcoming
        if f.matchday in chosen or (f.matchday not in full and f.kickoff_utc <= end)
    ]
    return chosen, weighed


def describe_fixture(f: TeamFixture) -> str:
    venue = "vs" if f.is_home else "at"
    return f"{venue} {f.opponent} ({f.difficulty:.2f})"


# --- expected return ------------------------------------------------------------------


@dataclass(frozen=True)
class Assessment:
    player: PlayerInput
    fixture: FixtureOutlook
    minutes_factor: float
    expected_points_used: bool
    expected_return: float | None  # expected points per jornada over the window
    points_term: float | None  # expected_return × jornadas
    value_term: float  # predicted next move, in points at the rules' cash-per-point
    hold_value: float | None  # points_term + value_term
    efficiency: float | None  # expected points per jornada per €1M
    evidence: float
    bids: Bids

    @property
    def player_id(self) -> int:
        return self.player.player_id

    @property
    def name(self) -> str:
        return self.player.name

    @property
    def position(self) -> str:
        return self.player.position


def minutes_factor(p: PlayerInput) -> float:
    avail = AVAILABILITY_FACTOR.get(p.availability, 1.0)
    if p.starter_probability is None:
        return avail
    return avail * (STARTER_FLOOR + (1 - STARTER_FLOOR) * p.starter_probability / 100)


def evidence_factor(recent_jornadas: int) -> float:
    filled = min(max(recent_jornadas, 0), an.RECENT_WINDOW) / an.RECENT_WINDOW
    return EVIDENCE_FLOOR + (1 - EVIDENCE_FLOOR) * filled


def assess_player(
    p: PlayerInput, outlook: FixtureOutlook, jornadas: int, cash_per_point: int
) -> Assessment:
    """Expected points per jornada over the window, and the hold value.

    Without expected points: `backward_ppg × fixture × minutes`.
    With them (MODEL-02): `w · xP + (1 − w) · backward_ppg × fixture`, with
    `w = EXPECTED_POINTS_WEIGHT`; the minutes guess is dropped
    because expected points carry their own.

    `hold_value = expected_return · jornadas + mv · predicted% / cash_per_point`
    — the game converts points to cash at a published rate, so a predicted
    market move and expected points are added in one unit.
    """
    minutes = minutes_factor(p)
    xp_used = p.expected_points is not None
    backward = p.backward_ppg * outlook.multiplier if p.backward_ppg is not None else None
    if xp_used:
        w = EXPECTED_POINTS_WEIGHT
        er = p.expected_points if backward is None else w * p.expected_points + (1 - w) * backward
    elif backward is not None:
        er = backward * minutes
    else:
        er = None
    if er is not None:
        er = max(er, 0.0)

    value_term = p.market_value * (p.predicted_pct or 0.0) / 100 / cash_per_point
    points_term = er * jornadas if er is not None else None
    return Assessment(
        player=p,
        fixture=outlook,
        minutes_factor=minutes,
        expected_points_used=xp_used,
        expected_return=er,
        points_term=points_term,
        value_term=value_term,
        hold_value=points_term + value_term if points_term is not None else None,
        efficiency=(er / (p.market_value / 1_000_000)
                    if er is not None and p.market_value > 0 else None),
        evidence=evidence_factor(p.recent_jornadas),
        bids=compute_bids(p),
    )


# --- prices and the owner's ceiling ----------------------------------------------------


def price_on(a: Assessment, basis: str) -> int | None:
    if basis == "marketValue":
        return a.player.market_value
    if basis == "idealBid":
        return a.player.source_ideal_bid
    if basis == "maxBid":
        return a.player.source_max_bid
    if basis == "ourIdealBid":
        return a.bids.ideal
    if basis == "ourMaxBid":
        return a.bids.maximum
    raise ValueError(f"unknown price basis {basis!r}")


def affordable(a: Assessment, ceiling: Ceiling | None) -> bool:
    """A player whose price on the basis is unknown cannot be shown to be
    within the ceiling, so an active ceiling excludes him (BROWSE-05's rule)."""
    if ceiling is None:
        return True
    limit, basis = ceiling
    price = price_on(a, basis)
    return price is not None and price <= limit


# --- TRANSFER-02: legality --------------------------------------------------------------


@dataclass(frozen=True)
class MoveVerdict:
    allowed: bool
    violation: Violation | None
    resulting: object  # SquadVerdict of the squad after the move


def _missing(verdict) -> int:
    return sum(verdict.missing_for_xi.values())


def check_move(
    members: list[SquadMember], sell_id: int | None, buy: SquadMember, rules: Rules
) -> MoveVerdict:
    """Would selling `sell_id` (or nobody) and buying `buy` leave the squad
    legal? Squad cap and duplicates via `evaluate_add`, unchanged. Then XI
    feasibility, which `evaluate_add` deliberately leaves alone because a
    partial squad is legal: a squad that can field an XI must still be able
    to; one that cannot must not end up further from one."""
    if sell_id is not None and not any(m.player_id == sell_id for m in members):
        v = Violation("not_in_squad", 0, 1, "The player to sell is not in your squad.")
        return MoveVerdict(False, v, evaluate_squad(members, rules))
    remaining = [m for m in members if m.player_id != sell_id]
    add = evaluate_add(remaining, buy, rules)
    if not add.allowed:
        return MoveVerdict(False, add.violation, add.resulting)
    before = evaluate_squad(members, rules)
    after = add.resulting
    if not after.is_legal:
        return MoveVerdict(False, after.violations[0], after)
    if before.can_field_xi and not after.can_field_xi:
        v = Violation(
            "xi_feasibility", 0, 1,
            f"Buying {buy.name} for this player leaves no formation the squad can field.",
        )
        return MoveVerdict(False, v, after)
    if not before.can_field_xi and _missing(after) > _missing(before):
        v = Violation(
            "xi_feasibility", _missing(after), _missing(before),
            f"Buying {buy.name} for this player moves the squad further from a fieldable XI.",
        )
        return MoveVerdict(False, v, after)
    return MoveVerdict(True, None, after)


# --- TRANSFER-04: freshness -------------------------------------------------------------


@dataclass(frozen=True)
class DatasetFreshness:
    dataset: str
    last_success_at: datetime | None
    age_days: float | None
    factor: float
    note: str | None


@dataclass(frozen=True)
class Freshness:
    factor: float
    reasons: list[str]
    datasets: list[DatasetFreshness]


def _age_days(at: datetime | None, now: datetime) -> float | None:
    if at is None:
        return None
    return (now - _as_aware(at)).total_seconds() / 86400


def missed_market_updates(started_at: datetime, now: datetime) -> int:
    return (last_market_update(now).date() - last_market_update(_as_aware(started_at)).date()).days


def assess_freshness(
    last_success: Mapping[str, datetime | None],
    now: datetime,
    fixtures_available: bool,
    expected_points_used: bool,
) -> Freshness:
    """How far to trust anything built from the data held right now.

    `last_success` maps dataset → the `started_at` of its latest successful
    run: `market`, `jornada_points`, `fixtures`, `football_data` (odds).
    Market staleness is the market's own question (`core.freshness`): each
    missed 00:15 update multiplies confidence by `MARKET_STALE_FACTOR`.
    The others are elapsed-days questions. Odds only count once expected
    points (MODEL-02) — their only consumer — are in use.
    """
    datasets: list[DatasetFreshness] = []

    def add(name, factor, note):
        at = last_success.get(name)
        datasets.append(DatasetFreshness(name, at, _age_days(at, now), factor, note))

    market = last_success.get("market")
    if market is None:
        add("market", 0.3, "No successful market scrape — prices and bids are unknown.")
    elif is_stale(market, now):
        missed = max(missed_market_updates(market, now), 1)
        charged = min(missed, MAX_MISSED_UPDATES_CHARGED)
        plural = "s" if missed != 1 else ""
        add("market", MARKET_STALE_FACTOR**charged,
            f"Prices are {missed} market update{plural} behind — refresh before acting.")
    else:
        add("market", 1.0, None)

    points = last_success.get("jornada_points")
    age = _age_days(points, now)
    if points is None:
        add("jornada_points", 0.6, "No successful jornada points refresh — form is unknown.")
    elif age > JORNADA_STALE_DAYS:
        add("jornada_points", 0.8, f"Jornada points last refreshed {age:.0f} days ago.")
    else:
        add("jornada_points", 1.0, None)

    fixtures = last_success.get("fixtures")
    age = _age_days(fixtures, now)
    if not fixtures_available:
        add("fixtures", 0.85,
            "No upcoming fixtures stored — fixture difficulty is not applied.")
    elif fixtures is None:
        add("fixtures", 0.9, "No successful fixture refresh on record — the calendar's age "
                             "is unknown.")
    elif age > FIXTURES_STALE_DAYS:
        add("fixtures", 0.9, f"Fixture calendar last refreshed {age:.0f} days ago.")
    else:
        add("fixtures", 1.0, None)

    odds = last_success.get("football_data")
    age = _age_days(odds, now)
    if not expected_points_used:
        add("football_data", 1.0, "Not used until expected points (MODEL-02) are available.")
    elif odds is None or age > ODDS_STALE_DAYS:
        add("football_data", 0.9, "Odds are missing or over a week old — expected points "
                                  "rest on old prices.")
    else:
        add("football_data", 1.0, None)

    factor = 1.0
    for d in datasets:
        factor *= d.factor
    reasons = [d.note for d in datasets if d.factor < 1.0 and d.note]
    return Freshness(round(factor, 4), reasons, datasets)


def confidence_label(value: float) -> str:
    if value >= HIGH_CONFIDENCE:
        return "high"
    if value >= MEDIUM_CONFIDENCE:
        return "medium"
    return "low"


def _evidence_reasons(assessments: Iterable[Assessment]) -> list[str]:
    return [
        f"{a.name} has only {a.player.recent_jornadas} jornadas on record."
        for a in assessments
        if a.player.recent_jornadas < an.RECENT_WINDOW
    ]


# --- TRANSFER-01: moves ------------------------------------------------------------------


@dataclass(frozen=True)
class Signal:
    name: str  # points | value | efficiency | fixtures | valuation | availability
    text: str
    contribution: float | None  # points-equivalent this signal adds to the gain


@dataclass(frozen=True)
class Move:
    kind: str  # swap | add
    sell: Assessment | None
    buy: Assessment
    gain: float
    signals: list[Signal]
    confidence: float
    confidence_label: str
    confidence_reasons: list[str]
    feasible_formations: tuple[str, ...]


def _fmt_eur(v: float) -> str:
    sign = "-" if v < 0 else "+"
    return f"{sign}€{abs(v) / 1_000_000:.2f}M"


def _fixtures_text(a: Assessment) -> str | None:
    if not a.fixture.available:
        return None
    if not a.fixture.fixtures:
        return f"{a.name}: no match in the window (×{a.fixture.multiplier:.2f})"
    shown = ", ".join(describe_fixture(f) for f in a.fixture.fixtures)
    return f"{a.name}: {shown} (×{a.fixture.multiplier:.2f})"


def _signals(
    sell: Assessment | None, buy: Assessment, jornadas: int, xi_delta: float, starts: bool
) -> list[Signal]:
    s_er = sell.expected_return if sell else None
    plural = "s" if jornadas != 1 else ""
    text = (
        f"Best XI {xi_delta:+.1f} expected pts/jornada over {jornadas} jornada{plural}: "
        f"{buy.name} {buy.expected_return:.1f}"
        + (f" vs {sell.name} {s_er:.1f}" if s_er is not None else "")
        + ("" if starts else f" — {buy.name} would not start")
    )
    out = [Signal("points", text, xi_delta * jornadas)]
    if buy.player.predicted_pct is not None or (sell and sell.player.predicted_pct is not None):
        def move(a):
            pct = a.player.predicted_pct
            if pct is None:
                return f"{a.name} no prediction"
            conf = f", {a.player.prediction_confidence}" if a.player.prediction_confidence else ""
            return (f"{a.name} {pct:+.2f}% ({_fmt_eur(a.player.market_value * pct / 100)}"
                    f"{conf})")

        text = "Next market update: " + move(buy) + (f"; {move(sell)}" if sell else "")
        out.append(Signal("value", text, buy.value_term - (sell.value_term if sell else 0.0)))

    if buy.efficiency is not None:
        text = f"{buy.name} {buy.efficiency:.2f} pts/jornada per €1M"
        if sell and sell.efficiency is not None:
            text += f" vs {sell.name} {sell.efficiency:.2f}"
        out.append(Signal("efficiency", text, None))

    fixture_parts = [t for t in (_fixtures_text(buy), sell and _fixtures_text(sell)) if t]
    if fixture_parts:
        out.append(Signal("fixtures", "; ".join(fixture_parts), None))

    gaps = [(a, a.player.valuation_gap) for a in (buy, sell) if a and a.player.valuation_gap
            is not None]
    if gaps:
        out.append(Signal(
            "valuation",
            "; ".join(f"{a.name} priced {g * 100:+.0f}% vs fair value" for a, g in gaps),
            None,
        ))
    if sell and sell.player.availability != "available":
        out.append(Signal("availability", f"{sell.name} is {sell.player.availability}", None))

    contributing = sorted((s for s in out if s.contribution is not None),
                          key=lambda s: -abs(s.contribution))
    return contributing + [s for s in out if s.contribution is None]


def _engine_member(a: Assessment, price: int) -> SquadMember:
    return SquadMember(a.player_id, a.name, a.position, price, a.player.market_value)


def _confidence(freshness: Freshness, players: list[Assessment]) -> tuple[float, str, list[str]]:
    value = freshness.factor * min(a.evidence for a in players)
    return round(value, 4), confidence_label(value), freshness.reasons + _evidence_reasons(players)


def best_xi(squad: Iterable[tuple[int, str, float]], rules: Rules) -> tuple[float, set[int]]:
    """The highest expected-points XI the squad can field under the league's
    formations: `(total per jornada, starter ids)`. A squad that cannot field
    any formation fields the best partial one, so an incomplete squad still
    has a number that improves as it fills. Only starters score — which is
    why a third goalkeeper is worth nothing to the XI however good he is.
    """
    by_pos: dict[str, list[tuple[float, int]]] = {}
    for pid, position, er in squad:
        by_pos.setdefault(position, []).append((er, pid))
    for group in by_pos.values():
        group.sort(key=lambda t: (-t[0], t[1]))
    best: tuple[float, set[int]] = (0.0, set())
    for formation in rules.formations:
        chosen = [
            pid
            for position, k in formation.required().items()
            for _, pid in by_pos.get(position, [])[:k]
        ]
        total = sum(
            er for position, k in formation.required().items()
            for er, _ in by_pos.get(position, [])[:k]
        )
        if total > best[0] + 1e-9:
            best = (total, set(chosen))
    return best


def _buy_pool(
    assessments: Mapping[int, Assessment], owned: set[int], ceiling: Ceiling | None
) -> list[Assessment]:
    pool = [
        a for pid, a in assessments.items()
        if pid not in owned
        and a.hold_value is not None
        and (a.expected_return or 0) > 0
        and AVAILABILITY_FACTOR.get(a.player.availability, 1.0) >= MIN_BUYABLE_AVAILABILITY
        and affordable(a, ceiling)
    ]
    kept: list[Assessment] = []
    for position in {a.position for a in pool}:
        group = sorted((a for a in pool if a.position == position), key=lambda a: -a.hold_value)
        kept.extend(group[:CANDIDATES_PER_POSITION])
    return sorted(kept, key=lambda a: (-a.hold_value, a.player_id))


def suggest_moves(
    members: list[SquadMember],
    assessments: Mapping[int, Assessment],
    rules: Rules,
    ceiling: Ceiling | None,
    freshness: Freshness,
    jornadas: int,
    limit: int = 10,
) -> list[Move]:
    """Ranked sell → buy suggestions, plus adds while the squad has free slots.

    A move's gain is what it does to the **best XI** the squad can field
    (expected points per jornada × jornadas — only starters score), plus the
    predicted next market move of the two players at the rules' cash per
    point. Efficiency, fixtures and the valuation gap are shown as the
    reasoning; the owner's ceiling is the only money constraint (TRANSFER-01
    — no derived budget). Every move passes `check_move` (TRANSFER-02).

    Moves are chosen greedily and applied one after another, so each is
    valued against the squad the previous ones leave, and a player appears
    in at most one move — the list reads as a set of things to actually do.
    """
    owned = {m.player_id for m in members}
    pool = _buy_pool(assessments, owned, ceiling)
    price_basis = ceiling[1] if ceiling else "marketValue"

    def er(pid: int) -> float:
        a = assessments.get(pid)
        return a.expected_return or 0.0 if a else 0.0

    squad = list(members)
    touched: set[int] = set()
    moves: list[Move] = []
    while len(moves) < limit:
        rows = [(m.player_id, m.position, er(m.player_id)) for m in squad]
        base, _ = best_xi(rows, rules)
        # An add first: on a tie it beats a swap, because it sells nobody.
        sells: list[Assessment | None] = [None] if len(squad) < rules.max_squad_size else []
        sells += [
            assessments[m.player_id] for m in squad
            if m.player_id in assessments and m.player_id not in touched
        ]
        best = None
        for sell in sells:
            kept = [r for r in rows if sell is None or r[0] != sell.player_id]
            for buy in pool:
                if buy.player_id in touched:
                    continue
                total, starters = best_xi([*kept, (buy.player_id, buy.position,
                                                   buy.expected_return)], rules)
                xi_delta = total - base
                gain = xi_delta * jornadas + buy.value_term - (sell.value_term if sell else 0.0)
                if gain <= MIN_GAIN or (best is not None and gain <= best[0]):
                    continue
                candidate = _engine_member(buy, price_on(buy, price_basis) or 0)
                verdict = check_move(squad, sell.player_id if sell else None, candidate, rules)
                if verdict.allowed:
                    best = (gain, sell, buy, xi_delta, buy.player_id in starters, verdict,
                            candidate)
        if best is None:
            break
        gain, sell, buy, xi_delta, starts, verdict, candidate = best
        conf, label, reasons = _confidence(freshness, [a for a in (sell, buy) if a])
        moves.append(Move(
            "swap" if sell else "add", sell, buy, gain,
            _signals(sell, buy, jornadas, xi_delta, starts), conf, label, reasons,
            verdict.resulting.feasible_formations,
        ))
        squad = [m for m in squad if sell is None or m.player_id != sell.player_id] + [candidate]
        touched |= {buy.player_id} | ({sell.player_id} if sell else set())
    return moves


# --- TRANSFER-05: best for a position ----------------------------------------------------


def best_for_position(
    assessments: Mapping[int, Assessment],
    position: str,
    ceiling: Ceiling | None,
    affordable_only: bool,
    limit: int = 20,
) -> list[Assessment]:
    """The statistically best players at a position by expected return.
    The ceiling applies only when `affordable_only` — seeing the best
    regardless of price says what the squad is short of."""
    rows = [
        a for a in assessments.values()
        if a.position == position
        and a.expected_return is not None
        and (not affordable_only or affordable(a, ceiling))
    ]
    rows.sort(key=lambda a: (-a.expected_return, -(a.hold_value or 0), a.player_id))
    return rows[:limit]


# --- MODEL-05: bargains -----------------------------------------------------------------


@dataclass(frozen=True)
class Bargain:
    assessment: Assessment
    forward_fair_value: int
    forward_gap: float  # forward fair / market − 1


def _loglog_fits(rows: list[Assessment]) -> dict[str, tuple[float, float]]:
    """`ln(mv) = a + b · ln(expected_return)` per position, pooled when a
    position has fewer than `analytics.MIN_POSITION_FIT` players."""
    def fit(group):
        return an._ols([(math.log(a.expected_return), math.log(a.player.market_value))
                        for a in group])

    pooled = fit(rows)
    out = {}
    for position in {a.position for a in rows}:
        group = [a for a in rows if a.position == position]
        own = fit(group) if len(group) >= an.MIN_POSITION_FIT else None
        chosen = own or pooled
        if chosen is not None:
            out[position] = (chosen[0], chosen[1])
    return out


def bargains(
    assessments: Mapping[int, Assessment],
    ceiling: Ceiling | None = None,
    affordable_only: bool = False,
    position: str | None = None,
    limit: int = 20,
) -> list[Bargain]:
    """Players whose expected return is high against their price.

    "High": expected return in the top quarter of his position
    (`BARGAIN_MIN_PERCENTILE`), so a cheap squad-filler never tops the list.
    "Against price": priced below what that return usually costs at his
    position — a price curve `ln(mv) = a + b · ln(expected_return)` fitted
    over every player with enough evidence (at least
    `analytics.MIN_VALUATION_JORNADAS` recent jornadas). Log-log rather than
    ANALYTICS-04's exponential curve, because the exponential extrapolates a
    top scorer's "fair" price to several times anything the market pays.
    Ranked by the gap.
    """
    rows = [a for a in assessments.values()
            if (a.expected_return or 0) > 0
            and a.player.market_value > 0
            and a.player.recent_jornadas >= an.MIN_VALUATION_JORNADAS]
    fits = _loglog_fits(rows)
    thresholds = {}
    for pos in {a.position for a in rows}:
        ers = sorted(a.expected_return for a in rows if a.position == pos)
        thresholds[pos] = ers[int(BARGAIN_MIN_PERCENTILE * (len(ers) - 1))]
    out = []
    for a in rows:
        if a.position not in fits or a.expected_return < thresholds[a.position]:
            continue
        if _unavailable(a.player.availability):
            continue
        if position is not None and a.position != position:
            continue
        if affordable_only and not affordable(a, ceiling):
            continue
        intercept, slope = fits[a.position]
        fair = math.exp(intercept + slope * math.log(a.expected_return))
        gap = fair / a.player.market_value - 1
        if gap > 0:
            out.append(Bargain(a, round(fair), gap))
    out.sort(key=lambda b: (-b.forward_gap, b.assessment.player_id))
    return out[:limit]
