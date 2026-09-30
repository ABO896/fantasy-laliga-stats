"""Ingestion of external football data (INGEST-09/10) — datasets that sit
beside the fantasy-source ones in the same refresh, but must never decide
its outcome.

**Degrade to absent, never break.** An external source is a nice-to-have
next to the fantasy market: its failure is recorded on its own `DatasetRun`
(visible on `/api/health`), and nothing else changes — the refresh's overall
status ignores it (`EXTERNAL_DATASETS`), and even an *unclassified*
exception is caught here and recorded rather than re-raised. That last part
deliberately differs from the fantasy datasets, whose unclassified errors
stay fail-loud: a bug in an optional source should be visible, not able to
stop the owner's market refresh.
"""

import traceback

from sqlmodel import Session

from core.config import Settings, get_settings
from scraper.errors import ScrapeError, ScrapeNotPublished
from scraper.sources.football_data import (
    SOURCE,
    fetch_fixtures_csv,
    fetch_season_csv,
    parse_matches,
)
from storage.external_repository import get_roster_teams, upsert_external_matches
from storage.models import ScrapeRun
from storage.repository import finish_dataset_run, finish_run, start_dataset_run, start_run

FOOTBALL_DATA_DATASET = "football_data"

#: Datasets whose failure never marks the refresh itself `failed`.
EXTERNAL_DATASETS = frozenset({FOOTBALL_DATA_DATASET})

#: Cap on how many per-row skip reasons are copied into the dataset run.
_MAX_NOTES = 10


def ingest_football_data(
    session: Session,
    run: ScrapeRun,
    settings: Settings | None = None,
    season_year: int | None = None,
    include_fixtures: bool = True,
) -> None:
    """Store LaLiga results, team match stats and odds from football-data.co.uk.

    Two requests at most: the season file (played matches) then, unless
    `include_fixtures` is off, the coming-round file (scheduled matches).
    Each part fails on its own; rows from the part that worked are kept.
    """
    settings = settings or get_settings()
    dataset_run = start_dataset_run(session, run.id, FOOTBALL_DATA_DATASET)
    if not settings.football_data_enabled:
        finish_dataset_run(
            session, dataset_run, "skipped", errors=["disabled: football_data_enabled=false"]
        )
        return

    season = season_year or settings.current_season_year
    try:
        parts = [(f"season {season}", lambda: fetch_season_csv(season, settings), season)]
        if include_fixtures:
            parts.append(("fixtures", lambda: fetch_fixtures_csv(settings), None))

        records: list[dict] = []
        notes: list[str] = []
        failures: list[str] = []
        unmapped: set[str] = set()
        succeeded = skipped = 0

        for label, fetch, expected in parts:
            try:
                parsed = parse_matches(fetch(), expected_season=expected)
            except ScrapeNotPublished as exc:
                notes.append(f"{label}: not published ({exc})")
                continue
            except (ScrapeError, ValueError) as exc:
                failures.append(f"{label}: {type(exc).__name__}: {exc}")
                continue
            succeeded += 1
            records.extend(parsed.records)
            skipped += len(parsed.skipped)
            unmapped |= parsed.unmapped_teams
            notes.extend(f"{label}: {s}" for s in parsed.skipped[:_MAX_NOTES])

        result = upsert_external_matches(session, records, run.id, source=SOURCE)

        if unmapped:
            notes.insert(0, f"unmapped clubs (add to core/external_teams.py): {sorted(unmapped)}")
        if season == settings.current_season_year:
            roster = get_roster_teams(session)
            stored = {r[side] for r in records for side in ("home_team", "away_team")}
            outside = sorted(t for t in stored if t not in roster) if roster else []
            if outside:
                notes.insert(0, f"clubs not in the fantasy roster: {outside}")
        notes.insert(
            0,
            f"{result.written} matches written; {result.kept_played} fixtures already played",
        )

        if failures:
            status = "failed"
        elif succeeded == 0:
            status = "not_published"
        else:
            status = "success"
        finish_dataset_run(
            session,
            dataset_run,
            status,
            row_count=result.written,
            skipped_count=skipped,
            season_year=season,
            errors=failures + notes,
        )
    except Exception as exc:  # noqa: BLE001 — see module docstring
        session.rollback()
        finish_dataset_run(
            session,
            dataset_run,
            "failed",
            season_year=season,
            errors=[
                f"unclassified {type(exc).__name__}: {exc}",
                traceback.format_exc(limit=3),
            ],
        )


def backfill_football_data(
    session: Session, season_year: int, settings: Settings | None = None
) -> ScrapeRun:
    """Store one past season's file — one request. The run is finished as
    `backfill`, never `success`, for the reason `scraper/backfill.py` gives:
    it writes no market snapshot, so it must not look like a refresh."""
    run = start_run(session)
    ingest_football_data(session, run, settings, season_year=season_year, include_fixtures=False)
    finish_run(session, run, "backfill", row_count=0)
    return run
