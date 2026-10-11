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
from core import team_strength as ts
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


def model_contexts(data: dict, season: int, info: dict) -> dict[tuple[str, int], xp.FixtureContext]:
    """The opponent model's fixture context for every (team, trusted week),
    each fitted only on matches played before that week's first match —
    this season's and last season's, recency-weighted, as the live model."""
    alignment = info["alignment"]
    records = [*data["matches"].get(season - 1, []), *data["matches"].get(season, [])]
    week_start: dict[int, date] = {}
    for (_, week), m in alignment.items():
        week_start[week] = min(week_start.get(week, m["match_date"]), m["match_date"])
    out = {}
    for week in info["trusted"]:
        strengths = ts.fit(ts.from_records(records, week_start[week]))
        for (team, w), m in alignment.items():
            if w != week:
                continue
            goals, clean = ts.team_view(strengths, m["home_team"], m["away_team"], team)
            home = team == m["home_team"]
            out[(team, week)] = xp.FixtureContext(
                opponent=m["away_team"] if home else m["home_team"], is_home=home,
                team_goals=goals, clean_sheet=clean, odds_source="model",
            )
    return out


def _gate_rows(label: str, cases: list[bt.Case], k: xp.Coefficients, kb: xp.Coefficients,
               ctx: dict, with_starter: bool) -> tuple[list[str], list[bt.Case], list[bt.Case]]:
    """Variant A (no opponent), B (opponent model, odds-fitted fixture
    coefficients), B2 (opponent model, coefficients `kb` fitted on model
    contexts) and C (odds) on the same cases: those in a trusted week whose
    fixture had odds."""
    same = [c for c in cases if (c.extra["team"], c.week) in ctx and c.fixture
            and c.fixture.team_goals is not None]
    with_model = [replace(c, fixture=ctx[(c.extra["team"], c.week)]) for c in same]
    actual = [c.actual for c in same]
    a = bt.model_predictor(bt.without_fixture(k), with_starter, False)
    full = bt.model_predictor(k, with_starter, True)
    full_b2 = bt.model_predictor(kb, with_starter, True)
    lines = [f"\n**{label}**\n", "| variant | n | MAE | RMSE | Spearman |", "|---|---|---|---|---|",
             _row("A — no opponent", bt.metrics([a(c) for c in same], actual)),
             _row("B — opponent model", bt.metrics([full(c) for c in with_model], actual)),
             _row("B2 — opponent model, own coefficients",
                  bt.metrics([full_b2(c) for c in with_model], actual)),
             _row("C — odds", bt.metrics([full(c) for c in same], actual))]
    return lines, same, with_model


def variants(data: dict) -> None:
    """The opponent-model gate (2026-10-08): B ships as the no-odds fallback
    only if the 95 % interval of RMSE_A − RMSE_B is above zero."""
    c25, i25 = season_cases(data, 2025)
    c26, i26 = season_cases(data, 2026)
    c26 = attach_market_inputs(data, c26, i26)
    ctx25, ctx26 = model_contexts(data, 2025, i25), model_contexts(data, 2026, i26)

    train = [c for c in c25 if c.week <= 19]
    rate = bt.fit_rate_only(train)
    k25 = xp.Coefficients(rate, xp.WITH_STARTER, bt.fit_fixture(train, rate))
    test25 = [c for c in c25 if c.week >= 20]
    rate_all = bt.fit_rate_only(c25)
    k26 = xp.Coefficients(rate_all, xp.WITH_STARTER, bt.fit_fixture(c25, rate_all))

    # B2: the fixture coefficients refitted on model contexts, from the same
    # training cases only (`fit_fixture` reads each case's `fixture`).
    def on_model(cases, ctx):
        return [replace(c, fixture=ctx.get((c.extra["team"], c.week))) for c in cases]

    kb25 = replace(k25, fixture=bt.fit_fixture(on_model(train, ctx25), rate))
    kb26 = replace(k26, fixture=bt.fit_fixture(on_model(c25, ctx25), rate_all))

    out: list[str] = []
    pooled_a: list[tuple[bt.Case, float]] = []
    pooled_b: dict[int, float] = {}
    pooled_c: dict[int, float] = {}
    pooled_b2: dict[int, float] = {}
    for label, cases, k, kb, ctx, starter in (
        ("2025/26 weeks 20–38 (coefficients from weeks 1–19)", test25, k25, kb25, ctx25, False),
        ("2026/27, form only (coefficients from 2025/26)", c26, k26, kb26, ctx26, False),
        ("2026/27, form + starter (the live model's basis)", c26, k26, kb26, ctx26, True),
    ):
        lines, same, with_model = _gate_rows(label, cases, k, kb, ctx, starter)
        out += lines
        if starter and label.startswith("2026"):
            continue  # pooled gate counts each case once
        a = bt.model_predictor(bt.without_fixture(k), starter, False)
        full = bt.model_predictor(k, starter, True)
        full_b2 = bt.model_predictor(kb, starter, True)
        for c, cm in zip(same, with_model, strict=True):
            pooled_a.append((c, a(c)))
            pooled_b[id(c)] = full(cm)
            pooled_b2[id(c)] = full_b2(cm)
            pooled_c[id(c)] = full(c)

    cases = [c for c, _ in pooled_a]
    pa = {id(c): v for c, v in pooled_a}
    ab = bt.paired_bootstrap_rmse_diff(cases, lambda c: pa[id(c)], lambda c: pooled_b[id(c)])
    ab2 = bt.paired_bootstrap_rmse_diff(cases, lambda c: pa[id(c)], lambda c: pooled_b2[id(c)])
    ac = bt.paired_bootstrap_rmse_diff(cases, lambda c: pa[id(c)], lambda c: pooled_c[id(c)])
    bc = bt.paired_bootstrap_rmse_diff(cases, lambda c: pooled_b2[id(c)], lambda c: pooled_c[id(c)])
    out += [
        f"\n**Gate — pooled out-of-sample cases (n={len(cases)}, "
        f"{len({c.player_id for c in cases})} players)**\n",
        f"- RMSE_A − RMSE_B = {ab[0]:+.4f} (95% CI {ab[1]:+.4f} … {ab[2]:+.4f})"
        f" → {'PASS: the model helps' if ab[1] > 0 else 'FAIL: not shown to help'}",
        f"- RMSE_A − RMSE_B2 = {ab2[0]:+.4f} (95% CI {ab2[1]:+.4f} … {ab2[2]:+.4f})"
        f" → {'PASS: the model helps' if ab2[1] > 0 else 'FAIL: not shown to help'}",
        f"- RMSE_B2 − RMSE_C = {bc[0]:+.4f} (95% CI {bc[1]:+.4f} … {bc[2]:+.4f})"
        " — what the model gives up against real odds",
        f"- RMSE_A − RMSE_C = {ac[0]:+.4f} (95% CI {ac[1]:+.4f} … {ac[2]:+.4f})"
        " — what real odds add over no opponent at all",
        "- Two variants were tried (B, then B2); read the intervals with that in mind.",
    ]
    print("\n".join(out))


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
    ap.add_argument("--variants", action="store_true",
                    help="the opponent-model gate: no opponent vs model vs odds")
    args = ap.parse_args(argv)

    data = load(args.db, DEFAULT_CSVS)
    if args.variants:
        variants(data)
        return
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
