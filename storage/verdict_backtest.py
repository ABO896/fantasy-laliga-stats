"""The walk-forward verdict harness over stored history (Plan C, Task 4),
and `ModelReport` — proof, not assertion, that each label beats chance
(spec success criterion 3).

For every day `d` with enough history, this computes the verdict with
exactly the inputs knowable on `d` — the same `core.inputs.compute_inputs`
the live app calls (`storage.inputs.compute_live_inputs`), fed stored
history only up to `d` — then measures what each labelled player actually
did over the following `horizon` jornadas / 7 days, and scores every label
through `core.verdict_harness.label_reports`.

    uv run python -m storage.verdict_backtest --db PATH [--write] [--grid]

`--write` stores the report as `ModelReport(name="verdict-validation")`;
`--grid` sweeps a coarse threshold grid and prints one line per
combination, never writing (see `run_grid`).
"""

import argparse
import itertools
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, create_engine, select

from core import analytics as an
from core import jornadas as jr
from core import market_v2 as m2
from core import verdict_harness as vh
from core.config import get_settings
from core.inputs import InputsData, PlayerInputs, UpcomingMatch, compute_inputs
from core.odds import match_probabilities
from core.reliability import CLASS_THRESHOLDS
from core.verdict import DEFAULT_THRESHOLDS, Thresholds, Verdict, verdicts
from core.verdict_harness import Observation
from storage.db import as_utc
from storage.expected_points import ODDS_SOURCE
from storage.inputs import load_inputs_data
from storage.market_v2 import OutlookHistory, load_schedule, outlook_history, outlooks_as_of
from storage.models import ExternalMatch, Fixture, ModelReport

REPORT_NAME = "verdict-validation"


# --- historical upcoming fixtures, with odds -------------------------------------------


@dataclass(frozen=True)
class ScheduleRow:
    home: str
    away: str
    day: date
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    odds_over25: float | None
    odds_under25: float | None


def _season_schedule_rows(session: Session, season: int) -> list[ScheduleRow]:
    """Every match this season — `ExternalMatch` ∪ `Fixture`, deduplicated
    on `(home, away)` with `ExternalMatch` winning, the same rule
    `storage.market_v2.load_schedule` uses — carrying pre-match odds where
    `ExternalMatch` has them. Loaded once per season; `historical_upcoming`
    reads it per date without any further query."""
    pairs: dict[tuple[str, str], ScheduleRow] = {}
    for home, away, kickoff in session.exec(
        select(Fixture.home_team, Fixture.away_team, Fixture.kickoff_utc)
        .where(Fixture.season_year == season)
    ).all():
        pairs[(home, away)] = ScheduleRow(home, away, as_utc(kickoff).date(),
                                           None, None, None, None, None)
    for home, away, match_date, oh, od, oa, oo, ou in session.exec(
        select(ExternalMatch.home_team, ExternalMatch.away_team, ExternalMatch.match_date,
               ExternalMatch.odds_home, ExternalMatch.odds_draw, ExternalMatch.odds_away,
               ExternalMatch.odds_over25, ExternalMatch.odds_under25)
        .where(ExternalMatch.season_year == season)
    ).all():
        pairs[(home, away)] = ScheduleRow(home, away, match_date, oh, od, oa, oo, ou)
    return list(pairs.values())


def historical_upcoming(
    schedule_rows: Sequence[ScheduleRow], as_of: date, horizon: int
) -> dict[str, list[UpcomingMatch]]:
    """Per club, its next `horizon` matches dated after `as_of`, with odds
    from `ExternalMatch`'s pre-match columns where that pairing has them —
    the same `core.odds.match_probabilities` logic
    `storage.expected_points.odds_probabilities` uses, applied to rows
    already loaded rather than one query per fixture. Every club named by
    `schedule_rows` gets a list, possibly empty."""
    teams = {r.home for r in schedule_rows} | {r.away for r in schedule_rows}
    out: dict[str, list[UpcomingMatch]] = {team: [] for team in teams}
    future = sorted((r for r in schedule_rows if r.day > as_of),
                     key=lambda r: (r.day, r.home, r.away))
    for r in future:
        probs = match_probabilities(r.odds_home, r.odds_draw, r.odds_away, r.odds_over25,
                                     r.odds_under25)
        for team, opponent, is_home in ((r.home, r.away, True), (r.away, r.home, False)):
            if len(out[team]) >= horizon:
                continue
            if probs is None:
                out[team].append(UpcomingMatch(opponent, is_home, None, None, None))
            else:
                team_goals = probs.exp_goals_home if is_home else probs.exp_goals_away
                clean_sheet = probs.p_clean_sheet_home if is_home else probs.p_clean_sheet_away
                out[team].append(UpcomingMatch(opponent, is_home, team_goals, clean_sheet,
                                               ODDS_SOURCE))
    return out


# --- per-season state, reused across every date (and every grid point) -----------------


@dataclass(frozen=True)
class SessionData:
    data: InputsData
    ends: dict[int, date]
    schedule_rows: list[ScheduleRow]
    outlooks: OutlookHistory
    thresholds: Thresholds = DEFAULT_THRESHOLDS
    disabled: frozenset = frozenset()
    horizon: int = 3
    class_thresholds: Sequence[tuple[str, float]] = CLASS_THRESHOLDS


def load_session_data(
    session: Session, season: int, thresholds: Thresholds = DEFAULT_THRESHOLDS,
    disabled: frozenset = frozenset(), horizon: int = 3,
    class_thresholds: Sequence[tuple[str, float]] = CLASS_THRESHOLDS,
) -> SessionData:
    """Every table the harness reads for `season`, loaded once."""
    data = load_inputs_data(session, season)
    schedule = load_schedule(session, season)
    ends = jr.week_end_dates(schedule)
    schedule_rows = _season_schedule_rows(session, season)
    return SessionData(data, ends, schedule_rows, outlook_history(session),
                        thresholds, disabled, horizon, class_thresholds)


def _inputs_and_verdicts(
    session_data: SessionData, d: date
) -> tuple[dict[int, PlayerInputs], dict[int, Verdict]]:
    kw = jr.known_weeks(session_data.ends, d)
    # Per player, his latest outlook ≤ d within the staleness cap — the
    # live rule (`storage.market_v2.latest_outlooks`), in memory.
    outlooks = outlooks_as_of(session_data.outlooks, d)
    upcoming = historical_upcoming(session_data.schedule_rows, d, session_data.horizon)
    inputs = compute_inputs(session_data.data, d, kw, upcoming, outlooks,
                             horizon=session_data.horizon,
                             class_thresholds=session_data.class_thresholds)
    return inputs, verdicts(inputs, session_data.thresholds, session_data.disabled)


def verdicts_on(session_data: SessionData, d: date) -> dict[int, Verdict]:
    """The verdict for every player, as of `d`, using only what `d` could
    have known — the point-in-time core the harness and its tests share."""
    return _inputs_and_verdicts(session_data, d)[1]


# --- outcomes ----------------------------------------------------------------------------


@dataclass(frozen=True)
class _StaticContext:
    """Everything the outcome computation needs that does not depend on
    thresholds — built once and reused across every grid point."""
    days: list[date]  # every PlayerMarketDaily day for the season
    played: dict[str, set[tuple[int, int]]]  # team -> {(season, week)} it actually played
    points_by_player: dict[int, dict[int, int]]  # pid -> week -> points, this season


def _static_context(season: int, data: InputsData) -> _StaticContext:
    days = sorted({d for prices in data.prices.values() for d in prices})
    team_of = {pid: b.team for pid, b in data.players.items()}
    played = an.team_played_weeks(data.gameweek_rows, team_of)
    points_by_player: dict[int, dict[int, int]] = defaultdict(dict)
    for r in data.gameweek_rows:
        if r.season_year == season:
            points_by_player[r.player_id][r.week] = r.points
    return _StaticContext(days, played, dict(points_by_player))


def _select_dates(ends: dict[int, date], days: Sequence[date]) -> list[date]:
    """Every day in `days` from the first with ≥3 known weeks to the day
    before the latest."""
    if not days:
        return []
    last_day = days[-1]
    candidates = [d for d in days if d < last_day]
    start = next(
        (i for i, d in enumerate(candidates) if len(jr.known_weeks(ends, d)) >= 3),
        len(candidates),
    )
    return candidates[start:]


def _observations_for(
    session_data: SessionData, season: int, ctx: _StaticContext, dates: Sequence[date],
) -> tuple[list[Observation], int]:
    """One `Observation` per player per date, with what happened over the
    following `horizon` jornadas / 7 days — `None` where it is not yet
    knowable from stored history."""
    last_day = ctx.days[-1]
    observations: list[Observation] = []
    full_window_count = 0
    for d in dates:
        kw = jr.known_weeks(session_data.ends, d)
        inputs, v = _inputs_and_verdicts(session_data, d)
        next_weeks = sorted(
            w for w in session_data.ends if w > max(kw) and session_data.ends[w] < last_day
        )[:session_data.horizon]
        have_full_window = len(next_weeks) == session_data.horizon
        if have_full_window:
            full_window_count += 1

        for pid, verdict_row in v.items():
            pi = inputs.get(pid)
            if pi is None:
                continue
            price = pi.price

            if have_full_window:
                points = 0
                for w in next_weeks:
                    if (season, w) in ctx.played.get(pi.team, set()):
                        points += ctx.points_by_player.get(pid, {}).get(w, 0)
                points_per_m = (
                    points / (price / 1e6) if price is not None and price > 0 else None
                )
                if pid in session_data.data.page_players:
                    minutes = sum(
                        session_data.data.match_lines.get(pid, {}).get(w, (0, "dnp"))[0]
                        for w in next_weeks
                    )
                else:
                    minutes = None
            else:
                points = points_per_m = minutes = None

            price_pct = m2.price_change_pct(
                session_data.data.prices.get(pid, {}), d + timedelta(days=7), 7
            )

            observations.append(Observation(
                day=d, player_id=pid, position=pi.position, label=verdict_row.label,
                outcomes={"points": points, "points_per_m": points_per_m,
                          "price_pct": price_pct, "minutes": minutes},
            ))
    return observations, full_window_count


# --- the report ----------------------------------------------------------------------------


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(w.capitalize() for w in rest)


def _round(x: float | None, n: int = 3) -> float | None:
    return round(x, n) if x is not None else None


def _label_payload(r: vh.LabelReport) -> dict:
    return {
        "label": r.label, "metric": r.metric, "n": r.n, "players": r.players,
        "hitRate": _round(r.hit_rate), "baseRate": _round(r.base_rate),
        "meanDiff": _round(r.mean_diff), "ciLow": _round(r.ci_low),
        "ciHigh": _round(r.ci_high), "beatsChance": r.beats_chance,
    }


def run_backtest(
    session: Session, season: int, thresholds: Thresholds = DEFAULT_THRESHOLDS,
    disabled: frozenset = frozenset(), horizon: int = 3,
) -> dict:
    """The point-in-time loop over every day stored history allows, scored
    through `core.verdict_harness.label_reports` — the JSON `ModelReport`
    payload (module docstring has the shape)."""
    session_data = load_session_data(session, season, thresholds, disabled, horizon)
    ctx = _static_context(season, session_data.data)
    dates = _select_dates(session_data.ends, ctx.days)
    observations, full_window_count = _observations_for(session_data, season, ctx, dates)
    reports = vh.label_reports(observations)

    notes = [
        f"points outcomes need {horizon} finished jornadas after the date: "
        f"{full_window_count} of {len(dates)} dates qualify.",
        f"{len(observations)} observation(s) across {len(dates)} date(s); "
        f"{len(disabled)} label(s) disabled.",
    ]
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "season": season,
        "dates": [d.isoformat() for d in dates],
        "thresholds": {_camel(k): v for k, v in asdict(thresholds).items()},
        "disabled": sorted(disabled),
        "labels": [_label_payload(r) for r in reports],
        "notes": notes,
    }


def write_report(session: Session, report: dict) -> None:
    """Upsert `ModelReport(name="verdict-validation")` with `report`."""
    row = session.get(ModelReport, REPORT_NAME)
    payload = json.dumps(report)
    generated_at = datetime.fromisoformat(report["generatedAt"])
    if row is None:
        row = ModelReport(name=REPORT_NAME, generated_at=generated_at, payload=payload)
    else:
        row.generated_at = generated_at
        row.payload = payload
    session.add(row)
    session.commit()


# --- the coarse threshold grid -----------------------------------------------------------


_GRID_BARGAIN_VALUE = (70.0, 80.0, 90.0)
_GRID_RISING_OUTLOOK = (75.0, 85.0, 95.0)
_GRID_ELITE_QUALITY = (85.0, 90.0, 95.0)
_GRID_REGULAR_THRESHOLD = (0.5, 0.55, 0.6)


def run_grid(session: Session, season: int, horizon: int = 3) -> list[dict]:
    """One line per combination of `bargain_value`, `rising_outlook`,
    `elite_quality` and the reliability `Regular` threshold — the data load
    and the day/outcome computation (`class_thresholds`/`thresholds` apart)
    happen once and are reused across every combination."""
    base = load_session_data(session, season, horizon=horizon)
    ctx = _static_context(season, base.data)
    dates = _select_dates(base.ends, ctx.days)

    out = []
    for bargain_value, rising_outlook, elite_quality, regular in itertools.product(
        _GRID_BARGAIN_VALUE, _GRID_RISING_OUTLOOK, _GRID_ELITE_QUALITY, _GRID_REGULAR_THRESHOLD
    ):
        thresholds = replace(DEFAULT_THRESHOLDS, bargain_value=bargain_value,
                              rising_outlook=rising_outlook, elite_quality=elite_quality)
        class_thresholds = tuple(
            (name, regular if name == "Regular" else threshold)
            for name, threshold in CLASS_THRESHOLDS
        )
        session_data = replace(base, thresholds=thresholds, class_thresholds=class_thresholds)
        observations, _ = _observations_for(session_data, season, ctx, dates)
        reports = {r.label: r for r in vh.label_reports(observations)}
        out.append({
            "bargainValue": bargain_value, "risingOutlook": rising_outlook,
            "eliteQuality": elite_quality, "regularThreshold": regular,
            "bargainBeatsChance": _label_beats(reports, "Bargain"),
            "eliteBeatsChance": _label_beats(reports, "Elite"),
            "risingBeatsChance": _label_beats(reports, "Rising"),
        })
    return out


def _label_beats(reports: dict[str, vh.LabelReport], label: str) -> bool | None:
    r = reports.get(label)
    return r.beats_chance if r is not None else None


# --- CLI -----------------------------------------------------------------------------------


def _fmt(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "—"
    return f"{x:.1%}" if pct else f"{x:.3f}"


def _print_table(report: dict) -> None:
    print(f"season {report['season']} — {len(report['dates'])} dates, "
          f"disabled: {report['disabled'] or 'none'}")
    print("| label | metric | n | players | hitRate | baseRate | meanDiff | ci | beatsChance |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in report["labels"]:
        ci = f"[{_fmt(r['ciLow'])}, {_fmt(r['ciHigh'])}]" if r["ciLow"] is not None else "—"
        print(f"| {r['label']} | {r['metric'] or '—'} | {r['n']} | {r['players']} | "
              f"{_fmt(r['hitRate'], pct=True)} | {_fmt(r['baseRate'], pct=True)} | "
              f"{_fmt(r['meanDiff'])} | {ci} | {r['beatsChance']} |")
    for note in report["notes"]:
        print(f"note: {note}")


def _print_grid(rows: list[dict]) -> None:
    print("| bargainValue | risingOutlook | eliteQuality | regularThreshold | "
          "bargain | elite | rising |")
    print("|---|---|---|---|---|---|---|")
    for row in rows:
        print(f"| {row['bargainValue']} | {row['risingOutlook']} | {row['eliteQuality']} | "
              f"{row['regularThreshold']} | {row['bargainBeatsChance']} | "
              f"{row['eliteBeatsChance']} | {row['risingBeatsChance']} |")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/fantasy.db")
    ap.add_argument("--write", action="store_true", help="store the report as a ModelReport")
    ap.add_argument("--grid", action="store_true", help="sweep a coarse threshold grid")
    args = ap.parse_args(argv)

    engine = create_engine(f"sqlite:///{args.db}")
    season = get_settings().current_season_year
    with Session(engine) as session:
        if args.grid:
            _print_grid(run_grid(session, season))
            return
        report = run_backtest(session, season)
        _print_table(report)
        if args.write:
            write_report(session, report)
            print(f"\nWrote ModelReport({REPORT_NAME!r}).")


if __name__ == "__main__":
    main()
