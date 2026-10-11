"""Team strength from results — the opponent term xP falls back on when a
fixture has no odds (2026-10-08)."""

import math

import pytest

from core import team_strength as ts


def _season(strong="Strong", weak="Weak", others=("A", "B", "C", "D")):
    """A small league: `strong` wins big, `weak` loses big, others draw 1-1."""
    out = []
    teams = [strong, weak, *others]
    for h in teams:
        for a in teams:
            if h == a:
                continue
            if h == strong:
                hg, ag = 3, 0
            elif a == strong:
                hg, ag = 0, 2
            elif h == weak:
                hg, ag = 0, 2
            elif a == weak:
                hg, ag = 3, 0
            else:
                hg, ag = 1, 1
            out.append(ts.MatchResult(h, a, hg, ag))
    return out


def test_a_strong_home_side_expects_more_goals_and_keeps_more_clean_sheets():
    s = ts.fit(_season())
    strong_goals, strong_cs = ts.team_view(s, "Strong", "Weak", "Strong")
    weak_goals, weak_cs = ts.team_view(s, "Strong", "Weak", "Weak")
    assert strong_goals > 2.0 > weak_goals
    assert strong_cs > weak_cs
    assert strong_cs == pytest.approx(math.exp(-weak_goals))


def test_average_sides_sit_near_the_league_average():
    s = ts.fit(_season())
    home, _ = ts.team_view(s, "A", "B", "A")
    away, _ = ts.team_view(s, "A", "B", "B")
    assert home > away  # home advantage
    assert 0.8 < (home + away) / 2 < 2.0


def test_no_matches_gives_the_league_average_for_everyone():
    s = ts.fit([])
    goals, cs = ts.team_view(s, "X", "Y", "X")
    assert goals == pytest.approx(ts.LEAGUE_GOALS_PRIOR, rel=0.15)
    assert cs == pytest.approx(math.exp(-ts.team_view(s, "X", "Y", "Y")[0]))


def test_an_unknown_team_is_the_league_mean():
    s = ts.fit(_season())
    assert sum(s.attack.values()) == pytest.approx(0, abs=1e-9)  # 0 is the mean
    goals, _ = ts.team_view(s, "Newcomer", "A", "Newcomer")
    assert goals == pytest.approx(math.exp(s.mu + s.home_advantage - s.defence["A"]))


def test_the_fit_is_deterministic():
    m = _season()
    assert ts.fit(m) == ts.fit(list(m))


def test_weights_let_recent_matches_count_more():
    old = [ts.MatchResult("A", "B", 0, 3, weight=0.01) for _ in range(5)]
    new = [ts.MatchResult("A", "B", 3, 0, weight=1.0) for _ in range(5)]
    s = ts.fit(old + new)
    a_goals, _ = ts.team_view(s, "A", "B", "A")
    b_goals, _ = ts.team_view(s, "A", "B", "B")
    assert a_goals > b_goals


def test_target_blends_goals_with_xg_when_present():
    assert ts.target(2, 1.0) == pytest.approx(1.5)
    assert ts.target(2, None) == 2


def test_recency_weight_halves_each_half_life():
    assert ts.recency_weight(0) == 1.0
    assert ts.recency_weight(ts.HALF_LIFE_DAYS) == pytest.approx(0.5)


def test_from_records_uses_only_matches_played_before_the_date():
    from datetime import date

    recs = [
        {"home_team": "A", "away_team": "B", "home_goals": 2, "away_goals": 0,
         "home_xg": 1.0, "away_xg": 0.4, "match_date": date(2026, 9, 1)},
        {"home_team": "B", "away_team": "A", "home_goals": 1, "away_goals": 1,
         "home_xg": None, "away_xg": None, "match_date": date(2026, 9, 20)},
        {"home_team": "A", "away_team": "C", "home_goals": None, "away_goals": None,
         "home_xg": None, "away_xg": None, "match_date": date(2026, 9, 5)},  # not played
    ]
    rows = ts.from_records(recs, as_of=date(2026, 9, 10))
    assert len(rows) == 1
    assert rows[0].home_goals == pytest.approx(1.5)  # 0.5·2 + 0.5·1.0
    assert rows[0].weight == pytest.approx(ts.recency_weight(9))
