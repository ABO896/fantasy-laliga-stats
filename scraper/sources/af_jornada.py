"""Per-jornada points (INGEST-05), and the season/week addressing the
backfill walks (INGEST-08).

**The trap this module exists to defeat.** Requesting a jornada that has
not been played returns HTTP 200, echoes the requested week back in the
page's component props, and serves the *latest* jornada's players. A naive
`for week in 1..38` loop would write one jornada's points under thirty-seven
different jornada numbers, with no error and no bad status anywhere, and
every fixture-based test green.

The payload defends itself if asked correctly. `fantasyLiveInitialSnapshot`
carries `activeWeek` — the week actually served, which reports 2 when 38 was
requested — and `rounds`, the jornadas that exist. `props.week` is an echo of
the request and is never trusted; `activeWeek` is the source's own statement
of what it returned.

`rounds` also matters on its own: season 2025/26 lists **36** jornadas, not
38 — weeks 30 and 35 do not exist. Verified 2026-08-23.
"""

from dataclasses import dataclass

from core.config import Settings, get_settings
from scraper.http import fetch_page
from scraper.sources.flight import find_key, find_mapping, iter_flight_chunks

#: Lowercased structural fingerprint for `classify_response`.
JORNADA_MARKERS: tuple[str, ...] = ("fantasyliveinitialsnapshot",)

#: The site's `positionId` -> this project's normalized position enum, the
#: same mapping `analiticafantasy.py` uses. `positionId == 5` is a club
#: coach, not a fantasy player.
_POSITION_ID_MAP = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL"}


class JornadaFallback(ValueError):
    """The response is the site's fallback, not the requested jornada."""


@dataclass(frozen=True)
class JornadaSnapshot:
    season_year: int
    week: int
    rounds: tuple[int, ...]
    records: list[dict]


def _season_year(html: str) -> int:
    """Read the season the page declares.

    `fantasyLiveInitialSnapshot` does **not** carry `seasonYear` — verified
    against all three jornada fixtures. It lives in the component props in
    a different chunk, so this searches the decoded chunks. Do not try to
    `str.find` it in the raw HTML: the flight payload is JSON-escaped
    there, so the literal `"seasonYear":` never appears.
    """
    for chunk in iter_flight_chunks(html, must_contain="seasonYear"):
        season = find_key(chunk, "seasonYear")
        if isinstance(season, int):
            return season
    raise ValueError("No seasonYear found in the jornada page")


def parse_jornada(html: str, requested_week: int | None) -> JornadaSnapshot:
    """Parse one scores page. Pure over HTML — no network of its own.

    `requested_week=None` means "latest", which cannot be a fallback by
    definition. Any other value must equal `activeWeek` or this raises.
    """
    snapshot = find_mapping(html, "fantasyLiveInitialSnapshot", "activeWeek")
    if snapshot is None:
        raise ValueError(
            "No fantasyLiveInitialSnapshot found in the fetched page — the "
            "site's structure may have changed."
        )

    active_week = snapshot.get("activeWeek")
    if not isinstance(active_week, int):
        raise ValueError(f"activeWeek is missing or not an int: {active_week!r}")

    rounds = tuple(sorted(r["week"] for r in (snapshot.get("rounds") or []) if "week" in r))

    if requested_week is not None:
        if requested_week not in rounds:
            raise JornadaFallback(
                f"Jornada {requested_week} is not in this season's rounds {rounds!r} — "
                "it was never played, and the response is the site's fallback."
            )
        if active_week != requested_week:
            raise JornadaFallback(
                f"Requested jornada {requested_week} but the page served activeWeek "
                f"{active_week} — this is the site's fallback, not the jornada asked for."
            )

    # Keyed by slug so a player the source lists twice — once per club
    # registration, while a transfer is recent or pending — collapses to
    # one row. `PlayerGameweekPoints`'s key is (season_year, week,
    # player_id), so two rows for one player is not a duplicate to tidy up
    # later, it is an insert that fails. The market page's
    # `parse_points_predictions` already collapses the same way; here the
    # ranking field is `weekPoints`, since the registration he actually
    # played under is the one carrying the points. Slugless rows are never
    # collapsed — 31 real players carry no slug, and they are different
    # people, not repeats of each other.
    records: list[dict] = []
    index_by_slug: dict[str, int] = {}
    for player in snapshot.get("players") or []:
        points = player.get("weekPoints")
        if not isinstance(points, int):
            # Nothing to store for this row. Distinct from a missing slug,
            # which is common and must NOT cause a skip — see below.
            continue
        record = {
            # `slug` is absent for some players persistently — in
            # 2025/26 week 38 that is 31 real players, Bellingham and
            # Pepe among them, and it is absent in every week for the
            # same players. Emit identity as-is; Task 7 resolves by
            # (name, position) where the slug is missing. Skipping here
            # would delete real points silently.
            "slug": player.get("slug"),
            "player_name": player.get("playerName") or "",
            "position": _POSITION_ID_MAP.get(player.get("positionId")),
            "team_name": player.get("teamName") or "",
            "is_coach": player.get("positionId") == 5 or bool(player.get("coachId")),
            "points": points,
        }
        slug = record["slug"]
        if slug is not None and slug in index_by_slug:
            seen = index_by_slug[slug]
            if points > records[seen]["points"]:
                records[seen] = record
            continue
        if slug is not None:
            index_by_slug[slug] = len(records)
        records.append(record)

    return JornadaSnapshot(
        season_year=_season_year(html),
        week=active_week,
        rounds=rounds,
        records=records,
    )


def fetch_jornada(season_year: int, week: int | None, settings: Settings | None = None) -> str:
    """Fetch one scores page. `week=None` fetches the season's latest."""
    settings = settings or get_settings()
    url = f"{settings.jornada_base_url}/{season_year}"
    if week is not None:
        url = f"{url}/{week}"
    return fetch_page(url, JORNADA_MARKERS, settings)
