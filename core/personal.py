"""The personal line — one player's verdict, read against *your* squad
(Plan C, Task 2). Pure.

Built on `core.transfers.best_xi`: a move's gain is always what it does to
the expected-points total of the best XI the squad can field, which is why
a fifth goalkeeper (or a fourth who never starts) is worth nothing here
however good he is — `best_xi` only scores starters.

**Owned** players either carry a sell-labelled verdict (`SELL_LABELS`), in
which case the line says sell; or the squad is searched for a same-position,
eligible upgrade from the pool that would raise the best XI's total by more
than `core.transfers.MIN_GAIN`; or, failing that, the line says keep.

**Unowned** players are compared against the weakest player at their
position who is currently a *starter* in the best XI (not merely owned) —
replacing a benched duplicate is not a move worth suggesting, since it
never changes what the XI scores. When nobody at the position starts at
all (an empty slot), the candidate is compared against the empty slot
itself (`best_xi(squad + player)`), with no "other player" to name — the
line still reads `replace` (a move is still suggested), worded as
"Would fill your empty {position} slot: …" rather than naming someone.

The incoming player's `xpts` is already a total over the caller's horizon
(Plan B's `WindowXp.total`), not a per-jornada rate — `best_xi` returns the
XI total of whatever numbers it is given, so no further scaling happens
here. `over_ceiling_by` is checked against the price of the player being
bought, following `core.transfers`' own ceiling semantics (a cap on the buy
price, independent of what, if anything, is sold).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from core.rules import Rules
from core.transfers import MIN_GAIN, best_xi
from core.verdict import Verdict, _eur  # _eur shared from here, never duplicated

SELL_LABELS = frozenset({"Sell high", "Avoid", "Overpriced"})


@dataclass(frozen=True)
class SquadEntry:
    player_id: int
    name: str
    position: str
    xpts: float  # 0.0 when unknown
    price: int | None


@dataclass(frozen=True)
class Candidate:
    player_id: int
    name: str
    position: str
    xpts: float
    price: int | None
    eligible: bool  # available, evidence ok — a suggestable upgrade


@dataclass(frozen=True)
class PersonalLine:
    kind: str  # keep | sell | upgrade | replace | no_improvement
    text: str
    gain: float | None  # expected points over the horizon
    cost: int | None  # net € (positive = costs money)
    other_player_id: int | None
    other_name: str | None
    over_ceiling_by: int | None  # € over the owner's ceiling, None when affordable or no ceiling


def _cost_phrase(cost: int | None, more: bool) -> str:
    if cost is None:
        return "price unknown"
    if cost < 0:
        return f"saves {_eur(abs(cost))}"
    suffix = " more" if more else ""
    return f"costs {_eur(cost)}{suffix}"


def _over_ceiling(price: int | None, ceiling: int | None) -> int | None:
    if ceiling is None or price is None or price <= ceiling:
        return None
    return price - ceiling


def _rows(entries: Sequence[SquadEntry]) -> list[tuple[int, str, float]]:
    return [(s.player_id, s.position, s.xpts) for s in entries]


def _find_upgrade(
    player: Candidate, squad: Sequence[SquadEntry], pool: Sequence[Candidate],
    owned_ids: set[int], rules: Rules, base_total: float,
) -> tuple[Candidate, float] | None:
    best: tuple[Candidate, float] | None = None
    kept = [s for s in squad if s.player_id != player.player_id]
    for c in pool:
        if not c.eligible or c.position != player.position or c.player_id in owned_ids:
            continue
        total, _ = best_xi([*_rows(kept), (c.player_id, c.position, c.xpts)], rules)
        gain = total - base_total
        if best is None or gain > best[1]:
            best = (c, gain)
    return best


def personal_line(
    player: Candidate,
    verdict: Verdict,
    squad: Sequence[SquadEntry],
    pool: Sequence[Candidate],
    rules: Rules,
    horizon: int,
    ceiling: int | None = None,
) -> PersonalLine | None:
    if not squad:
        return None

    owned_ids = {s.player_id for s in squad}
    base_total, starters = best_xi(_rows(squad), rules)

    if player.player_id in owned_ids:
        if verdict.label in SELL_LABELS:
            return PersonalLine("sell", f"Sell — {verdict.reason}", None, None, None, None,
                                None)

        found = _find_upgrade(player, squad, pool, owned_ids, rules, base_total)
        if found is not None and found[1] > MIN_GAIN:
            candidate, gain = found
            cost = None if player.price is None or candidate.price is None else (
                candidate.price - player.price
            )
            over = _over_ceiling(candidate.price, ceiling)
            ceiling_clause = f"; {_eur(over)} over your ceiling" if over is not None else ""
            text = (
                f"Upgrade available: {candidate.name} (+{gain:.1f} pts over {horizon} "
                f"jornadas, {_cost_phrase(cost, more=True)}{ceiling_clause})"
            )
            return PersonalLine("upgrade", text, gain, cost, candidate.player_id, candidate.name,
                                over)

        gain = found[1] if found is not None else None
        return PersonalLine("keep", f"Keep — {verdict.reason}", gain, None, None, None, None)

    # Not owned.
    same_position_starters = [
        s for s in squad if s.position == player.position and s.player_id in starters
    ]
    weakest = min(same_position_starters, key=lambda s: (s.xpts, s.player_id), default=None)
    if weakest is not None:
        kept = [s for s in squad if s.player_id != weakest.player_id]
        other_id, other_name, other_price = weakest.player_id, weakest.name, weakest.price
    else:
        kept = list(squad)
        other_id, other_name, other_price = None, None, None

    new_total, _ = best_xi([*_rows(kept), (player.player_id, player.position, player.xpts)],
                           rules)
    gain = new_total - base_total

    if other_price is not None and player.price is not None:
        cost = player.price - other_price
    elif player.price is not None:
        cost = player.price
    else:
        cost = None

    if gain > MIN_GAIN:
        if other_name is not None:
            text = (
                f"Would replace your {other_name}: +{gain:.1f} expected points over "
                f"{horizon} jornadas, {_cost_phrase(cost, more=False)}"
            )
        else:
            text = (
                f"Would fill your empty {player.position} slot: +{gain:.1f} expected "
                f"points over {horizon} jornadas, {_cost_phrase(cost, more=False)}"
            )
        over = _over_ceiling(player.price, ceiling)
        return PersonalLine("replace", text, gain, cost, other_id, other_name, over)

    return PersonalLine(
        "no_improvement", f"No improvement on your current {player.position}s.", gain, None,
        None, None, None,
    )
