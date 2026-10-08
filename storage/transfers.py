"""Storage side of Phase 11: load everything `core.transfers` needs, once per
request, as plain values.

Computed on read, like Phase 10's analytics — nothing here is persisted,
so there is no migration and nothing that can go stale on its own. Kept
out of `storage/repository.py` (shared, edited in parallel) the same way
`storage/our_models.py` is.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, func, select

from core import market_v2 as m2
from core import transfers as tr
from core.fixture_difficulty import FixtureView, fixture_difficulty, team_strength
from core.rules import Rules
from core.squad_rules import SquadMember
from storage.db import as_utc
from storage.expected_points import expected_points_map
from storage.market_v2 import latest_outlooks
from storage.models import DatasetRun
from storage.our_models import compute_player_analytics
from storage.repository import (
    get_fixtures,
    get_last_successful_run,
    get_latest_players,
    get_squad_members,
    get_team_week_points,
)

#: The datasets whose age TRANSFER-04 weighs. `market` is read from the
#: last successful `ScrapeRun`, as `/api/health` does; the rest from their
#: own `DatasetRun` rows.
FRESHNESS_DATASETS = ("jornada_points", "fixtures", "football_data")


def load_expected_points(session: Session, season: int | None = None) -> dict[int, float] | None:
    """**The MODEL-02 hook for Phase 11.** `{player_id: expected points}` for
    the latest stored jornada (`storage.expected_points.expected_points_map`,
    blank-jornada rows excluded), or `None` when no expected points are
    stored yet — Phase 11 then degrades to its backward-looking form.

    From here xP flows into expected return only, through
    `PlayerInput.expected_points` — not into Power, which since Power v2 is
    its own backward-looking number — and the odds dataset's age starts
    counting toward confidence, because odds are what xP is built on.
    """
    xp_map = expected_points_map(session, season)
    return xp_map or None


@dataclass(frozen=True)
class TransferContext:
    as_of: str | None
    assessments: dict[int, tr.Assessment]
    members: list[SquadMember]
    freshness: tr.Freshness
    jornadas_requested: int
    window: list[int]  # the jornada numbers the window covers, in kickoff order
    jornadas: int  # how many jornadas expected return is spread over
    expected_points_used: bool


def last_successes(session: Session) -> dict[str, datetime | None]:
    """`started_at` of each dataset's latest successful run (UTC-aware)."""
    out: dict[str, datetime | None] = dict.fromkeys(("market", *FRESHNESS_DATASETS))
    run = get_last_successful_run(session)
    out["market"] = as_utc(run.started_at) if run else None
    rows = session.exec(
        select(DatasetRun.dataset, func.max(DatasetRun.started_at))
        .where(DatasetRun.status == "success")
        .where(DatasetRun.dataset.in_(FRESHNESS_DATASETS))
        .group_by(DatasetRun.dataset)
    ).all()
    for dataset, started in rows:
        out[dataset] = as_utc(started)
    return out


def fixture_outlooks(session: Session, season: int, n: int, now: datetime):
    """Per team, the fixtures to weigh in the window, and the window's
    jornadas. A team the calendar knows but with nothing in the window gets
    an empty list (a genuine blank); a team the calendar has never named is
    left out, so its players read as "no fixture data", not as a blank.

    Shared with `storage.inputs.compute_live_inputs` (Plan B Task 6), which
    feeds the per-team multiplier straight into `core.inputs.compute_inputs`."""
    rows = get_fixtures(session, season)
    views = [
        FixtureView(r.fixture_id, r.matchday, r.kickoff_utc, r.kickoff_confirmed, r.is_final,
                    r.home_team, r.away_team)
        for r in rows
    ]
    window, weighed = tr.select_window(views, now, n)
    if not weighed:
        return {}, [], False
    known = {f.home_team for f in views} | {f.away_team for f in views}
    strength = team_strength(
        get_team_week_points(session, season), get_team_week_points(session, season - 1), known
    )
    ranked = fixture_difficulty(weighed, strength, len({f.matchday for f in weighed}))
    per_team = {team: [] for team in known}
    per_team.update({t.team: t.fixtures for t in ranked})
    return per_team, window, True


#: Pre-rename alias for `build_context`, this module's existing caller.
_fixture_outlooks = fixture_outlooks


def build_context(
    session: Session,
    rules: Rules,
    season: int,
    jornadas: int,
    now: datetime,
    expected_points: Mapping[int, float] | None = None,
) -> TransferContext:
    xp = (
        dict(expected_points) if expected_points is not None
        else load_expected_points(session, season)
    )
    analytics = compute_player_analytics(session)
    rows = get_latest_players(session)
    # market-v2: each player's latest 7-day outlook (v1 retired 2026-10-08).
    predictions = latest_outlooks(session)
    per_team, window, fixtures_available = _fixture_outlooks(session, season, jornadas, now)
    spread = len(window) if window else jornadas

    assessments: dict[int, tr.Assessment] = {}
    for snapshot, player in rows:
        a = analytics.get(player.id)
        power = a.power if a else None
        valuation = a.valuation if a else None
        prediction = predictions.get(player.id)
        p = tr.PlayerInput(
            player_id=player.id,
            name=player.name,
            team=player.team,
            position=player.position,
            market_value=snapshot.market_value,
            source_ideal_bid=snapshot.ideal_bid,
            source_max_bid=snapshot.max_bid,
            availability=snapshot.availability_status,
            starter_probability=snapshot.starter_probability,
            backward_ppg=power.quality_ppg if power else None,
            recent_jornadas=a.power_inputs.recent_jornadas if a and a.power_inputs else 0,
            expected_points=(xp or {}).get(player.id),
            fair_value=valuation.fair_value if valuation else None,
            valuation_gap=valuation.gap if valuation else None,
            power_score=power.score if power else None,
            predicted_pct=prediction.expected_pct if prediction else None,
            prediction_confidence=m2.confidence_for(prediction) if prediction else None,
        )
        outlook = tr.fixture_outlook(per_team.get(player.team), spread)
        assessments[player.id] = tr.assess_player(p, outlook, spread, rules.cash_per_point)

    freshness = tr.assess_freshness(
        last_successes(session), now, fixtures_available, expected_points_used=bool(xp)
    )
    return TransferContext(
        as_of=rows[0][0].as_of.isoformat() if rows else None,
        assessments=assessments,
        members=get_squad_members(session),
        freshness=freshness,
        jornadas_requested=jornadas,
        window=window,
        jornadas=spread,
        expected_points_used=bool(xp),
    )
