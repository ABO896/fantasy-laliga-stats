"""compute_inputs — every verdict input for every player, as of a date."""

from datetime import date

import pytest

from core import analytics as an
from core.inputs import (
    InputsData,
    PlayerBase,
    SnapshotState,
    UpcomingMatch,
    compute_inputs,
)
from core.market_v2 import Outlook
from core.rules import load_rules

SEASON = 2026
AS_OF = date(2026, 9, 20)
CASH = load_rules().cash_per_point
FILLERS_PER_CLUB = 5  # core.xp_backtest.MIN_TEAM_ROWS: every filled week counts as played


def player(pid, position="DEL", team="A", points=None, lines=None, page=True, price=5_000_000,
           snaps=None, last_mean=None, last_apps=0, starter=None, availability="available"):
    """One player spec for `make_data`. `points` / `lines` are {week: ...};
    default `lines` is a 90-minute start in every week he has points."""
    points = points or {}
    if lines is None:
        lines = {w: (90, "start") for w in points}
    if snaps is None:
        snaps = [SnapshotState(date(2026, 8, 1), price, availability, starter)]
    return dict(pid=pid, position=position, team=team, points=points, lines=lines, page=page,
                price=price, snaps=snaps, last_mean=last_mean, last_apps=last_apps)


def make_data(players, club_weeks=(1, 2, 3)):
    """Builds `InputsData`, adding filler teammates (no price, no snapshot,
    so never in the output) so every club played every `club_weeks` week."""
    bases, rows, match_lines, page, prices, snapshots = {}, [], {}, set(), {}, {}
    means, apps = {}, {}
    for p in players:
        pid = p["pid"]
        bases[pid] = PlayerBase(pid, f"P{pid}", p["team"], p["position"])
        rows += [an.GameweekRow(SEASON, w, pid, pts, False) for w, pts in p["points"].items()]
        match_lines[pid] = dict(p["lines"])
        if p["page"]:
            page.add(pid)
        if p["price"] is not None:
            prices[pid] = {date(2026, 9, 1): p["price"]}
        snapshots[pid] = list(p["snaps"])
        if p["last_mean"] is not None:
            means[pid] = p["last_mean"]
        apps[pid] = p["last_apps"]
    for i, team in enumerate(sorted({p["team"] for p in players})):
        for k in range(FILLERS_PER_CLUB):
            fid = 10_000 + 100 * i + k
            bases[fid] = PlayerBase(fid, f"F{fid}", team, "MED")
            rows += [an.GameweekRow(SEASON, w, fid, 1, False) for w in club_weeks]
    return InputsData(
        season=SEASON,
        players=bases,
        gameweek_rows=rows,
        match_lines=match_lines,
        page_players=frozenset(page),
        prices=prices,
        snapshots=snapshots,
        last_season_means=means,
        last_season_apps=apps,
        cash_per_point=CASH,
    )


def fixture(opponent="B", is_home=True):
    return [UpcomingMatch(opponent, is_home, 1.4, 0.3, "test")]


def run(data, known=(1, 2, 3), upcoming=None, outlooks=None, as_of=AS_OF):
    teams = {b.team for b in data.players.values()}
    upcoming = upcoming if upcoming is not None else {t: fixture() for t in teams}
    return compute_inputs(data, as_of, set(known), upcoming, outlooks or {})


def test_power_matches_analytics_recipe():
    data = make_data([player(1, "DEL", points={1: 6, 2: 8, 3: 7})])
    got = run(data)[1]

    timeline = [(SEASON, 1), (SEASON, 2), (SEASON, 3)]
    rows = [r for r in data.gameweek_rows if r.player_id == 1]
    series = an.player_series(timeline, rows, an.FORM_WINDOW + an.BASELINE_WINDOW, set(timeline))
    history = an.player_series(timeline, rows, len(timeline), set(timeline))
    expected = an.power_score(an.power_inputs(series, history, None, "DEL", "available"))
    assert got.power.score == expected.score


def test_known_weeks_hide_the_future():
    base = make_data([player(1, points={1: 6, 2: 8, 3: 7})], club_weeks=(1, 2, 3, 4))
    future = make_data(
        [player(1, points={1: 6, 2: 8, 3: 7, 4: 20})], club_weeks=(1, 2, 3, 4)
    )
    a, b = run(base)[1], run(future)[1]
    assert (a.power, a.reliability) == (b.power, b.reliability)


def test_snapshot_state_as_of():
    snaps = [
        SnapshotState(date(2026, 9, 1), 5_000_000, "available", 70.0),
        SnapshotState(date(2026, 9, 10), 5_000_000, "injured", 70.0),
    ]
    data = make_data([player(1, points={1: 6, 2: 8, 3: 7}, snaps=snaps)])
    early = run(data, as_of=date(2026, 9, 5))[1]
    late = run(data, as_of=date(2026, 9, 12))[1]
    assert early.availability == "available"
    assert late.availability == "injured"
    assert late.reliability.p_start_next == 0


def test_blank_vs_unknown_club():
    data = make_data([
        player(1, team="A", points={1: 6, 2: 8, 3: 7}),
        player(2, team="C", points={1: 6, 2: 8, 3: 7}),
    ])
    got = run(data, upcoming={"A": []})
    assert got[1].xpts.total == 0
    assert got[1].xpts.basis == "blank"
    assert got[2].xpts is None
    assert got[2].points_value_reason == "no fixture data"


def test_points_value_against_replacement():
    cheap = [
        player(i, "DEF", points={1: 6, 2: 6, 3: 6}, price=1_000_000, starter=80.0)
        for i in range(1, 6)
    ]
    star = player(9, "DEF", points={1: 15, 2: 15, 3: 15}, price=10_000_000, starter=80.0)
    got = run(make_data(cheap + [star]))

    cheap_xp = got[1].xpts.total
    assert got[9].replacement == pytest.approx(cheap_xp)
    assert got[9].points_value == pytest.approx(
        (got[9].xpts.total - cheap_xp) * CASH / 10_000_000, abs=1e-6
    )
    assert got[9].points_value > 0
    for i in range(1, 6):
        assert got[i].points_value == pytest.approx(0, abs=1e-9)


def test_below_evidence_floor_has_no_points_value():
    data = make_data([player(1, points={1: 6, 2: 8}, lines={1: (90, "start"), 2: (90, "start")})])
    got = run(data)[1]
    assert got.points_value is None
    assert "2 matches" in got.points_value_reason


def test_ranks_within_position_only():
    data = make_data([
        player(1, "POR", points={1: 15, 2: 15, 3: 15}),
        player(2, "DEF", points={1: 8, 2: 8, 3: 8}),
        player(3, "DEF", points={1: 2, 2: 2, 3: 2}),
    ])
    got = run(data)
    assert (got[1].ranks["power"].rank, got[1].ranks["power"].of) == (1, 1)
    assert (got[2].ranks["power"].rank, got[2].ranks["power"].of) == (1, 2)


def test_expected_return_eur():
    data = make_data([player(1, points={1: 6, 2: 6, 3: 6}, price=5_000_000)])
    outlook = Outlook(2.0, "rise", 0.0, 4.0, False, "ridge", {})
    got = run(data, outlooks={1: outlook})[1]
    assert got.expected_return_eur == pytest.approx(
        got.xpts.total * 100_000 + 5_000_000 * 0.02
    )
    # The brief's worked example: xP 6.0 → 6 × 100 000 + 5 000 000 × 2 % = 700 000.
    assert 6.0 * CASH + 5_000_000 * 2.0 / 100 == 700_000


def test_source_only_player_is_low_confidence():
    data = make_data([player(1, points={1: 6, 2: 8, 3: 7}, page=False, starter=70.0)])
    got = run(data)[1]
    assert got.reliability.basis == "source-only"
    assert got.confidence == "low"
    assert got.evidence.matches_with_minutes == 0


# --- price freshness: the more recent of daily price and snapshot (final review #5) -------


def test_newer_snapshot_price_beats_an_older_daily_price():
    snaps = [SnapshotState(date(2026, 9, 4), 7_000_000, "available", None)]
    data = make_data([player(1, points={1: 6, 2: 8, 3: 7}, price=5_000_000, snaps=snaps)])
    # make_data dates the daily price 2026-09-01; the snapshot is newer.
    got = run(data)[1]
    assert (got.price, got.price_as_of) == (7_000_000, date(2026, 9, 4))


def test_daily_price_wins_a_tie_and_when_newer():
    tie = [SnapshotState(date(2026, 9, 1), 7_000_000, "available", None)]
    older = [SnapshotState(date(2026, 8, 20), 7_000_000, "available", None)]
    for snaps in (tie, older):
        data = make_data([player(1, points={1: 6, 2: 8, 3: 7}, price=5_000_000, snaps=snaps)])
        got = run(data)[1]
        assert (got.price, got.price_as_of) == (5_000_000, date(2026, 9, 1))
