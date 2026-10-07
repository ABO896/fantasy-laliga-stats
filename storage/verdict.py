"""Live verdicts, the personal line, and the validation report — read-time
shaping for the API (Plan C, Task 5).

`live_verdicts` is the one place a request computes `core.verdict.verdicts`
over `storage.inputs.compute_live_inputs` — every route that needs a verdict
calls this once and reuses the result, never `compute_live_inputs` directly,
so a request with several verdict-bearing sections (the player list, a
player's own page, the squad) never loads the database's input tables twice.

`player_verdict_payload` additionally builds the personal line
(`core.personal.personal_line`) against the owner's current squad, and
looks up what the walk-forward harness (`storage/verdict_backtest.py`) found
for that label, if a report has been stored. The squad's formation rules
are resolved the same way `api.deps.resolve_league_context` resolves them
for every other squad-aware route — narrowed by the league's own
`premium_formations_enabled` setting — without this module importing the
API layer: `storage/` only ever reaches down into `core/`.
"""

import json
from collections.abc import Mapping

from sqlmodel import Session, select

from core.inputs import PlayerInputs
from core.personal import Candidate, PersonalLine, SquadEntry, personal_line
from core.rules import Rules, load_rules
from core.verdict import DISABLED_LABELS, Verdict, verdicts
from storage.inputs import compute_live_inputs
from storage.models import ModelReport, Player
from storage.repository import get_league_settings, get_squad_members
from storage.verdict_backtest import REPORT_NAME

#: Plan B's default look-ahead window — the same horizon
#: `storage.inputs.LIVE_HORIZON` feeds `compute_live_inputs`.
HORIZON = 3
_UNAVAILABLE = frozenset({"injured", "suspended"})


def live_verdicts(
    session: Session, inputs: dict[int, PlayerInputs] | None = None
) -> tuple[dict[int, PlayerInputs], dict[int, Verdict]]:
    """Every player's current inputs and verdict. Pass `inputs` (from an
    earlier `compute_live_inputs` call this same request already made) to
    avoid loading the database a second time; omitted, this loads it once."""
    if inputs is None:
        inputs = compute_live_inputs(session)
    return inputs, verdicts(inputs, disabled=DISABLED_LABELS)


def verdict_fields(v: Verdict | None) -> dict:
    """The compact `verdict` block the player list and squad payloads carry."""
    if v is None:
        return {"verdict": None}
    return {"verdict": {"label": v.label, "tags": list(v.tags), "confidence": v.confidence}}


def _xpts(i: PlayerInputs | None) -> float:
    return i.xpts.total if i is not None and i.xpts is not None else 0.0


def _eligible(i: PlayerInputs) -> bool:
    return i.availability not in _UNAVAILABLE and i.evidence.ok


def _league_rules(session: Session) -> Rules:
    settings = get_league_settings(session)
    return load_rules().for_league(settings.premium_formations_enabled)


def _squad_entries(squad, inputs: Mapping[int, PlayerInputs]) -> list[SquadEntry]:
    return [
        SquadEntry(m.player_id, m.name, m.position, _xpts(inputs.get(m.player_id)),
                   m.effective_value)
        for m in squad
    ]


def _pool(
    session: Session, inputs: Mapping[int, PlayerInputs], owned_ids: set[int]
) -> list[Candidate]:
    names = dict(session.exec(select(Player.id, Player.name)).all())
    return [
        Candidate(pid, names[pid], i.position, _xpts(i), i.price, _eligible(i))
        for pid, i in inputs.items()
        if pid not in owned_ids and pid in names
    ]


def _personal_payload(line: PersonalLine | None) -> dict | None:
    if line is None:
        return None
    return {
        "kind": line.kind,
        "text": line.text,
        "gain": line.gain,
        "cost": line.cost,
        "otherPlayerId": line.other_player_id,
        "otherName": line.other_name,
        "overCeilingBy": line.over_ceiling_by,
    }


def validation_report(session: Session) -> dict:
    """The stored walk-forward report, or the documented empty shape when
    the harness has never been run with `--write` — plus `disabledLabels`,
    the labels live verdicts skip right now (the stored report's own
    `disabled` records what that run used)."""
    row = session.get(ModelReport, REPORT_NAME)
    report = {"generatedAt": None, "labels": []} if row is None else json.loads(row.payload)
    return {**report, "disabledLabels": sorted(DISABLED_LABELS)}


def _validation_for_label(session: Session, label: str) -> dict | None:
    for entry in validation_report(session).get("labels", []):
        if entry.get("label") == label:
            return {
                "label": entry["label"],
                "beatsChance": entry["beatsChance"],
                "hitRate": entry["hitRate"],
                "n": entry["n"],
            }
    return None


def player_verdict_payload(
    session: Session, player_id: int, ceiling: int | None = None
) -> dict | None:
    """`None` for an unknown player (or one `compute_live_inputs` has no
    inputs for) — the route turns that into a 404. `personal` is `None` when
    the owner's squad is empty, per `core.personal.personal_line`."""
    player = session.get(Player, player_id)
    if player is None:
        return None

    inputs, vmap = live_verdicts(session)
    i = inputs.get(player_id)
    v = vmap.get(player_id)
    if i is None or v is None:
        return None

    squad = get_squad_members(session)
    squad_entries = _squad_entries(squad, inputs)
    owned_ids = {m.player_id for m in squad}
    pool = _pool(session, inputs, owned_ids)
    target = Candidate(player_id, player.name, i.position, _xpts(i), i.price, _eligible(i))

    line = personal_line(target, v, squad_entries, pool, _league_rules(session), HORIZON, ceiling)

    return {
        "playerId": player_id,
        "label": v.label,
        "tags": list(v.tags),
        "reason": v.reason,
        "confidence": v.confidence,
        "deciding": v.deciding,
        "disabledLabels": sorted(DISABLED_LABELS),
        "personal": _personal_payload(line),
        "validation": _validation_for_label(session, v.label),
    }
