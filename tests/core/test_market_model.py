"""MODEL-01/03/04 — the market model's pure parts."""

from datetime import date

import pytest

from core.market_model import (
    MODEL_VERSION,
    ScoredCall,
    SnapshotPoint,
    confidence_for,
    predict,
    score,
    source_direction,
    summarize,
)


def snap(day, pct, mv=10_000_000, starter=50.0, availability="available", points=0):
    return SnapshotPoint(date(2026, 9, day), mv, pct, starter, availability, points)


def test_model_version_is_named():
    assert MODEL_VERSION == "market-v1"


def test_persistence_when_nothing_else_is_known():
    p = predict(snap(10, -1.2), None)
    assert p.direction == "fall"
    assert p.predicted_pct == pytest.approx(-1.2)
    assert p.confidence == "strong"
    assert p.inputs["lastMovePct"] == -1.2
    assert p.inputs["accelerationTerm"] is None


def test_acceleration_needs_a_snapshot_exactly_one_day_earlier():
    decelerating = predict(snap(10, 0.4), snap(9, 1.4))
    assert decelerating.predicted_pct == pytest.approx(0.4 + 0.5 * (0.4 - 1.4))
    assert decelerating.direction == "fall"
    stale = predict(snap(10, 0.4), snap(7, 1.2))
    assert stale.inputs["accelerationTerm"] is None
    assert stale.predicted_pct == pytest.approx(0.4)


def test_availability_and_starter_terms():
    injured = predict(snap(10, 0.3, availability="injured", starter=20), snap(9, 0.3, starter=70))
    # 0.3 + 0 accel - 1 availability + 0.01 * (20 - 70)
    assert injured.predicted_pct == pytest.approx(0.3 - 1.0 - 0.5)
    back = predict(snap(10, -0.2), snap(9, -0.2, availability="doubtful"))
    assert back.predicted_pct == pytest.approx(-0.2 + 0.5)
    assert back.inputs["availabilityChange"] == "doubtful → available"


def test_fresh_points_term_only_for_a_recent_previous_snapshot():
    fresh = predict(snap(10, -0.1, points=12), snap(9, -0.1, points=4))
    assert fresh.predicted_pct == pytest.approx(-0.1 + 0.15 * (8 - 2))
    old = predict(snap(10, -0.1, points=12), snap(5, -0.1, points=4))
    assert old.inputs["freshPointsTerm"] is None


def test_no_signal_falls_back_to_the_base_rate_never_to_flat():
    p = predict(snap(10, 0.0), None)
    assert p.direction == "fall" and p.confidence == "weak"
    assert p.inputs["baseRateFallback"] is True
    assert predict(snap(10, 0.3), None).inputs["baseRateFallback"] is False


def test_confidence_tiers():
    assert confidence_for(1.0) == "strong"
    assert confidence_for(-0.99) == "moderate"
    assert confidence_for(0.5) == "moderate"
    assert confidence_for(0.49) == "weak"


def test_score_exact_uses_next_days_published_move():
    outcome = score(snap(10, 1.0, mv=10_000_000), "rise", snap(11, -0.4, mv=9_960_000))
    assert outcome.scoring == "exact"
    assert outcome.gap_days == 1
    assert outcome.actual_pct == pytest.approx(-0.4)
    assert outcome.actual_direction == "fall"
    assert outcome.hit is False


def test_score_interval_uses_cumulative_value_change():
    outcome = score(snap(10, 1.0, mv=10_000_000), "rise", snap(16, -0.4, mv=10_500_000))
    assert outcome.scoring == "interval"
    assert outcome.gap_days == 6
    assert outcome.actual_pct == pytest.approx(5.0)
    assert outcome.hit is True


def test_source_directions():
    assert source_direction("market_top_risers") == "rise"
    assert source_direction("market_possible_risers") == "rise"
    assert source_direction("market_top_fallers") == "fall"
    assert source_direction("market_possible_fallers") == "fall"
    assert source_direction("points") is None


def test_summarize_splits_live_from_retroactive_and_by_tier_and_mode():
    calls = [
        ScoredCall("strong", "exact", True, False, 1),
        ScoredCall("strong", "exact", False, False, 1),
        ScoredCall("weak", "interval", True, False, 6),
        ScoredCall("strong", "exact", True, True, 1),
        ScoredCall("weak", None, None, False, None),  # pending
    ]
    s = summarize(calls)
    assert s["live"]["scored"] == 3
    assert s["live"]["pending"] == 1
    assert s["live"]["hits"] == 2
    assert s["live"]["hitRate"] == pytest.approx(2 / 3)
    assert s["live"]["byConfidence"]["strong"] == {"scored": 2, "hits": 1, "hitRate": 0.5}
    assert s["live"]["byScoring"]["interval"]["scored"] == 1
    assert s["retroactive"]["scored"] == 1
    assert s["live"]["byConfidence"]["moderate"] == {"scored": 0, "hits": 0, "hitRate": None}
