"""Loads the official LaLiga Fantasy rules from versioned data.

Every cap, quota and formation the app enforces originates here and nowhere
else. The prose source of truth — including the provenance of each value and
the dated change log — is `docs/RULES-LALIGA-FANTASY.md`; this module reads
its machine-readable twin, `core/rules_data/laliga_fantasy.json`.

A mid-season rules change is therefore a reviewable commit touching both
files together, never a constant edited somewhere in validation code.
"""

import json
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

POSITIONS: tuple[str, ...] = ("POR", "DEF", "MED", "DEL")

RULES_FILE = Path(__file__).resolve().parent / "rules_data" / "laliga_fantasy.json"


@dataclass(frozen=True)
class Violation:
    """A broken rule, with everything needed to explain and fix it.

    Lives here rather than in either engine because both `core.squad_rules`
    and `core.lineup_rules` emit it and LN-23 forbids the lineup engine
    importing from the squad engine. `actual` and `limit` stay
    machine-readable for the UI; `message` is the sentence shown to the
    owner, and the API returns this shape verbatim as a 409 `detail`.
    """

    rule: str
    actual: float
    limit: float
    message: str


@dataclass(frozen=True)
class Formation:
    """One legal starting XI shape. `name` is written DEF-MED-DEL; the
    goalkeeper is implicit in the official notation but explicit here.

    `premium` marks the five shapes that exist only in a Premium league whose
    admin has the feature switched on — a property of the owner's league, not
    of the game.
    """

    name: str
    POR: int
    DEF: int
    MED: int
    DEL: int
    premium: bool

    def required(self) -> dict[str, int]:
        return {"POR": self.POR, "DEF": self.DEF, "MED": self.MED, "DEL": self.DEL}


@dataclass(frozen=True)
class Rules:
    source_url: str
    retrieved_on: str
    max_squad_size: int
    debt_limit_fraction: float
    cash_per_point: int
    formations: tuple[Formation, ...]

    def for_league(self, premium_enabled: bool) -> "Rules":
        """Narrow the formation set to what the owner's league actually allows.

        Resolved once, here at the boundary, so no engine function needs a
        `premium` parameter and no caller can forget to pass one.
        """
        if premium_enabled:
            return self
        return replace(self, formations=tuple(f for f in self.formations if not f.premium))

    def min_squad_for_any_xi(self) -> dict[str, int]:
        """Per position, the fewest players that could possibly appear in any
        legal XI. A squad below this in some position cannot field anything.

        Call this on an already-narrowed `Rules` — with premium formations
        included the answer changes materially (`4-6-0` needs no forward at
        all), which is exactly why narrowing happens first.
        """
        return {
            position: min(f.required()[position] for f in self.formations) for position in POSITIONS
        }


def find_formation(rules: Rules, name: str) -> Formation | None:
    """The named formation, or `None` when this rule set does not contain it.

    Lives here because two callers need it against *different* rule sets: the
    engine looks the owner's choice up in the league-narrowed set to decide
    whether it may be saved, while the squad surface looks the *stored*
    formation up in the full set so a shape that predates the league turning
    premium formations off can still be drawn.
    """
    return next((f for f in rules.formations if f.name == name), None)


@lru_cache(maxsize=1)
def load_rules() -> Rules:
    """Every formation, standard and premium. Callers narrow with
    `for_league()` — they must not filter by hand."""
    raw = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    formations = tuple(
        Formation(
            name=f["name"],
            POR=f["POR"],
            DEF=f["DEF"],
            MED=f["MED"],
            DEL=f["DEL"],
            premium=f["premium"],
        )
        for f in raw["formations"]
    )
    return Rules(
        source_url=raw["source_url"],
        retrieved_on=raw["retrieved_on"],
        max_squad_size=raw["max_squad_size"],
        debt_limit_fraction=raw["debt_limit_fraction"],
        cash_per_point=raw["cash_per_point"],
        formations=formations,
    )
