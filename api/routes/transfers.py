"""Phase 11 — bargains, our bids (MODEL-05) and transfer suggestions
(TRANSFER-01…05). All computed on read; the maths is `core/transfers.py`,
the loading `storage/transfers.py`.

The owner's price ceiling is BROWSE-05's, carried the same way: `max`
(euros) and `basis`, typed by the owner from the figure they read off the
official app. Nothing here derives a budget.
"""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from api.deps import SessionDep, SettingsDep, resolve_league_context
from core import transfers as tr
from storage.transfers import TransferContext, build_context

router = APIRouter()

Basis = Literal["marketValue", "idealBid", "maxBid", "ourIdealBid", "ourMaxBid"]
Position = Literal["POR", "DEF", "MED", "DEL"]

#: The source's fixture window holds five jornadas; more is accepted and
#: simply returns what exists.
MAX_JORNADAS = 38


def _r(x: float | None, n: int = 2) -> float | None:
    return round(x, n) if x is not None else None


def _fixture(f) -> dict:
    return {
        "matchday": f.matchday,
        "kickoffUtc": f.kickoff_utc.isoformat(),
        "kickoffConfirmed": f.kickoff_confirmed,
        "opponent": f.opponent,
        "isHome": f.is_home,
        "difficulty": _r(f.difficulty, 3),
        "label": tr.describe_fixture(f),
    }


def assessment_payload(a: tr.Assessment, owned: set[int] | None = None) -> dict:
    p = a.player
    return {
        "playerId": p.player_id,
        "name": p.name,
        "team": p.team,
        "position": p.position,
        "owned": p.player_id in owned if owned is not None else None,
        "marketValue": p.market_value,
        "availability": p.availability,
        "starterProbability": p.starter_probability,
        "recentJornadas": p.recent_jornadas,
        "powerScore": _r(p.power_score, 1),
        "economyScore": _r(p.economy, 1),
        "fairValue": p.fair_value,
        "valuationGapPct": _r(p.valuation_gap * 100, 1) if p.valuation_gap is not None else None,
        "predictedPct": _r(p.predicted_pct, 3),
        "predictionConfidence": p.prediction_confidence,
        "expectedReturn": _r(a.expected_return),
        "expectedPoints": p.expected_points,
        "expectedPointsUsed": a.expected_points_used,
        "backwardPpg": _r(p.backward_ppg),
        "minutesFactor": _r(a.minutes_factor, 3),
        "fixtureMultiplier": _r(a.fixture.multiplier, 3),
        "fixtureDataAvailable": a.fixture.available,
        "fixtures": [_fixture(f) for f in a.fixture.fixtures],
        "fixtureDriver": _fixture(a.fixture.driver) if a.fixture.driver else None,
        "efficiency": _r(a.efficiency, 3),
        "holdValue": _r(a.hold_value),
        "evidence": _r(a.evidence, 3),
        "bids": {
            "ourIdeal": a.bids.ideal,
            "ourMax": a.bids.maximum,
            "sourceIdeal": p.source_ideal_bid,
            "sourceMax": p.source_max_bid,
            "inputs": a.bids.inputs,
        },
    }


def _freshness(ctx: TransferContext) -> dict:
    f = ctx.freshness
    return {
        "confidence": f.factor,
        "label": tr.confidence_label(f.factor),
        "reasons": f.reasons,
        "datasets": [
            {
                "dataset": d.dataset,
                "lastSuccessAt": d.last_success_at.isoformat() if d.last_success_at else None,
                "ageDays": _r(d.age_days, 1),
                "factor": _r(d.factor, 3),
                "note": d.note,
            }
            for d in f.datasets
        ],
    }


def _envelope(ctx: TransferContext, ceiling: tr.Ceiling | None) -> dict:
    return {
        "serverTime": datetime.now(UTC).isoformat(),
        "asOf": ctx.as_of,
        "jornadas": {
            "requested": ctx.jornadas_requested,
            "window": ctx.window,
            "spreadOver": ctx.jornadas,
        },
        "ceiling": {"max": ceiling[0], "basis": ceiling[1]} if ceiling else None,
        "expectedPointsUsed": ctx.expected_points_used,
        "freshness": _freshness(ctx),
    }


def _ceiling(max_price: int | None, basis: str) -> tr.Ceiling | None:
    return (max_price, basis) if max_price is not None else None


def _context(session, settings, n: int) -> tuple[TransferContext, object]:
    rules = resolve_league_context(session).rules
    ctx = build_context(session, rules, settings.current_season_year, n, datetime.now(UTC))
    return ctx, rules


@router.get("/transfers/suggestions")
def suggestions(
    session: SessionDep,
    settings: SettingsDep,
    n: int = Query(tr.DEFAULT_JORNADAS, ge=1, le=MAX_JORNADAS),
    max: int | None = Query(None, ge=0),  # noqa: A002 — BROWSE-05's own param name
    basis: Basis = "marketValue",
    limit: int = Query(10, ge=1, le=30),
):
    """TRANSFER-01…04: ranked sell → buy moves (and adds for free slots),
    each legal by the squad-rules engine, with its signals and confidence."""
    ctx, rules = _context(session, settings, n)
    ceiling = _ceiling(max, basis)
    moves = tr.suggest_moves(ctx.members, ctx.assessments, rules, ceiling, ctx.freshness,
                             ctx.jornadas, limit=limit)
    owned = {m.player_id for m in ctx.members}
    unassessed = [m.name for m in ctx.members if m.player_id not in ctx.assessments
                  or ctx.assessments[m.player_id].hold_value is None]
    return {
        **_envelope(ctx, ceiling),
        "squadSize": len(ctx.members),
        "maxSquadSize": rules.max_squad_size,
        "unassessedMembers": unassessed,
        "moves": [
            {
                "kind": m.kind,
                "sell": assessment_payload(m.sell, owned) if m.sell else None,
                "buy": assessment_payload(m.buy, owned),
                "gain": _r(m.gain),
                "signals": [
                    {"name": s.name, "text": s.text, "contribution": _r(s.contribution)}
                    for s in m.signals
                ],
                "confidence": m.confidence,
                "confidenceLabel": m.confidence_label,
                "confidenceReasons": m.confidence_reasons,
                "feasibleFormations": list(m.feasible_formations),
            }
            for m in moves
        ],
    }


@router.get("/transfers/bargains")
def bargains(
    session: SessionDep,
    settings: SettingsDep,
    n: int = Query(tr.DEFAULT_JORNADAS, ge=1, le=MAX_JORNADAS),
    position: Position | None = None,
    max: int | None = Query(None, ge=0),  # noqa: A002
    basis: Basis = "marketValue",
    affordableOnly: bool = False,
    limit: int = Query(20, ge=1, le=100),
):
    """MODEL-05's bargains view: expected return high against price."""
    ctx, _ = _context(session, settings, n)
    ceiling = _ceiling(max, basis)
    owned = {m.player_id for m in ctx.members}
    rows = tr.bargains(ctx.assessments, ceiling, affordableOnly and ceiling is not None,
                       position, limit)
    return {
        **_envelope(ctx, ceiling),
        "affordableOnly": affordableOnly and ceiling is not None,
        "players": [
            {
                **assessment_payload(b.assessment, owned),
                "forwardFairValue": b.forward_fair_value,
                "forwardGapPct": _r(b.forward_gap * 100, 1),
            }
            for b in rows
        ],
    }


@router.get("/transfers/best")
def best(
    session: SessionDep,
    settings: SettingsDep,
    position: Position,
    n: int = Query(tr.DEFAULT_JORNADAS, ge=1, le=MAX_JORNADAS),
    max: int | None = Query(None, ge=0),  # noqa: A002
    basis: Basis = "marketValue",
    affordableOnly: bool = True,
    limit: int = Query(20, ge=1, le=100),
):
    """TRANSFER-05: the best players at a position by expected return.
    Affordable-only by default — which needs a ceiling; without one the
    response says so (`ceilingMissing`) and shows everyone."""
    ctx, _ = _context(session, settings, n)
    ceiling = _ceiling(max, basis)
    applied = affordableOnly and ceiling is not None
    owned = {m.player_id for m in ctx.members}
    rows = tr.best_for_position(ctx.assessments, position, ceiling, applied, limit)
    return {
        **_envelope(ctx, ceiling),
        "position": position,
        "affordableOnly": applied,
        "ceilingMissing": affordableOnly and ceiling is None,
        "players": [assessment_payload(a, owned) for a in rows],
    }


@router.get("/transfers/bids")
def bids(
    session: SessionDep,
    settings: SettingsDep,
    position: Position | None = None,
    limit: int = Query(50, ge=1, le=700),
):
    """MODEL-05: our ideal and maximum bid beside the source's, most
    valuable first."""
    ctx, _ = _context(session, settings, tr.DEFAULT_JORNADAS)
    rows = [a for a in ctx.assessments.values() if position is None or a.position == position]
    rows.sort(key=lambda a: (-a.player.market_value, a.player_id))
    return {
        "serverTime": datetime.now(UTC).isoformat(),
        "asOf": ctx.as_of,
        "freshness": _freshness(ctx),
        "players": [_bid_row(a) for a in rows[:limit]],
    }


def _bid_row(a: tr.Assessment) -> dict:
    p = a.player
    return {
        "playerId": p.player_id,
        "name": p.name,
        "team": p.team,
        "position": p.position,
        "marketValue": p.market_value,
        "availability": p.availability,
        "ourIdeal": a.bids.ideal,
        "ourMax": a.bids.maximum,
        "sourceIdeal": p.source_ideal_bid,
        "sourceMax": p.source_max_bid,
        "inputs": a.bids.inputs,
    }


@router.get("/transfers/bids/{player_id}")
def bid_for_player(player_id: int, session: SessionDep, settings: SettingsDep):
    ctx, _ = _context(session, settings, tr.DEFAULT_JORNADAS)
    a = ctx.assessments.get(player_id)
    if a is None:
        raise HTTPException(status_code=404, detail="No current snapshot for this player")
    return {"asOf": ctx.as_of, "freshness": _freshness(ctx), **_bid_row(a)}
