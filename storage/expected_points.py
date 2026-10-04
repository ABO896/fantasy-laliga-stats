"""Storage side of MODEL-02: gather each player's inputs, store one
expected-points prediction per player for the next jornada, and score stored
predictions against `PlayerGameweekPoints` once the jornada is played.

Kept out of `storage/repository.py` and `storage/our_models.py` — both are
edited by other work; this module is owned by the expected-points model.

**Which jornada is "next".** The earliest jornada in the restored calendar
(`Fixture`) whose *first* kickoff is still in the future — the lineup
deadline is that first kickoff, so once a jornada has started the useful
question is the one after it. A lone postponed fixture left over from an
old jornada does not make that jornada "next". Without a calendar, the
jornada after the latest one with stored points, with no fixture context.

Power Score does **not** read expected points (Power v2, audit 2026-09-30);
the transfer engine's expected return does, via `expected_points_map`.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlmodel import Session, func, select

from core import expected_points as xp
from core.config import get_settings
from core.odds import match_probabilities
from core.xp_backtest import MIN_TEAM_ROWS
from storage.db import as_utc
from storage.models import (
    ExpectedPointsPrediction,
    ExternalMatch,
    Fixture,
    Player,
    PlayerGameweekPoints,
    PlayerSnapshot,
)

ODDS_SOURCE = "football-data"


# --- choosing the target jornada ------------------------------------------------------


@dataclass(frozen=True)
class Target:
    season_year: int
    jornada: int
    #: team -> its fixture in the jornada; empty when there is no calendar.
    fixtures: dict[str, Fixture] = field(default_factory=dict)
    #: Every team name the calendar knows — a roster team outside this set is
    #: a vocabulary miss, not a team without a fixture.
    calendar_teams: frozenset[str] = frozenset()
    #: The jornada's first kickoff (its lineup deadline), or None.
    locks_at: datetime | None = None


def _stored_weeks(session: Session, season: int) -> list[tuple[int, bool]]:
    rows = session.exec(
        select(PlayerGameweekPoints.week, func.max(PlayerGameweekPoints.is_provisional))
        .where(PlayerGameweekPoints.season_year == season)
        .group_by(PlayerGameweekPoints.week)
        .order_by(PlayerGameweekPoints.week)
    ).all()
    return [(w, bool(p)) for w, p in rows]


def select_target(session: Session, now: datetime, season: int) -> Target:
    fixtures = session.exec(select(Fixture).where(Fixture.season_year == season)).all()
    by_jornada: dict[int, list[Fixture]] = defaultdict(list)
    for f in fixtures:
        f.kickoff_utc = as_utc(f.kickoff_utc)
        by_jornada[f.matchday].append(f)
    starts = {j: min(f.kickoff_utc for f in fs) for j, fs in by_jornada.items()}
    future = sorted((start, j) for j, start in starts.items() if start > now)
    if future:
        start, jornada = future[0]
        team_fixture: dict[str, Fixture] = {}
        for f in sorted(by_jornada[jornada], key=lambda f: f.kickoff_utc):
            team_fixture.setdefault(f.home_team, f)
            team_fixture.setdefault(f.away_team, f)
        teams = frozenset(t for f in fixtures for t in (f.home_team, f.away_team))
        return Target(season, jornada, team_fixture, teams, start)

    weeks = _stored_weeks(session, season)
    return Target(season, (weeks[-1][0] + 1) if weeks else 1)


# --- inputs -----------------------------------------------------------------------------


def _latest_snapshots(session: Session) -> dict[int, PlayerSnapshot]:
    latest = session.exec(select(func.max(PlayerSnapshot.as_of))).one()
    if latest is None:
        return {}
    rows = session.exec(select(PlayerSnapshot).where(PlayerSnapshot.as_of == latest)).all()
    return {r.player_id: r for r in rows}


def _odds_context(session: Session, season: int, f: Fixture, team: str) -> xp.FixtureContext:
    home = team == f.home_team
    opponent = f.away_team if home else f.home_team
    match = session.get(ExternalMatch, (ODDS_SOURCE, season, f.home_team, f.away_team))
    probs = match and match_probabilities(
        match.odds_home, match.odds_draw, match.odds_away, match.odds_over25, match.odds_under25
    )
    if not probs:
        return xp.FixtureContext(opponent=opponent, is_home=home)
    return xp.FixtureContext(
        opponent=opponent,
        is_home=home,
        team_goals=probs.exp_goals_home if home else probs.exp_goals_away,
        clean_sheet=probs.p_clean_sheet_home if home else probs.p_clean_sheet_away,
        odds_source=ODDS_SOURCE,
    )


@dataclass(frozen=True)
class PlayerPrediction:
    player_id: int
    result: xp.XpResult
    fixture: Fixture | None


def compute_expected_points(
    session: Session, now: datetime | None = None, season: int | None = None
) -> tuple[Target, list[PlayerPrediction]]:
    """xP for every player in the latest market snapshot, for the next
    jornada. Reads only; `refresh_expected_points` stores."""
    now = now or datetime.now(UTC)
    season = season or get_settings().current_season_year
    target = select_target(session, now, season)
    snapshots = _latest_snapshots(session)
    if not snapshots:
        return target, []

    players = {
        p.id: p
        for p in session.exec(select(Player).where(Player.id.in_(list(snapshots)))).all()
    }
    weeks = [(w, prov) for w, prov in _stored_weeks(session, season) if w < target.jornada]
    in_progress = weeks[-1][0] if weeks and weeks[-1][1] else None
    rows = session.exec(
        select(PlayerGameweekPoints.player_id, PlayerGameweekPoints.week,
               PlayerGameweekPoints.points)
        .where(PlayerGameweekPoints.season_year == season)
        .where(PlayerGameweekPoints.week < target.jornada)
    ).all()
    by_player: dict[int, dict[int, int]] = defaultdict(dict)
    team_rows: dict[tuple[str, int], int] = defaultdict(int)
    all_players = {p.id: p.team for p in session.exec(select(Player)).all()}
    for pid, week, pts in rows:
        if week == in_progress:
            continue
        by_player[pid][week] = pts
        if pid in all_players:
            team_rows[(all_players[pid], week)] += 1

    prior = last_season_means(session, season)

    week_numbers = [w for w, _ in weeks if w != in_progress]
    out = []
    for pid, snap in snapshots.items():
        player = players.get(pid)
        if player is None:
            continue
        own = by_player.get(pid, {})
        first = min(own) if own else None
        history = [
            own.get(w, 0)
            for w in week_numbers
            if first is not None and w >= first and team_rows[(player.team, w)] >= MIN_TEAM_ROWS
        ]
        fixture = target.fixtures.get(player.team)
        has_fixture = fixture is not None or player.team not in target.calendar_teams
        context = _odds_context(session, season, fixture, player.team) if fixture else None
        result = xp.expected_points(
            xp.XpInputs(
                position=player.position,
                history=history,
                prior_season_mean=prior.get(pid),
                starter_probability=snap.starter_probability,
                availability=snap.availability_status,
                fixture=context,
                has_fixture=has_fixture,
            )
        )
        # The naive comparator the track record reports beside ours.
        naive = sum(history) / len(history) if history else prior.get(pid)
        result.inputs["naiveSeasonAverage"] = None if naive is None else round(naive, 3)
        result.inputs["snapshotAsOf"] = snap.as_of.isoformat()
        out.append(PlayerPrediction(pid, result, fixture))
    return target, out


# --- storing ----------------------------------------------------------------------------


@dataclass(frozen=True)
class RefreshSummary:
    season_year: int
    jornada: int
    written: int
    frozen: bool
    by_basis: dict[str, int]


def _is_locked(session: Session, target: Target, now: datetime) -> bool:
    if target.locks_at is not None:
        return now >= target.locks_at
    has_points = session.exec(
        select(func.count())
        .select_from(PlayerGameweekPoints)
        .where(PlayerGameweekPoints.season_year == target.season_year)
        .where(PlayerGameweekPoints.week == target.jornada)
    ).one()
    return has_points > 0


def refresh_expected_points(session: Session, now: datetime | None = None) -> RefreshSummary:
    """Compute and store xP for the next jornada. Rewrites only while the
    jornada has not started; after that its rows are frozen history."""
    now = now or datetime.now(UTC)
    target, predictions = compute_expected_points(session, now)
    counts: dict[str, int] = defaultdict(int)
    if _is_locked(session, target, now):
        return RefreshSummary(target.season_year, target.jornada, 0, True, {})

    for p in predictions:
        key = (target.season_year, target.jornada, p.player_id, xp.MODEL_VERSION)
        row = session.get(ExpectedPointsPrediction, key)
        if row is None:
            row = ExpectedPointsPrediction(
                season_year=target.season_year,
                jornada=target.jornada,
                player_id=p.player_id,
                model_version=xp.MODEL_VERSION,
                created_at=now,
                predicted=0,
                basis="",
                inputs="{}",
                updated_at=now,
            )
        fixture_info = p.result.inputs.get("fixture") or {}
        row.predicted = round(p.result.value, 3)
        row.basis = p.result.basis
        row.inputs = json.dumps(p.result.inputs, sort_keys=True)
        row.fixture_id = p.fixture.fixture_id if p.fixture else None
        row.opponent = fixture_info.get("opponent")
        row.is_home = fixture_info.get("isHome")
        row.locks_at = target.locks_at
        row.updated_at = now
        session.add(row)
        counts[p.result.basis] += 1
    session.commit()
    return RefreshSummary(
        target.season_year, target.jornada, len(predictions), False, dict(counts)
    )


# --- reading ----------------------------------------------------------------------------


def _latest_stored_jornada(session: Session, season: int) -> int | None:
    return session.exec(
        select(func.max(ExpectedPointsPrediction.jornada))
        .where(ExpectedPointsPrediction.season_year == season)
        .where(ExpectedPointsPrediction.model_version == xp.MODEL_VERSION)
    ).one()


def latest_expected_points(
    session: Session, season: int | None = None
) -> dict[int, tuple[float, str]]:
    """`{player_id: (xP, basis)}` for the latest stored jornada, blanks
    included — what the browser column and the squad cards show."""
    season = season or get_settings().current_season_year
    jornada = _latest_stored_jornada(session, season)
    if jornada is None:
        return {}
    rows = session.exec(
        select(ExpectedPointsPrediction.player_id, ExpectedPointsPrediction.predicted,
               ExpectedPointsPrediction.basis)
        .where(ExpectedPointsPrediction.season_year == season)
        .where(ExpectedPointsPrediction.jornada == jornada)
        .where(ExpectedPointsPrediction.model_version == xp.MODEL_VERSION)
    ).all()
    return {pid: (value, basis) for pid, value, basis in rows}


def last_season_means(session: Session, season: int) -> dict[int, float]:
    """`{player_id: mean points per appearance}` over season − 1 — the prior
    `xp.points_rate` shrinks toward, shared by xP and Power."""
    rows = session.exec(
        select(PlayerGameweekPoints.player_id, func.avg(PlayerGameweekPoints.points))
        .where(PlayerGameweekPoints.season_year == season - 1)
        .group_by(PlayerGameweekPoints.player_id)
    ).all()
    return {pid: float(avg) for pid, avg in rows}


def expected_points_map(session: Session, season: int | None = None) -> dict[int, float]:
    """`{player_id: xP}` for the latest stored jornada — what the transfer
    engine blends into expected return (`storage.transfers`).

    `no_fixture` rows are left out: a blank jornada carries no fixture to
    project, so it says nothing the backward-looking return does not.
    """
    return {
        pid: value
        for pid, (value, basis) in latest_expected_points(session, season).items()
        if basis != "no_fixture"
    }


def xp_fields(latest: dict[int, tuple[float, str]], player_id: int) -> dict:
    """The two fields the browser and squad payloads carry."""
    value, basis = latest.get(player_id, (None, None))
    return {
        "expectedPoints": None if value is None else round(value, 2),
        "expectedPointsBasis": basis,
    }


def stored_predictions(
    session: Session,
    season: int | None = None,
    jornada: int | None = None,
    player_id: int | None = None,
) -> tuple[int, int | None, list[tuple[ExpectedPointsPrediction, Player]]]:
    season = season or get_settings().current_season_year
    if jornada is None:
        if player_id is not None:
            jornada = session.exec(
                select(func.max(ExpectedPointsPrediction.jornada))
                .where(ExpectedPointsPrediction.season_year == season)
                .where(ExpectedPointsPrediction.player_id == player_id)
                .where(ExpectedPointsPrediction.model_version == xp.MODEL_VERSION)
            ).one()
        else:
            jornada = _latest_stored_jornada(session, season)
    if jornada is None:
        return season, None, []
    query = (
        select(ExpectedPointsPrediction, Player)
        .join(Player, Player.id == ExpectedPointsPrediction.player_id)
        .where(ExpectedPointsPrediction.season_year == season)
        .where(ExpectedPointsPrediction.jornada == jornada)
        .where(ExpectedPointsPrediction.model_version == xp.MODEL_VERSION)
        .order_by(ExpectedPointsPrediction.predicted.desc(), Player.id)
    )
    if player_id is not None:
        query = query.where(ExpectedPointsPrediction.player_id == player_id)
    return season, jornada, list(session.exec(query).all())


def prediction_payload(row: ExpectedPointsPrediction, player: Player | None = None) -> dict:
    out = {
        "playerId": row.player_id,
        "seasonYear": row.season_year,
        "jornada": row.jornada,
        "expectedPoints": round(row.predicted, 2),
        "basis": row.basis,
        "opponent": row.opponent,
        "isHome": row.is_home,
        "locksAt": as_utc(row.locks_at).isoformat() if row.locks_at else None,
        "updatedAt": as_utc(row.updated_at).isoformat(),
        "modelVersion": row.model_version,
        "inputs": json.loads(row.inputs),
    }
    if player is not None:
        out |= {"name": player.name, "team": player.team, "position": player.position}
    return out


def expected_points_payload(
    session: Session, jornada: int | None = None, season: int | None = None
) -> dict:
    season, jornada, rows = stored_predictions(session, season, jornada)
    return {
        "seasonYear": season,
        "jornada": jornada,
        "modelVersion": xp.MODEL_VERSION,
        "predictions": [prediction_payload(r, p) for r, p in rows],
    }


# --- scoring (MODEL-03 for xP) ------------------------------------------------------------


@dataclass(frozen=True)
class ScoredPrediction:
    row: ExpectedPointsPrediction
    actual: int | None  # None = not scorable yet (or ever)
    status: str  # scored | pending | unscorable


def score_expected_points(session: Session) -> list[ScoredPrediction]:
    """Every stored prediction against what happened.

    `scored`: the jornada's points are final. A missing row counts 0 when
    his team has rows that week (he was not in the matchday squad), exactly
    as the backtest counts it. `pending`: no points yet, or the jornada is
    still in progress. `unscorable`: the week is final but his team has no
    rows — a blank or a data gap, never averaged over as a zero.
    """
    preds = session.exec(
        select(ExpectedPointsPrediction)
        .where(ExpectedPointsPrediction.model_version == xp.MODEL_VERSION)
    ).all()
    if not preds:
        return []
    teams = {p.id: p.team for p in session.exec(select(Player)).all()}
    seasons = {p.season_year for p in preds}
    points: dict[tuple[int, int, int], int] = {}
    team_rows: dict[tuple[int, int, str], int] = defaultdict(int)
    provisional: set[tuple[int, int]] = set()
    for season in seasons:
        for pid, week, pts, prov in session.exec(
            select(PlayerGameweekPoints.player_id, PlayerGameweekPoints.week,
                   PlayerGameweekPoints.points, PlayerGameweekPoints.is_provisional)
            .where(PlayerGameweekPoints.season_year == season)
        ).all():
            points[(season, week, pid)] = pts
            team_rows[(season, week, teams.get(pid, ""))] += 1
            if prov:
                provisional.add((season, week))
    latest_week: dict[int, int] = defaultdict(int)
    weeks_with_rows = {(season, week) for season, week, _ in points}
    for season, week in weeks_with_rows:
        latest_week[season] = max(latest_week[season], week)

    out = []
    for p in preds:
        key = (p.season_year, p.jornada)
        has_week = key in weeks_with_rows
        in_progress = key in provisional and latest_week[p.season_year] == p.jornada
        if not has_week or in_progress:
            out.append(ScoredPrediction(p, None, "pending"))
        elif (p.season_year, p.jornada, p.player_id) in points:
            out.append(ScoredPrediction(p, points[(p.season_year, p.jornada, p.player_id)],
                                        "scored"))
        elif team_rows[(p.season_year, p.jornada, teams.get(p.player_id, ""))] >= MIN_TEAM_ROWS:
            out.append(ScoredPrediction(p, 0, "scored"))
        else:
            out.append(ScoredPrediction(p, None, "unscorable"))
    return out


def _summary(pairs: list[tuple[float, float]]) -> dict:
    s = xp.summarize_errors([xp.ScoredPair(p, a, "") for p, a in pairs])
    def r(v: float | None) -> float | None:
        return None if v is None else round(v, 3)

    return {"n": s.n, "mae": r(s.mae), "rmse": r(s.rmse), "bias": r(s.bias)}


def track_record_payload(session: Session) -> dict:
    """xP's track record: our error, beside the naive season average made
    from the same inputs at the same time, overall, by basis and by jornada.
    `no_fixture` predictions are counted but never scored (a predicted 0
    for a team that did not play would flatter every number)."""
    scored = score_expected_points(session)
    counts = defaultdict(int)
    ours: list[tuple[float, float]] = []
    naive: list[tuple[float, float]] = []
    by_basis: dict[str, list[tuple[float, float]]] = defaultdict(list)
    by_jornada: dict[tuple[int, int], dict[str, list]] = defaultdict(
        lambda: {"ours": [], "naive": []}
    )
    for s in scored:
        if s.row.basis == "no_fixture":
            counts["noFixture"] += 1
            continue
        counts[s.status] += 1
        if s.status != "scored":
            continue
        pair = (s.row.predicted, float(s.actual))
        ours.append(pair)
        by_basis[s.row.basis].append(pair)
        by_jornada[(s.row.season_year, s.row.jornada)]["ours"].append(pair)
        base = json.loads(s.row.inputs).get("naiveSeasonAverage")
        if base is not None:
            naive.append((base, float(s.actual)))
            by_jornada[(s.row.season_year, s.row.jornada)]["naive"].append((base, float(s.actual)))

    return {
        "modelVersion": xp.MODEL_VERSION,
        "counts": {
            "scored": counts["scored"],
            "pending": counts["pending"],
            "unscorable": counts["unscorable"],
            "noFixture": counts["noFixture"],
        },
        "overall": _summary(ours),
        "naiveSeasonAverage": _summary(naive),
        "byBasis": [{"basis": b, **_summary(v)} for b, v in sorted(by_basis.items())],
        "byJornada": [
            {"seasonYear": season, "jornada": j, **_summary(v["ours"]),
             "naiveMae": _summary(v["naive"])["mae"]}
            for (season, j), v in sorted(by_jornada.items())
        ],
        "note": (
            "Scored against final per-jornada points; a player missing from a "
            "jornada his team played counts as 0. MAE rewards predicting low on "
            "a skewed points distribution — RMSE is the fairer test of an "
            "expected value."
        ),
    }
