"""The source site's own model outputs (INGEST-07), stored as reference
fields only — never presented as this app's output.

Two pages, two very different shapes.

`/predicciones` returns `players[]`, one row per player per fixture, with
`predictedPoints`. **The first `"players"` key in tree order is not the
data** — it is the i18n string `"players": "Jugadores"`; the 492-row
array is the *second* `"players"` key. A plain first-match search returns
that string and breaks the parser, so the validating search in
`find_records` is still required — but here it does its work by
rejecting a string via `isinstance(value, list)`, not by choosing between
two competing arrays.

The 492 rows are not 492 distinct players: `SourcePrediction`'s primary
key is `(as_of, source, player_id)`, one row per player per day, but a
player with a recent or pending transfer is listed once per club
registration — same `fixtureId`, same `predictedPoints`, differing
`playerTeamId` and `chance`. Adding `fixtureId` to the key would not help,
since it is identical across the duplicate rows; only `chance`
distinguishes the live registration (nonzero) from the vacated one
(`chance: 0`). `parse_points_predictions` therefore collapses to one
record per player, keeping the highest-`chance` row and tie-breaking on
the highest `predictedPoints`.

`/prediccion-de-mercado` returns four separate lists with abbreviated
keys, and some rows carry neither `id` nor `slug`. Those cannot be joined
to a player; they are skipped and counted. A list can also be absent
entirely — nothing in the payload distinguishes "the site dropped this
list" from "there are none today" (`posiblesCambiosALaBaja` legitimately
carries a single row), so a missing list is reported, not raised on;
only all four missing is treated as a structural failure.
"""

import json

from core.config import Settings, get_settings
from scraper.http import fetch_page
from scraper.sources.flight import find_records

POINTS_MARKERS: tuple[str, ...] = ("predictedpoints",)
MARKET_MARKERS: tuple[str, ...] = ("topsubidas",)

#: The market page's list keys -> this project's `SourcePrediction.source`.
_MARKET_LISTS: tuple[tuple[str, str], ...] = (
    ("topSubidas", "market_top_risers"),
    ("topBajadas", "market_top_fallers"),
    ("posiblesCambiosAlAlza", "market_possible_risers"),
    ("posiblesCambiosALaBaja", "market_possible_fallers"),
)


#: Every `SourcePrediction.source` this module's market parser can emit.
#: `replace_predictions` deletes by source, and must be told all four even
#: when a list is empty today — see its docstring.
MARKET_SOURCES: frozenset[str] = frozenset(source for _, source in _MARKET_LISTS)


def _rank(row: dict) -> tuple[float, float]:
    """Sort key for choosing between duplicate registrations of the same
    player. `chance` (probability of featuring for that club) separates
    the live registration from the vacated one; `predictedPoints` breaks
    a tie when `chance` is equal."""
    return (row.get("chance") or 0, row.get("predictedPoints") or 0)


def parse_points_predictions(html: str) -> tuple[list[dict], int]:
    rows = find_records(html, "players", "predictedPoints")
    if rows is None:
        raise ValueError(
            "No predictedPoints array found in the predictions page — the "
            "site's structure may have changed."
        )

    best: dict[str, dict] = {}
    skipped = 0
    for row in rows:
        slug = row.get("slug")
        value = row.get("predictedPoints")
        if not slug or value is None:
            skipped += 1
            continue
        candidate = {
            "external_id": slug,
            "source": "points",
            "value": float(value),
            "raw": row,
        }
        current = best.get(slug)
        if current is None or _rank(row) > _rank(current["raw"]):
            best[slug] = candidate
    return list(best.values()), skipped


def parse_market_predictions(html: str) -> tuple[list[dict], int, frozenset[str]]:
    """Parse the market-prediction page's four lists.

    Returns `(records, skipped, found_sources)` — `found_sources` is the
    subset of the four `source` labels whose list was actually present in
    this payload. A quiet market day can legitimately empty any one of
    the four lists (there is nothing in the payload to tell "the site
    dropped this list" apart from "there are none today"), so a missing
    list is reported here rather than raised on. Only all four missing
    raises `ValueError`, since that is a structural failure no plausible
    market day produces.
    """
    records: list[dict] = []
    skipped = 0
    found_sources: set[str] = set()

    for key, source in _MARKET_LISTS:
        rows = find_records(html, key, "n")
        if rows is None:
            continue
        found_sources.add(source)
        for row in rows:
            slug = row.get("slug")
            value = row.get("su")
            if not slug or value is None:
                # The page publishes some entries without an id or slug.
                # Nothing can be joined to them; count, do not guess.
                skipped += 1
                continue
            records.append(
                {
                    "external_id": slug,
                    "source": source,
                    "value": float(value),
                    "raw": row,
                }
            )

    if not found_sources:
        raise ValueError(
            "None of the four market-prediction lists were found — the "
            "site's structure may have changed."
        )
    return records, skipped, frozenset(found_sources)


def fetch_points_predictions(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return fetch_page(settings.points_prediction_url, POINTS_MARKERS, settings)


def fetch_market_predictions(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return fetch_page(settings.market_prediction_url, MARKET_MARKERS, settings)


def to_raw_json(record: dict) -> str:
    return json.dumps(record["raw"], ensure_ascii=False)
