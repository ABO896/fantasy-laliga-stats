"""`core.transfers` — MODEL-05 bids, expected return, TRANSFER-01…05.

Pure, so every case is hand-built. Rule values (squad cap, formations,
cash per point) are read from `core.rules`, never restated here."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from core.fixture_difficulty import TeamFixture
from core.rules import load_rules
from core.squad_rules import SquadMember
from core.transfers import (
    AVAILABILITY_FACTOR,
    FIXTURE_WEIGHT,
    MAX_BID_PREMIUM,
    MAX_GAP_COUNTED,
    SURPLUS_SHARE,
    PlayerInput,
    assess_freshness,
    assess_player,
    bargains,
    best_for_position,
    check_move,
    compute_bids,
    confidence_label,
    fixture_outlook,
    suggest_moves,
)

RULES = load_rules().for_league(False)
CPP = RULES.cash_per_point
NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def _p(pid, position="MED", mv=10_000_000, ppg=5.0, **kw) -> PlayerInput:
    base = dict(
        player_id=pid, name=f"P{pid}", team=f"T{pid}", position=position, market_value=mv,
        source_ideal_bid=mv, source_max_bid=mv, availability="available",
        starter_probability=None, backward_ppg=ppg, recent_jornadas=10,
        expected_points=None, fair_value=None, valuation_gap=None, economy=None,
        power_score=None, predicted_pct=None, prediction_confidence=None,
    )
    base.update(kw)
    return PlayerInput(**base)


def _tf(opponent, difficulty, is_home=True, matchday=8):
    return TeamFixture(
        fixture_id=hash((opponent, matchday)) & 0xFFFF, matchday=matchday,
        kickoff_utc=NOW + timedelta(days=matchday), kickoff_confirmed=True,
        opponent=opponent, is_home=is_home, opponent_strength=difficulty,
        difficulty=difficulty,
    )


# --- MODEL-05: our own bids -------------------------------------------------------


def test_bids_never_go_below_market_value():
    bids = compute_bids(_p(1, predicted_pct=-2.0))
    assert bids.ideal == 10_000_000
    assert bids.maximum == 10_000_000


def test_ideal_bid_is_the_predicted_post_update_value_for_a_riser():
    bids = compute_bids(_p(1, predicted_pct=2.0))
    assert bids.ideal == 10_200_000
    assert bids.maximum >= bids.ideal


def test_max_bid_adds_a_share_of_the_valuation_gap_and_is_capped():
    modest = compute_bids(_p(1, valuation_gap=0.2, predicted_pct=0.0))
    assert modest.maximum == round(10_000_000 * (1 + SURPLUS_SHARE * 0.2))
    huge_gap = compute_bids(_p(1, valuation_gap=40.0, predicted_pct=0.0))
    assert huge_gap.maximum == round(10_000_000 * (1 + SURPLUS_SHARE * MAX_GAP_COUNTED))
    capped = compute_bids(_p(1, valuation_gap=40.0, predicted_pct=9.0))
    assert capped.maximum == round(10_000_000 * (1 + MAX_BID_PREMIUM))


def test_max_bid_carries_no_surplus_for_an_unavailable_player():
    bids = compute_bids(_p(1, valuation_gap=1.0, availability="injured"))
    assert bids.maximum == bids.ideal == 10_000_000


def test_bids_report_their_inputs():
    bids = compute_bids(_p(1, predicted_pct=1.0, fair_value=11_000_000))
    assert bids.inputs["predictedPct"] == 1.0
    assert bids.inputs["fairValue"] == 11_000_000


# --- TRANSFER-03: fixture outlook ----------------------------------------------------


def test_fixture_outlook_neutral_without_fixture_data():
    out = fixture_outlook(None, jornadas=3)
    assert out.multiplier == 1.0
    assert out.available is False
    assert out.driver is None


def test_fixture_outlook_rewards_easy_runs_and_names_the_driving_opponent():
    easy = fixture_outlook([_tf("Weak", 0.5), _tf("Avg", 1.0, matchday=9)], jornadas=2)
    assert easy.multiplier == pytest.approx((1 + FIXTURE_WEIGHT * 0.5 + 1) / 2)
    assert easy.driver.opponent == "Weak"
    hard = fixture_outlook([_tf("Madrid", 1.8, is_home=False)], jornadas=1)
    assert hard.multiplier < 1.0
    assert hard.driver.opponent == "Madrid"


def test_fixture_outlook_charges_a_blank_jornada():
    one_game = fixture_outlook([_tf("Avg", 1.0)], jornadas=3)
    assert one_game.multiplier == pytest.approx(1 / 3)


# --- expected return ----------------------------------------------------------------


def test_expected_return_applies_fixtures_and_minutes():
    a = assess_player(_p(1, ppg=6.0, availability="doubtful", starter_probability=100.0),
                      fixture_outlook(None, 3), jornadas=3, cash_per_point=CPP)
    assert a.expected_return == pytest.approx(6.0 * AVAILABILITY_FACTOR["doubtful"])
    assert a.minutes_factor == AVAILABILITY_FACTOR["doubtful"]


def test_starter_probability_scales_minutes_with_a_floor():
    a = assess_player(_p(1, ppg=4.0, starter_probability=0.0), fixture_outlook(None, 3),
                      jornadas=3, cash_per_point=CPP)
    assert a.expected_return == pytest.approx(2.0)


def test_expected_points_blend_in_when_supplied_and_skip_the_minutes_guess():
    a = assess_player(_p(1, ppg=4.0, expected_points=8.0, availability="doubtful"),
                      fixture_outlook(None, 3), jornadas=3, cash_per_point=CPP)
    assert a.expected_points_used is True
    assert a.expected_return == pytest.approx(0.5 * 8.0 + 0.5 * 4.0)


def test_no_evidence_means_no_expected_return():
    a = assess_player(_p(1, ppg=None), fixture_outlook(None, 3), jornadas=3,
                      cash_per_point=CPP)
    assert a.expected_return is None
    assert a.hold_value is None


def test_hold_value_adds_the_predicted_move_at_the_rules_exchange_rate():
    a = assess_player(_p(1, ppg=5.0, predicted_pct=1.0), fixture_outlook(None, 2),
                      jornadas=2, cash_per_point=CPP)
    assert a.points_term == pytest.approx(10.0)
    assert a.value_term == pytest.approx(10_000_000 * 0.01 / CPP)
    assert a.hold_value == pytest.approx(a.points_term + a.value_term)


# --- TRANSFER-02: legality ----------------------------------------------------------


def _member(pid, position):
    return SquadMember(pid, f"P{pid}", position, 1_000_000, 1_000_000)


def _full_squad():
    """At the cap, with exactly one goalkeeper."""
    positions = ["POR"] + ["DEF"] * 8 + ["MED"] * 8 + ["DEL"] * 7
    assert len(positions) == RULES.max_squad_size
    return [_member(i + 1, pos) for i, pos in enumerate(positions)]


def test_a_same_position_swap_at_the_cap_is_legal():
    squad = _full_squad()
    verdict = check_move(squad, 2, _member(100, "DEF"), RULES)
    assert verdict.allowed
    assert verdict.resulting.squad_size == RULES.max_squad_size


def test_an_add_to_a_full_squad_is_refused():
    verdict = check_move(_full_squad(), None, _member(100, "DEF"), RULES)
    assert not verdict.allowed
    assert verdict.violation.rule == "squad_size"


def test_selling_the_only_goalkeeper_for_an_outfielder_is_refused():
    verdict = check_move(_full_squad(), 1, _member(100, "DEL"), RULES)
    assert not verdict.allowed
    assert verdict.violation.rule == "xi_feasibility"


def test_buying_someone_already_owned_is_refused():
    verdict = check_move(_full_squad(), 2, _member(3, "DEF"), RULES)
    assert not verdict.allowed
    assert verdict.violation.rule == "already_owned"


def test_selling_a_player_not_in_the_squad_is_refused():
    verdict = check_move(_full_squad(), 999, _member(100, "DEF"), RULES)
    assert not verdict.allowed
    assert verdict.violation.rule == "not_in_squad"


def test_an_incomplete_squad_may_move_but_never_further_from_an_xi():
    squad = [_member(1, "POR")] + [_member(2 + i, "DEF") for i in range(5)] + [_member(7, "MED")]
    assert check_move(squad, 2, _member(100, "DEL"), RULES).allowed  # same distance
    assert check_move(squad, 7, _member(100, "MED"), RULES).allowed  # like for like
    worse = check_move(squad, 7, _member(100, "DEF"), RULES)  # a sixth defender, no midfield
    assert not worse.allowed
    assert worse.violation.rule == "xi_feasibility"


# --- TRANSFER-04: freshness ---------------------------------------------------------


def test_fresh_data_keeps_full_confidence():
    f = assess_freshness(
        {"market": NOW - timedelta(hours=1), "jornada_points": NOW - timedelta(days=1),
         "fixtures": NOW - timedelta(days=1), "football_data": None},
        now=NOW, fixtures_available=True, expected_points_used=False,
    )
    assert f.factor == 1.0
    assert f.reasons == []


def test_stale_market_loses_confidence_per_missed_update_and_says_why():
    f = assess_freshness(
        {"market": NOW - timedelta(days=3), "jornada_points": NOW - timedelta(days=1),
         "fixtures": NOW - timedelta(days=1), "football_data": None},
        now=NOW, fixtures_available=True, expected_points_used=False,
    )
    assert f.factor < 0.75
    assert any("market update" in r for r in f.reasons)


def test_missing_fixtures_and_old_points_both_cost_confidence():
    f = assess_freshness(
        {"market": NOW - timedelta(hours=1), "jornada_points": NOW - timedelta(days=20),
         "fixtures": None, "football_data": None},
        now=NOW, fixtures_available=False, expected_points_used=False,
    )
    assert f.factor < 1.0
    assert any("fixture" in r.lower() for r in f.reasons)
    assert any("jornada points" in r.lower() for r in f.reasons)


def test_odds_age_only_matters_once_expected_points_use_them():
    ages = {"market": NOW - timedelta(hours=1), "jornada_points": NOW - timedelta(days=1),
            "fixtures": NOW - timedelta(days=1), "football_data": NOW - timedelta(days=30)}
    assert assess_freshness(ages, NOW, True, expected_points_used=False).factor == 1.0
    assert assess_freshness(ages, NOW, True, expected_points_used=True).factor < 1.0


def test_confidence_labels():
    assert confidence_label(0.9) == "high"
    assert confidence_label(0.6) == "medium"
    assert confidence_label(0.3) == "low"


# --- TRANSFER-01: suggestions -------------------------------------------------------


def _assess(players, jornadas=3, outlooks=None):
    outlooks = outlooks or {}
    return {
        p.player_id: assess_player(p, outlooks.get(p.player_id, fixture_outlook(None, jornadas)),
                                   jornadas=jornadas, cash_per_point=CPP)
        for p in players
    }


def _fresh():
    return assess_freshness(
        {"market": NOW, "jornada_points": NOW, "fixtures": NOW, "football_data": None},
        now=NOW, fixtures_available=True, expected_points_used=False,
    )


def test_suggests_upgrading_a_weak_player_and_shows_its_signals():
    squad = _full_squad()
    owned = [_p(m.player_id, m.position, mv=1_000_000, ppg=3.0) for m in squad]
    owned[1] = _p(2, "DEF", mv=1_000_000, ppg=0.5)  # the weak one
    target = _p(100, "DEF", mv=2_000_000, ppg=6.0)
    assessments = _assess([*owned, target])
    moves = suggest_moves(squad, assessments, RULES, ceiling=None, freshness=_fresh(), jornadas=3)
    assert moves[0].sell.player_id == 2
    assert moves[0].buy.player_id == 100
    names = [s.name for s in moves[0].signals]
    assert "points" in names and "efficiency" in names
    assert moves[0].gain > 0


def test_suggestions_respect_the_owners_ceiling():
    squad = _full_squad()
    owned = [_p(m.player_id, m.position, mv=1_000_000, ppg=3.0) for m in squad]
    pricey = _p(100, "DEF", mv=50_000_000, ppg=9.0)
    cheap = _p(101, "DEF", mv=3_000_000, ppg=5.0)
    assessments = _assess([*owned, pricey, cheap])
    moves = suggest_moves(squad, assessments, RULES, ceiling=(5_000_000, "marketValue"),
                          freshness=_fresh(), jornadas=3)
    assert moves
    assert all(m.buy.player_id != 100 for m in moves)


def test_every_suggested_move_is_legal():
    squad = _full_squad()
    owned = [_p(m.player_id, m.position, mv=1_000_000, ppg=1.0) for m in squad]
    # A star forward — only reachable by selling the goalkeeper if the engine
    # were not consulted, since he is the weakest player.
    owned[0] = _p(1, "POR", mv=1_000_000, ppg=0.0)
    star = _p(100, "DEL", mv=2_000_000, ppg=9.0)
    assessments = _assess([*owned, star])
    moves = suggest_moves(squad, assessments, RULES, ceiling=None, freshness=_fresh(), jornadas=3)
    assert all(not (m.sell and m.sell.player_id == 1 and m.buy.position != "POR") for m in moves)
    for m in moves:
        assert check_move(squad, m.sell.player_id if m.sell else None,
                          _member(m.buy.player_id, m.buy.position), RULES).allowed


def test_each_player_appears_in_at_most_one_move():
    squad = _full_squad()
    owned = [_p(m.player_id, m.position, mv=1_000_000, ppg=0.5) for m in squad]
    pool = [_p(100 + i, "MED", mv=2_000_000, ppg=6.0 + i) for i in range(5)]
    moves = suggest_moves(squad, _assess([*owned, *pool]), RULES, ceiling=None,
                          freshness=_fresh(), jornadas=3, limit=10)
    sells = [m.sell.player_id for m in moves if m.sell]
    buys = [m.buy.player_id for m in moves]
    assert len(sells) == len(set(sells))
    assert len(buys) == len(set(buys))


def test_a_free_slot_yields_an_add_move():
    squad = _full_squad()[:-1]
    owned = [_p(m.player_id, m.position, mv=1_000_000, ppg=3.0) for m in squad]
    target = _p(100, "DEL", mv=2_000_000, ppg=6.0)
    moves = suggest_moves(squad, _assess([*owned, target]), RULES, ceiling=None,
                          freshness=_fresh(), jornadas=3)
    adds = [m for m in moves if m.kind == "add"]
    assert adds and adds[0].buy.player_id == 100 and adds[0].sell is None


def test_injured_players_are_never_suggested_buys():
    squad = _full_squad()
    owned = [_p(m.player_id, m.position, mv=1_000_000, ppg=1.0) for m in squad]
    hurt = _p(100, "DEF", mv=2_000_000, ppg=9.0, availability="injured")
    moves = suggest_moves(squad, _assess([*owned, hurt]), RULES, ceiling=None,
                          freshness=_fresh(), jornadas=3)
    assert all(m.buy.player_id != 100 for m in moves)


def test_confidence_falls_with_stale_data_and_thin_evidence():
    squad = _full_squad()
    owned = [_p(m.player_id, m.position, mv=1_000_000, ppg=3.0) for m in squad]
    owned[1] = _p(2, "DEF", mv=1_000_000, ppg=0.5)
    target = _p(100, "DEF", mv=2_000_000, ppg=6.0, recent_jornadas=2)
    assessments = _assess([*owned, target])
    stale = assess_freshness(
        {"market": NOW - timedelta(days=4), "jornada_points": NOW, "fixtures": NOW,
         "football_data": None}, now=NOW, fixtures_available=True, expected_points_used=False)
    fresh_move = suggest_moves(squad, assessments, RULES, None, _fresh(), 3)[0]
    stale_move = suggest_moves(squad, assessments, RULES, None, stale, 3)[0]
    assert stale_move.confidence < fresh_move.confidence
    assert any("market update" in r for r in stale_move.confidence_reasons)
    assert any("2 jornadas" in r for r in fresh_move.confidence_reasons)


def test_fixture_driver_is_carried_on_the_move():
    squad = _full_squad()
    owned = [_p(m.player_id, m.position, mv=1_000_000, ppg=3.0) for m in squad]
    target = _p(100, "DEF", mv=2_000_000, ppg=3.0)
    outlooks = {100: fixture_outlook([_tf("Weak", 0.4)], jornadas=1),
                2: fixture_outlook([_tf("Madrid", 1.8, is_home=False)], jornadas=1)}
    moves = suggest_moves(squad, _assess([*owned, target], jornadas=1, outlooks=outlooks),
                          RULES, None, _fresh(), 1)
    move = next(m for m in moves if m.buy.player_id == 100)
    assert move.sell.player_id == 2
    fixtures = next(s for s in move.signals if s.name == "fixtures")
    assert "Weak" in fixtures.text and "Madrid" in fixtures.text


# --- TRANSFER-05 and bargains -------------------------------------------------------


def test_best_for_position_toggles_the_ceiling():
    players = [_p(1, "DEL", mv=80_000_000, ppg=9.0), _p(2, "DEL", mv=5_000_000, ppg=6.0),
               _p(3, "MED", mv=1_000_000, ppg=10.0)]
    a = _assess(players)
    within = best_for_position(a, "DEL", ceiling=(10_000_000, "marketValue"), affordable_only=True)
    assert [x.player_id for x in within] == [2]
    regardless = best_for_position(a, "DEL", ceiling=(10_000_000, "marketValue"),
                                   affordable_only=False)
    assert [x.player_id for x in regardless] == [1, 2]


def test_best_for_position_filters_by_our_own_bid_basis():
    players = [_p(1, "DEL", mv=10_000_000, ppg=9.0, predicted_pct=5.0)]
    a = _assess(players)
    assert best_for_position(a, "DEL", (10_000_000, "marketValue"), True)
    assert not best_for_position(a, "DEL", (10_000_000, "ourIdealBid"), True)


def test_bargains_rank_expected_return_against_price_and_skip_non_players():
    players = [_p(i, "MED", mv=1_000_000 * (i + 1), ppg=1.0 + i * 0.5) for i in range(20)]
    players.append(_p(50, "MED", mv=2_000_000, ppg=9.0))  # the bargain
    players.append(_p(51, "MED", mv=500_000, ppg=0.2))  # cheap non-player
    rows = bargains(_assess(players))
    assert rows[0].assessment.player_id == 50
    assert all(r.assessment.player_id != 51 for r in rows)
    assert rows[0].forward_gap > 0


def test_ceiling_on_an_unknown_price_excludes_the_player():
    p = replace(_p(1, "DEL"), source_ideal_bid=None)
    a = _assess([p])
    assert not best_for_position(a, "DEL", (99_000_000, "idealBid"), True)


# --- the fixture window and the best XI ---------------------------------------------


def _fv(fid, matchday, home, away, days, is_final=False):
    from core.fixture_difficulty import FixtureView

    return FixtureView(fid, matchday, NOW + timedelta(days=days), True, is_final, home, away)


def test_a_mostly_played_jornada_is_not_a_window_jornada_but_its_catch_up_counts():
    fixtures = [
        _fv(1, 6, "A", "B", -5, is_final=True),
        _fv(2, 6, "C", "D", -5, is_final=True),
        _fv(3, 6, "E", "F", -5, is_final=True),
        _fv(4, 6, "G", "H", 1.5),  # postponed, played inside the window
        _fv(5, 8, "A", "C", 2), _fv(6, 8, "B", "D", 2), _fv(7, 8, "E", "G", 2),
        _fv(8, 8, "F", "H", 2),
        _fv(9, 9, "A", "D", 9), _fv(10, 9, "B", "C", 9), _fv(11, 9, "E", "H", 9),
        _fv(12, 9, "F", "G", 9),
        _fv(13, 6, "X", "Y", 30),  # postponed far beyond the window: not weighed
    ]
    from core.transfers import select_window

    jornadas, weighed = select_window(fixtures, NOW, 1)
    assert jornadas == [8]
    assert {f.fixture_id for f in weighed} == {4, 5, 6, 7, 8}
    jornadas, weighed = select_window(fixtures, NOW, 2)
    assert jornadas == [8, 9]
    assert 13 not in {f.fixture_id for f in weighed}


def test_best_xi_only_counts_starters():
    from core.transfers import best_xi

    squad = [(1, "POR", 5.0), (2, "POR", 9.0)] + [(10 + i, "DEF", 3.0) for i in range(4)] + [
        (20 + i, "MED", 3.0) for i in range(4)] + [(30 + i, "DEL", 3.0) for i in range(2)]
    total, starters = best_xi(squad, RULES)
    assert 2 in starters and 1 not in starters
    assert total == pytest.approx(9.0 + 10 * 3.0)


def test_a_good_backup_goalkeeper_is_not_worth_buying_over_an_outfield_upgrade():
    squad = _full_squad()
    owned = [_p(m.player_id, m.position, mv=1_000_000, ppg=3.0) for m in squad]
    owned[0] = _p(1, "POR", mv=1_000_000, ppg=6.0)
    keeper = _p(100, "POR", mv=2_000_000, ppg=5.5)  # better than every outfielder, but benched
    winger = _p(101, "MED", mv=2_000_000, ppg=4.0)
    moves = suggest_moves(squad, _assess([*owned, keeper, winger]), RULES, None, _fresh(), 3)
    assert moves[0].buy.player_id == 101
    assert all(m.buy.player_id != 100 for m in moves)
