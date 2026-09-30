"""football-data.co.uk — LaLiga (`SP1`) fixtures, results, team match
statistics and betting odds (INGEST-10, and the team half of INGEST-09).

Two plain CSV files, no browser, no key:

- `mmz4281/{yy}{yy+1}/SP1.csv` — the season so far: every played match with
  result, team shots/shots on target, pre-match *and* closing odds, and from
  2026/27 on, team expected goals (`HxG`/`AxG`). Updated twice a week.
- `fixtures.csv` — the coming round across ~20 leagues, with pre-match odds;
  rows whose `Div` is not `SP1` are ignored. A weekend without LaLiga (an
  international break) carries **no** SP1 rows, which is a normal state.

Terms and conduct are recorded in `docs/SCRAPING-POLICY.md` ("football-data.co.uk").

**Columns are read by name, never by position** — the header differs by
season (2025/26 has no `HxG`) and between the two files (`fixtures.csv` has
`Referee` and no results). A column that is absent reads as `None`.

**Odds basis.** `Avg*` is the market average across the bookmakers the site
samples — chosen over any single bookmaker so one book's margin or stale
price does not become the model's prior. `AvgC*` is the same at closing.
"""

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from core.config import Settings, get_settings
from core.external_teams import canonical_team
from scraper.http import fetch_page

SOURCE = "football-data"
DIVISION = "SP1"

#: Lowercased structural fingerprint for `classify_response`: the header of
#: every football-data CSV starts with it (after an optional BOM).
FOOTBALL_DATA_MARKERS: tuple[str, ...] = ("div,date",)

#: Kickoff times are UK local time (BST in summer, GMT in winter).
_KICKOFF_TZ = ZoneInfo("Europe/London")

_REQUIRED_COLUMNS = ("Div", "Date", "HomeTeam", "AwayTeam")

#: record field -> CSV column
_INT_COLUMNS = {
    "home_goals": "FTHG",
    "away_goals": "FTAG",
    "home_shots": "HS",
    "away_shots": "AS",
    "home_shots_on_target": "HST",
    "away_shots_on_target": "AST",
}
_FLOAT_COLUMNS = {"home_xg": "HxG", "away_xg": "AxG"}
_ODDS_COLUMNS = {
    "odds_home": "AvgH",
    "odds_draw": "AvgD",
    "odds_away": "AvgA",
    "odds_over25": "Avg>2.5",
    "odds_under25": "Avg<2.5",
    "closing_odds_home": "AvgCH",
    "closing_odds_draw": "AvgCD",
    "closing_odds_away": "AvgCA",
    "closing_odds_over25": "AvgC>2.5",
    "closing_odds_under25": "AvgC<2.5",
}


def season_code(season_year: int) -> str:
    """2026 -> "2627": the site's path segment for season 2026/27."""
    return f"{season_year % 100:02d}{(season_year + 1) % 100:02d}"


def season_csv_url(base_url: str, season_year: int) -> str:
    return f"{base_url.rstrip('/')}/mmz4281/{season_code(season_year)}/{DIVISION}.csv"


def fixtures_csv_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/fixtures.csv"


def _fetch(url: str, settings: Settings) -> str:
    # This source's own pacing, independent of the fantasy site's.
    return fetch_page(
        url,
        FOOTBALL_DATA_MARKERS,
        settings,
        min_delay=settings.football_data_min_delay_seconds,
        max_delay=settings.football_data_min_delay_seconds * 2,
    )


def fetch_season_csv(season_year: int, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return _fetch(season_csv_url(settings.football_data_base_url, season_year), settings)


def fetch_fixtures_csv(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return _fetch(fixtures_csv_url(settings.football_data_base_url), settings)


@dataclass
class ParsedMatches:
    records: list[dict] = field(default_factory=list)
    #: One human-readable reason per SP1 row not turned into a record.
    skipped: list[str] = field(default_factory=list)
    unmapped_teams: set[str] = field(default_factory=set)


def _cell(row: dict, column: str) -> str | None:
    value = row.get(column)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _int(row: dict, column: str) -> int | None:
    value = _cell(row, column)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _float(row: dict, column: str) -> float | None:
    value = _cell(row, column)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _odds(row: dict, column: str) -> float | None:
    """Decimal odds, or `None` for anything that is not a valid price — a
    single bad cell makes that price absent, never the row."""
    value = _float(row, column)
    return value if value is not None and value > 1.0 else None


def _date(text: str | None) -> date | None:
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _kickoff(day: date, text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        hh, mm = (int(p) for p in text.split(":"))
        local = datetime(day.year, day.month, day.day, hh, mm, tzinfo=_KICKOFF_TZ)
    except ValueError:
        return None
    return local.astimezone(UTC)


def _season_of(day: date) -> int:
    """LaLiga seasons run August-May; July belongs to the coming season."""
    return day.year if day.month >= 7 else day.year - 1


def parse_matches(text: str, expected_season: int | None) -> ParsedMatches:
    """Parse one football-data CSV into match records. Pure — no network.

    `expected_season` guards the season file: every row must fall in that
    season or the whole file is refused, the same "the payload must say it
    is what was asked for" rule the jornada parser follows. `None` (the
    fixtures file) derives each row's season from its date.

    Raises `ValueError` when the header lacks the required columns, or when
    more than half of the SP1 rows are unreadable (a format change, not
    noise). Rows with an unmapped club are skipped and reported, not fatal.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    columns = set(reader.fieldnames or [])
    missing = [c for c in _REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise ValueError(f"football-data CSV is missing required columns: {missing}")

    parsed = ParsedMatches()
    seen: set[tuple[int, str, str]] = set()
    sp1_rows = unreadable = 0

    for row in reader:
        if _cell(row, "Div") != DIVISION:
            continue
        sp1_rows += 1
        src_home, src_away = _cell(row, "HomeTeam"), _cell(row, "AwayTeam")
        day = _date(_cell(row, "Date"))
        if day is None or not src_home or not src_away:
            unreadable += 1
            parsed.skipped.append(f"unreadable row: {src_home} v {src_away} {row.get('Date')!r}")
            continue

        season = _season_of(day)
        if expected_season is not None and season != expected_season:
            raise ValueError(
                f"football-data season file for {expected_season} carries a {season} "
                f"match ({day.isoformat()} {src_home} v {src_away}) — not the season asked for"
            )

        home, away = canonical_team(src_home), canonical_team(src_away)
        if home is None or away is None:
            for name, mapped in ((src_home, home), (src_away, away)):
                if mapped is None:
                    parsed.unmapped_teams.add(name)
            parsed.skipped.append(f"unmapped club: {src_home} v {src_away}")
            continue

        key = (season, home, away)
        if key in seen:
            parsed.skipped.append(f"duplicate pairing ignored: {home} v {away} {season}")
            continue
        seen.add(key)

        record = {
            "season_year": season,
            "match_date": day,
            "kickoff_at": _kickoff(day, _cell(row, "Time")),
            "home_team": home,
            "away_team": away,
            "source_home_team": src_home,
            "source_away_team": src_away,
        }
        record.update({f: _int(row, c) for f, c in _INT_COLUMNS.items()})
        record.update({f: _float(row, c) for f, c in _FLOAT_COLUMNS.items()})
        record.update({f: _odds(row, c) for f, c in _ODDS_COLUMNS.items()})
        played = record["home_goals"] is not None and record["away_goals"] is not None
        record["status"] = "played" if played else "scheduled"
        record["raw_fields"] = {k: v for k, v in row.items() if k and v not in (None, "")}
        parsed.records.append(record)

    if sp1_rows and unreadable * 2 > sp1_rows:
        raise ValueError(
            f"{unreadable} of {sp1_rows} LaLiga rows unreadable — the file format has changed"
        )
    return parsed


def raw_fields_json(record: dict) -> str:
    return json.dumps(record["raw_fields"], ensure_ascii=False, sort_keys=True)
