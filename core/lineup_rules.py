"""The XI rule engine — pure, and deliberately so.

An arrangement and the loaded rules go in; a structured verdict comes out.
No database session, no HTTP type, no FastAPI or SQLModel import, mirroring
`core/squad_rules.py` exactly.

**This module imports nothing from `core.squad_rules`, and that is a rule,
not an accident (LN-23).** The two engines answer different questions about
the same formations. `squad_rules.feasible_formations` asks whether a squad
*could* field a shape and compares with `>=`, because a 24-player squad with
six defenders can obviously field a back four. An XI *is* a shape: 4-4-2
means at most four defenders, not at least four. Sharing that predicate
would accept a five-defender 4-4-2 — an `alineación indebida` the real game
scores zero. The shared refusal DTO lives in `core.rules`, which both
engines import.

The module keeps its name after the 2026-08-22 lineup cut, and the name no
longer describes anything: it validates the squad's current shape, not a
lineup. Renaming it to `core/xi_rules.py` is a plausible follow-up that was
deliberately left out of that work — it would inflate the diff for no
behavioural gain.
"""

from dataclasses import dataclass

from core.rules import POSITIONS, Rules, Violation, find_formation

#: How a position id reads in a refusal sentence. The owner sees "defender",
#: not "DEF" — a remedy nobody can parse is not a remedy.
_POSITION_NAMES = {
    "POR": "goalkeeper",
    "DEF": "defender",
    "MED": "midfielder",
    "DEL": "forward",
}


@dataclass(frozen=True)
class EligiblePlayer:
    """One player currently in the squad, as the engine sees them.

    Deliberately lighter than `squad_rules.SquadMember` (LN-20): no
    `purchase_price`, no `market_value`. Money has no bearing on whether an
    arrangement is legal, and threading it through would invite a later
    change to make it so.
    """

    player_id: int
    name: str
    position: str


@dataclass(frozen=True)
class LineupSelection:
    """What the owner is trying to field right now."""

    formation: str
    starter_ids: tuple[int, ...]
    bench_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class LeagueFeatures:
    """Which Premium features the owner's league has switched on. The league
    admin toggles each separately, so this is not one master switch."""

    bench_enabled: bool


@dataclass(frozen=True)
class LineupVerdict:
    """The answer to 'may the squad stand like this?'.

    `is_complete` is not a legality field and must never be rendered as one:
    an XI with empty slots saves perfectly well and is simply not finished
    yet. It is this engine's own answer to that question, exercised by this
    module's tests — but nothing in `api/routes/squad.py` reads it. The UI
    derives completeness itself, client-side, from `members[].role` in the
    `GET /api/squad` payload (`web/src/lib/xi.ts`'s `isComplete`), since that
    payload already carries everything the arithmetic needs. Keep this field
    accurate regardless: it is the engine's contract, not dead code.
    """

    allowed: bool
    violation: Violation | None
    is_complete: bool
    position_counts: dict[str, int]


def _count_positions(players: list[EligiblePlayer]) -> dict[str, int]:
    """Always returns all four positions, zero-filled — callers index this
    directly and must never hit a KeyError."""
    counts = dict.fromkeys(POSITIONS, 0)
    for player in players:
        if player.position in counts:
            counts[player.position] += 1
    return counts


def evaluate_lineup(
    selection: LineupSelection,
    eligible: list[EligiblePlayer],
    rules: Rules,
    features: LeagueFeatures,
) -> LineupVerdict:
    """Validate one arrangement against the league's rules and the current squad.

    `rules` must already be narrowed by `for_league()` — this engine never
    learns that premium formations are a concept, exactly as the squad engine
    does not.

    Checks are ordered by which constraint actually binds, following
    `evaluate_add`'s precedent that a refusal naming the wrong remedy is
    worse than no remedy. Duplicates and unknown players are checked *before*
    shape, because both distort the position counts: a duplicated defender in
    an otherwise-correct 4-4-2 would otherwise be reported as
    `formation_shape` and send the owner to fix a shape that is not wrong.
    """
    by_id = {player.player_id: player for player in eligible}
    starters = [by_id[pid] for pid in selection.starter_ids if pid in by_id]
    position_counts = _count_positions(starters)

    def refuse(rule: str, actual: float, limit: float, message: str) -> LineupVerdict:
        return LineupVerdict(
            allowed=False,
            violation=Violation(rule=rule, actual=actual, limit=limit, message=message),
            is_complete=False,
            position_counts=position_counts,
        )

    # 1. Formation — every later check is expressed in terms of it.
    formation = find_formation(rules, selection.formation)
    if formation is None:
        available = ", ".join(f.name for f in rules.formations)
        return refuse(
            "formation_unavailable",
            actual=0,
            limit=len(rules.formations),
            message=(
                f"{selection.formation} isn't one of your league's formations. "
                f"Choose one of: {available}."
            ),
        )

    # 2. Duplicates — before shape, because a repeat distorts the counts.
    selected = [*selection.starter_ids, *selection.bench_ids]
    seen: set[int] = set()
    for player_id in selected:
        if player_id in seen:
            name = by_id[player_id].name if player_id in by_id else str(player_id)
            return refuse(
                "duplicate_selection",
                actual=selected.count(player_id),
                limit=1,
                message=f"{name} can only stand in one place at a time.",
            )
        seen.add(player_id)

    # 3. Eligibility — before shape, because an unknown player has no
    #    position and the shape cannot be computed without one.
    unknown = [pid for pid in selected if pid not in by_id]
    if unknown:
        return refuse(
            "not_in_squad",
            actual=len(unknown),
            limit=0,
            message=(
                f"{len(unknown)} of the players you've placed aren't in your squad — "
                "add them before you can field them."
            ),
        )

    # 4. Shape. Over-filling is refused; under-filling is a normal, saveable
    #    state and is reported as incomplete instead (spec §5).
    required = formation.required()
    for position in POSITIONS:
        needed = required[position]
        have = position_counts[position]
        if have > needed:
            noun = _POSITION_NAMES[position]
            return refuse(
                "formation_shape",
                actual=have,
                limit=needed,
                message=(
                    f"{selection.formation} fields {needed} {noun}(s) and you've "
                    f"placed {have}. Move one off the pitch, or pick a formation "
                    "with room for them."
                ),
            )

    is_complete = all(position_counts[p] == required[p] for p in POSITIONS)

    # 5. The bench. There is deliberately no bench_size rule — "at most four"
    #    is what the two checks below produce, since there are exactly four
    #    positions. An empty or partial bench is valid: an uncovered position
    #    just means that starter cannot be substituted, which is the owner's
    #    business, not an error.
    if selection.bench_ids and not features.bench_enabled:
        return refuse(
            "bench_disabled",
            actual=len(selection.bench_ids),
            limit=0,
            message=(
                "The bench is a Premium-league feature and isn't enabled for your "
                "league, so no substitutes can be named."
            ),
        )

    bench_seen: set[str] = set()
    for player_id in selection.bench_ids:
        position = by_id[player_id].position
        noun = _POSITION_NAMES[position]

        if required[position] == 0:
            return refuse(
                "bench_position_not_fielded",
                actual=1,
                limit=0,
                message=(
                    f"{selection.formation} fields no {noun}s, so a {noun} can't sit "
                    "on its bench. Pick a different formation or a different substitute."
                ),
            )

        if position in bench_seen:
            return refuse(
                "bench_position_duplicate",
                actual=2,
                limit=1,
                message=(
                    f"You've picked two {noun}s on the bench — it holds one substitute "
                    "per position."
                ),
            )
        bench_seen.add(position)

    return LineupVerdict(
        allowed=True,
        violation=None,
        is_complete=is_complete,
        position_counts=position_counts,
    )
