"""The squad rule engine — pure, and deliberately so.

Squad composition and the loaded rules go in; structured verdicts come out.
No database session, no HTTP request, no FastAPI or SQLModel type appears in
this module. That is what makes the boundary cases cheap to test and what
lets the later transfer engine (TRANSFER-02: "no suggestion may produce an
illegal squad") reuse it untouched.

Spec D-07 — the two layers are separate and must stay separate:

  * squad legality   : squad size. What the official rules actually
                       constrain about *ownership*. Money is not part of
                       this layer — see `evaluate_squad`'s docstring.
  * XI feasibility   : which of the league's allowed formations the squad
                       could still field. What the official rules constrain
                       about the *starting eleven*.

Conflating them produces a validator wrong in both directions: it rejects
legal squads and accepts unplayable ones.
"""

from dataclasses import dataclass

from core.rules import POSITIONS, Rules, Violation


@dataclass(frozen=True)
class SquadMember:
    """One owned player, as the engine sees them.

    `market_value` is `None` when the player has no snapshot for the latest
    scrape date — a rejected scrape or a player who left the source roster.
    Callers must never drop such a member; see `effective_value`.
    """

    player_id: int
    name: str
    position: str
    purchase_price: int
    market_value: int | None

    @property
    def effective_value(self) -> int:
        """Market value where known, else what was paid. Falls back rather
        than counting the member as worth zero, which would silently shrink
        squad value the day a scrape is rejected."""
        return self.market_value if self.market_value is not None else self.purchase_price


def count_positions(members: list[SquadMember]) -> dict[str, int]:
    """Always returns all four positions, zero-filled — callers index this
    directly and must never hit a KeyError on an empty squad."""
    counts = dict.fromkeys(POSITIONS, 0)
    for m in members:
        if m.position in counts:
            counts[m.position] += 1
    return counts


def feasible_formations(counts: dict[str, int], rules: Rules) -> tuple[str, ...]:
    """The formations this composition could still field, in the rules file's
    own order. Empty means no legal starting XI is reachable."""
    return tuple(
        f.name
        for f in rules.formations
        if all(counts.get(position, 0) >= needed for position, needed in f.required().items())
    )


def _shortfall(counts: dict[str, int], formation) -> dict[str, int]:
    return {
        position: needed - counts.get(position, 0)
        for position, needed in formation.required().items()
        if counts.get(position, 0) < needed
    }


def _cheapest_route(counts: dict[str, int], rules: Rules):
    """The formation reachable with the fewest additional signings, and that
    shortfall. Ties break on the rules file's own order, so the answer is
    deterministic. Returns `None` when some formation is already reachable."""
    if feasible_formations(counts, rules):
        return None
    best = None
    for formation in rules.formations:
        gap = _shortfall(counts, formation)
        total = sum(gap.values())
        if best is None or total < best[0]:
            best = (total, formation.name, gap)
    return best


def missing_for_xi(counts: dict[str, int], rules: Rules) -> dict[str, int]:
    """How many more players per position are needed before *any* formation
    becomes reachable. Empty when at least one already is.

    This must be computed against whole formations, not against the
    per-position minimum. Those minima are a lower bound, not a reachability
    condition: 1 POR / 3 DEF / 3 MED / 1 DEL clears every individual minimum
    of the standard set and still fields nothing, because no single formation
    wants that shape. A floor-based report would answer 'nothing missing'
    while `feasible_formations` returned empty — two outputs of the same
    module contradicting each other.
    """
    route = _cheapest_route(counts, rules)
    return {} if route is None else route[2]


def nearest_formation(counts: dict[str, int], rules: Rules) -> str | None:
    """Which formation `missing_for_xi` is counting towards, so the UI can say
    'one more midfielder to reach 3-4-3' rather than leaving the owner to work
    out what the shortfall buys them. `None` once an XI is reachable."""
    route = _cheapest_route(counts, rules)
    return None if route is None else route[1]


@dataclass(frozen=True)
class SquadVerdict:
    violations: tuple[Violation, ...]
    is_legal: bool
    can_field_xi: bool
    squad_size: int
    squad_value: int
    position_counts: dict[str, int]
    feasible_formations: tuple[str, ...]
    missing_for_xi: dict[str, int]
    nearest_formation: str | None


def evaluate_squad(members: list[SquadMember], rules: Rules) -> SquadVerdict:
    """Answer 'is this squad legal?' and 'can it still field an XI?' — two
    separate questions, deliberately answered in two separate fields.

    An incomplete squad is legal (spec D-09). Money is not a question this
    engine answers any more: the game's daily claimable €100k is
    unobservable in principle, so any balance the app derived was wrong by
    construction. The owner reads their real figure off the official app and
    filters the player browser by it.
    """
    counts = count_positions(members)
    squad_value = sum(m.effective_value for m in members)

    violations: list[Violation] = []

    if len(members) > rules.max_squad_size:
        excess = len(members) - rules.max_squad_size
        violations.append(
            Violation(
                rule="squad_size",
                actual=len(members),
                limit=rules.max_squad_size,
                message=(
                    f"Squad has {len(members)} players, {excess} over the "
                    f"{rules.max_squad_size}-player limit — remove {excess}."
                ),
            )
        )

    formations = feasible_formations(counts, rules)

    return SquadVerdict(
        violations=tuple(violations),
        is_legal=not violations,
        can_field_xi=bool(formations),
        squad_size=len(members),
        squad_value=squad_value,
        position_counts=counts,
        feasible_formations=formations,
        missing_for_xi=missing_for_xi(counts, rules),
        nearest_formation=nearest_formation(counts, rules),
    )


@dataclass(frozen=True)
class AddVerdict:
    """The answer to 'would this specific change be legal?'.

    There is no `warning` any more. It carried one case — spending into the
    20% debt allowance — which required knowing a cash balance the app has
    stopped deriving.
    """

    allowed: bool
    violation: Violation | None
    resulting: SquadVerdict


def evaluate_add(
    members: list[SquadMember],
    candidate: SquadMember,
    rules: Rules,
) -> AddVerdict:
    """Checks are ordered by which constraint actually binds. A refusal that
    names the wrong remedy is worse than no remedy.

    Affordability is deliberately absent. It required a cash balance the app
    no longer derives, and the price filter in the player browser is where
    "can I afford this" is now answered — by the owner, against the figure
    they can actually see.
    """
    resulting = evaluate_squad([*members, candidate], rules)

    def refuse(violation: Violation) -> AddVerdict:
        return AddVerdict(allowed=False, violation=violation, resulting=resulting)

    if candidate.purchase_price < 0:
        return refuse(
            Violation(
                rule="purchase_price",
                actual=candidate.purchase_price,
                limit=0,
                message=(
                    "Purchase price cannot be negative — enter what you "
                    "actually paid."
                ),
            )
        )

    if any(m.player_id == candidate.player_id for m in members):
        return refuse(
            Violation(
                rule="already_owned",
                actual=1,  # copies of this player owned
                limit=0,   # additional copies allowed
                message=f"{candidate.name} is already in your squad.",
            )
        )

    if len(members) >= rules.max_squad_size:
        return refuse(
            Violation(
                rule="squad_size",
                actual=len(members) + 1,
                limit=rules.max_squad_size,
                message=(
                    f"Squad is full ({rules.max_squad_size}/"
                    f"{rules.max_squad_size}) — remove a player before adding "
                    f"{candidate.name}."
                ),
            )
        )

    return AddVerdict(allowed=True, violation=None, resulting=resulting)
