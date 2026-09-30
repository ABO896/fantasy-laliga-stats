"""Deep per-player season statistics (INGEST-06).

The page serves the **latest published** season, which is last season
while the current one is young — 2025/26 as of 2026-08-23, with no
current-season equivalent published at any address. The parser therefore
reads `seasonYear` out of the payload and stores under that key rather
than assuming the configured current season; when the source flips, this
follows with no code change.

Per D-01 last season's numbers are wanted regardless, so today's payload
is the desired outcome, not a degraded one.
"""

import json
from dataclasses import dataclass

from core.config import Settings, get_settings
from core.season_stats_schema import STAT_PAIRS, SUMMARY_FIELDS, column_name
from scraper.http import fetch_page
from scraper.sources.flight import find_key, find_records, iter_flight_chunks

SEASON_STATS_MARKERS: tuple[str, ...] = ("initialplayers",)

#: The site's `positionId` -> this project's normalized position enum.
_POSITION_ID_MAP = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL"}


@dataclass(frozen=True)
class SeasonStats:
    season_year: int
    records: list[dict]


def parse_season_stats(html: str) -> SeasonStats:
    rows = find_records(html, "initialPlayers", "totalPoints")
    if rows is None:
        raise ValueError(
            "No initialPlayers array found in the statistics page — the "
            "site's structure may have changed."
        )

    season_year = _season_year(html)

    records: list[dict] = []
    for row in rows:
        record: dict = {
            # `slug` is absent on 83 of 702 rows, and those rows are the
            # league's best players — Lamine Yamal, Mbappe, Vini Jr. This
            # parser therefore emits identity as-is and resolves nothing;
            # dropping a row here for a missing slug would delete exactly
            # the players that matter, silently. See Task 7.
            "slug": row.get("slug"),
            "nickname": row.get("nickname") or row.get("playerName") or "",
            "position": _POSITION_ID_MAP.get(row.get("positionId")),
            "team_name": row.get("teamName") or "",
            # positionId 5 / a populated coachId is a club coach, not a
            # fantasy player — the same filter the market scraper applies.
            "is_coach": row.get("positionId") == 5 or bool(row.get("coachId")),
            "raw": row,
        }
        for field in SUMMARY_FIELDS:
            record[column_name(field)] = row.get(field)
        for counter, points in STAT_PAIRS:
            record[column_name(counter)] = row.get(counter, 0)
            record[column_name(points)] = row.get(points, 0)
        records.append(record)

    return SeasonStats(season_year=season_year, records=records)


def _season_year(html: str) -> int:
    """The season the page declares. Verified 2026-08-23: this fixture
    declares 2025, i.e. last season — see the module docstring."""
    for chunk in iter_flight_chunks(html, must_contain="seasonYear"):
        season = find_key(chunk, "seasonYear")
        if isinstance(season, int):
            return season
    raise ValueError("No seasonYear found in the statistics page")


def fetch_season_stats(settings: Settings | None = None, season_year: int | None = None) -> str:
    """Fetch the statistics page. Bare, it serves the latest *published*
    season — which is last season while the current one is young, and
    flips to the current one once the site publishes it (observed: 2025 on
    2026-08-23, 2026 on 2026-08-27). `season_year` appends the path
    segment that pins a specific season, which is the only way to reach a
    past one after the site has moved on. Verified live 2026-08-27:
    `/estadisticas/2025` still serves all 702 of last season's rows.

    The caller must still check the season the *payload* declares — the
    segment is a request, not a guarantee. See `backfill_season`.
    """
    settings = settings or get_settings()
    url = settings.season_stats_url
    if season_year is not None:
        url = f"{url}/{season_year}"
    return fetch_page(url, SEASON_STATS_MARKERS, settings)


def to_raw_json(record: dict) -> str:
    """Verbatim payload for the table's `raw_fields` column."""
    return json.dumps(record["raw"], ensure_ascii=False)
