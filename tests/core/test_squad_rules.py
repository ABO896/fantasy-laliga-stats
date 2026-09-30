"""Boundary tests for the pure rule engine.

Spec D-07: squad legality and starting-XI feasibility are separate layers,
tested separately. This file starts with the feasibility layer.
"""

from core.rules import load_rules
from core.squad_rules import (
    SquadMember,
    count_positions,
    evaluate_add,
    evaluate_squad,
    feasible_formations,
    missing_for_xi,
    nearest_formation,
)

# Every test runs against the standard set unless it says otherwise — that is
# the app's default, and the premium set is exercised explicitly.
RULES = load_rules().for_league(premium_enabled=False)
PREMIUM_RULES = load_rules().for_league(premium_enabled=True)


def member(player_id: int, position: str, price: int = 1_000_000) -> SquadMember:
    return SquadMember(
        player_id=player_id,
        name=f"Player {player_id}",
        position=position,
        purchase_price=price,
        market_value=price,
    )


def _member(
    player_id: int,
    purchase_price: int,
    name: str | None = None,
    position: str = "DEL",
) -> SquadMember:
    """Like `member`, but keyword-first — for tests that only care about
    price/id and want the rest defaulted."""
    return SquadMember(
        player_id=player_id,
        name=name or f"Player {player_id}",
        position=position,
        purchase_price=purchase_price,
        market_value=purchase_price,
    )


def squad_of(**counts: int) -> list[SquadMember]:
    """squad_of(POR=1, DEF=4) -> one keeper and four defenders."""
    members: list[SquadMember] = []
    next_id = 1
    for position, how_many in counts.items():
        for _ in range(how_many):
            members.append(member(next_id, position))
            next_id += 1
    return members


def test_counts_every_position_even_when_zero():
    assert count_positions(squad_of(POR=1, DEF=2)) == {"POR": 1, "DEF": 2, "MED": 0, "DEL": 0}


def test_empty_squad_reaches_no_formation():
    assert feasible_formations(count_positions([]), RULES) == ()


def test_minimum_viable_squad_reaches_exactly_one_formation():
    counts = count_positions(squad_of(POR=1, DEF=3, MED=4, DEL=3))
    assert feasible_formations(counts, RULES) == ("3-4-3",)


def test_one_player_below_minimum_viable_squad_reaches_nothing():
    counts = count_positions(squad_of(POR=1, DEF=3, MED=4, DEL=2))
    assert feasible_formations(counts, RULES) == ()


def test_deep_squad_reaches_every_formation():
    counts = count_positions(squad_of(POR=2, DEF=5, MED=5, DEL=3))
    assert set(feasible_formations(counts, RULES)) == {
        "3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-3-2", "5-4-1"
    }


def test_no_goalkeeper_blocks_every_formation():
    counts = count_positions(squad_of(DEF=5, MED=5, DEL=3))
    assert feasible_formations(counts, RULES) == ()
    assert missing_for_xi(counts, RULES) == {"POR": 1}


def test_missing_report_names_only_the_short_positions():
    counts = count_positions(squad_of(POR=1, DEF=2, MED=5, DEL=3))
    assert missing_for_xi(counts, RULES) == {"DEF": 1}


def test_nothing_missing_once_any_formation_is_reachable():
    counts = count_positions(squad_of(POR=1, DEF=3, MED=4, DEL=3))
    assert missing_for_xi(counts, RULES) == {}


def test_missing_report_is_the_cheapest_route_not_a_per_position_floor():
    """1 POR / 3 DEF / 3 MED / 1 DEL meets the per-position minimum of every
    position and still cannot field anything — no single formation wants that
    exact shape. A report built from per-position floors would say 'nothing
    missing' while no XI is reachable, which is the contradiction this
    function must never produce."""
    counts = count_positions(squad_of(POR=1, DEF=3, MED=3, DEL=1))
    assert feasible_formations(counts, RULES) == ()
    assert missing_for_xi(counts, RULES) == {"MED": 1, "DEL": 2}
    assert nearest_formation(counts, RULES) == "3-4-3"


def test_premium_makes_a_forwardless_squad_fieldable():
    """4-6-0 fields no forward at all. The same squad is one forward short
    under the standard seven and complete in a Premium league."""
    counts = count_positions(squad_of(POR=1, DEF=4, MED=6))
    assert feasible_formations(counts, RULES) == ()
    assert missing_for_xi(counts, RULES) == {"DEL": 1}
    assert feasible_formations(counts, PREMIUM_RULES) == ("4-6-0",)
    assert missing_for_xi(counts, PREMIUM_RULES) == {}


def test_nearest_formation_is_none_once_an_xi_is_reachable():
    counts = count_positions(squad_of(POR=1, DEF=3, MED=4, DEL=3))
    assert nearest_formation(counts, RULES) is None


def test_empty_squad_is_legal_but_cannot_field_an_xi():
    verdict = evaluate_squad([], RULES)
    assert verdict.is_legal is True
    assert verdict.violations == ()
    assert verdict.can_field_xi is False


def test_partial_squad_is_incomplete_never_illegal():
    """Spec D-09: incomplete is a distinct state from illegal."""
    verdict = evaluate_squad(squad_of(POR=1, DEF=2), RULES)
    assert verdict.is_legal is True
    assert verdict.violations == ()
    assert verdict.can_field_xi is False
    # Cheapest route is 3-4-3: one more defender, four midfielders, three forwards.
    assert verdict.missing_for_xi == {"DEF": 1, "MED": 4, "DEL": 3}
    assert verdict.nearest_formation == "3-4-3"


def test_squad_at_exactly_the_cap_is_legal():
    verdict = evaluate_squad(squad_of(POR=2, DEF=8, MED=8, DEL=6), RULES)
    assert verdict.squad_size == 24
    assert verdict.is_legal is True


def test_squad_one_over_the_cap_is_illegal_and_says_so():
    verdict = evaluate_squad(squad_of(POR=2, DEF=8, MED=8, DEL=7), RULES)
    assert verdict.squad_size == 25
    assert verdict.is_legal is False
    violation = verdict.violations[0]
    assert violation.rule == "squad_size"
    assert violation.actual == 25
    assert violation.limit == 24
    assert "remove" in violation.message.lower()


def test_squad_value_falls_back_to_purchase_price_when_a_snapshot_is_missing():
    """A rejected scrape must not make a squad member worth zero."""
    members = [
        SquadMember(1, "Keeper", "POR", purchase_price=3_000_000, market_value=None),
        SquadMember(2, "Back", "DEF", purchase_price=1_000_000, market_value=2_000_000),
    ]
    verdict = evaluate_squad(members, RULES)
    assert verdict.squad_value == 5_000_000


def test_legal_squad_can_still_be_unable_to_field_an_xi():
    """The whole reason spec D-07 keeps the layers apart: 24 legal players,
    every one of them a midfielder, and no formation is reachable."""
    verdict = evaluate_squad(squad_of(MED=24), RULES)
    assert verdict.is_legal is True
    assert verdict.violations == ()
    assert verdict.can_field_xi is False
    # Cheapest route from 24 midfielders is 3-5-2: a keeper, three defenders, two forwards.
    assert verdict.missing_for_xi == {"POR": 1, "DEF": 3, "DEL": 2}
    assert verdict.nearest_formation == "3-5-2"


def candidate(price: int, position: str = "DEL") -> SquadMember:
    return SquadMember(
        player_id=999,
        name="Target",
        position=position,
        purchase_price=price,
        market_value=price,
    )


def test_add_is_allowed_when_squad_has_room():
    verdict = evaluate_add(squad_of(POR=1), candidate(5_000_000), RULES)
    assert verdict.allowed is True
    assert verdict.violation is None
    assert verdict.resulting.squad_size == 2


def test_add_to_a_full_squad_is_refused_naming_the_cap():
    full = squad_of(POR=2, DEF=8, MED=8, DEL=6)
    verdict = evaluate_add(full, candidate(1), RULES)
    assert verdict.allowed is False
    assert verdict.violation.rule == "squad_size"
    assert verdict.violation.limit == 24
    assert "24" in verdict.violation.message


def test_add_of_a_player_already_owned_is_refused():
    owned = [member(7, "DEL")]
    duplicate = SquadMember(7, "Player 7", "DEL", purchase_price=1, market_value=1)
    verdict = evaluate_add(owned, duplicate, RULES)
    assert verdict.allowed is False
    assert verdict.violation.rule == "already_owned"
    assert verdict.violation.actual == 1
    assert verdict.violation.limit == 0


def test_add_with_a_negative_purchase_price_is_refused():
    verdict = evaluate_add(squad_of(POR=1), candidate(-1), RULES)
    assert verdict.allowed is False
    assert verdict.violation.rule == "purchase_price"


def test_the_last_add_that_unlocks_a_formation_reports_it():
    nearly = squad_of(POR=1, DEF=3, MED=4, DEL=2)
    verdict = evaluate_add(nearly, candidate(1, "DEL"), RULES)
    assert verdict.allowed is True
    assert verdict.resulting.can_field_xi is True
    assert verdict.resulting.feasible_formations == ("3-4-3",)


def test_evaluate_squad_takes_no_cash_balance():
    # The game pays €100k a day if you claim it and forfeits it if you don't,
    # so a derived balance is wrong by design. The engine no longer pretends
    # to know one. See the 2026-08-21 spec.
    rules = load_rules()
    members = [_member(player_id=i, purchase_price=1_000_000) for i in range(3)]

    verdict = evaluate_squad(members, rules)

    assert verdict.squad_size == 3
    assert verdict.squad_value == 3_000_000
    assert not hasattr(verdict, "cash_balance")
    assert not hasattr(verdict, "spending_power")
    assert not hasattr(verdict, "in_debt")


def test_a_squad_is_never_illegal_for_money_reasons():
    # debt_limit and spending_power are gone. The only standing-squad
    # violation left is the 24-player cap.
    rules = load_rules()
    members = [_member(player_id=i, purchase_price=90_000_000) for i in range(3)]

    verdict = evaluate_squad(members, rules)

    assert verdict.is_legal
    assert verdict.violations == ()


def test_evaluate_add_refuses_only_on_squad_shape_not_price():
    # An expensive player is no longer refusable — the app cannot know what
    # you can afford, and the owner reads that off the official app.
    rules = load_rules()
    members = [_member(player_id=i, purchase_price=0) for i in range(3)]
    candidate = _member(player_id=99, name="Raphinha", purchase_price=93_471_864)

    verdict = evaluate_add(members, candidate, rules)

    assert verdict.allowed
    assert verdict.violation is None
