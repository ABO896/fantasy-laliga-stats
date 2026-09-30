"""The XI engine's boundaries. Pure functions, so every one of these is a
cheap unit test — which is the point: a wrong verdict here either refuses an
arrangement the game permits, or accepts one it scores zero.

Two things changed on 2026-08-22 when the gameweek went away. There is no
deadline, so nothing freezes and nothing is recorded late. And an
under-filled XI is now *accepted and incomplete* rather than refused: a
squad being built is a normal state, and an app that calls it illegal is
wrong about what the owner is doing (spec D-09, applied to a partial XI).
"""

import pytest

from core.lineup_rules import (
    EligiblePlayer,
    LeagueFeatures,
    LineupSelection,
    evaluate_lineup,
)
from core.rules import load_rules

STANDARD = load_rules().for_league(premium_enabled=False)
PREMIUM = load_rules().for_league(premium_enabled=True)
NO_BENCH = LeagueFeatures(bench_enabled=False)
WITH_BENCH = LeagueFeatures(bench_enabled=True)


def squad(por=2, dfn=8, mid=8, fwd=6) -> list[EligiblePlayer]:
    """A squad large enough to field any shape, with predictable ids:
    100s are keepers, 200s defenders, 300s midfielders, 400s forwards."""
    people = []
    for base, position, count in (
        (100, "POR", por),
        (200, "DEF", dfn),
        (300, "MED", mid),
        (400, "DEL", fwd),
    ):
        for n in range(count):
            people.append(
                EligiblePlayer(player_id=base + n, name=f"{position}{n}", position=position)
            )
    return people


def xi(por=1, dfn=4, mid=4, fwd=2) -> tuple[int, ...]:
    ids = []
    for base, count in ((100, por), (200, dfn), (300, mid), (400, fwd)):
        ids.extend(base + n for n in range(count))
    return tuple(ids)


def evaluate(selection, *, eligible=None, rules=STANDARD, features=NO_BENCH):
    return evaluate_lineup(
        selection,
        squad() if eligible is None else eligible,
        rules,
        features,
    )


# --- shape -----------------------------------------------------------------


def test_a_complete_xi_is_accepted_and_complete():
    verdict = evaluate(LineupSelection(formation="4-4-2", starter_ids=xi()))
    assert verdict.allowed is True
    assert verdict.violation is None
    assert verdict.is_complete is True
    assert verdict.position_counts == {"POR": 1, "DEF": 4, "MED": 4, "DEL": 2}


def test_an_empty_pitch_is_accepted_and_incomplete():
    verdict = evaluate(LineupSelection(formation="4-4-2", starter_ids=()))
    assert verdict.allowed is True
    assert verdict.is_complete is False


def test_an_under_filled_position_is_accepted_and_incomplete():
    """A squad being built is a normal state. Refusing it would make the page
    unusable for exactly the owner it is for."""
    verdict = evaluate(LineupSelection(formation="4-4-2", starter_ids=xi(dfn=3)))
    assert verdict.allowed is True
    assert verdict.is_complete is False
    assert verdict.position_counts["DEF"] == 3


def test_an_over_filled_position_is_refused_with_the_position_named():
    verdict = evaluate(LineupSelection(formation="4-4-2", starter_ids=xi(dfn=5, mid=3)))
    assert verdict.allowed is False
    assert verdict.violation.rule == "formation_shape"
    assert verdict.violation.actual == 5
    assert verdict.violation.limit == 4
    assert "defender" in verdict.violation.message


def test_there_is_no_separate_size_rule():
    """Over-filling is impossible without some position exceeding its count,
    and `formation_shape` names that position. A size rule could only fire
    where this one already did, with a vaguer remedy."""
    verdict = evaluate(LineupSelection(formation="4-4-2", starter_ids=xi(fwd=3)))
    assert verdict.violation.rule == "formation_shape"


# --- formation -------------------------------------------------------------


def test_a_formation_outside_the_leagues_set_is_refused():
    verdict = evaluate(LineupSelection(formation="4-6-0", starter_ids=()))
    assert verdict.allowed is False
    assert verdict.violation.rule == "formation_unavailable"


def test_a_premium_formation_is_accepted_when_the_league_allows_it():
    verdict = evaluate(
        LineupSelection(formation="4-6-0", starter_ids=xi(dfn=4, mid=6, fwd=0)),
        rules=PREMIUM,
    )
    assert verdict.allowed is True
    assert verdict.is_complete is True


def test_an_unknown_formation_name_is_refused():
    verdict = evaluate(LineupSelection(formation="9-9-9", starter_ids=()))
    assert verdict.violation.rule == "formation_unavailable"


# --- who is being named ----------------------------------------------------


def test_a_player_not_in_the_squad_is_refused():
    verdict = evaluate(LineupSelection(formation="4-4-2", starter_ids=(999,)))
    assert verdict.allowed is False
    assert verdict.violation.rule == "not_in_squad"


def test_a_player_named_twice_is_refused_as_a_duplicate_not_a_shape_error():
    """Checked before shape, because a repeat distorts the position counts
    and would otherwise send the owner to fix a shape that is not wrong."""
    verdict = evaluate(LineupSelection(formation="4-4-2", starter_ids=(200, 200)))
    assert verdict.violation.rule == "duplicate_selection"


def test_a_player_on_both_the_pitch_and_the_bench_is_refused():
    verdict = evaluate(
        LineupSelection(formation="4-4-2", starter_ids=xi(), bench_ids=(200,)),
        features=WITH_BENCH,
    )
    assert verdict.violation.rule == "duplicate_selection"


def test_a_duplicate_that_overfills_a_position_still_reports_the_duplicate():
    """The ordering guard. This is the case that discriminates: the repeat
    pushes DEF to five in a 4-4-2, so a shape check running first would
    refuse it as `formation_shape` and send the owner to fix a shape that is
    not wrong. Both the shipped duplicate tests undercount, and would pass
    either way round."""
    verdict = evaluate(LineupSelection(formation="4-4-2", starter_ids=(*xi(), 200)))
    assert verdict.violation.rule == "duplicate_selection"
    assert verdict.position_counts["DEF"] == 5


def test_an_unknown_player_alongside_an_overfilled_position_reports_the_unknown():
    """The same guard for eligibility. 204 is a real squad defender who makes
    DEF five; 999 is nobody. Shape running first would report
    `formation_shape` and never mention the player who does not exist."""
    verdict = evaluate(LineupSelection(formation="4-4-2", starter_ids=(*xi(), 204, 999)))
    assert verdict.violation.rule == "not_in_squad"
    assert verdict.position_counts["DEF"] == 5


# --- the bench -------------------------------------------------------------


def test_a_bench_given_while_the_feature_is_off_is_refused():
    verdict = evaluate(LineupSelection(formation="4-4-2", starter_ids=xi(), bench_ids=(204,)))
    assert verdict.violation.rule == "bench_disabled"


def test_an_empty_bench_is_valid():
    verdict = evaluate(
        LineupSelection(formation="4-4-2", starter_ids=xi(), bench_ids=()),
        features=WITH_BENCH,
    )
    assert verdict.allowed is True


def test_a_partial_bench_is_valid():
    """An uncovered position just means that starter cannot be substituted,
    which is the owner's business and not an error."""
    verdict = evaluate(
        LineupSelection(formation="4-4-2", starter_ids=xi(), bench_ids=(204, 304)),
        features=WITH_BENCH,
    )
    assert verdict.allowed is True


def test_a_full_bench_of_four_is_valid():
    verdict = evaluate(
        LineupSelection(formation="4-4-2", starter_ids=xi(), bench_ids=(101, 204, 304, 402)),
        features=WITH_BENCH,
    )
    assert verdict.allowed is True


def test_two_substitutes_of_one_position_are_refused():
    verdict = evaluate(
        LineupSelection(formation="4-4-2", starter_ids=xi(), bench_ids=(204, 205)),
        features=WITH_BENCH,
    )
    assert verdict.violation.rule == "bench_position_duplicate"


def test_a_substitute_the_formation_does_not_field_is_refused():
    """A 4-6-0 offers no forward slot, so it offers no forward substitute."""
    verdict = evaluate(
        LineupSelection(formation="4-6-0", starter_ids=xi(dfn=4, mid=6, fwd=0), bench_ids=(400,)),
        rules=PREMIUM,
        features=WITH_BENCH,
    )
    assert verdict.violation.rule == "bench_position_not_fielded"
    assert verdict.violation.actual == 1
    assert verdict.violation.limit == 0


def test_a_bench_may_be_named_while_the_xi_is_still_incomplete():
    verdict = evaluate(
        LineupSelection(formation="4-4-2", starter_ids=xi(dfn=2), bench_ids=(204,)),
        features=WITH_BENCH,
    )
    assert verdict.allowed is True
    assert verdict.is_complete is False


# --- what no longer exists -------------------------------------------------


def test_the_engine_has_no_captain_surface():
    """Guard, not decoration: the captain was removed rather than disabled,
    and a reintroduction should have to be deliberate."""
    assert not hasattr(LineupSelection("4-4-2", ()), "captain_id")
    assert not hasattr(LeagueFeatures(bench_enabled=True), "captain_enabled")


def test_the_engine_needs_no_clock():
    """No deadline, no freeze, no recorded-late. The signature is the proof:
    passing one would be a TypeError."""
    with pytest.raises(TypeError):
        evaluate_lineup(
            LineupSelection(formation="4-4-2", starter_ids=xi()),
            squad(),
            STANDARD,
            NO_BENCH,
            "2026-08-22T00:00:00Z",
        )
