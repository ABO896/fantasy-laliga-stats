"""`run_daily_refresh()` — the single entrypoint shared by the OS scheduler
(plan 01-06), the manual `make scrape` / `python -m scraper.run` trigger,
and the API's "Refresh now" trigger (plan 01-05).

Pipeline: fetch -> stage (`RawScrape` DB rows + on-disk retention) ->
parse -> validate (`core/validation.py`, the gate between parse and load)
-> transform -> load.

A classified `ScrapeError` (blocked / structure-changed / network,
`scraper/errors.py`) finishes the run with `status="failed"` and a
single-entry `validation_errors` naming the specific subclass, without
re-raising — this is an expected, classified operational outcome the
caller should be able to read off the returned `ScrapeRun`, not a crash.
Any other, unclassified exception still re-raises after recording the
failure, preserving the original fail-loud behavior for genuine bugs
(T-02-03). A `validate_scrape()` rejection finishes the run with
`status="rejected"` and never reaches `transform`/load at all. Either way
`player_snapshots` is left untouched — the distinction between `failed`
and `rejected` is only how far the run got, never whether existing
history survives.
"""

import argparse
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlmodel import Session

from core.config import get_settings
from core.player_pages import expected_last_day, select_players
from core.transform import to_snapshot
from core.validation import validate_fixtures, validate_scrape
from scraper.errors import (
    ScrapeBlocked,
    ScrapeError,
    ScrapeNetworkError,
    ScrapeNotPublished,
    ScrapeStructureChanged,
)
from scraper.external_ingest import EXTERNAL_DATASETS, ingest_football_data
from scraper.sources.af_jornada import fetch_jornada, parse_jornada
from scraper.sources.af_player_page import fetch_player_page, parse_player_page
from scraper.sources.af_predictions import (
    MARKET_SOURCES,
    fetch_market_predictions,
    fetch_points_predictions,
    parse_market_predictions,
    parse_points_predictions,
)
from scraper.sources.af_season_stats import fetch_season_stats, parse_season_stats
from scraper.sources.analiticafantasy import fetch_pages, parse_page
from scraper.sources.analiticafantasy_calendar import fetch_calendar, parse_calendar
from storage.db import get_engine
from storage.expected_points import refresh_expected_points
from storage.models import Player, RawScrape, ScrapeRun
from storage.our_models import refresh_market_predictions
from storage.player_pages import (
    build_candidates,
    my_player_ids,
    record_fetch,
    upsert_player_page,
)
from storage.repository import (
    finish_dataset_run,
    finish_run,
    get_dataset_runs,
    purge_old_raw_scrapes,
    replace_predictions,
    replace_snapshots,
    resolve_player_ids,
    resolve_players,
    start_dataset_run,
    start_run,
    stored_weeks,
    upsert_fixtures,
    upsert_gameweek_points,
    upsert_players,
    upsert_season_stats,
    weeks_to_refetch,
)

#: Refresh modes. `quick` is the daily refresh as it always was; `mine` adds
#: the player pages of the squad and watchlist; `complete` adds every due
#: player page in the latest market snapshot, up to the request budget.
MODES = ("quick", "mine", "complete")

#: Gap errors listed on the dataset run's notes, so one bad night cannot
#: bury the counts under hundreds of lines.
MAX_GAP_NOTES = 5

MADRID = ZoneInfo("Europe/Madrid")

#: A final jornada normally has all 20 clubs. Fewer is recorded as a note on
#: the dataset run (a postponed match, or a capture problem) — not a failure.
MIN_FINAL_CLUBS = 18


def ingest_jornada_points(session, run, settings) -> None:
    """Store the current season's active jornada, plus any earlier week of
    this season not yet stored or stored stale (`weeks_to_refetch`:
    captured mid-play, or a postponed match has since finished). Re-fetched
    weeks are written final, which also clears a stale provisional flag.

    A week that cannot be fetched or that the site answers with a fallback
    is recorded and skipped, not fatal: per the spec's criterion 5 a missed
    jornada *is* a week present in `rounds` with no stored row. Only a
    failure fetching `latest` fails the dataset, because without it there is
    no round list and no active week to work from.
    """
    settings = settings or get_settings()
    dataset_run = start_dataset_run(session, run.id, "jornada_points")
    try:
        season = settings.current_season_year
        latest = parse_jornada(fetch_jornada(season, None, settings), requested_week=None)
    except ScrapeNotPublished as exc:
        finish_dataset_run(session, dataset_run, "not_published", errors=[str(exc)])
        return
    except (ScrapeError, ValueError) as exc:
        session.rollback()
        finish_dataset_run(session, dataset_run, "failed", errors=[f"{type(exc).__name__}: {exc}"])
        return

    written = unresolved = 0
    gaps: list[str] = []
    already = stored_weeks(session, season)
    stale = weeks_to_refetch(session, season)
    wanted = [w for w in latest.rounds
              if w != latest.week and (w not in already or w in stale)]

    for week in wanted:
        try:
            snapshot = parse_jornada(fetch_jornada(season, week, settings), requested_week=week)
        except (ScrapeError, ValueError) as exc:
            gaps.append(f"week {week}: {type(exc).__name__}: {exc}")
            continue
        clubs = {r["team_name"] for r in snapshot.records if r["team_name"] and not r["is_coach"]}
        if len(clubs) < MIN_FINAL_CLUBS:
            gaps.append(f"week {week}: only {len(clubs)} clubs published")
        res = resolve_players(session, snapshot.records, name_field="player_name")
        written += upsert_gameweek_points(
            session, season, week, False, snapshot.records, res, run.id
        )
        unresolved += res.unresolved

    res = resolve_players(session, latest.records, name_field="player_name")
    written += upsert_gameweek_points(
        session, season, latest.week, True, latest.records, res, run.id
    )
    unresolved += res.unresolved

    finish_dataset_run(
        session,
        dataset_run,
        "success",
        row_count=written,
        skipped_count=unresolved,
        season_year=season,
        errors=gaps or None,
    )


def ingest_season_stats(session, run, settings) -> None:
    """Store the latest published season's deep per-player statistics,
    under whatever `season_year` the payload itself declares."""
    settings = settings or get_settings()
    dataset_run = start_dataset_run(session, run.id, "season_stats")
    try:
        stats = parse_season_stats(fetch_season_stats(settings))
        resolution = resolve_players(session, stats.records, name_field="nickname")
        written = upsert_season_stats(session, stats.season_year, stats.records, resolution, run.id)

        note = (
            f"resolved {resolution.by_slug + resolution.by_name} "
            f"({resolution.by_slug} by slug, {resolution.by_name} by name); "
            f"{resolution.coaches} coaches; {resolution.unresolved} not in market"
        )
        finish_dataset_run(
            session,
            dataset_run,
            "success",
            row_count=written,
            skipped_count=resolution.unresolved,
            season_year=stats.season_year,
            errors=[note],
        )
    except ScrapeNotPublished as exc:
        finish_dataset_run(session, dataset_run, "not_published", errors=[str(exc)])
    except (ScrapeError, ValueError) as exc:
        session.rollback()
        finish_dataset_run(session, dataset_run, "failed", errors=[f"{type(exc).__name__}: {exc}"])


def ingest_points_predictions(session, run, settings) -> None:
    """Store the source's own points-prediction model output, as a
    reference field only — never presented as this app's output."""
    settings = settings or get_settings()
    dataset_run = start_dataset_run(session, run.id, "points_predictions")
    try:
        records, skipped = parse_points_predictions(fetch_points_predictions(settings))
        player_ids = resolve_player_ids(session, [r["external_id"] for r in records])
        as_of = date.today()
        # This dataset owns exactly one source label; naming it keeps the
        # market lists this refresh writes minutes later out of the delete.
        written, unresolved = replace_predictions(
            session, as_of, records, player_ids, run.id, {"points"}
        )

        finish_dataset_run(
            session,
            dataset_run,
            "success",
            row_count=written,
            skipped_count=skipped + unresolved,
        )
    except ScrapeNotPublished as exc:
        finish_dataset_run(session, dataset_run, "not_published", errors=[str(exc)])
    except (ScrapeError, ValueError) as exc:
        session.rollback()
        finish_dataset_run(session, dataset_run, "failed", errors=[f"{type(exc).__name__}: {exc}"])


def ingest_market_predictions(session, run, settings) -> None:
    """Store the source's own market-movement prediction lists (four
    distinct lists per day), as a reference field only. A list can
    legitimately be empty — see `parse_market_predictions`'s docstring —
    so a missing list is recorded as a note, not a failure."""
    settings = settings or get_settings()
    dataset_run = start_dataset_run(session, run.id, "market_predictions")
    try:
        records, skipped, found_sources = parse_market_predictions(
            fetch_market_predictions(settings)
        )
        player_ids = resolve_player_ids(session, [r["external_id"] for r in records])
        as_of = date.today()
        # All four labels, not `found_sources`: a list that is empty today
        # must still clear whatever an earlier run today wrote under it.
        written, unresolved = replace_predictions(
            session, as_of, records, player_ids, run.id, MARKET_SOURCES
        )

        missing = sorted(MARKET_SOURCES - found_sources)
        errors = [f"missing lists: {', '.join(missing)}"] if missing else None

        finish_dataset_run(
            session,
            dataset_run,
            "success",
            row_count=written,
            skipped_count=skipped + unresolved,
            errors=errors,
        )
    except ScrapeNotPublished as exc:
        finish_dataset_run(session, dataset_run, "not_published", errors=[str(exc)])
    except (ScrapeError, ValueError) as exc:
        session.rollback()
        finish_dataset_run(session, dataset_run, "failed", errors=[f"{type(exc).__name__}: {exc}"])


def ingest_fixtures(session, run, settings) -> None:
    """Store the source's rolling five-jornada fixture window (INGEST-04).

    Upsert-only: a fixture that has scrolled out of the window is kept as
    history. A window that fails `validate_fixtures` is `rejected` and
    writes nothing, so stored fixtures survive a malformed payload.
    """
    settings = settings or get_settings()
    dataset_run = start_dataset_run(session, run.id, "fixtures")
    try:
        records = parse_calendar(fetch_calendar(settings))
        validation = validate_fixtures(records, settings)
        if not validation.ok:
            finish_dataset_run(
                session,
                dataset_run,
                "rejected",
                row_count=validation.row_count,
                errors=validation.reasons,
            )
            return
        written = upsert_fixtures(session, records)
        finish_dataset_run(session, dataset_run, "success", row_count=written)
    except ScrapeNotPublished as exc:
        finish_dataset_run(session, dataset_run, "not_published", errors=[str(exc)])
    except (ScrapeError, ValueError) as exc:
        session.rollback()
        finish_dataset_run(session, dataset_run, "failed", errors=[f"{type(exc).__name__}: {exc}"])


def ingest_player_pages(session, run, settings, mode: str, now: datetime | None = None) -> None:
    """Store per-player pages (daily market values and per-jornada match
    rows) for the players this refresh mode covers.

    - `quick`: nothing — returns before any request and writes no
      `DatasetRun`, so a quick refresh is exactly the refresh it always was.
    - `mine`: the current squad plus the watchlist, no request budget.
    - `complete`: everyone in the latest market snapshot, capped at
      `settings.player_pages_max_requests` requests; a run cut short by the
      budget resumes next time, because selection puts the oldest fetch
      first.

    Only players with a gap (or due their weekly re-sweep) are fetched — see
    `core/player_pages.select_players`.

    A bad page is a gap, not a failure: not published, a structure change,
    an unparseable payload, or a network error that survived the fetcher's
    own retries is logged on that player's fetch row and the loop moves on.
    A block (403/429) is the one exception — it stops the loop at once and
    fails the dataset, keeping what was already written; the blocked player
    is not logged as fetched, so he stays first in line for the next run.
    """
    if mode not in MODES:
        raise ValueError(f"unknown refresh mode {mode!r}; expected one of {MODES}")
    if mode == "quick":
        return

    settings = settings or get_settings()
    now = now or datetime.now(UTC)
    season = settings.current_season_year
    dataset_run = start_dataset_run(session, run.id, "player_pages")

    if mode == "mine":
        scope = my_player_ids(session)
        budget = None
        if not scope:
            finish_dataset_run(
                session, dataset_run, "success", season_year=season,
                errors=["no squad or watchlist players"],
            )
            return
    else:
        scope = None
        budget = settings.player_pages_max_requests

    expected = expected_last_day(now.astimezone(MADRID), settings.market_update_hour)
    candidates = build_candidates(session, season, now, scope)
    due = select_players(candidates, expected, now, settings.player_pages_sweep_days, None)
    selected = due if budget is None else due[:budget]

    written = attempted = 0
    gaps: list[str] = []
    blocked: str | None = None
    for player_id in selected:
        slug = session.get(Player, player_id).external_id
        attempted += 1
        try:
            page = parse_player_page(fetch_player_page(slug, settings))
        except ScrapeBlocked as exc:
            blocked = f"{type(exc).__name__}: {exc}"
            break
        except (
            ScrapeNotPublished, ScrapeStructureChanged, ScrapeNetworkError, ValueError
        ) as exc:
            error = f"{type(exc).__name__}: {exc}"
            gaps.append(f"{slug}: {error}")
            record_fetch(session, player_id, now, "gap", error)
            continue
        days, matches = upsert_player_page(session, season, player_id, page, run.id)
        record_fetch(session, player_id, now, "ok")
        written += days + matches

    notes = [f"fetched {attempted} of {len(due)} due"]
    if len(selected) < len(due):
        notes.append("budget reached")
    notes.extend(gaps[:MAX_GAP_NOTES])

    if blocked is not None:
        session.rollback()
        finish_dataset_run(
            session, dataset_run, "failed", row_count=written, skipped_count=len(gaps),
            season_year=season, errors=[blocked, *notes],
        )
        return
    finish_dataset_run(
        session, dataset_run, "success", row_count=written, skipped_count=len(gaps),
        season_year=season, errors=notes,
    )


def run_our_models(session, run) -> None:
    """Generate and score our own market predictions (MODEL-01/03).

    Runs after every dataset ingest and after the run's status is settled,
    and swallows every exception: a model bug is recorded as a failed
    `market_model` dataset — visible on /health — but never fails the
    scrape, never changes the run's status, and never re-raises. Safe to
    run after a failed market scrape too: it only fills dates that have no
    predictions yet and never rewrites a prediction whose outcome exists.
    """
    dataset_run = start_dataset_run(session, run.id, "market_model")
    try:
        summary = refresh_market_predictions(session)
        finish_dataset_run(
            session,
            dataset_run,
            "success",
            row_count=summary.generated,
            errors=[f"generated {summary.generated}, scored {summary.scored}"],
        )
    except Exception as exc:  # noqa: BLE001 — deliberately total, see docstring
        session.rollback()
        finish_dataset_run(session, dataset_run, "failed", errors=[f"{type(exc).__name__}: {exc}"])


def run_expected_points(session, run) -> None:
    """Compute and store expected points for the next jornada (MODEL-02).

    Needs today's snapshots (starter probability), the jornada points, the
    fixture calendar and the football-data odds, so it runs after all of
    them. Same contract as `run_our_models`: every exception is recorded on
    its own `expected_points` dataset and swallowed — it never fails the
    scrape and never changes the run's status.
    """
    dataset_run = start_dataset_run(session, run.id, "expected_points")
    try:
        summary = refresh_expected_points(session)
        if summary.frozen:
            note = f"jornada {summary.jornada} already started; predictions kept frozen"
        else:
            basis = ", ".join(f"{k} {v}" for k, v in sorted(summary.by_basis.items()))
            note = f"jornada {summary.jornada}: {basis or 'no players'}"
        finish_dataset_run(
            session,
            dataset_run,
            "success",
            row_count=summary.written,
            season_year=summary.season_year,
            errors=[note],
        )
    except Exception as exc:  # noqa: BLE001 — deliberately total, see docstring
        session.rollback()
        finish_dataset_run(session, dataset_run, "failed", errors=[f"{type(exc).__name__}: {exc}"])


def run_daily_refresh(run_id: int | None = None, mode: str = "quick"):
    """Run the pipeline. When `run_id` is given, reuse that already-started
    `ScrapeRun` row instead of creating a new one via `start_run` — this is
    how `POST /api/scrape/trigger` (01-05) gets a persisted run id to
    return in its response *before* scheduling this function as a
    `BackgroundTasks` callback, without duplicating the pipeline or
    leaving an orphaned second run row. The scheduler/CLI paths call this
    with no `run_id`.

    `mode` (one of `MODES`) only decides which player pages are fetched —
    see `ingest_player_pages`. It is stamped on the run before anything is
    fetched, in both the new-run and reused-run paths."""
    if mode not in MODES:
        raise ValueError(f"unknown refresh mode {mode!r}; expected one of {MODES}")
    settings = get_settings()
    with Session(get_engine()) as session:
        if run_id is not None:
            run = session.get(ScrapeRun, run_id)
        else:
            run = start_run(session)

        raw_dir = Path(settings.raw_snapshot_root) / f"run_{run.id}"
        raw_dir.mkdir(parents=True, exist_ok=True)
        run.raw_snapshot_dir = str(raw_dir)
        run.mode = mode
        session.add(run)
        session.commit()

        market_dataset_run = start_dataset_run(session, run.id, "market")
        try:
            try:
                pages = fetch_pages(settings)

                records: list[dict] = []
                for page_number, html in enumerate(pages, start=1):
                    session.add(
                        RawScrape(
                            scrape_run_id=run.id,
                            page_number=page_number,
                            fetched_at=datetime.now(UTC),
                            html=html,
                        )
                    )
                    (raw_dir / f"page_{page_number}.html").write_text(html, encoding="utf-8")
                    records.extend(parse_page(html))
                session.commit()

                validation = validate_scrape(records, settings)
                if not validation.ok:
                    finish_run(
                        session,
                        run,
                        status="rejected",
                        row_count=validation.row_count,
                        errors=validation.reasons,
                    )
                    finish_dataset_run(
                        session,
                        market_dataset_run,
                        "rejected",
                        row_count=validation.row_count,
                        errors=validation.reasons,
                    )
                else:
                    player_ids = upsert_players(session, records)

                    as_of = date.today()
                    snapshots = [
                        to_snapshot(record, player_ids[record["external_id"]], as_of, run.id)
                        for record in records
                    ]
                    # Delete-then-reinsert scoped to today's `as_of` only —
                    # the narrow, bounded exception to append-only that
                    # makes a same-day re-run replace rather than
                    # duplicate/crash (T-03-05). See `replace_snapshots`'s
                    # own docstring.
                    replace_snapshots(session, as_of, snapshots)

                    finish_run(session, run, status="success", row_count=len(records))
                    finish_dataset_run(
                        session, market_dataset_run, "success", row_count=len(records)
                    )
            except ScrapeError as exc:
                session.rollback()
                errors = [f"{type(exc).__name__}: {exc}"]
                finish_run(session, run, status="failed", row_count=0, errors=errors)
                finish_dataset_run(session, market_dataset_run, "failed", errors=errors)
            except Exception as exc:
                session.rollback()
                # Record *why* before re-raising. An unclassified exception
                # is a bug rather than an operational outcome, but a run
                # row that says only "failed" leaves `/health` with
                # nothing to act on — the failure is then visible only to
                # whoever is watching the terminal. Fail-loud is
                # unchanged: this still re-raises, which skips the four
                # dataset ingests below (a genuine bug in the market path
                # aborts the whole refresh, exactly as before this task).
                errors = [f"{type(exc).__name__}: {exc}"]
                finish_run(session, run, status="failed", row_count=0, errors=errors)
                finish_dataset_run(session, market_dataset_run, "failed", errors=errors)
                raise

            try:
                # Each dataset owns its own `DatasetRun` and its own
                # try/except (see each `ingest_*`'s docstring) — a blocked
                # jornada fetch must still leave season stats ingested, and
                # vice versa. These run whenever the market half above
                # didn't re-raise, i.e. after a market success, rejection,
                # or classified failure — only an unclassified market bug
                # skips them, matching the existing fail-loud behavior for
                # genuine bugs.
                # First: the re-fetch rule reads which fixtures have gone final.
                ingest_fixtures(session, run, settings)
                ingest_jornada_points(session, run, settings)
                ingest_season_stats(session, run, settings)
                ingest_points_predictions(session, run, settings)
                ingest_market_predictions(session, run, settings)
                # After the jornada points (selection needs the final weeks)
                # and last of the source's own datasets: up to hundreds of
                # page requests, so a block it provokes cannot cost the
                # cheaper datasets above their one request each.
                ingest_player_pages(session, run, settings, mode)

                # The overall status stays "success" only when no dataset
                # (including "market") ended "failed" — `not_published` and
                # `skipped` are states, not failures, and don't degrade it.
                # "rejected" is left alone: it is a distinct, more specific
                # outcome from the validation gate, not something a dataset
                # failure should overwrite or be overwritten by.
                if run.status == "success" and any(
                    d.status == "failed" and d.dataset not in EXTERNAL_DATASETS
                    for d in get_dataset_runs(session, run.id)
                ):
                    run.status = "failed"
                    session.add(run)
                    session.commit()

                # External sources (INGEST-09/10) run last and never touch
                # the run's status: each records its own `DatasetRun`, and
                # `ingest_football_data` catches even its own bugs — see
                # `scraper/external_ingest.py`. Degrade to absent.
                ingest_football_data(session, run, settings)

                # After the status is settled, so a model failure can never
                # degrade it. `run_our_models` catches everything itself.
                run_our_models(session, run)
                run_expected_points(session, run)
            except Exception as exc:
                # An `ingest_*` only catches `ScrapeNotPublished` and
                # `(ScrapeError, ValueError)` — anything else (a genuine
                # bug, or an upstream data collision like the two real
                # ones this task's own fixtures surfaced) is unclassified
                # and must not leave the run looking like a quiet success.
                # `session.rollback()` first: without it, the poisoned
                # transaction means `finally`'s `purge_old_raw_scrapes` is
                # the next statement to touch the session, and it would
                # raise `PendingRollbackError` instead — masking the real
                # exception as a mere `__context__`. Re-raise so fail-loud
                # for genuine bugs is preserved, exactly like the market
                # pipeline's own `except Exception` above.
                session.rollback()
                finish_run(
                    session,
                    run,
                    status="failed",
                    row_count=0,
                    errors=[f"{type(exc).__name__}: {exc}"],
                )
                raise
        finally:
            # `finish_run`'s commit expires ORM attributes by default —
            # refresh to reload them while the session is still open, then
            # expunge so the loaded values stay readable once this session
            # closes at the end of the `with` block.
            purge_old_raw_scrapes(session, settings)
            session.refresh(run)
            session.expunge(run)

    return run


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns a process exit code: 0 only when the run
    finished with `status="success"`, 1 for `rejected`/`failed` (or any
    other non-success status) — so a shell caller (`make scrape`) can
    detect failure without parsing stdout.

    No flag runs the quick refresh; `--mine` adds the squad and watchlist
    player pages, `--full` every due player page (mutually exclusive)."""
    parser = argparse.ArgumentParser(prog="python -m scraper.run")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--mine", action="store_const", const="mine", dest="mode",
        help="also fetch the player pages of the squad and watchlist",
    )
    group.add_argument(
        "--full", action="store_const", const="complete", dest="mode",
        help="also fetch every due player page, up to the request budget",
    )
    parser.set_defaults(mode="quick")
    args = parser.parse_args(argv)

    result = run_daily_refresh(mode=args.mode)
    print(f"Scrape run {result.id} finished with status={result.status!r}, rows={result.row_count}")
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
