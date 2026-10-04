"""Fetcher + parser for analiticafantasy.com's `calendario-predictor`
fixture calendar (INGEST-04).

Restored 2026-09-27 for TRANSFER-03's fixture difficulty and Phase 10's
expected-points model, after being deleted with the lineup cut (commit
`1d9e52f`). Lineup deadlines were its only reader then; they are not a
reader now.

**No Playwright.** The page is CDN-prerendered and carries its whole
payload in the server-rendered HTML, so one `httpx` GET through the shared
policy-compliant `scraper.http.fetch_page` is sufficient.

**Where the data actually is.** The fixtures are embedded in the page's
flight data as one *team-fixture cell* per team per window slot:

    {"matchday": {"matchday": 1, "round": "Regular Season - 6",
                  "fixtureId": 100011981,
                  "fixtureDate": "2026-09-16T19:30:00+00:00",
                  "opponentId": 4665, "opponentName": "Racing Santander",
                  "isHome": true, "difficulty": "very_easy",
                  "isFinal": true, ...},
     "teamId": 529, "teamName": "Barcelona"}

Twenty teams over the source's rolling five-slot window gives 100 cells
and 50 distinct fixtures — every fixture appears twice, once from each
side. What drives this module's shape:

  * **`matchday.matchday` is the window slot (1..5), not the jornada.**
    The jornada is the number at the end of `round`. The two coincided in
    the 2026-08-08 capture — the season's first five jornadas filled the
    first five slots — and the original parser read the slot. By September
    slot 1 held jornada 6. Found by the re-probe of 2026-09-27.
  * `difficulty` is *that team's* view of the fixture and differs by side,
    so it is recorded per side, never once. It is the source's own derived
    label and is kept as a reference field only (SCRAPING-POLICY, Data
    handling); this project's own difficulty is `core/fixture_difficulty.py`.
  * The two cells disagree about naming ("Atlético de Madrid" as subject,
    "Atletico Madrid" as opponent). The *opponent* spelling is the one the
    market scrape writes to `Player.team`, so it is the one stored — every
    reader joins fixtures to players on that name. The source's own team
    ids are stored too, as the stable key should the spellings drift.

The parse anchors on `{"matchday":{"matchday":` — a property of the data —
and brace-matches over each raw flight payload string, so it does not
depend on the build-generated component name (`"$La2"`) nor on the
hexadecimal, per-deploy chunk id prefix (see `scraper/sources/flight.py`).
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime

from bs4 import BeautifulSoup

from core.config import Settings, get_settings
from core.seasons import season_of
from scraper.http import fetch_page

_NEXT_F_PUSH_RE = re.compile(r"self\.__next_f\.push\((\[.*\])\)\s*$", re.S)

#: Anchors the brace-match onto the data's own shape rather than onto the
#: build-generated component name that renders it. See module docstring.
_CELL_ANCHOR = '{"matchday":{"matchday":'

#: "Regular Season - 6" -> 6. Anchored on the trailing number only, so a
#: relabelled prefix still parses.
_ROUND_NUMBER_RE = re.compile(r"(\d+)\s*$")

#: A data-only field name that never appears in the page's i18n tables —
#: the structural fingerprint `classify_response` checks for.
CALENDAR_MARKERS: tuple[str, ...] = ("fixturedate",)

#: Below this many distinct kickoff times across a jornada's fixtures, the
#: times are LaLiga placeholders rather than scheduled kickoffs. Three
#: rather than two so a jornada thinned by postponements still reads as
#: confirmed; a genuinely scheduled jornada has nine or ten.
DISTINCT_KICKOFF_CONFIRMED_THRESHOLD = 3


@dataclass(frozen=True)
class FixtureRecord:
    """One match, from both sides. `kickoff_utc` is timezone-aware UTC.
    `matchday` is the real jornada. Team names are market vocabulary."""

    fixture_id: int
    matchday: int
    season_year: int
    kickoff_utc: datetime
    kickoff_confirmed: bool
    is_final: bool
    home_team: str
    away_team: str
    home_team_id: int | None
    away_team_id: int | None
    home_difficulty: str | None
    away_difficulty: str | None


def fetch_calendar(settings: Settings | None = None) -> str:
    """Fetch the calendar page's HTML. One request, no browser."""
    settings = settings or get_settings()
    return fetch_page(settings.calendar_target_url, CALENDAR_MARKERS, settings)


def _flight_payloads(html: str) -> list[str]:
    """Every `self.__next_f.push([1, "<payload>"])` payload string, unescaped
    by `json.loads` so the cells inside can be brace-matched as plain JSON.
    Deliberately *not* `flight.iter_flight_chunks`: that decodes each payload
    as a whole JSON document, and the cells live inside React element arrays
    whose payloads are not always standalone JSON."""
    soup = BeautifulSoup(html, "lxml")
    payloads: list[str] = []
    for script in soup.find_all("script"):
        text = script.string
        if not text or "self.__next_f.push(" not in text:
            continue
        match = _NEXT_F_PUSH_RE.search(text.strip())
        if not match:
            continue
        try:
            outer = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if len(outer) > 1 and isinstance(outer[1], str):
            payloads.append(outer[1])
    return payloads


def _objects_at(text: str, anchor: str) -> list[dict]:
    """Every JSON object beginning at an `anchor` occurrence, found by
    brace-matching. String-aware, so a brace inside a team name or an
    escaped quote cannot end the object early."""
    found: list[dict] = []
    for match in re.finditer(re.escape(anchor), text):
        start = match.start()
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        found.append(json.loads(text[start : index + 1]))
                    except json.JSONDecodeError:
                        pass
                    break
    return found


def _jornada(fixture: dict) -> int:
    label = fixture.get("round")
    match = _ROUND_NUMBER_RE.search(label) if isinstance(label, str) else None
    if match is None:
        raise ValueError(
            f"fixture {fixture.get('fixtureId')}: no jornada number in round {label!r} — "
            "the calendar payload's structure may have changed"
        )
    return int(match.group(1))


def parse_calendar(html: str) -> list[FixtureRecord]:
    """Parse one fetched calendar page into one record per distinct fixture.

    Pure function over HTML — no network I/O — so it is testable against a
    saved capture and against hand-built payloads.
    """
    cells: list[dict] = []
    for payload in _flight_payloads(html):
        for cell in _objects_at(payload, _CELL_ANCHOR):
            fixture = cell.get("matchday")
            if isinstance(fixture, dict) and fixture.get("fixtureId") is not None:
                cells.append(cell)

    if not cells:
        raise ValueError(
            "No fixture data found in the fetched calendar page — the site's "
            "structure may have changed."
        )

    # Market-vocabulary name per source team id, learned from every cell in
    # which that team is the opponent.
    market_name: dict[int, str] = {}
    for cell in cells:
        fixture = cell["matchday"]
        if fixture.get("opponentId") is not None and fixture.get("opponentName"):
            market_name[int(fixture["opponentId"])] = fixture["opponentName"]

    # Group the two per-team views of each match back together. Keyed by
    # side, so a repeated cell for the same side collapses rather than
    # duplicating the fixture.
    sides: dict[int, dict[bool, dict]] = {}
    jornada_of: dict[int, int] = {}
    for cell in cells:
        fixture = cell["matchday"]
        fixture_id = int(fixture["fixtureId"])
        sides.setdefault(fixture_id, {})[bool(fixture["isHome"])] = cell
        jornada_of[fixture_id] = _jornada(fixture)

    # Confirmation is a property of the whole jornada, so it can only be
    # decided once every fixture in it has been seen.
    kickoffs_by_jornada: dict[int, set[str]] = {}
    for fixture_id, by_side in sides.items():
        known = by_side.get(True) or by_side.get(False)
        kickoffs_by_jornada.setdefault(jornada_of[fixture_id], set()).add(
            known["matchday"]["fixtureDate"]
        )
    confirmed = {
        jornada
        for jornada, times in kickoffs_by_jornada.items()
        if len(times) >= DISTINCT_KICKOFF_CONFIRMED_THRESHOLD
    }

    records: list[FixtureRecord] = []
    for fixture_id, by_side in sides.items():
        home_cell = by_side.get(True)
        away_cell = by_side.get(False)
        fixture = (home_cell or away_cell)["matchday"]

        if home_cell is not None:
            home_id = home_cell.get("teamId")
            away_id = home_cell["matchday"].get("opponentId")
        else:
            home_id = away_cell["matchday"].get("opponentId")
            away_id = away_cell.get("teamId")

        def _name(team_id, subject_cell, opponent_cell) -> str:
            if team_id is not None and int(team_id) in market_name:
                return market_name[int(team_id)]
            if opponent_cell is not None:
                return opponent_cell["matchday"]["opponentName"]
            return subject_cell["teamName"]

        kickoff_utc = datetime.fromisoformat(fixture["fixtureDate"])
        records.append(
            FixtureRecord(
                fixture_id=fixture_id,
                matchday=jornada_of[fixture_id],
                season_year=season_of(kickoff_utc),
                kickoff_utc=kickoff_utc,
                kickoff_confirmed=jornada_of[fixture_id] in confirmed,
                is_final=any(
                    bool(c["matchday"].get("isFinal")) for c in (home_cell, away_cell) if c
                ),
                home_team=_name(home_id, home_cell, away_cell),
                away_team=_name(away_id, away_cell, home_cell),
                home_team_id=int(home_id) if home_id is not None else None,
                away_team_id=int(away_id) if away_id is not None else None,
                home_difficulty=(
                    home_cell["matchday"].get("difficulty") if home_cell is not None else None
                ),
                away_difficulty=(
                    away_cell["matchday"].get("difficulty") if away_cell is not None else None
                ),
            )
        )

    return sorted(records, key=lambda r: (r.matchday, r.kickoff_utc, r.fixture_id))
