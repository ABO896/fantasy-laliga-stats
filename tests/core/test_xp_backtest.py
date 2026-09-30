"""core/xp_backtest.py — calendar reconstruction, cases, fitting, metrics."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core import xp_backtest as bt
from scraper.sources.football_data import parse_matches

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "external"
TEAMS = [f"T{i}" for i in range(20)]


def _m(home, away, when, hg=1, ag=0):
    return {"home_team": home, "away_team": away, "kickoff_at": when,
            "match_date": when.date(), "home_goals": hg, "away_goals": ag,
            "odds_home": 2.0, "odds_draw": 3.4, "odds_away": 4.0,
            "odds_over25": 1.9, "odds_under25": 1.9}


def _round(start, pairs):
    return [_m(h, a, start + timedelta(hours=3 * i)) for i, (h, a) in enumerate(pairs)]


R1 = [(TEAMS[i], TEAMS[i + 1]) for i in range(0, 20, 2)]
R2 = [(TEAMS[i + 1], TEAMS[(i + 2) % 20]) for i in range(0, 20, 2)]


def test_rounds_are_numbered_by_window():
    t0 = datetime(2026, 8, 15, 17, tzinfo=UTC)
    a = bt.assign_jornadas(_round(t0, R1) + _round(t0 + timedelta(days=7), R2))
    assert a[("T0", 1)]["away_team"] == "T1"
    assert a[("T1", 2)]["away_team"] == "T2"


def test_a_postponed_match_returns_to_its_own_round():
    t0 = datetime(2026, 8, 15, 17, tzinfo=UTC)
    r1 = _round(t0, R1)
    postponed = r1.pop()  # T18 v T19 played a month later
    late = _m(postponed["home_team"], postponed["away_team"], t0 + timedelta(days=30))
    a = bt.assign_jornadas(r1 + _round(t0 + timedelta(days=7), R2) + [late])
    assert a[("T18", 1)] is late
    assert a[("T19", 1)] is late


def test_real_2025_calendar_reconstructs_38_full_rounds():
    records = parse_matches((FIXTURES / "football-data-SP1-2526.csv").read_text(),
                            expected_season=2025).records
    a = bt.assign_jornadas(records)
    per_round = {}
    for (_, j), _m2 in a.items():
        per_round[j] = per_round.get(j, 0) + 1
    assert sorted(per_round) == list(range(1, 39))
    assert all(n == 20 for n in per_round.values())  # 10 matches × 2 teams


def test_alignment_validation_detects_a_shift():
    t0 = datetime(2026, 8, 15, 17, tzinfo=UTC)
    r1 = [_m(h, a, t0 + timedelta(hours=i), hg=i % 3, ag=(i + 1) % 2)
          for i, (h, a) in enumerate(R1)]
    a = bt.assign_jornadas(r1)
    right, wrong = {}, {}
    for m in r1:
        gd = m["home_goals"] - m["away_goals"]
        right[(m["home_team"], 1)] = 10 + 3 * gd
        right[(m["away_team"], 1)] = 10 - 3 * gd
        wrong[(m["home_team"], 1)] = 10
        wrong[(m["away_team"], 1)] = 10
    assert bt.validate_alignment(a, right)[1] == pytest.approx(1.0)
    assert bt.validate_alignment(a, wrong)[1] is None


def test_fixture_context_uses_the_teams_side():
    m = _m("A", "B", datetime(2026, 8, 15, tzinfo=UTC))
    home = bt.fixture_context(m, "A")
    away = bt.fixture_context(m, "B")
    assert home.is_home and not away.is_home
    assert home.opponent == "B"
    assert home.team_goals > away.team_goals
    assert away.clean_sheet < home.clean_sheet


def test_fixture_context_without_prices_has_no_odds():
    m = _m("A", "B", datetime(2026, 8, 15, tzinfo=UTC)) | {"odds_draw": None}
    ctx = bt.fixture_context(m, "A")
    assert ctx.team_goals is None and ctx.opponent == "B"


def test_build_cases_scores_missing_rows_as_zero_only_inside_the_players_span():
    players = {1: ("T", "DEL")}
    points = {1: {2: 5, 4: 7}}  # absent week 3 → 0; weeks 1 and 5 outside the span
    team_rows = {("T", w): 10 for w in range(1, 6)}
    cases = bt.build_cases(2025, [1, 2, 3, 4, 5], points, {}, players, team_rows)
    assert [(c.week, c.actual, c.history) for c in cases] == [
        (2, 5, []), (3, 0, [5]), (4, 7, [5, 0]),
    ]


def test_build_cases_skips_weeks_the_team_did_not_play():
    players = {1: ("T", "DEL")}
    points = {1: {1: 5, 3: 7}}
    team_rows = {("T", 1): 10, ("T", 3): 10}  # week 2 blank for the team
    cases = bt.build_cases(2025, [1, 2, 3], points, {1: {}}, players, team_rows)
    assert [c.week for c in cases] == [1, 3]
    assert cases[1].history == [5]


def test_least_squares_recovers_a_line():
    rows = [[x, 1.0] for x in range(10)]
    ys = [2 * x + 3 for x in range(10)]
    a, b = bt.least_squares(rows, ys)
    assert a == pytest.approx(2) and b == pytest.approx(3)


def test_metrics():
    m = bt.metrics([1, 2, 3, 4], [1, 2, 3, 8])
    assert m.mae == 1
    assert m.rmse == 2
    assert m.spearman == pytest.approx(1.0)


def test_baselines():
    c = bt.Case(2025, 5, 1, "DEL", 3, [1, 2, 3, 4, 5, 6], 9.0)
    assert bt.season_average(c) == 3.5
    assert bt.last5_average(c) == 4
    first = bt.Case(2025, 1, 1, "DEL", 3, [], 9.0)
    assert bt.season_average(first) == 9.0


def test_fit_all_returns_every_position():
    cases = []
    for pos in bt.POSITIONS:
        for i in range(30):
            fx = bt.fixture_context(_m("A", "B", datetime(2026, 1, 1, tzinfo=UTC)), "A")
            cases.append(bt.Case(2025, 5, i, pos, i % 7, [i % 5, (i * 3) % 7], None,
                                 fixture=fx, starter_probability=float((i * 13) % 100)))
    # vary the fixture so the fixture fit is not singular
    cases = [bt.replace(c, fixture=bt.xp.FixtureContext("B", True, 1 + (c.player_id % 5) / 4,
                                                        0.1 + (c.player_id % 3) / 10))
             for c in cases]
    k = bt.fit_all(cases, cases)
    assert set(k.rate_only) == set(k.with_starter) == set(k.fixture) == set(bt.POSITIONS)
