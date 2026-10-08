"""The squad surface.

Every legality decision here delegates to `core.squad_rules` — this module
does arithmetic nowhere. A refusal is an HTTP 409 whose `detail` is the
engine's `Violation` verbatim, so the UI can render the remedy sentence
without re-deriving it (spec D-05).
"""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import func, select

from api.deps import SessionDep, resolve_league_context
from core.lineup_rules import EligiblePlayer, LineupSelection, evaluate_lineup
from core.rules import Rules, find_formation, load_rules
from core.squad_rules import SquadMember as EngineMember
from core.squad_rules import SquadVerdict, evaluate_add, evaluate_squad
from storage.expected_points import latest_expected_points, xp_fields
from storage.inputs import inputs_fields
from storage.models import Player, PlayerSnapshot
from storage.our_models import compute_player_analytics, score_fields
from storage.repository import (
    add_squad_member,
    get_availability_as_of,
    get_league_settings,
    get_season_week_ranges,
    get_squad_members,
    get_squad_points_history,
    get_squad_roles,
    get_squad_setup,
    get_squad_value_history,
    remove_squad_member,
    save_xi,
)
from storage.verdict import live_verdicts, verdict_fields

router = APIRouter()


class AddPlayerRequest(BaseModel):
    playerId: int
    purchasePrice: int


def _rules(session) -> Rules:
    """The one place premium formations are resolved. Every other function in
    this module — and the whole engine — sees an already-narrowed rule set and
    never learns the concept exists."""
    return resolve_league_context(session).rules


def _serialize_summary(verdict: SquadVerdict, member_ids: list[int], rules: Rules) -> dict:
    return {
        "squadSize": verdict.squad_size,
        "maxSquadSize": rules.max_squad_size,
        "squadValue": verdict.squad_value,
        "isLegal": verdict.is_legal,
        "canFieldXi": verdict.can_field_xi,
        "positionCounts": verdict.position_counts,
        "feasibleFormations": verdict.feasible_formations,
        "missingForXi": verdict.missing_for_xi,
        "nearestFormation": verdict.nearest_formation,
        "memberPlayerIds": member_ids,
        "violations": [
            {"rule": v.rule, "actual": v.actual, "limit": v.limit, "message": v.message}
            for v in verdict.violations
        ],
    }


def _squad_payload(session) -> dict:
    """Everything the squad page needs, in one query set.

    One payload rather than three, deliberately. The editor this replaces
    fetched the league settings separately and had to guard every save
    against that query being unresolved — a save fired early sent an empty
    bench and silently wiped one. Carrying `benchEnabled` and
    `allowedFormations` here removes the category rather than re-implementing
    the guard.
    """
    league = resolve_league_context(session)
    rules = league.rules
    members = get_squad_members(session)
    roles = get_squad_roles(session)
    availability = get_availability_as_of(session, [m.player_id for m in members], date.today())
    setup = get_squad_setup(session)
    analytics = compute_player_analytics(session)
    latest_xp = latest_expected_points(session)
    live, vmap = live_verdicts(session)

    # Looked up in the *full* rule set, not the league's: a shape stored
    # while premium formations were on must still be drawable after they are
    # switched off. `formationAvailable` is how the page learns it may not be
    # saved again as it stands.
    shape = find_formation(load_rules(), setup.formation)

    verdict = evaluate_squad(members, rules)
    summary = _serialize_summary(verdict, [m.player_id for m in members], rules)
    summary.update(
        {
            "formation": setup.formation,
            "formationShape": shape.required() if shape is not None else None,
            "formationAvailable": find_formation(rules, setup.formation) is not None,
            "allowedFormations": [f.name for f in rules.formations],
            "formationShapes": {f.name: f.required() for f in rules.formations},
            "benchEnabled": league.features.bench_enabled,
        }
    )

    return {
        "members": [
            {
                "playerId": m.player_id,
                "name": m.name,
                "position": m.position,
                "purchasePrice": m.purchase_price,
                "marketValue": m.market_value,
                "effectiveValue": m.effective_value,
                "role": roles.get(m.player_id, "reserve"),
                "availability": availability.get(m.player_id, "available"),
                # ANALYTICS-06/07 on each card: comparing same-position
                # members' Power is the "who should I start" answer.
                **score_fields(analytics.get(m.player_id)),
                # MODEL-02: same-position xP side by side is "who do I start".
                **xp_fields(latest_xp, m.player_id),
                # Plan B Task 7: reliability, points value, outlook and
                # Power's position rank, same as the browser table.
                **inputs_fields(live.get(m.player_id)),
                # Plan C Task 5: the verdict label every surface agrees on.
                **verdict_fields(vmap.get(m.player_id)),
            }
            for m in members
        ],
        "summary": summary,
    }


@router.get("/squad")
def read_squad(session: SessionDep):
    return _squad_payload(session)


@router.get("/squad/history")
def read_squad_history(session: SessionDep):
    """SQUAD-04. Separate from `GET /squad` on purpose — that route is
    refetched on every pitch rearrangement, and this aggregation has no
    reason to run that often."""
    return {
        "valueHistory": [
            {"asOf": as_of.isoformat(), "squadValue": value}
            for as_of, value in get_squad_value_history(session)
        ],
        "pointsHistory": [
            {
                "seasonYear": row.season_year,
                "week": row.week,
                "points": row.points,
                "isProvisional": row.is_provisional,
            }
            for row in get_squad_points_history(session)
        ],
        "seasonWeekRanges": get_season_week_ranges(session),
    }


@router.get("/squad/rules")
def read_rules(session: SessionDep):
    """Reports the formations this league actually allows, not everything the
    file knows about — so the UI can never show a shape the league would
    score zero."""
    league = resolve_league_context(session)
    rules = league.rules
    return {
        "sourceUrl": rules.source_url,
        "retrievedOn": rules.retrieved_on,
        "maxSquadSize": rules.max_squad_size,
        "debtLimitFraction": rules.debt_limit_fraction,
        "premiumFormationsEnabled": get_league_settings(session).premium_formations_enabled,
        "cashPerPoint": rules.cash_per_point,
        "formations": [
            {"name": f.name, "POR": f.POR, "DEF": f.DEF, "MED": f.MED, "DEL": f.DEL}
            for f in rules.formations
        ],
    }


class SaveXiRequest(BaseModel):
    """The whole desired shape, not one player's move.

    Whole-shape for two reasons. A swap is one transaction rather than two
    writes with an illegal state between them. And changing formation demotes
    whichever starters no longer fit — a decision the client makes visibly,
    in front of the owner, rather than one the server makes by a heuristic
    nobody can see. That second reason is why there is no separate
    `PUT /api/squad/formation`.
    """

    formation: str
    starterIds: list[int] = []
    benchIds: list[int] = []


@router.put("/squad/lineup")
def put_squad_lineup(payload: SaveXiRequest, session: SessionDep):
    league = resolve_league_context(session)
    members = get_squad_members(session)
    eligible = [
        EligiblePlayer(player_id=m.player_id, name=m.name, position=m.position) for m in members
    ]

    verdict = evaluate_lineup(
        LineupSelection(
            formation=payload.formation,
            starter_ids=tuple(payload.starterIds),
            bench_ids=tuple(payload.benchIds),
        ),
        eligible,
        league.rules,
        league.features,
    )

    if not verdict.allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "rule": verdict.violation.rule,
                "actual": verdict.violation.actual,
                "limit": verdict.violation.limit,
                "message": verdict.violation.message,
            },
        )

    save_xi(
        session,
        formation=payload.formation,
        starter_ids=payload.starterIds,
        bench_ids=payload.benchIds,
    )
    return _squad_payload(session)


@router.post("/squad/players", status_code=201)
def add_player(payload: AddPlayerRequest, session: SessionDep):
    player = session.get(Player, payload.playerId)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    latest_date = session.exec(select(func.max(PlayerSnapshot.as_of))).one()
    snapshot = (
        session.get(PlayerSnapshot, (latest_date, payload.playerId))
        if latest_date is not None
        else None
    )

    candidate = EngineMember(
        player_id=player.id,
        name=player.name,
        position=player.position,
        purchase_price=payload.purchasePrice,
        market_value=snapshot.market_value if snapshot is not None else None,
    )

    rules = _rules(session)
    members = get_squad_members(session)
    verdict = evaluate_add(members, candidate, rules)

    if not verdict.allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "rule": verdict.violation.rule,
                "actual": verdict.violation.actual,
                "limit": verdict.violation.limit,
                "message": verdict.violation.message,
            },
        )

    add_squad_member(session, player_id=player.id, purchase_price=payload.purchasePrice)

    return {"added": player.id, **_squad_payload(session)}


@router.delete("/squad/players/{player_id}")
def remove_player(player_id: int, session: SessionDep, salePrice: int | None = None):
    if salePrice is not None and salePrice < 0:
        raise HTTPException(
            status_code=409,
            detail={
                "rule": "sale_price",
                "actual": salePrice,
                "limit": 0,
                "message": (
                    "A sale price can't be negative — enter what you actually "
                    "received, or leave it blank to skip recording the sale."
                ),
            },
        )
    if not remove_squad_member(session, player_id=player_id, sale_price=salePrice):
        raise HTTPException(status_code=404, detail="Player is not in your squad")
    return _squad_payload(session)
