"""One-off historical backfill of per-jornada points (INGEST-08).

Separate from the refresh because it is a one-off by nature, not a cadence.
`ingest_jornada_points` already fills gaps in `current_season_year` on every
run; this walks a *past* season, once. Three properties matter and all three
are tested:

**`rounds`-driven.** The season's own round list is the work list. Season
2025/26 has 36 jornadas, not 38 — weeks 30 and 35 do not exist, and
requesting them returns the site's fallback rather than an error.

**Resumable.** Weeks already stored are skipped, so an interrupted run is
re-run rather than restarted.

**Bounded.** `Settings.backfill_request_budget` caps requests, per
`docs/SCRAPING-POLICY.md`'s runaway-protection rule: a loop that does not
converge is a failure to report, not a reason to keep fetching.

**Its `ScrapeRun` is finished as `backfill`, never `success`.** The run row
exists only because `PlayerGameweekPoints.scrape_run_id` and
`DatasetRun.scrape_run_id` need provenance. Leaving it `running` would trip
`has_running_run` and refuse the in-app "Refresh now" button forever;
finishing it `success` would make `get_last_successful_run` — and through it
the stale banner — report a market refresh that never happened. A backfill
writes last season's points and not one `PlayerSnapshot`, so it is neither.
"""

import argparse
import json
from dataclasses import dataclass, field

from sqlmodel import Session

from core.config import Settings, get_settings
from scraper.errors import ScrapeError
from scraper.sources.af_jornada import fetch_jornada, parse_jornada
from scraper.sources.af_season_stats import fetch_season_stats, parse_season_stats
from storage.db import get_engine
from storage.models import ScrapeRun
from storage.repository import (
    finish_dataset_run,
    finish_run,
    resolve_players,
    start_dataset_run,
    start_run,
    stored_weeks,
    upsert_gameweek_points,
    upsert_season_stats,
)


@dataclass
class BackfillResult:
    season_year: int
    weeks_written: int = 0
    weeks_skipped: int = 0
    rows_written: int = 0
    rows_skipped: int = 0
    stats_rows_written: int = 0
    budget_exhausted: bool = False
    errors: list[str] = field(default_factory=list)


def backfill_season(
    session: Session, season_year: int, settings: Settings | None = None
) -> BackfillResult:
    """Walk one past season's jornadas and store every week not yet held.

    Takes the `session` rather than opening one, for the reason Task 8
    recorded: a function that reaches for `get_engine()` itself can only
    ever be tested against the live database.
    """
    settings = settings or get_settings()
    result = BackfillResult(season_year=season_year)

    run = start_run(session)
    dataset_run = start_dataset_run(session, run.id, f"backfill_{season_year}")
    budget = settings.backfill_request_budget

    try:
        latest = parse_jornada(fetch_jornada(season_year, None, settings), requested_week=None)
    except (ScrapeError, ValueError) as exc:
        # Without `latest` there is no round list, so there is no work list
        # to walk — this one failure is fatal to the backfill, exactly as it
        # is to `ingest_jornada_points`.
        result.errors.append(f"latest: {type(exc).__name__}: {exc}")
        finish_dataset_run(session, dataset_run, "failed", errors=result.errors)
        finish_run(session, run, "backfill", row_count=0, errors=result.errors)
        return result
    budget -= 1

    already = stored_weeks(session, season_year)
    try:
        # One request, before the walk, so the season's deep statistics are
        # covered even if the walk later exhausts its budget. Its own
        # `DatasetRun` and its own `except`: five datasets that fail
        # independently is the rule the refresh already follows, and a
        # blocked statistics page must still leave 36 weeks backfilled.
        _backfill_stats(session, run, season_year, settings, result)
        budget -= 1
        _walk_rounds(session, run, latest.rounds, already, budget, season_year, settings, result)
    except Exception as exc:
        # An unclassified exception is a bug, not a gap, and stays loud —
        # but dying with this `ScrapeRun` still `running` would trip
        # `has_running_run` and refuse every future "Refresh now" click,
        # permanently. Record why, finish both rows, then re-raise: the
        # same shape `run_daily_refresh` uses for the same class of
        # failure.
        session.rollback()
        result.errors.append(f"{type(exc).__name__}: {exc}")
        finish_dataset_run(session, dataset_run, "failed", errors=result.errors)
        finish_run(session, run, "failed", row_count=result.rows_written, errors=result.errors)
        raise

    finish_dataset_run(
        session,
        dataset_run,
        "success" if not result.errors else "failed",
        row_count=result.rows_written,
        skipped_count=result.rows_skipped,
        season_year=season_year,
        errors=result.errors or None,
    )
    finish_run(
        session, run, "backfill", row_count=result.rows_written, errors=result.errors or None
    )
    return result


def _walk_rounds(
    session: Session,
    run: ScrapeRun,
    rounds: tuple[int, ...],
    already: set[int],
    budget: int,
    season_year: int,
    settings: Settings,
    result: BackfillResult,
) -> None:
    """The week loop, extracted only so `backfill_season` can wrap it in
    one `except` without also wrapping its own bookkeeping."""
    for week in rounds:
        if week in already:
            result.weeks_skipped += 1
            continue
        if budget <= 0:
            result.budget_exhausted = True
            break
        budget -= 1
        try:
            snapshot = parse_jornada(
                fetch_jornada(season_year, week, settings), requested_week=week
            )
        except (ScrapeError, ValueError) as exc:
            # A week that cannot be fetched simply is a gap — recorded and
            # skipped, never fatal. Same rule as the refresh's.
            result.errors.append(f"week {week}: {type(exc).__name__}: {exc}")
            continue

        res = resolve_players(session, snapshot.records, name_field="player_name")
        # A finished season has no jornada in progress: every week of it is
        # final, including its highest.
        result.rows_written += upsert_gameweek_points(
            session, season_year, week, False, snapshot.records, res, run.id
        )
        result.weeks_written += 1
        result.rows_skipped += res.unresolved


def _backfill_stats(
    session: Session,
    run: ScrapeRun,
    season_year: int,
    settings: Settings,
    result: BackfillResult,
) -> None:
    """Store one past season's deep per-player statistics — INGEST-08's
    other half. A finished season's totals are final, so this is one
    request, not a walk.
    """
    dataset_run = start_dataset_run(session, run.id, f"backfill_stats_{season_year}")
    try:
        stats = parse_season_stats(fetch_season_stats(settings, season_year=season_year))
    except (ScrapeError, ValueError) as exc:
        session.rollback()
        error = f"stats {season_year}: {type(exc).__name__}: {exc}"
        result.errors.append(error)
        finish_dataset_run(session, dataset_run, "failed", errors=[error])
        return

    if stats.season_year != season_year:
        # The same fallback class the jornada guard exists for. Filing this
        # season's totals under last season's label would be wrong twice
        # over: `upsert_season_stats` deletes by season, so it would also
        # wipe whatever the requested season already held.
        error = (
            f"stats {season_year}: page declared season {stats.season_year} — "
            "this is the site's fallback, not the season asked for."
        )
        result.errors.append(error)
        finish_dataset_run(session, dataset_run, "failed", errors=[error])
        return

    resolution = resolve_players(session, stats.records, name_field="nickname")
    result.stats_rows_written = upsert_season_stats(
        session, season_year, stats.records, resolution, run.id
    )
    finish_dataset_run(
        session,
        dataset_run,
        "success",
        row_count=result.stats_rows_written,
        skipped_count=resolution.unresolved,
        season_year=season_year,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill one season of per-jornada points.")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument(
        "--football-data",
        action="store_true",
        help="Instead: store that season's LaLiga results, team stats and odds "
        "from football-data.co.uk (one request).",
    )
    args = parser.parse_args()

    if args.football_data:
        return _backfill_football_data(args.season)

    with Session(get_engine()) as session:
        result = backfill_season(session, args.season)

    print(
        f"season {result.season_year}: {result.weeks_written} weeks written, "
        f"{result.weeks_skipped} already present, {result.rows_written} rows, "
        f"{result.rows_skipped} skipped (not in market); "
        f"{result.stats_rows_written} season-statistics rows"
    )
    if result.budget_exhausted:
        print("request budget exhausted — re-run to continue")
    for err in result.errors:
        print(f"  ! {err}")
    return 1 if result.errors else 0


def _backfill_football_data(season_year: int) -> int:
    # Imported here so the fantasy backfill never depends on it.
    from scraper.external_ingest import FOOTBALL_DATA_DATASET, backfill_football_data
    from storage.repository import get_dataset_runs

    with Session(get_engine()) as session:
        run = backfill_football_data(session, season_year)
        [dataset] = [
            d for d in get_dataset_runs(session, run.id) if d.dataset == FOOTBALL_DATA_DATASET
        ]
        print(
            f"football-data {season_year}: {dataset.status}, {dataset.row_count} matches, "
            f"{dataset.skipped_count} skipped"
        )
        for note in json.loads(dataset.errors or "[]"):
            print(f"  - {note}")
        return 0 if dataset.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
