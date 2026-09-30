"""Offline backtest and coefficient fit for MODEL-02 (`core/expected_points.py`).

Pure: `storage/xp_backtest.py` loads the rows and prints the tables. Nothing
here runs inside the app.

**The one hard part is the calendar.** Scoring a fixture-aware prediction
for a *past* jornada needs to know which match each team played in that
jornada, and neither history source says: football-data.co.uk has dates but
no round number, and the fantasy source's per-jornada page carries no
fixtures. `assign_jornadas` reconstructs rounds from kickoff times; then
`validate_alignment` checks each reconstructed week against the fantasy data
itself (a team's summed points should track its goal difference) and only
weeks that pass get odds. Weeks that fail still count — their cases simply
fall back to the no-odds basis, the same path the live model takes when a
fixture has no price. The reconstruction affects the fixture terms only:
the points rate and the starter term never needed a calendar.
"""

import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from core import expected_points as xp
from core.odds import match_probabilities

#: Kickoffs further apart than this start a new round window.
WINDOW_GAP_HOURS = 40
#: A window with fewer matches is a rescheduled stray, not a round.
MIN_ROUND_SIZE = 6
#: A reconstructed week is trusted when team points track goal difference.
MIN_ALIGNMENT_CORRELATION = 0.5
#: A team "played" a week when at least this many of its players have rows.
MIN_TEAM_ROWS = 5


# --- calendar reconstruction ----------------------------------------------------------


def _kickoff(m: dict) -> datetime:
    return m.get("kickoff_at") or datetime.combine(m["match_date"], datetime.min.time())


def assign_jornadas(matches: Sequence[dict]) -> dict[tuple[str, int], dict]:
    """`{(team, jornada): match}` reconstructed from kickoff times.

    Matches are grouped into windows (a gap over `WINDOW_GAP_HOURS`, or a team
    appearing twice, starts a new one). Windows of `MIN_ROUND_SIZE`+ matches
    are rounds, numbered in order; smaller ones are rescheduled strays, each
    placed in the earliest round in which neither team has played.
    """
    ordered = sorted(matches, key=lambda m: _kickoff(m).replace(tzinfo=None))
    windows: list[list[dict]] = []
    for m in ordered:
        if windows:
            last = windows[-1]
            teams = {t for x in last for t in (x["home_team"], x["away_team"])}
            gap = _kickoff(m).replace(tzinfo=None) - _kickoff(last[-1]).replace(tzinfo=None)
            if (
                gap <= timedelta(hours=WINDOW_GAP_HOURS)
                and m["home_team"] not in teams
                and m["away_team"] not in teams
            ):
                last.append(m)
                continue
        windows.append([m])

    played: dict[str, set[int]] = defaultdict(set)
    out: dict[tuple[str, int], dict] = {}
    strays: list[dict] = []
    rnd = 0
    for window in windows:
        if len(window) < MIN_ROUND_SIZE:
            strays.extend(window)
            continue
        rnd += 1
        for m in window:
            for team in (m["home_team"], m["away_team"]):
                out[(team, rnd)] = m
                played[team].add(rnd)
    for m in strays:
        home, away = m["home_team"], m["away_team"]
        j = 1
        while j in played[home] or j in played[away]:
            j += 1
        for team in (home, away):
            out[(team, j)] = m
            played[team].add(j)
    return out


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def validate_alignment(
    alignment: dict[tuple[str, int], dict], team_week_points: dict[tuple[str, int], int]
) -> dict[int, float | None]:
    """Per week: correlation of each team's summed fantasy points with its
    goal difference in the reconstructed match. A right calendar gives
    0.65–0.95; a shifted one gives about zero."""
    by_week: dict[int, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    for (team, week), total in team_week_points.items():
        m = alignment.get((team, week))
        if m is None or m.get("home_goals") is None or m.get("away_goals") is None:
            continue
        gd = m["home_goals"] - m["away_goals"]
        if team == m["away_team"]:
            gd = -gd
        by_week[week][0].append(gd)
        by_week[week][1].append(total)
    return {w: pearson(xs, ys) for w, (xs, ys) in by_week.items()}


def fixture_context(match: dict, team: str) -> xp.FixtureContext | None:
    """Pre-match odds only — closing prices are not known at prediction time."""
    probs = match_probabilities(
        match.get("odds_home"),
        match.get("odds_draw"),
        match.get("odds_away"),
        match.get("odds_over25"),
        match.get("odds_under25"),
    )
    home = team == match["home_team"]
    opponent = match["away_team"] if home else match["home_team"]
    if probs is None:
        return xp.FixtureContext(opponent=opponent, is_home=home)
    return xp.FixtureContext(
        opponent=opponent,
        is_home=home,
        team_goals=probs.exp_goals_home if home else probs.exp_goals_away,
        clean_sheet=probs.p_clean_sheet_home if home else probs.p_clean_sheet_away,
        odds_source="football-data",
    )


# --- cases ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    season: int
    week: int
    player_id: int
    position: str
    actual: int
    history: list[int]
    prior_season_mean: float | None
    fixture: xp.FixtureContext | None = None
    starter_probability: float | None = None
    availability: str | None = None
    source_prediction: float | None = None
    extra: dict = field(default_factory=dict)

    def inputs(self, with_starter: bool = True, with_odds: bool = True) -> xp.XpInputs:
        return xp.XpInputs(
            position=self.position,
            history=self.history,
            prior_season_mean=self.prior_season_mean,
            starter_probability=self.starter_probability if with_starter else None,
            availability=self.availability if with_starter else None,
            fixture=self.fixture if with_odds else None,
        )


def build_cases(
    season: int,
    weeks: Sequence[int],
    points: dict[int, dict[int, int]],
    prior_points: dict[int, dict[int, int]],
    players: dict[int, tuple[str, str]],
    team_rows: dict[tuple[str, int], int],
    fixture_for: Callable[[str, int], xp.FixtureContext | None] = lambda team, week: None,
) -> list[Case]:
    """One case per (player, week) the player could have scored in.

    `points[player][week]` is this season's rows. A player is eligible for a
    week between his first and last row of the season (so a mid-season
    arrival or departure is not scored as zeros) when his current team
    played that week; a week without his row is an actual 0 — he was not in
    the matchday squad. History is every earlier week his team played.
    """
    cases = []
    for pid, by_week in points.items():
        team, position = players[pid]
        first, last = min(by_week), max(by_week)
        prior_rows = list(prior_points.get(pid, {}).values())
        prior_mean = sum(prior_rows) / len(prior_rows) if prior_rows else None
        team_weeks = [
            w for w in range(first, last + 1) if team_rows.get((team, w), 0) >= MIN_TEAM_ROWS
        ]
        for week in weeks:
            if week < first or week > last or week not in team_weeks:
                continue
            history = [by_week.get(w, 0) for w in team_weeks if w < week]
            cases.append(
                Case(
                    season=season,
                    week=week,
                    player_id=pid,
                    position=position,
                    actual=by_week.get(week, 0),
                    history=history,
                    prior_season_mean=prior_mean,
                    fixture=fixture_for(team, week),
                    extra={"team": team},
                )
            )
    return cases


# --- fitting ----------------------------------------------------------------------------


def least_squares(rows: Sequence[Sequence[float]], ys: Sequence[float]) -> list[float]:
    """Ordinary least squares via the normal equations (tiny systems only)."""
    k = len(rows[0])
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(k)] for i in range(k)]
    aty = [sum(r[i] * y for r, y in zip(rows, ys, strict=True)) for i in range(k)]
    # Gaussian elimination with partial pivoting.
    m = [row[:] + [b] for row, b in zip(ata, aty, strict=True)]
    for col in range(k):
        pivot = max(range(col, k), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        if abs(m[col][col]) < 1e-12:
            raise ValueError("singular system")
        for r in range(k):
            if r != col:
                f = m[r][col] / m[col][col]
                m[r] = [a - f * b for a, b in zip(m[r], m[col], strict=True)]
    return [m[i][k] / m[i][i] for i in range(k)]


POSITIONS = ("POR", "DEF", "MED", "DEL")


def _rate(c: Case) -> float:
    return xp.points_rate(c.history, c.prior_season_mean, c.position).value


def fit_rate_only(cases: Sequence[Case]) -> dict[str, tuple[float, float]]:
    out = {}
    for pos in POSITIONS:
        sub = [c for c in cases if c.position == pos]
        a, c0 = least_squares([[_rate(c), 1.0] for c in sub], [c.actual for c in sub])
        out[pos] = (a, c0)
    return out


def fit_fixture(
    cases: Sequence[Case], rate_only: dict[str, tuple[float, float]]
) -> dict[str, tuple[float, float]]:
    """Residual of the rate-only base on (base·Δgoals, Δclean-sheet)."""
    out = {}
    for pos in POSITIONS:
        sub = [c for c in cases if c.position == pos and c.fixture and c.fixture.team_goals]
        a, c0 = rate_only[pos]
        rows, ys = [], []
        for c in sub:
            base = a * _rate(c) + c0
            rows.append([
                base * (c.fixture.team_goals - xp.LEAGUE_TEAM_GOALS),
                c.fixture.clean_sheet - xp.LEAGUE_CLEAN_SHEET,
            ])
            ys.append(c.actual - base)
        alpha, gamma = least_squares(rows, ys)
        out[pos] = (alpha, gamma)
    return out


def fit_with_starter(cases: Sequence[Case]) -> dict[str, tuple[float, float, float]]:
    out = {}
    for pos in POSITIONS:
        sub = [c for c in cases if c.position == pos and c.starter_probability is not None]
        rows = []
        for c in sub:
            r, s = _rate(c), c.starter_probability / 100
            rows.append([r, r * s, s])
        a, b, c0 = least_squares(rows, [c.actual for c in sub])
        out[pos] = (a, b, c0)
    return out


def fit_all(
    history_cases: Sequence[Case], starter_cases: Sequence[Case]
) -> xp.Coefficients:
    rate_only = fit_rate_only(history_cases)
    return xp.Coefficients(
        rate_only=rate_only,
        with_starter=fit_with_starter(starter_cases),
        fixture=fit_fixture(history_cases, rate_only),
    )


# --- metrics ----------------------------------------------------------------------------


def _ranks(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


@dataclass(frozen=True)
class Metrics:
    n: int
    mae: float
    rmse: float
    spearman: float | None


def metrics(predicted: Sequence[float], actual: Sequence[float]) -> Metrics:
    n = len(predicted)
    errors = [p - a for p, a in zip(predicted, actual, strict=True)]
    return Metrics(
        n=n,
        mae=sum(abs(e) for e in errors) / n,
        rmse=math.sqrt(sum(e * e for e in errors) / n),
        spearman=pearson(_ranks(predicted), _ranks(actual)),
    )


# --- baselines ----------------------------------------------------------------------------


def season_average(c: Case) -> float:
    """Season-to-date points per team match; last season's per-appearance
    average (then 0) before his first match."""
    if c.history:
        return sum(c.history) / len(c.history)
    return c.prior_season_mean or 0.0


def last5_average(c: Case) -> float:
    return sum(c.history[-5:]) / len(c.history[-5:]) if c.history else season_average(c)


def model_predictor(
    k: xp.Coefficients, with_starter: bool = True, with_odds: bool = True
) -> Callable[[Case], float]:
    return lambda c: xp.expected_points(c.inputs(with_starter, with_odds), k).value


def without_fixture(k: xp.Coefficients) -> xp.Coefficients:
    zero = {pos: (0.0, 0.0) for pos in POSITIONS}
    return replace(k, fixture=zero)
