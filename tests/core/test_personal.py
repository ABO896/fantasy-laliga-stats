from core.personal import Candidate, SquadEntry, _cost_phrase, personal_line
from core.rules import load_rules
from core.verdict import Verdict

RULES = load_rules()


def v(label: str, reason: str = "because reasons") -> Verdict:
    return Verdict(player_id=1, label=label, tags=(), reason=reason, confidence="high",
                   deciding={})


def test_empty_squad_has_no_line():
    candidate = Candidate(1, "Someone", "DEF", 5.0, 1_000_000, True)
    assert personal_line(candidate, v("Fair price"), [], [], RULES, 3) is None


def test_owned_sell_label_says_sell():
    owned = SquadEntry(1, "Owned Player", "DEF", 6.0, 2_000_000)
    squad = [owned]
    player = Candidate(1, "Owned Player", "DEF", 6.0, 2_000_000, True)
    verdict = v("Overpriced", reason="Bottom-10% DEF points per €, above the median.")

    line = personal_line(player, verdict, squad, [], RULES, 3)

    assert line.kind == "sell"
    assert line.text == f"Sell — {verdict.reason}"
    assert line.gain is None and line.cost is None
    assert line.other_player_id is None


def test_owned_with_better_option_says_upgrade():
    owned = SquadEntry(1, "Owned Player", "DEF", 6.0, 2_000_000)
    squad = [owned]
    player = Candidate(1, "Owned Player", "DEF", 6.0, 2_000_000, True)
    pool = [Candidate(2, "Better Player", "DEF", 12.0, 3_000_000, True)]

    line = personal_line(player, v("Fair price"), squad, pool, RULES, 3)

    assert line.kind == "upgrade"
    assert line.gain > 0
    assert line.other_player_id == 2
    assert line.other_name == "Better Player"
    assert "Better Player" in line.text


def test_owned_with_nothing_better_says_keep():
    owned = SquadEntry(1, "Owned Player", "DEF", 10.0, 2_000_000)
    squad = [owned]
    player = Candidate(1, "Owned Player", "DEF", 10.0, 2_000_000, True)
    pool = [Candidate(2, "Worse Player", "DEF", 3.0, 3_000_000, True)]
    verdict = v("Fair price", reason="Priced about right.")

    line = personal_line(player, verdict, squad, pool, RULES, 3)

    assert line.kind == "keep"
    assert line.text == f"Keep — {verdict.reason}"


def test_not_owned_replaces_weakest_starter():
    squad = [
        SquadEntry(1, "Keeper", "POR", 6.0, 1_000_000),
        SquadEntry(201, "D1", "DEF", 5.0, 1_000_000),
        SquadEntry(202, "D2", "DEF", 5.0, 1_000_000),
        SquadEntry(203, "D3", "DEF", 5.0, 1_000_000),
        SquadEntry(301, "M1", "MED", 10.0, 1_000_000),
        SquadEntry(302, "M2", "MED", 9.0, 1_000_000),
        SquadEntry(303, "M3", "MED", 6.0, 1_000_000),
        SquadEntry(304, "Weakest Med", "MED", 4.0, 1_000_000),
        SquadEntry(401, "F1", "DEL", 5.0, 1_000_000),
        SquadEntry(402, "F2", "DEL", 5.0, 1_000_000),
        SquadEntry(403, "F3", "DEL", 5.0, 1_000_000),
    ]
    candidate = Candidate(999, "New Med", "MED", 15.0, 4_000_000, True)

    line = personal_line(candidate, v("Fair price"), squad, [], RULES, 3)

    assert line.kind == "replace"
    assert line.gain == 11.0
    assert line.other_player_id == 304
    assert line.other_name == "Weakest Med"


def test_extra_keeper_adds_nothing():
    squad = [
        SquadEntry(101, "Starter Keeper", "POR", 8.0, 1_000_000),
        SquadEntry(102, "Backup Keeper", "POR", 3.0, 1_000_000),
        SquadEntry(201, "D1", "DEF", 5.0, 1_000_000),
        SquadEntry(202, "D2", "DEF", 5.0, 1_000_000),
        SquadEntry(203, "D3", "DEF", 5.0, 1_000_000),
        SquadEntry(204, "D4", "DEF", 5.0, 1_000_000),
        SquadEntry(301, "M1", "MED", 6.0, 1_000_000),
        SquadEntry(302, "M2", "MED", 6.0, 1_000_000),
        SquadEntry(303, "M3", "MED", 6.0, 1_000_000),
        SquadEntry(304, "M4", "MED", 6.0, 1_000_000),
        SquadEntry(305, "M5", "MED", 6.0, 1_000_000),
        SquadEntry(306, "M6", "MED", 6.0, 1_000_000),
    ]
    candidate = Candidate(999, "Third Keeper", "POR", 5.0, 1_000_000, True)

    line = personal_line(candidate, v("Fair price"), squad, [], RULES, 3)

    assert line.kind == "no_improvement"
    assert line.text == "No improvement on your current PORs."


def test_not_owned_fills_empty_slot_when_no_starter_at_position():
    # No MED at all in the squad: there is nobody at the candidate's
    # position to replace, so the line compares against the empty slot
    # (`best_xi(squad + player)`) and names no other player.
    squad = [
        SquadEntry(1, "Keeper", "POR", 6.0, 1_000_000),
        SquadEntry(201, "D1", "DEF", 5.0, 1_000_000),
        SquadEntry(202, "D2", "DEF", 5.0, 1_000_000),
        SquadEntry(203, "D3", "DEF", 5.0, 1_000_000),
        SquadEntry(401, "F1", "DEL", 5.0, 1_000_000),
        SquadEntry(402, "F2", "DEL", 5.0, 1_000_000),
        SquadEntry(403, "F3", "DEL", 5.0, 1_000_000),
    ]
    candidate = Candidate(999, "New Med", "MED", 7.0, 2_000_000, True)

    line = personal_line(candidate, v("Fair price"), squad, [], RULES, 3)

    assert line.kind == "replace"
    assert line.other_player_id is None
    assert line.other_name is None
    assert line.gain == 7.0
    assert line.text == (
        "Would fill your empty MED slot: +7.0 expected points over 3 jornadas, "
        "costs €2.0M"
    )


def test_cost_phrase_with_unknown_cost():
    assert _cost_phrase(None, more=True) == "price unknown"
    assert _cost_phrase(None, more=False) == "price unknown"


def test_ceiling_reports_overage():
    owned = SquadEntry(1, "Owned Player", "DEF", 6.0, 1_000_000)
    squad = [owned]
    player = Candidate(1, "Owned Player", "DEF", 6.0, 1_000_000, True)
    pool = [Candidate(2, "Better Player", "DEF", 12.0, 3_000_000, True)]

    line = personal_line(player, v("Fair price"), squad, pool, RULES, 3, ceiling=1_000_000)

    assert line.kind == "upgrade"
    assert line.over_ceiling_by == 2_000_000
    assert "over your ceiling" in line.text
