import pytest

from core.inputs import PlayerInputs
from core.market_v2 import Outlook
from core.ranks import Rank
from core.reliability import DEFAULT_PRIOR, Evidence, Reliability
from core.verdict import (
    DEFAULT_THRESHOLDS,
    Cutoffs,
    position_cutoffs,
    verdict,
)


def pi(**overrides) -> PlayerInputs:
    """A healthy Regular DEF: evidence ok, all percentiles 50, outlook flat.

    Override names translate into the real `PlayerInputs` shape: `q`, `v`,
    `o` set the within-position percentiles verdict reads; `outlook` is a
    `(direction, expected_pct, drop_risk)` tuple, or `None` for no market
    outlook at all (which also removes the `outlook` rank, as the real
    pipeline would); `power=None` / `points_value=None` remove the
    `power` / `pointsValue` rank without touching anything else.
    """
    position = overrides.get("position", "DEF")
    price = overrides.get("price", 2_000_000)
    availability = overrides.get("availability", "available")
    evidence_ok = overrides.get("evidence_ok", True)
    cls = overrides.get("cls", "Regular")
    confidence = overrides.get("confidence", "medium")
    minutes_trend = overrides.get("minutes_trend", 0.0)
    points_vs_expected = overrides.get("points_vs_expected", 0.0)
    fixture_multiplier = overrides.get("fixture_multiplier", 1.0)
    p_start = overrides.get("p_start", 0.75)

    outlook_spec = overrides.get("outlook", ("flat", 0.0, False))
    outlook = None
    if outlook_spec is not None:
        direction, pct, drop_risk = outlook_spec
        outlook = Outlook(pct, direction, pct - 5, pct + 5, drop_risk, "ridge", {})

    ranks: dict[str, Rank] = {}
    if not ("power" in overrides and overrides["power"] is None):
        ranks["power"] = Rank(1, 2, overrides.get("q", 50.0))
    if not ("points_value" in overrides and overrides["points_value"] is None):
        ranks["pointsValue"] = Rank(1, 2, overrides.get("v", 50.0))
    if outlook is not None:
        ranks["outlook"] = Rank(1, 2, overrides.get("o", 50.0))

    evidence = Evidence(
        matches_with_minutes=10 if evidence_ok else 1,
        last_season_apps=20 if evidence_ok else 0,
        ok=evidence_ok,
        level="high" if evidence_ok else "low",
        reason=None if evidence_ok else "not enough evidence this season",
    )

    reliability = Reliability(
        p_play_next=p_start,
        p_start_next=p_start,
        start_share=0.8,
        play_share=0.9,
        sub_share=0.1,
        minutes_share=0.8,
        shrunk_start=p_start,
        shrunk_play=p_start,
        source_starter=None,
        availability=availability,
        availability_factor=1.0,
        minutes_trend=minutes_trend,
        matches=10,
        appearances=10,
        cls=cls,
        confidence="high",
        basis="matches",
    )

    return PlayerInputs(
        player_id=overrides.get("player_id", 1),
        position=position,
        team="TeamA",
        price=price,
        price_as_of=None,
        availability=availability,
        power_inputs=None,
        power=None,
        reliability=reliability,
        prior=DEFAULT_PRIOR,
        evidence=evidence,
        xpts=None,
        replacement=None,
        points_value=None,
        points_value_reason=None,
        points_vs_expected=points_vs_expected,
        outlook=outlook,
        expected_return_eur=None,
        fixture_multiplier=fixture_multiplier,
        confidence=confidence,
        ranks=ranks,
    )


CUTOFFS = Cutoffs({"DEF": 5_000_000.0})


@pytest.mark.parametrize(("overrides", "label"), [
    ({"availability": "injured"}, "Unavailable"),
    ({"evidence_ok": False}, "Unproven"),
    ({"price": 9_000_000, "outlook": ("fall", -2.5, True), "minutes_trend": -20}, "Sell high"),
    ({"q": 95, "cls": "Nailed"}, "Elite"),
    ({"v": 85, "q": 60, "cls": "Regular", "confidence": "high"}, "Bargain"),
    ({"o": 90, "outlook": ("rise", 2.0, False)}, "Rising"),
    ({"v": 10, "price": 9_000_000}, "Overpriced"),
    ({"q": 10, "cls": "Fringe"}, "Avoid"),
    ({}, "Fair price"),
])
def test_first_match_wins(overrides, label):
    v = verdict(pi(**overrides), CUTOFFS)
    assert v.label == label


def test_rotation_risk_with_disabled_empty():
    """Test that Rotation risk is returned when explicitly enabled."""
    v = verdict(pi(q=70, cls="Rotation"), CUTOFFS, disabled=frozenset())
    assert v.label == "Rotation risk"


def test_rotation_risk_disabled_by_default_falls_through():
    """With module default (Rotation risk disabled), a player matching only
    that rule falls through to the next matching rule."""
    # q=70, cls="Rotation" matches Rotation risk rule, but it's disabled by
    # default, so it falls through. No other rules match (q > avoid_quality,
    # no outlook direction to trigger Avoid), so it's Fair price.
    v = verdict(pi(q=70, cls="Rotation"), CUTOFFS)
    assert v.label != "Rotation risk"
    assert v.label == "Fair price"


def test_success_criterion_2():
    extreme = pi(evidence_ok=False, q=99, v=99, o=99, cls="Nailed", confidence="high",
                 outlook=("rise", 5.0, False))
    assert verdict(extreme, CUTOFFS).label not in {"Bargain", "Elite", "Rising"}

    fringe = pi(cls="Fringe", v=99, q=99, confidence="high")
    assert verdict(fringe, CUTOFFS).label != "Bargain"


def test_missing_inputs_never_satisfy_a_rule():
    no_value = pi(points_value=None, price=9_000_000)
    assert verdict(no_value, CUTOFFS).label != "Overpriced"

    no_outlook_sell = pi(outlook=None, price=9_000_000, minutes_trend=-20)
    assert verdict(no_outlook_sell, CUTOFFS).label != "Sell high"

    no_outlook_rising = pi(outlook=None, cls="Nailed", confidence="high")
    assert verdict(no_outlook_rising, CUTOFFS).label != "Rising"

    no_power = pi(power=None, cls="Nailed")
    result = verdict(no_power, CUTOFFS).label
    assert result not in {"Elite", "Avoid"}


def test_disabled_label_falls_through():
    base = pi(q=95, cls="Nailed", v=85, confidence="high")
    assert verdict(base, CUTOFFS).label == "Elite"
    assert verdict(base, CUTOFFS, disabled=frozenset({"Elite"})).label == "Bargain"


def test_tags_keep_strongest_two():
    # NOTE: the brief's example used "price falling -3%", which under the
    # literal strength formulas (|expected_pct| = 3.0 vs |minutes_trend|/15
    # = 2.67) would outrank "minutes down" and appear instead of it. Using
    # -2% here preserves the test's intent (low confidence always wins a
    # slot; the two next-strongest tags fill the rest) while matching the
    # documented maths exactly. Recorded in the task report.
    p = pi(confidence="low", outlook=("fall", -2.0, False), minutes_trend=-40)
    v = verdict(p, CUTOFFS, DEFAULT_THRESHOLDS)
    assert v.tags == ("low confidence", "minutes down")


def test_reason_templates():
    p = pi(v=92, price=1_200_000, confidence="high")
    v = verdict(p, CUTOFFS)
    assert v.label == "Bargain"
    assert v.reason == "Top-8% DEF points per €, regular starter, priced €1.2M."


def test_position_cutoffs_are_medians():
    inputs = {
        1: pi(player_id=1, price=1_000_000),
        2: pi(player_id=2, price=2_000_000),
        3: pi(player_id=3, price=9_000_000),
    }
    cutoffs = position_cutoffs(inputs)
    assert cutoffs.median_price["DEF"] == 2_000_000
