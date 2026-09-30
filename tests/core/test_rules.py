"""The rules loader must reproduce docs/RULES-LALIGA-FANTASY.md exactly.

These assertions are deliberately literal: they are the tripwire that fires
if someone edits the JSON without editing the doc's change log, or vice versa.
"""

from core.rules import load_rules


def test_squad_cap_is_24():
    assert load_rules().max_squad_size == 24


def test_debt_limit_is_twenty_percent():
    assert load_rules().debt_limit_fraction == 0.20


def test_exactly_the_seven_standard_formations():
    names = {f.name for f in load_rules().for_league(premium_enabled=False).formations}
    assert names == {"3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-3-2", "5-4-1"}


def test_premium_adds_exactly_five_more():
    standard = {f.name for f in load_rules().for_league(premium_enabled=False).formations}
    premium = {f.name for f in load_rules().for_league(premium_enabled=True).formations}
    assert premium - standard == {"3-3-4", "3-6-1", "4-2-4", "4-6-0", "5-2-3"}
    assert standard < premium


def test_every_formation_fields_exactly_eleven_with_one_keeper():
    for formation in load_rules().formations:
        assert formation.POR == 1, formation.name
        total = formation.POR + formation.DEF + formation.MED + formation.DEL
        assert total == 11, f"{formation.name} fields {total}"


def test_formation_shape_matches_its_name():
    for formation in load_rules().formations:
        assert formation.name == f"{formation.DEF}-{formation.MED}-{formation.DEL}"


def test_minimum_squad_able_to_field_any_standard_xi():
    rules = load_rules().for_league(premium_enabled=False)
    assert rules.min_squad_for_any_xi() == {"POR": 1, "DEF": 3, "MED": 3, "DEL": 1}


def test_premium_lowers_the_minimum_because_4_6_0_needs_no_forward():
    rules = load_rules().for_league(premium_enabled=True)
    assert rules.min_squad_for_any_xi() == {"POR": 1, "DEF": 3, "MED": 2, "DEL": 0}


def test_rules_carry_their_provenance():
    rules = load_rules()
    assert rules.retrieved_on == "2026-08-07"
    assert "laligafantasy.zendesk.com" in rules.source_url


def test_load_rules_is_cached():
    assert load_rules() is load_rules()


def test_cash_per_point_comes_from_the_rules_data():
    """Never a literal in logic — a mid-season rate change must be one dated
    edit to the versioned rules, not a hunt through the codebase."""
    assert load_rules().cash_per_point == 100_000


def test_violation_is_defined_in_rules_and_shared_by_squad_rules():
    """LN-23 forbids `core.lineup_rules` importing from `core.squad_rules`,
    so the refusal DTO both engines emit lives in `core.rules` — one
    definition, not two structurally identical ones (plan P-05)."""
    from core.rules import Violation
    from core.squad_rules import Violation as SquadViolation

    assert SquadViolation is Violation

    v = Violation(rule="xi_size", actual=10, limit=11, message="Ten players.")
    assert (v.rule, v.actual, v.limit, v.message) == ("xi_size", 10, 11, "Ten players.")
