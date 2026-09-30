"""Fetcher + parser for analiticafantasy.com's `puja-ideal` player table.

Self-imposed access limits are documented in `docs/SCRAPING-POLICY.md` and
are binding on this module: an honest, identifying User-Agent, capped
retries with a terminal "blocked" outcome on 403/429 rather than retrying
into a block, no proxy rotation, and never a request under `/api/`.

**Full-roster extraction — a deviation from the originally-planned
click-through pagination (see 01-03-SUMMARY.md "Deviations"):** the
tracer's `<table>` only ever shows the current page of the site's
client-side, JS-driven pagination (10 rows by default), which is why
01-RESEARCH.md assumed a Playwright click-through loop (~37 pages at
10/page, or ~4 at 100/page) was required for the ~370-player roster. The
*same* page's embedded Next.js flight-data JSON (`initialPlayers`,
already read by `_extract_initial_players` for the tracer's team/
availability join) carries the **entire roster in one page load** —
verified directly against the live fixture: 361 total entries, of which
342 are real players (`positionId` 1-4) and 19 are club coaches
(`positionId` 5, not fantasy players, filtered out). Parsing directly from
this JSON instead of clicking through "Siguiente"/raising "Filas por
página" is strictly better: one page load instead of ~4-37, every field
already typed (ints/floats, no locale string-parsing needed), and a
smaller footprint against `docs/SCRAPING-POLICY.md`'s self-imposed access
limits. `fetch_pages` still returns a `list[str]` (rather than a bare
string) so the multi-page contract stays available if a future source, or
a structural change to this one, ever requires real pagination again.
"""

import json
import random
import time

from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import Settings, get_settings
from core.parsing import normalize_availability
from scraper.errors import (
    ScrapeBlocked,
    ScrapeNetworkError,
    ScrapeStructureChanged,
    classify_response,
)
from scraper.sources.flight import _FLIGHT_REF_PREFIX_RE, _NEXT_F_PUSH_RE, find_key

# The site's `positionId` -> this project's normalized position enum.
# `positionId == 5` is a club coach, not a fantasy player — verified by
# cross-referencing several `positionId == 5` entries directly: they carry
# a populated `coachId` and a `null` `id`, unlike every real player entry.
_POSITION_ID_MAP = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL"}

# Jitter bounds for the pre-navigation delay applied in `fetch_pages` —
# see that function's own comment for why the sleep lives there and not
# inside `_goto`.
_MIN_NAV_DELAY_SECONDS = 0.5
_MAX_NAV_DELAY_SECONDS = 2.0


@retry(
    # Only a transport/timeout failure is worth retrying — `ScrapeBlocked`
    # and `ScrapeStructureChanged` are terminal (PITFALLS.md Pitfall 2;
    # docs/SCRAPING-POLICY.md's "never retry into a block" rule). Retrying
    # a block only makes it worse; retrying a redesigned page won't make
    # it parse.
    retry=retry_if_exception_type(ScrapeNetworkError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _goto(page, url: str) -> str:
    """Navigate to `url` and return its rendered HTML, classifying the
    response before returning. Raises the specific `ScrapeError` subclass
    `classify_response` names, or returns the HTML when the response looks
    healthy."""
    try:
        response = page.goto(url, wait_until="networkidle", timeout=30_000)
    except PlaywrightError as exc:
        raise ScrapeNetworkError(str(exc)) from exc

    status = response.status if response is not None else None
    try:
        page.wait_for_selector("table tbody tr", timeout=15_000)
    except PlaywrightError:
        # A missing table isn't necessarily a network failure — let
        # `classify_response` decide from status + whatever HTML we got
        # (e.g. a challenge page never renders a `<table>` at all).
        pass

    html = page.content()
    error_type = classify_response(status, html)
    if error_type is ScrapeBlocked:
        raise ScrapeBlocked(f"Blocked by target site: HTTP {status}")
    if error_type is ScrapeStructureChanged:
        raise ScrapeStructureChanged("Expected player table/data not found in response")
    return html


def fetch_pages(settings: Settings | None = None, max_pages: int | None = None) -> list[str]:
    """Fetch the `puja-ideal` page with Playwright.

    A single page load already carries the full roster in its embedded
    flight-data JSON (see module docstring) — no pagination loop is
    needed. `max_pages` is accepted for interface stability only; it has
    no effect while this fetch is inherently single-page.
    """
    settings = settings or get_settings()
    # Jittered delay before navigation, per docs/SCRAPING-POLICY.md's "no
    # fixed, machine-cadence timing" rule. Applied here (not inside
    # `_goto`) so unit tests exercising `_goto`/retry-classification
    # directly don't pay a real sleep.
    time.sleep(random.uniform(_MIN_NAV_DELAY_SECONDS, _MAX_NAV_DELAY_SECONDS))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=settings.user_agent)
            html = _goto(page, settings.scrape_target_url)
        finally:
            browser.close()
    return [html]


def _extract_initial_players(html: str) -> dict[str, dict]:
    """Extract the `initialPlayers` array embedded in the page's Next.js
    flight-data payload, keyed by player slug.

    This is the same page's own hydration data — reading it costs no
    extra network request. It carries every field this module needs
    (price, points, price change, team, availability, starter chance,
    next opponent) for the *entire* roster, not just the rendered
    `<table>`'s current page.
    """
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script"):
        text = script.string
        if not text or "self.__next_f.push(" not in text or "initialPlayers" not in text:
            continue

        match = _NEXT_F_PUSH_RE.search(text.strip())
        if not match:
            continue
        try:
            outer = json.loads(match.group(1))
            payload_str = outer[1]
            ref_match = _FLIGHT_REF_PREFIX_RE.match(payload_str)
            inner = ref_match.group(1) if ref_match else payload_str
            data = json.loads(inner)
        except (json.JSONDecodeError, IndexError, TypeError):
            continue

        players = find_key(data, "initialPlayers")
        if players:
            return {p["slug"]: p for p in players if p.get("slug")}

    return {}


def parse_page(html: str) -> list[dict]:
    """Parse one fetched page's embedded roster JSON into one dict per
    player.

    Pure function over HTML — no network I/O of its own — so it is
    testable against a saved fixture. Reads the full `initialPlayers`
    array directly (see module docstring), not the rendered `<table>`,
    since the table only ever exposes its current 10-row page.
    """
    players = _extract_initial_players(html)
    if not players:
        raise ValueError(
            "No initialPlayers JSON found in the fetched page — the "
            "site's structure may have changed."
        )

    records = []
    for slug, p in players.items():
        position = _POSITION_ID_MAP.get(p.get("positionId"))
        if position is None:
            # positionId 5 (club coaches) and any other unrecognized value
            # are a legitimate, expected part of this payload — not a
            # parse failure, just not fantasy players. Skip, don't raise.
            continue

        club = p.get("club") or {}
        team = club.get("name")
        if not team:
            # Fail loud rather than silently write a NULL team into a NOT
            # NULL column (T-02-03) — a missing team here means the
            # embedded JSON's shape has drifted from what this parser
            # expects, not a value worth guessing at.
            raise ValueError(f"Player {slug!r} has no club/team in embedded JSON")

        raw_status = p.get("status")
        availability_status = normalize_availability(raw_status) if raw_status else "available"
        next_fixture = p.get("nextFixture") or {}
        chance = p.get("chance")

        records.append(
            {
                "external_id": slug,
                "name": p["name"],
                "team": team,
                "position": position,
                "points": p.get("points", 0),
                "ideal_bid": p.get("pujaIdeal"),
                "max_bid": p.get("pujaMaxima"),
                "price_change_abs": p.get("subida"),
                "price_change_pct": p.get("percentIncreased"),
                "market_value": p["marketValue"],
                "next_opponent": next_fixture.get("rivalName"),
                "starter_probability": float(chance) if chance is not None else None,
                "availability_status": availability_status,
            }
        )

    return records
