"""Run MODEL-02's backtest against a database, read-only.

    uv run python -m storage.xp_backtest [--db data/fantasy.db] [--fit]

Opens the SQLite file with `mode=ro` — this never writes, and never needs
the Alembic head (it reads only Phase 7 tables and the snapshots). Odds
history comes from football-data.co.uk season files on disk (the committed
test captures by default), because the live database may predate the
`externalmatch` table. Prints the tables the spec reports; `--fit` also
prints the coefficients to paste into `core/expected_points.py`.
"""

import argparse
import json
import sqlite3
from collections import defaultdict
from dataclasses import replace
from datetime import date
from pathlib import Path

from core import expected_points as xp
from core import xp_backtest as bt
from scraper.sources.football_data import parse_matches

DEFAULT_CSVS = {
    2025: "tests/fixtures/external/football-data-SP1-2526.csv",
    2026: "tests/fixtures/external/football-data-SP1-2627.csv",
}


def _connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)


def load(db: str, csvs: dict[int, str]) -> dict:
    con = _connect(db)
    players = {pid: (team, pos) for pid, team, pos in con.execute(
        "select id, team, position from player")}
    points: dict[int, dict[int, dict[int, int]]] = defaultdict(lambda: defaultdict(dict))
    provisional: dict[int, set[int]] = defaultdict(set)
    for season, week, pid, pts, prov in con.execute(
        "select season_year, week, player_id, points, is_provisional from playergameweekpoints"
    ):
        points[season][pid][week] = pts
        if prov:
            provisional[season].add(week)
    snapshots: dict[str, dict[int, tuple[float | None, str]]] = defaultdict(dict)
    for as_of, pid, sp, av in con.execute(
        "select as_of, player_id, starter_probability, availability_status from playersnapshot"
    ):
        snapshots[as_of][pid] = (sp, av)
    source: dict[int, list[tuple[str, float, dict]]] = defaultdict(list)
    for as_of, pid, value, raw in con.execute(
        "select as_of, player_id, value, raw_fields from sourceprediction where source='points'"
    ):
        source[pid].append((as_of, value, json.loads(raw)))
    matches = {
        season: parse_matches(Path(path).read_text(), expected_season=season).records
        for season, path in csvs.items()
    }
    return dict(players=players, points=points, provisional=provisional,
                snapshots=snapshots, source=source, matches=matches)


def season_cases(data: dict, season: int) -> tuple[list[bt.Case], dict]:
    players, pts = data["players"], data["points"][season]
    team_rows: dict[tuple[str, int], int] = defaultdict(int)
    team_points: dict[tuple[str, int], int] = defaultdict(int)
    for pid, by_week in pts.items():
        for week, p in by_week.items():
            team_rows[(players[pid][0], week)] += 1
            team_points[(players[pid][0], week)] += p
    weeks = sorted({w for by_week in pts.values() for w in by_week})
    # The in-progress jornada is still moving — never score against it.
    if weeks and weeks[-1] in data["provisional"][season]:
        weeks = weeks[:-1]
    alignment = bt.assign_jornadas(data["matches"].get(season, []))
    corr = bt.validate_alignment(
        alignment, {k: v for k, v in team_points.items() if team_rows[k] >= bt.MIN_TEAM_ROWS}
    )
    trusted = {w for w, r in corr.items() if r is not None and r >= bt.MIN_ALIGNMENT_CORRELATION}

    def fixture_for(team: str, week: int):
        m = alignment.get((team, week))
        return bt.fixture_context(m, team) if m and week in trusted else None

    prior = data["points"].get(season - 1, {})
    cases = bt.build_cases(season, weeks, pts, prior, players, team_rows, fixture_for)
    info = dict(weeks=weeks, trusted=sorted(trusted & set(weeks)), corr=corr, alignment=alignment)
    return cases, info


def attach_market_inputs(data: dict, cases: list[bt.Case], info: dict) -> list[bt.Case]:
    """Starter probability from the last snapshot strictly before the
    jornada's first reconstructed kickoff, and the source's own prediction
    for the same fixture made before it — both known at prediction time."""
    alignment = info["alignment"]
    week_start: dict[int, date] = {}
    for (_, week), m in alignment.items():
        d = m["match_date"]
        week_start[week] = min(week_start.get(week, d), d)
    snap_dates = sorted(data["snapshots"])
    pair_week = {
        (m["home_team"], m["away_team"]): (week, m["match_date"])
        for (team, week), m in alignment.items() if team == m["home_team"]
    }

    out = []
    for c in cases:
        start = week_start.get(c.week)
        sp = av = None
        if start is not None:
            before = [d for d in snap_dates if date.fromisoformat(d) < start]
            if before and c.player_id in data["snapshots"][before[-1]]:
                sp, av = data["snapshots"][before[-1]][c.player_id]
        src = None
        for as_of, value, raw in sorted(data["source"].get(c.player_id, []), key=lambda t: t[0]):
            wk = pair_week.get((raw.get("homeTeamName"), raw.get("awayTeamName")))
            if wk and wk[0] == c.week and date.fromisoformat(as_of) < wk[1]:
                src = value
        out.append(replace(c, starter_probability=sp, availability=av, source_prediction=src))
    return out


def _row(name: str, m: bt.Metrics) -> str:
    rho = f"{m.spearman:.3f}" if m.spearman is not None else "—"
    return f"| {name} | {m.n} | {m.mae:.3f} | {m.rmse:.3f} | {rho} |"


def table(title: str, cases: list[bt.Case], predictors: dict) -> list[str]:
    lines = [f"\n**{title}**\n", "| predictor | n | MAE | RMSE | Spearman |",
             "|---|---|---|---|---|"]
    actual = [c.actual for c in cases]
    for name, f in predictors.items():
        lines.append(_row(name, bt.metrics([f(c) for c in cases], actual)))
    return lines


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/fantasy.db")
    ap.add_argument("--fit", action="store_true", help="print full-data coefficients")
    args = ap.parse_args(argv)

    data = load(args.db, DEFAULT_CSVS)
    c25, i25 = season_cases(data, 2025)
    c26, i26 = season_cases(data, 2026)
    c26 = attach_market_inputs(data, c26, i26)
    print(f"2025/26 weeks {i25['weeks'][0]}–{i25['weeks'][-1]} ({len(i25['weeks'])}); "
          f"odds-trusted {len(i25['trusted'])}: {i25['trusted']}")
    print(f"2026/27 weeks {i26['weeks']}; odds-trusted {i26['trusted']}")

    # 2025/26: fit on the first half, score the second.
    train = [c for c in c25 if c.week <= 19]
    test = [c for c in c25 if c.week >= 20]
    rate_only = bt.fit_rate_only(train)
    k = xp.Coefficients(rate_only, xp.WITH_STARTER, bt.fit_fixture(train, rate_only))
    lines = table(
        "2025/26 — coefficients fitted on weeks 1–19, scored on weeks 20–38",
        test,
        {
            "season average (naive)": bt.season_average,
            "last-5 average (naive)": bt.last5_average,
            "xP, form only": bt.model_predictor(bt.without_fixture(k), False, False),
            "xP, form + odds": bt.model_predictor(k, False, True),
        },
    )
    with_odds = [c for c in test if c.fixture and c.fixture.team_goals]
    lines += table(
        "2025/26 second half — only cases whose fixture had odds",
        with_odds,
        {
            "last-5 average (naive)": bt.last5_average,
            "xP, form only": bt.model_predictor(bt.without_fixture(k), False, False),
            "xP, form + odds": bt.model_predictor(k, False, True),
        },
    )

    # 2026/27: rate/fixture from all of 2025/26 (strictly earlier); starter
    # terms leave-one-week-out within 2026/27.
    rate_all = bt.fit_rate_only(c25)
    fix_all = bt.fit_fixture(c25, rate_all)
    preds: dict[str, dict[int, float]] = defaultdict(dict)
    for week in sorted({c.week for c in c26}):
        fold = [c for c in c26 if c.week != week]
        kw = xp.Coefficients(rate_all, bt.fit_with_starter(fold), fix_all)
        for c in c26:
            if c.week == week:
                key = id(c)
                preds["full"][key] = bt.model_predictor(kw)(c)
                preds["starter"][key] = bt.model_predictor(bt.without_fixture(kw))(c)
    k_hist = xp.Coefficients(rate_all, xp.WITH_STARTER, fix_all)
    p26 = {
        "season average (naive)": bt.season_average,
        "last-5 average (naive)": bt.last5_average,
        "xP, form only": bt.model_predictor(bt.without_fixture(k_hist), False, False),
        "xP, form + odds": bt.model_predictor(k_hist, False, True),
        "xP, form + starter": lambda c: preds["starter"][id(c)],
        "xP, form + starter + odds (the model)": lambda c: preds["full"][id(c)],
    }
    lines += table("2026/27 — starter terms leave-one-week-out", c26, p26)
    with_src = [c for c in c26 if c.source_prediction is not None]
    lines += table(
        "2026/27 — only cases the source published a prediction for, before kickoff",
        with_src,
        {**p26, "source's own prediction": lambda c: c.source_prediction},
    )
    per_week = ["\n**2026/27 per week (MAE)**\n", "| week | n | season avg | model |",
                "|---|---|---|---|"]
    for week in sorted({c.week for c in c26}):
        sub = [c for c in c26 if c.week == week]
        a = [c.actual for c in sub]
        per_week.append(
            f"| {week} | {len(sub)} | {bt.metrics([bt.season_average(c) for c in sub], a).mae:.3f} "
            f"| {bt.metrics([preds['full'][id(c)] for c in sub], a).mae:.3f} |"
        )
    print("\n".join(lines + per_week))

    if args.fit:
        full = xp.Coefficients(rate_all, bt.fit_with_starter(c26), fix_all)
        starters = [c.starter_probability / 100 for c in c26 if c.starter_probability is not None]
        print("\nRATE_ONLY =", {p: tuple(round(v, 3) for v in t)
                                 for p, t in full.rate_only.items()})
        print("WITH_STARTER =", {p: tuple(round(v, 3) for v in t)
                                 for p, t in full.with_starter.items()})
        print("FIXTURE =", {p: tuple(round(v, 3) for v in t) for p, t in full.fixture.items()})
        print("MEAN_STARTER =", round(sum(starters) / len(starters), 3))


if __name__ == "__main__":
    main()
