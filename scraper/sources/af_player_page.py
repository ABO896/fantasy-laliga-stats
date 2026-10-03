"""One player's page: daily market values and per-jornada match rows for
his whole season, in a single fetch.

Unlike the jornada scraper, there is no activeWeek trap here — the page
carries the player's complete `marketHistory` and `statsRows` every time,
so one fetch fills every gap he has. Selection (`core/player_pages.py`)
decides *who* gets fetched; this module only parses what comes back.
"""

from dataclasses import dataclass
from datetime import date
from urllib.parse import quote

from core.config import Settings, get_settings
from scraper.http import fetch_page
from scraper.sources.flight import find_records

#: Lowercased structural fingerprint for `classify_response`, which matches
#: markers against the response body lowercased — see `af_jornada.py`'s
#: `JORNADA_MARKERS` for the same convention.
PLAYER_PAGE_MARKERS: tuple[str, ...] = ("markethistory",)


@dataclass(frozen=True)
class DailyValue:
    day: date
    market_value: int
    delta: int | None


@dataclass(frozen=True)
class MatchRow:
    week: int
    minutes: int
    points: int
    components: dict  # the source's `stats` dict, verbatim ({} when he didn't play)


@dataclass(frozen=True)
class PlayerPage:
    market: list[DailyValue]  # oldest first
    matches: list[MatchRow]  # week ascending


def player_page_url(slug: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return settings.player_page_url_template.format(slug=quote(slug, safe="-"))


def fetch_player_page(slug: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    url = player_page_url(slug, settings)
    return fetch_page(
        url,
        PLAYER_PAGE_MARKERS,
        settings,
        min_delay=settings.player_pages_min_delay_seconds,
        max_delay=settings.player_pages_max_delay_seconds,
    )


def _int(value) -> int:
    """`value` if it is a real int — not a bool, not null, not a float."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"expected an int, got {value!r}")
    return value


def _daily_value(r: dict) -> DailyValue:
    delta = r.get("delta")
    return DailyValue(
        day=date.fromisoformat(r["date"]),
        market_value=_int(r["marketValue"]),
        delta=None if delta is None else _int(delta),
    )


def _match_row(r: dict) -> MatchRow:
    components = r.get("stats") or {}
    if not isinstance(components, dict):
        raise TypeError(f"expected a stats dict, got {components!r}")
    return MatchRow(
        week=_int(r["week"]),
        minutes=_int(r["minutes"]),
        points=_int(r["points"]),
        components=components,
    )


def _rows(records: list, build, key: str) -> list:
    """Build every row, turning any per-row shape error into one
    `ValueError` — `find_records` vets only the first row, so a later row
    missing a field (or carrying a null) must still read as a malformed
    page, which the refresh records as a gap, not a crash."""
    out = []
    for i, r in enumerate(records):
        try:
            if not isinstance(r, dict):
                raise TypeError(f"expected a dict, got {type(r).__name__}")
            out.append(build(r))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"malformed player page: {key}[{i}]: {type(exc).__name__}: {exc}"
            ) from exc
    return out


def parse_player_page(html: str) -> PlayerPage:
    """Parse one player's page. Pure over HTML — no network of its own.

    Raises `ValueError` when there is no `marketHistory`, or when any row of
    `marketHistory` / `statsRows` lacks a field or carries the wrong type
    (`minutes`, `points`, `week`, `marketValue` must be ints; a null
    `minutes` is malformed, not "did not play")."""
    market_records = find_records(html, "marketHistory", "marketValue")
    if market_records is None:
        raise ValueError("no marketHistory in player page")
    market = sorted(_rows(market_records, _daily_value, "marketHistory"), key=lambda m: m.day)

    # `statsRows` may be absent early in a season, before the player's
    # first jornada — not an error, just no matches yet.
    match_records = find_records(html, "statsRows", "minutes") or []
    matches = sorted(_rows(match_records, _match_row, "statsRows"), key=lambda m: m.week)

    return PlayerPage(market=market, matches=matches)
