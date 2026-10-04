import pytest

from core.reliability import (
    DEFAULT_PRIOR,
    ClubMatch,
    Prior,
    evidence,
    position_priors,
    reliability,
)


def started(n, first_week=1):
    return [ClubMatch(first_week + i, 90, "start") for i in range(n)]


def test_ever_present_starter_is_nailed():
    r = reliability(started(8), DEFAULT_PRIOR, None, "available")
    assert r.cls == "Nailed"
    assert r.start_share == pytest.approx(1.0)
    assert r.p_start_next > 0.8
    assert r.confidence == "high" and r.basis == "matches"


def test_new_player_starts_near_the_prior():
    r = reliability([], Prior(0.5, 0.6), None, "available")
    assert r.p_start_next == pytest.approx(0.5)
    assert r.start_share is None and r.confidence == "low"


def test_no_page_data_is_source_only():
    r = reliability(None, DEFAULT_PRIOR, 90.0, "available")
    assert r.basis == "source-only" and r.confidence == "low"
    assert r.matches == 0
    # Source blend still moves him above the prior.
    assert r.p_start_next > DEFAULT_PRIOR.start


def test_club_not_playing_is_not_a_dnp():
    # Weeks 1–4 all started; week 5 his club didn't play, so it is simply
    # absent from the list the caller passes — the caller filters by club weeks.
    r = reliability(started(4), DEFAULT_PRIOR, None, "available")
    assert r.matches == 4 and r.appearances == 4


def test_availability_applied_last():
    nailed = started(8)
    assert reliability(nailed, DEFAULT_PRIOR, 95.0, "injured").p_start_next == 0.0
    assert reliability(nailed, DEFAULT_PRIOR, 95.0, "injured").cls == "Fringe"
    healthy = reliability(nailed, DEFAULT_PRIOR, 95.0, "available").p_start_next
    doubtful = reliability(nailed, DEFAULT_PRIOR, 95.0, "doubtful").p_start_next
    assert doubtful == pytest.approx(healthy * 0.6)


def test_sub_appearances_and_trend():
    ms = [ClubMatch(w, 90, "start") for w in range(1, 6)] + [
        ClubMatch(6, 20, "sub"), ClubMatch(7, 0, "dnp"), ClubMatch(8, 15, "sub")]
    r = reliability(ms, DEFAULT_PRIOR, None, "available")
    assert r.sub_share > 0
    assert r.minutes_trend == pytest.approx((20 + 0 + 15) / 3 - 90)
    assert r.p_play_next >= r.p_start_next


def test_trend_needs_enough_matches():
    assert reliability(started(3), DEFAULT_PRIOR, None, "available").minutes_trend is None


def test_position_priors_use_players_with_three_matches():
    priors = position_priors({
        1: ("DEF", started(4)),
        2: ("DEF", [ClubMatch(w, 0, "dnp") for w in range(1, 5)]),
        3: ("DEF", started(2)),  # too few, ignored
    })
    assert priors["DEF"].start == pytest.approx(0.5)
    assert priors["DEL"] == DEFAULT_PRIOR


@pytest.mark.parametrize(
    ("this", "last", "ok"),
    [(3, 0, True), (2, 0, False), (1, 10, True), (0, 20, False), (2, 9, False)],
)
def test_evidence_floor(this, last, ok):
    e = evidence(this, last)
    assert e.ok is ok
    assert (e.reason is None) is ok
