"""Repository functions — the only place the rest of the app talks SQL.

`append_snapshots` is insert-only by design: overwriting history is the one
failure `PITFALLS.md` rates unrecoverable (Pitfall 4). Delete/merge calls on
`PlayerSnapshot` never appear in this module, with one narrow, deliberate
exception: `replace_snapshots` deletes and reinserts the set for exactly
one `as_of` date, bounded to same-day re-runs only (T-03-05) — see its own
docstring.

`purge_old_raw_scrapes` is the other exception to "never delete" in this
module, and it is scoped to staging HTML only (`RawScrape` rows and their
on-disk directories) — it must never reference `PlayerSnapshot`.
"""

import json
import shutil
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, delete, distinct, func, select

from core.config import Settings
from core.season_stats_schema import SEASON_RECORD_FIELDS, column_name
from core.squad_rules import SquadMember as EngineMember
from core.xp_backtest import MIN_TEAM_ROWS
from storage.db import as_utc
from storage.models import (
    DatasetRun,
    Fixture,
    LeagueSettings,
    Player,
    PlayerGameweekPoints,
    PlayerSeasonStats,
    PlayerSnapshot,
    RawScrape,
    ScrapeRun,
    SourcePrediction,
    SquadMember,
    SquadSetup,
    WatchlistEntry,
)


def upsert_players(session: Session, records: list[dict]) -> dict[str, int]:
    """Insert new players / update slowly-changing identity fields for
    existing ones, keyed by `external_id`. Returns `external_id -> player_id`."""
    now = datetime.now(UTC)
    external_ids = [r["external_id"] for r in records]
    existing = session.exec(select(Player).where(Player.external_id.in_(external_ids))).all()
    existing_by_external_id = {p.external_id: p for p in existing}

    result: dict[str, int] = {}
    for record in records:
        external_id = record["external_id"]
        player = existing_by_external_id.get(external_id)
        if player is None:
            player = Player(
                external_id=external_id,
                name=record["name"],
                team=record["team"],
                position=record["position"],
                created_at=now,
                updated_at=now,
            )
            session.add(player)
            session.flush()  # populate player.id without committing
        else:
            player.name = record["name"]
            player.team = record["team"]
            player.position = record["position"]
            player.updated_at = now
            session.add(player)
        result[external_id] = player.id

    session.commit()
    return result


def append_snapshots(session: Session, snapshots: list[PlayerSnapshot]) -> int:
    """Insert-only. Never updates or deletes an existing `(as_of, player_id)` row."""
    for snapshot in snapshots:
        session.add(snapshot)
    session.commit()
    return len(snapshots)


def replace_snapshots(session: Session, as_of: date, snapshots: list[PlayerSnapshot]) -> int:
    """Delete, then reinsert, the snapshot set for exactly one `as_of`
    date, inside one transaction.

    This is the sole, narrow exception to `append_snapshots`'s insert-only
    rule (T-03-05, the flagged same-day-idempotency assumption in
    01-03-PLAN.md): `run_daily_refresh` running twice on one calendar date
    must replace that date's rows rather than raising a composite-PK
    violation or silently duplicating. The delete is scoped to a single
    `as_of` value passed in by the caller — it can never reach any other
    date, including a first-time run's date (deleting zero rows there is
    a harmless no-op, identical in effect to `append_snapshots`)."""
    session.exec(delete(PlayerSnapshot).where(PlayerSnapshot.as_of == as_of))
    for snapshot in snapshots:
        session.add(snapshot)
    session.commit()
    return len(snapshots)


def get_latest_players(session: Session) -> list[tuple[PlayerSnapshot, Player]]:
    """Resolves `MAX(as_of)` in one query, then range-scans that date —
    an index scan given the composite PK leads with `as_of`."""
    latest_date = session.exec(select(func.max(PlayerSnapshot.as_of))).one()
    if latest_date is None:
        return []
    rows = session.exec(
        select(PlayerSnapshot, Player)
        .join(Player, Player.id == PlayerSnapshot.player_id)
        .where(PlayerSnapshot.as_of == latest_date)
    ).all()
    return list(rows)


def get_last_successful_run(session: Session) -> ScrapeRun | None:
    """The most recent run whose status is `success` specifically — never
    merely the most recent run of any status. A `rejected`/`failed` run
    finishing later must not make the data look fresher than it is
    (T-05-04)."""
    return session.exec(
        select(ScrapeRun)
        .where(ScrapeRun.status == "success")
        .order_by(ScrapeRun.finished_at.desc())
    ).first()


def get_recent_runs(session: Session, limit: int = 10) -> list[ScrapeRun]:
    """The `limit` most recent runs of any status, most recent first, so
    the health page can show failures alongside successes."""
    return list(
        session.exec(select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(limit)).all()
    )


def has_running_run(session: Session) -> bool:
    """True while a `ScrapeRun` is in the `running` state — the
    single-flight guard `POST /api/scrape/trigger` uses to refuse a second
    concurrent scrape (T-05-01)."""
    return session.exec(select(ScrapeRun).where(ScrapeRun.status == "running")).first() is not None


def start_run(session: Session) -> ScrapeRun:
    run = ScrapeRun(started_at=datetime.now(UTC), status="running")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def finish_run(
    session: Session,
    run: ScrapeRun,
    status: str,
    row_count: int,
    errors: list[str] | None = None,
) -> None:
    run.finished_at = datetime.now(UTC)
    run.status = status
    run.row_count = row_count
    if errors is not None:
        import json

        run.validation_errors = json.dumps(errors, ensure_ascii=False)
    session.add(run)
    session.commit()


def purge_old_raw_scrapes(session: Session, settings: Settings) -> int:
    """Delete staging `RawScrape` rows (and their on-disk HTML
    directories) older than `settings.raw_retention_days`. Scoped to
    staging data only — never touches player-facing storage. Called from
    `run_daily_refresh` at the end of every run, success or not, so
    retention is an executed step rather than a written intention."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.raw_retention_days)
    old_scrapes = session.exec(select(RawScrape).where(RawScrape.fetched_at < cutoff)).all()

    stale_run_ids = {rs.scrape_run_id for rs in old_scrapes}
    stale_dirs = {
        run.raw_snapshot_dir
        for run_id in stale_run_ids
        if (run := session.get(ScrapeRun, run_id)) is not None and run.raw_snapshot_dir
    }

    deleted_count = len(old_scrapes)
    for rs in old_scrapes:
        session.delete(rs)
    session.commit()

    for dir_path in stale_dirs:
        shutil.rmtree(dir_path, ignore_errors=True)

    return deleted_count


def get_squad_members(session: Session) -> list[EngineMember]:
    """The current squad (`sold_at IS NULL`), joined to player identity and to
    the latest snapshot's market value.

    The snapshot join is a LEFT OUTER JOIN on purpose. An inner join would
    make a squad member silently disappear from their own squad on any day a
    scrape was rejected or the player left the source roster. Missing values
    arrive as `None` and the engine falls back to purchase price.
    """
    latest_date = session.exec(select(func.max(PlayerSnapshot.as_of))).one()

    rows = session.exec(
        select(SquadMember, Player, PlayerSnapshot)
        .join(Player, Player.id == SquadMember.player_id)
        .outerjoin(
            PlayerSnapshot,
            (PlayerSnapshot.player_id == SquadMember.player_id)
            & (PlayerSnapshot.as_of == latest_date),
        )
        .where(SquadMember.sold_at.is_(None))
        .order_by(SquadMember.id)
    ).all()

    return [
        EngineMember(
            player_id=player.id,
            name=player.name,
            position=player.position,
            purchase_price=squad_member.purchase_price,
            market_value=snapshot.market_value if snapshot is not None else None,
        )
        for squad_member, player, snapshot in rows
    ]


def get_squad_setup(session: Session) -> SquadSetup:
    """The squad's current shape. Migration 0007 guarantees the row exists,
    so this never creates one — a create-if-missing branch here would be a
    second, silent seeding path that could disagree with the migration's,
    exactly as `get_league_settings` avoids."""
    setup = session.get(SquadSetup, 1)
    if setup is None:  # pragma: no cover — migration 0007 seeds this row
        raise RuntimeError("squadsetup row 1 is missing — run `alembic upgrade head`")
    return setup


def get_squad_roles(session: Session) -> dict[int, str]:
    """Where each currently-held player is standing. Sold members are absent
    rather than reported as reserves — they are not in the squad at all."""
    rows = session.exec(
        select(SquadMember.player_id, SquadMember.role).where(SquadMember.sold_at.is_(None))
    ).all()
    return {player_id: role for player_id, role in rows}


def save_xi(
    session: Session,
    *,
    formation: str,
    starter_ids: Sequence[int],
    bench_ids: Sequence[int],
) -> None:
    """Write the whole arrangement — formation and every member's role — in
    one commit.

    Whole-shape rather than per-player, so a swap is one transaction instead
    of two writes with an illegal state in between. Every current member is
    rewritten, not only the ones named: a player who has left both lists is
    back in the rail, and saying so explicitly is what makes this idempotent.

    Legality is the caller's gate, not this function's — `evaluate_lineup`
    has already run by the time anything reaches here.
    """
    setup = get_squad_setup(session)
    setup.formation = formation
    session.add(setup)

    starters, bench = set(starter_ids), set(bench_ids)
    members = session.exec(select(SquadMember).where(SquadMember.sold_at.is_(None))).all()
    for member in members:
        if member.player_id in starters:
            member.role = "starter"
        elif member.player_id in bench:
            member.role = "bench"
        else:
            member.role = "reserve"
        session.add(member)

    session.commit()


def add_squad_member(session: Session, player_id: int, purchase_price: int) -> None:
    """Record a holding and what was paid for it. No money moves anywhere
    else — `purchase_price` is a fact about this player, not an entry in a
    balance the app has stopped deriving."""
    player = session.get(Player, player_id)
    if player is None:
        raise ValueError(f"unknown player id {player_id}")
    session.add(
        SquadMember(
            player_id=player_id,
            purchase_price=purchase_price,
            acquired_on=datetime.now(UTC).date(),
        )
    )
    session.commit()


def remove_squad_member(session: Session, player_id: int, sale_price: int | None = None) -> bool:
    """Soft-deletes the current holding, in one commit. Returns False when
    the player is not in the squad, so the caller can answer 404 rather than
    pretend it worked — that early return commits nothing.

    The sale price is recorded only when given — a fact nobody stated should
    not be invented as a zero.
    """
    member = session.exec(
        select(SquadMember)
        .where(SquadMember.player_id == player_id)
        .where(SquadMember.sold_at.is_(None))
    ).first()
    if member is None:
        return False

    member.sold_at = datetime.now(UTC)
    member.sale_price = sale_price
    # Reset alongside the sale, not lazily on the next read: a player bought
    # back later must return to the rail, never holding a slot in a formation
    # that may no longer exist.
    member.role = "reserve"
    session.add(member)
    session.commit()
    return True


def get_availability_as_of(session: Session, player_ids: list[int], on: date) -> dict[int, str]:
    """Each player's availability from their latest snapshot at or before
    `on` (LN-26). Players with no snapshot by that date are simply absent,
    and the engine treats absence as available — a warning nobody has
    evidence for is worse than no warning."""
    if not player_ids:
        return {}
    latest = session.exec(
        select(func.max(PlayerSnapshot.as_of)).where(PlayerSnapshot.as_of <= on)
    ).one()
    if latest is None:
        return {}
    rows = session.exec(
        select(PlayerSnapshot.player_id, PlayerSnapshot.availability_status)
        .where(PlayerSnapshot.as_of == latest)
        .where(PlayerSnapshot.player_id.in_(player_ids))
    ).all()
    return {player_id: status for player_id, status in rows}


def get_league_settings(session: Session) -> LeagueSettings:
    """The league's premium flags. Migration 0005 guarantees the row exists,
    so this never creates one — a create-if-missing branch here would be a
    second, silent seeding path that could disagree with the migration's."""
    settings = session.get(LeagueSettings, 1)
    if settings is None:  # pragma: no cover — migration 0005 seeds this row
        raise RuntimeError("leaguesettings row 1 is missing — run `alembic upgrade head`")
    return settings


def set_league_settings(
    session: Session,
    *,
    premium_formations_enabled: bool,
    premium_bench_enabled: bool,
) -> LeagueSettings:
    """Replace both flags in one commit. They are written together because
    the UI submits them together; a partial update API would invite a caller
    to send one flag and silently reset the other."""
    settings = get_league_settings(session)
    settings.premium_formations_enabled = premium_formations_enabled
    settings.premium_bench_enabled = premium_bench_enabled
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


# --- Deep ingestion (jornada points, season stats, predictions) -----------
#
# Both ingested payloads omit `slug` for some players, and in both cases
# those players include the league's best (Lamine Yamal, Mbappe, Vini Jr on
# the statistics page; Bellingham, Pepe, Fornals among 31 others on the
# jornada page). `resolve_players` below is the one place identity
# resolution happens for these two datasets, because it is the first point
# in the pipeline that has the database. The prediction payloads are
# different: both always carry a slug, so `resolve_player_ids` — a plain
# slug lookup — is all they need.


@dataclass
class Resolution:
    """The outcome of resolving a batch of jornada/season-stats records to
    player ids, with the four ways a record can turn out kept separate.

    "Unresolved because the player left the league" and "dropped because a
    field was missing" are different facts an owner needs to be able to
    tell apart from a run's summary — a single blended `skipped` count
    cannot answer which one happened, so the counts stay apart all the way
    out to the caller.
    """

    player_id_by_index: dict[int, int] = field(default_factory=dict)
    by_slug: int = 0
    by_name: int = 0
    coaches: int = 0
    unresolved: int = 0
    #: Records repeating a slug already claimed in this batch — the same
    #: player seen twice, not a player who could not be found. Kept apart
    #: from `unresolved` because that count means "no longer in the
    #: market" and is what a run's summary reports as skipped.
    duplicates: int = 0


def resolve_player_ids(session: Session, external_ids: list[str]) -> dict[str, int]:
    """Slug-only lookup for the prediction paths, whose payloads carry a
    slug on every usable row (verified: 492/492 on the points page).
    Slugs with no matching `Player` row are simply absent from the
    result — that absence is how `replace_predictions` counts what it
    could not join."""
    if not external_ids:
        return {}
    rows = session.exec(
        select(Player.external_id, Player.id).where(Player.external_id.in_(external_ids))
    ).all()
    return dict(rows)


def resolve_players(session: Session, records: list[dict], name_field: str) -> Resolution:
    """Resolve jornada or season-statistics records to player ids. One
    resolver serves both datasets — `name_field` is `"player_name"` for
    jornada records and `"nickname"` for statistics records, the only
    thing that differs between them.

    Per record, in order, stopping at the first hit:

    1. `record["slug"]` against `Player.external_id`, exactly.
    2. `record["is_coach"]` — counted as `coaches`, never stored. Checked
       here, before any name-based resolution is attempted, so a club
       coach who happens to share a name with a real player is never
       resolved to them (a coach is not a fantasy player at all).
    3. `(record[name_field], record["position"])` against
       `(Player.name, Player.position)`, name compared `.strip().lower()`.
       Position, not team, is the corroborating field here — measured,
       not assumed: the source's team names ("Atletico de Madrid") don't
       match `Player.team` ("Atletico Madrid") often enough to be useful
       (a team-only join resolved 9 of 31 on the jornada page), while
       position resolved 21 of 31 there and 28 of 54 on the statistics
       page. The lookup is built as `{(name, position): [ids]}` and only
       a single-element entry is accepted — a fuzzy join that silently
       picks one of several candidates is worse than no join at all: on
       the statistics page two name-only matches carry a contradicting
       position, two mis-attributions this refuses that a name-or-team
       join would have made.
    4. Otherwise `unresolved` — most often a player who has left the
       league entirely, D-02's departed-player case.

    Resolution must also be **injective**: at most one record per batch
    may claim a given `Player`. That holds for slug matches too, and not
    only for fallbacks: the source lists a player once per club
    registration while a transfer is recent or pending, so one payload can
    carry the same slug twice — 2025 week 16 carried
    `alfon-gonzalez-119213` twice, and resolving both crashed the first
    real backfill on `PlayerGameweekPoints`'s (season_year, week,
    player_id) key. A repeat is counted `duplicates`, never `unresolved`.

    The live database surfaced a second case the
    unambiguity check above does not guard — two *different* footballers
    named Navarro, same position, one at Athletic Club (has a `Player`
    row, matched by slug) and one at Valencia (not in the current market,
    no `Player` row of his own). The Valencia Navarro's slug never
    matches, so he falls to the `(name, position)` fallback — which lands
    on the Athletic Club Navarro, a real player already claimed by an
    exact slug match. Writing his stats there would be the exact
    mis-attribution this resolver exists to refuse, and it collides on
    the primary key besides. So: a `(name, position)` fallback that would
    land on a player already claimed — by an exact slug match, or by
    another fallback in the same batch — is refused and counted
    `unresolved`, never `by_name`. A slug match can never lose this
    contest regardless of where in `records` it appears, because every
    slug match is collected before any fallback is decided. This is a
    distinct guard from the unambiguity check above: that one refuses one
    record that could match two players; this one refuses two records
    that would both match one player.
    """
    all_players = session.exec(select(Player)).all()
    by_external_id = {p.external_id: p.id for p in all_players}
    name_position_index: dict[tuple[str, str | None], list[int]] = {}
    for p in all_players:
        name_position_index.setdefault((p.name.strip().lower(), p.position), []).append(p.id)

    resolution = Resolution()
    claimed_by_slug: set[int] = set()
    fallback_candidate_by_index: dict[int, int] = {}

    for index, record in enumerate(records):
        slug = record.get("slug")
        if slug and slug in by_external_id:
            player_id = by_external_id[slug]
            if player_id in claimed_by_slug:
                resolution.duplicates += 1
                continue
            resolution.player_id_by_index[index] = player_id
            resolution.by_slug += 1
            claimed_by_slug.add(player_id)
            continue

        if record.get("is_coach"):
            resolution.coaches += 1
            continue

        name = record.get(name_field)
        position = record.get("position")
        if name:
            candidates = name_position_index.get((name.strip().lower(), position), [])
            if len(candidates) == 1:
                fallback_candidate_by_index[index] = candidates[0]
                continue

        resolution.unresolved += 1

    # Fallback claims are decided only once every slug match is known, so a
    # slug match occurring later in `records` still wins. Candidates are
    # grouped by the player they would claim so that two fallback records
    # colliding with each other refuse each other, symmetrically — neither
    # is an arbitrary "first past the post" winner.
    fallback_indices_by_player: dict[int, list[int]] = {}
    for index, player_id in fallback_candidate_by_index.items():
        fallback_indices_by_player.setdefault(player_id, []).append(index)

    for player_id, indices in fallback_indices_by_player.items():
        if player_id in claimed_by_slug or len(indices) > 1:
            resolution.unresolved += len(indices)
        else:
            resolution.player_id_by_index[indices[0]] = player_id
            resolution.by_name += 1

    return resolution


def start_dataset_run(session: Session, scrape_run_id: int, dataset: str) -> DatasetRun:
    """One row per dataset attempt within a scrape run — see `DatasetRun`'s
    docstring for why `ScrapeRun`'s single status stopped being enough
    once one refresh covered five independently-failing datasets."""
    run = DatasetRun(scrape_run_id=scrape_run_id, dataset=dataset, started_at=datetime.now(UTC))
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def finish_dataset_run(
    session: Session,
    dataset_run: DatasetRun,
    status: str,
    row_count: int = 0,
    skipped_count: int = 0,
    season_year: int | None = None,
    errors: list[str] | None = None,
) -> None:
    """Mirrors `finish_run`'s shape, one level down: JSON-encodes `errors`
    into the same kind of column, scoped to a single dataset's outcome."""
    dataset_run.finished_at = datetime.now(UTC)
    dataset_run.status = status
    dataset_run.row_count = row_count
    dataset_run.skipped_count = skipped_count
    if season_year is not None:
        dataset_run.season_year = season_year
    if errors is not None:
        dataset_run.errors = json.dumps(errors, ensure_ascii=False)
    session.add(dataset_run)
    session.commit()


def upsert_gameweek_points(
    session: Session,
    season_year: int,
    week: int,
    is_provisional: bool,
    records: list[dict],
    resolution: Resolution,
    run_id: int,
) -> int:
    """Delete, then reinsert, the `(season_year, week)` rows in one
    transaction — the same bounded delete-then-reinsert pattern
    `replace_snapshots` uses, scoped to this week's key instead of a
    single `as_of` date. A re-fetch of a provisional jornada
    (`is_provisional=True`) must update its rows in place, never
    accumulate duplicates on every re-run.

    Takes the `Resolution` rather than a plain id map, and writes only
    the records `player_id_by_index` actually resolved — unresolved and
    coach rows are silently absent here, already counted by
    `resolve_players`.
    """
    session.exec(
        delete(PlayerGameweekPoints)
        .where(PlayerGameweekPoints.season_year == season_year)
        .where(PlayerGameweekPoints.week == week)
    )
    written = 0
    for index, player_id in resolution.player_id_by_index.items():
        record = records[index]
        session.add(
            PlayerGameweekPoints(
                season_year=season_year,
                week=week,
                player_id=player_id,
                points=record["points"],
                is_provisional=is_provisional,
                scrape_run_id=run_id,
            )
        )
        written += 1
    session.commit()
    return written


#: `PlayerSeasonStats` columns populated straight from a season-stats
#: record — every field except the ones this function itself supplies
#: (identity, provenance, and the verbatim payload).
_SEASON_STATS_RECORD_FIELDS = tuple(
    name
    for name in PlayerSeasonStats.model_fields
    if name not in {"season_year", "player_id", "raw_fields", "scrape_run_id"}
)


def upsert_season_stats(
    session: Session,
    season_year: int,
    records: list[dict],
    resolution: Resolution,
    run_id: int,
) -> int:
    """Delete, then reinsert, the `(season_year,)` rows in one
    transaction — same bounded delete-then-reinsert reasoning as
    `upsert_gameweek_points`, scoped to this season's key alone (there is
    no week dimension here).

    Takes the `Resolution` rather than a plain id map, and writes only
    the records `player_id_by_index` actually resolved.
    """
    session.exec(delete(PlayerSeasonStats).where(PlayerSeasonStats.season_year == season_year))
    written = 0
    for index, player_id in resolution.player_id_by_index.items():
        record = records[index]
        values = {name: record[name] for name in _SEASON_STATS_RECORD_FIELDS}
        session.add(
            PlayerSeasonStats(
                season_year=season_year,
                player_id=player_id,
                raw_fields=json.dumps(record["raw"], ensure_ascii=False),
                scrape_run_id=run_id,
                **values,
            )
        )
        written += 1
    session.commit()
    return written


def replace_predictions(
    session: Session,
    as_of: date,
    records: list[dict],
    player_ids: dict[str, int],
    run_id: int,
    sources: Collection[str],
) -> tuple[int, int]:
    """Delete, then reinsert, the rows for one `as_of` date *and* the
    `sources` this call owns, in one transaction — predictions are a daily
    snapshot and a same-day re-run must replace rather than duplicate, the
    same reasoning as `replace_snapshots`.

    `sources` is what keeps the two prediction datasets from erasing each
    other. `ingest_points_predictions` and `ingest_market_predictions` both
    write for today, one after the other, so a delete scoped to `as_of`
    alone let the second silently wipe the first — the live refresh on
    2026-08-27 recorded `points_predictions` success, 495 rows written, and
    zero surviving. Both datasets still reported success, which is how the
    loss stayed invisible.

    It is declared by the caller rather than inferred from `records`
    because a market list can legitimately be empty on a quiet day: an
    inferred scope would skip that source's delete and leave an earlier
    same-day run's rows standing as if they were current.

    `player_ids` comes from `resolve_player_ids`: a record whose slug has
    no entry there is skipped and counted rather than guessed at — these
    payloads always carry a slug on usable rows, so a miss here means the
    slug is not (or no longer) a known `Player`.

    Returns `(written, skipped)`.
    """
    session.exec(
        delete(SourcePrediction)
        .where(SourcePrediction.as_of == as_of)
        .where(SourcePrediction.source.in_(list(sources)))
    )
    written = 0
    skipped = 0
    for record in records:
        player_id = player_ids.get(record["external_id"])
        if player_id is None:
            skipped += 1
            continue
        session.add(
            SourcePrediction(
                as_of=as_of,
                source=record["source"],
                player_id=player_id,
                value=record["value"],
                raw_fields=json.dumps(record["raw"], ensure_ascii=False),
                scrape_run_id=run_id,
            )
        )
        written += 1
    session.commit()
    return written, skipped


def stored_weeks(session: Session, season_year: int) -> set[int]:
    """The distinct jornada weeks already stored for a season, via
    `select(distinct(...))` — what the backfill (Task 9) checks before
    re-fetching a week it already has."""
    rows = session.exec(
        select(distinct(PlayerGameweekPoints.week)).where(
            PlayerGameweekPoints.season_year == season_year
        )
    ).all()
    return set(rows)


def weeks_to_refetch(session: Session, season_year: int) -> set[int]:
    """Stored weeks of a season whose rows may be incomplete.

    Two ways a stored week goes stale. It was captured while in progress
    (`is_provisional`), and the ingest never re-fetched it once a later week
    existed — 2026/27 week 6 sat at 6 of 20 clubs for two weeks that way.
    Or it was fetched as final while a match was postponed, and that match
    has since been played: a `Fixture` of the same matchday is final and
    kicked off after the run that stored the week started.
    """
    provisional = set(
        session.exec(
            select(distinct(PlayerGameweekPoints.week))
            .where(PlayerGameweekPoints.season_year == season_year)
            .where(PlayerGameweekPoints.is_provisional == True)  # noqa: E712
        ).all()
    )
    captured = {
        week: as_utc(started)
        for week, started in session.exec(
            select(PlayerGameweekPoints.week, func.max(ScrapeRun.started_at))
            .join(ScrapeRun, ScrapeRun.id == PlayerGameweekPoints.scrape_run_id)
            .where(PlayerGameweekPoints.season_year == season_year)
            .group_by(PlayerGameweekPoints.week)
        ).all()
    }
    late = {
        f.matchday
        for f in session.exec(select(Fixture).where(Fixture.is_final == True)).all()  # noqa: E712
        if f.matchday in captured and as_utc(f.kickoff_utc) > captured[f.matchday]
    }
    return provisional | late


def get_dataset_runs(session: Session, scrape_run_id: int) -> list[DatasetRun]:
    """Every dataset outcome recorded within one scrape run, oldest first."""
    return list(
        session.exec(
            select(DatasetRun)
            .where(DatasetRun.scrape_run_id == scrape_run_id)
            .order_by(DatasetRun.id)
        ).all()
    )


def latest_dataset_runs(session: Session) -> dict[str, DatasetRun]:
    """The most recent `DatasetRun` per `dataset` name, regardless of which
    `scrape_run_id` it belongs to — "most recent" meaning highest `id`,
    since `DatasetRun.id` is monotonically assigned in start order."""
    latest: dict[str, DatasetRun] = {}
    for run in session.exec(select(DatasetRun).order_by(DatasetRun.id)).all():
        latest[run.dataset] = run
    return latest


def get_player(session: Session, player_id: int) -> Player | None:
    """Identity only. `None` is the 404 signal, not an error."""
    return session.get(Player, player_id)


def get_snapshot_history(session: Session, player_id: int) -> list[PlayerSnapshot]:
    """Every market snapshot for one player, oldest first — the DETAIL-02
    series. The composite PK leads with `as_of`, so this is a scan filtered
    by player rather than an index seek; at ~6k rows that is free."""
    return list(
        session.exec(
            select(PlayerSnapshot)
            .where(PlayerSnapshot.player_id == player_id)
            .order_by(PlayerSnapshot.as_of)
        ).all()
    )


def get_gameweek_points(session: Session, player_id: int) -> list[PlayerGameweekPoints]:
    """Both seasons, ordered so the caller can render one continuous
    timeline without re-sorting."""
    return list(
        session.exec(
            select(PlayerGameweekPoints)
            .where(PlayerGameweekPoints.player_id == player_id)
            .order_by(PlayerGameweekPoints.season_year, PlayerGameweekPoints.week)
        ).all()
    )


def get_season_stats(session: Session, player_id: int) -> list[PlayerSeasonStats]:
    """Oldest season first, so the page's columns read left-to-right in
    chronological order. Commonly length 1 — 283 of 642 players have no
    2025/26 row at all."""
    return list(
        session.exec(
            select(PlayerSeasonStats)
            .where(PlayerSeasonStats.player_id == player_id)
            .order_by(PlayerSeasonStats.season_year)
        ).all()
    )


def get_squad_membership(session: Session, player_id: int) -> SquadMember | None:
    """The *current* membership specifically. A sold row is kept forever for
    realized profit and loss (see SquadMember's own docstring), so filtering
    on `sold_at is None` is what separates "owned" from "once owned"."""
    return session.exec(
        select(SquadMember)
        .where(SquadMember.player_id == player_id)
        .where(SquadMember.sold_at.is_(None))
    ).first()


def get_latest_predictions(session: Session, player_id: int) -> dict[str, float]:
    """The most recent stored value per source. Ordering ascending by date
    and letting later rows overwrite earlier ones gives latest-per-source in
    one query — and stays correct if one source lags another, which a single
    global `MAX(as_of)` would not."""
    rows = session.exec(
        select(SourcePrediction)
        .where(SourcePrediction.player_id == player_id)
        .order_by(SourcePrediction.source, SourcePrediction.as_of)
    ).all()
    return {row.source: row.value for row in rows}


def get_season_week_ranges(session: Session) -> dict[int, int]:
    """Highest stored jornada per season, across every player (P-03).

    The chart's axis cannot come from one player's own rows: a player who
    was not in the league in week 1 has no week-1 row, and neither does a
    week nobody has played yet. Both look identical from inside a single
    player's record, so the league's own range is what makes an absent week
    visible as a gap."""
    rows = session.exec(
        select(PlayerGameweekPoints.season_year, func.max(PlayerGameweekPoints.week)).group_by(
            PlayerGameweekPoints.season_year
        )
    ).all()
    return {season_year: max_week for season_year, max_week in rows}


def get_squad_value_history(session: Session) -> list[tuple[date, int]]:
    """SQUAD-04's value series — reconstructed from *every* `SquadMember`
    row, not just the current squad, so a past sale doesn't rewrite what the
    squad was actually worth while it was held. A member counts toward a
    date if `acquired_on <= date < sold_at` (still held that day), and
    contributes their market-value snapshot for that exact date where one
    exists, falling back to `purchase_price` otherwise — the same fallback
    `core.squad_rules.SquadMember.effective_value` uses, for the same reason:
    a missing snapshot must not read as the player being worth zero.

    Dates are drawn from `PlayerSnapshot` rows for players who were ever
    held, and a date with nobody held yet (before the squad existed) is
    omitted rather than plotted as a zero.
    """
    members = session.exec(select(SquadMember)).all()
    if not members:
        return []

    player_ids = {m.player_id for m in members}
    snapshots = session.exec(
        select(PlayerSnapshot).where(PlayerSnapshot.player_id.in_(player_ids))
    ).all()
    value_by_player_date = {(s.player_id, s.as_of): s.market_value for s in snapshots}
    # Every scrape date the app has, not only dates a squad member happens to
    # have a row for — a held player missing *this* date's snapshot (a
    # rejected scrape for them alone) must still fall back to their purchase
    # price on a date the scraper otherwise ran, rather than the date
    # vanishing from the series entirely.
    all_dates = sorted(session.exec(select(distinct(PlayerSnapshot.as_of))).all())

    history: list[tuple[date, int]] = []
    for as_of in all_dates:
        total = 0
        held_any = False
        for member in members:
            sold_on = member.sold_at.date() if member.sold_at is not None else None
            if member.acquired_on > as_of or (sold_on is not None and as_of >= sold_on):
                continue
            held_any = True
            market_value = value_by_player_date.get((member.player_id, as_of))
            total += market_value if market_value is not None else member.purchase_price
        if held_any:
            history.append((as_of, total))
    return history


@dataclass(frozen=True)
class SquadJornadaPoints:
    """One jornada's points, summed across the current squad."""

    season_year: int
    week: int
    points: int
    is_provisional: bool


def get_squad_points_history(session: Session) -> list[SquadJornadaPoints]:
    """SQUAD-04's points series — the *current* squad only, summed across
    every recorded jornada. Unlike value history, this cannot be
    reconstructed from actual past composition: the fixture calendar
    (INGEST-04) that would map a jornada number to a calendar date was
    retired with the lineup cut, so there is no way to know who was actually
    held during a given past week. Reads as "if this squad had played all
    season," not as a record of what changed hands when."""
    player_ids = list(
        session.exec(select(SquadMember.player_id).where(SquadMember.sold_at.is_(None))).all()
    )
    if not player_ids:
        return []

    rows = session.exec(
        select(PlayerGameweekPoints).where(PlayerGameweekPoints.player_id.in_(player_ids))
    ).all()

    grouped: dict[tuple[int, int], list[PlayerGameweekPoints]] = {}
    for row in rows:
        grouped.setdefault((row.season_year, row.week), []).append(row)

    return [
        SquadJornadaPoints(
            season_year=season_year,
            week=week,
            points=sum(r.points for r in group),
            is_provisional=any(r.is_provisional for r in group),
        )
        for (season_year, week), group in sorted(grouped.items())
    ]


# --- League-wide stats (STATS-01…04) ---
#
# Every function below is a pure read-model over `PlayerGameweekPoints` /
# `PlayerSeasonStats` joined to `Player` for name/team/position — no new
# table, no write path. Team names come from the *current* `Player.team`,
# never historized, even when the season being queried is a past one.


@dataclass(frozen=True)
class JornadaScoreRow:
    """One player's score for one jornada, with identity joined in.
    `week` and `is_provisional` are carried even though `get_jornada_scores`
    fixes both to a single value per call — `get_jornada_point_records`
    (Task 5) spans every week of a season and needs both to vary per row.

    `market_value`/`price_per_point` default to `None` because only
    `get_jornada_scores` populates them (the Scores tab's context columns);
    `get_jornada_point_records` spans every week of a season, where "current
    value" would misleadingly attach today's price to a past jornada."""

    player_id: int
    name: str
    team: str
    position: str
    week: int
    points: int
    is_provisional: bool
    market_value: int | None = None
    price_per_point: float | None = None


def get_stats_seasons(session: Session) -> list[int]:
    """Distinct seasons with at least one jornada score, newest first —
    backs the `/stats` page's shared season selector. A season with zero
    `PlayerGameweekPoints` rows never appears, so it can never be selected
    into a dead page."""
    rows = session.exec(
        select(distinct(PlayerGameweekPoints.season_year)).order_by(
            PlayerGameweekPoints.season_year.desc()
        )
    ).all()
    return list(rows)


def get_jornada_scores(session: Session, season_year: int, week: int) -> list[JornadaScoreRow]:
    """Every player with a recorded score for this exact jornada, highest
    first. Only players with an actual row — no zero-filling for players
    who didn't feature that week, which would misrepresent "didn't play" as
    "scored zero".

    Also carries each player's *current* market value and season price/point
    (the latest `PlayerSnapshot`, outer-joined so a player with no snapshot
    yet still gets a row with `None` rather than disappearing) — context for
    "who scored well and is still cheap," not a value computed from this
    jornada's own points, which would be a different, noisier ratio."""
    latest_date = session.exec(select(func.max(PlayerSnapshot.as_of))).one()
    rows = session.exec(
        select(PlayerGameweekPoints, Player, PlayerSnapshot)
        .join(Player, Player.id == PlayerGameweekPoints.player_id)
        .outerjoin(
            PlayerSnapshot,
            (PlayerSnapshot.player_id == PlayerGameweekPoints.player_id)
            & (PlayerSnapshot.as_of == latest_date),
        )
        .where(PlayerGameweekPoints.season_year == season_year)
        .where(PlayerGameweekPoints.week == week)
        .order_by(PlayerGameweekPoints.points.desc(), Player.name.asc())
    ).all()
    return [
        JornadaScoreRow(
            player_id=player.id,
            name=player.name,
            team=player.team,
            position=player.position,
            week=gw.week,
            points=gw.points,
            is_provisional=gw.is_provisional,
            market_value=snapshot.market_value if snapshot is not None else None,
            price_per_point=snapshot.price_per_point if snapshot is not None else None,
        )
        for gw, player, snapshot in rows
    ]


@dataclass(frozen=True)
class TeamJornadaRow:
    team: str
    total_points: int
    player_count: int
    average_points: float


def get_team_jornada_summary(session: Session, season_year: int, week: int) -> list[TeamJornadaRow]:
    """One row per team that fielded at least one scoring player this
    jornada, ranked by total points descending — the Scores tab's team
    table."""
    rows = session.exec(
        select(
            Player.team,
            func.sum(PlayerGameweekPoints.points),
            func.count(PlayerGameweekPoints.player_id),
        )
        .join(Player, Player.id == PlayerGameweekPoints.player_id)
        .where(PlayerGameweekPoints.season_year == season_year)
        .where(PlayerGameweekPoints.week == week)
        .group_by(Player.team)
        .order_by(func.sum(PlayerGameweekPoints.points).desc())
    ).all()
    return [
        TeamJornadaRow(
            team=team,
            total_points=total,
            player_count=count,
            average_points=total / count,
        )
        for team, total, count in rows
    ]


@dataclass(frozen=True)
class StreakRow:
    player_id: int
    name: str
    team: str
    position: str
    total_points: int
    weeks_counted: int


def get_streak_leaderboard(
    session: Session, season_year: int, end_week: int, window: int
) -> list[StreakRow]:
    """Sums each player's points over `[max(1, end_week - window + 1),
    end_week]`, ranked highest first. `weeks_counted` is how many of the
    window's weeks the player actually has a row for — never assumed to be
    a full window, so a short window near the season's start is visible on
    the row rather than silently averaged away."""
    start_week = max(1, end_week - window + 1)
    rows = session.exec(
        select(
            Player.id,
            Player.name,
            Player.team,
            Player.position,
            func.sum(PlayerGameweekPoints.points),
            func.count(PlayerGameweekPoints.week),
        )
        .join(Player, Player.id == PlayerGameweekPoints.player_id)
        .where(PlayerGameweekPoints.season_year == season_year)
        .where(PlayerGameweekPoints.week >= start_week)
        .where(PlayerGameweekPoints.week <= end_week)
        .group_by(Player.id, Player.name, Player.team, Player.position)
        .order_by(func.sum(PlayerGameweekPoints.points).desc())
    ).all()
    return [
        StreakRow(
            player_id=player_id,
            name=name,
            team=team,
            position=position,
            total_points=total,
            weeks_counted=count,
        )
        for player_id, name, team, position, total, count in rows
    ]


def get_jornada_point_records(
    session: Session, season_year: int, limit: int = 10
) -> list[JornadaScoreRow]:
    """Top single-jornada performances for the season, across every week.
    Ties broken by `(week, player_id)` ascending for a stable, deterministic
    order — not meaningfully "correct" over any other tiebreak, just fixed
    so a rerun never reshuffles equal scores."""
    rows = session.exec(
        select(PlayerGameweekPoints, Player)
        .join(Player, Player.id == PlayerGameweekPoints.player_id)
        .where(PlayerGameweekPoints.season_year == season_year)
        .order_by(
            PlayerGameweekPoints.points.desc(),
            PlayerGameweekPoints.week.asc(),
            PlayerGameweekPoints.player_id.asc(),
        )
        .limit(limit)
    ).all()
    return [
        JornadaScoreRow(
            player_id=player.id,
            name=player.name,
            team=player.team,
            position=player.position,
            week=gw.week,
            points=gw.points,
            is_provisional=gw.is_provisional,
        )
        for gw, player in rows
    ]


@dataclass(frozen=True)
class StatRecordRow:
    field: str
    player_id: int
    name: str
    team: str
    value: float


def get_season_stat_records(session: Session, season_year: int) -> list[StatRecordRow]:
    """For each field in `SEASON_RECORD_FIELDS`, the single player with the
    highest value that season. A field is skipped entirely — not returned
    with a zero/null row — if every player's value is 0 or None, since
    "nobody recorded this" and "somebody recorded zero" are different facts
    and only the second is a record. Runs one query per field (24 total);
    fine at this app's scale, a single-user local tool."""
    records: list[StatRecordRow] = []
    for camel_field in SEASON_RECORD_FIELDS:
        column = getattr(PlayerSeasonStats, column_name(camel_field))
        row = session.exec(
            select(PlayerSeasonStats, Player)
            .join(Player, Player.id == PlayerSeasonStats.player_id)
            .where(PlayerSeasonStats.season_year == season_year)
            .where(column.is_not(None))
            .where(column != 0)
            .order_by(column.desc(), PlayerSeasonStats.player_id.asc())
        ).first()
        if row is None:
            continue
        stats, player = row
        records.append(
            StatRecordRow(
                field=camel_field,
                player_id=player.id,
                name=player.name,
                team=player.team,
                value=getattr(stats, column_name(camel_field)),
            )
        )
    return records


@dataclass(frozen=True)
class LeaderboardRow:
    player_id: int
    name: str
    team: str
    position: str
    value: float
    total_points: int


def get_season_leaderboard(
    session: Session,
    season_year: int,
    stat: str,
    position: str | None = None,
    team: str | None = None,
) -> list[LeaderboardRow]:
    """Every player with a non-null value for `stat` that season, optionally
    narrowed by position/team, ordered by the stat descending. A stored
    zero is a real observation and sorts normally; only `None` is excluded.
    As of this writing the scraper's parser defaults an omitted counter to
    0 rather than `None` (`scraper/sources/af_season_stats.py`), so in
    practice every row is non-null and this exclusion is currently inert —
    it activates automatically if that parser is ever changed to preserve
    "the source never published a figure" as `None`. Ties break by total
    season points, then name, for a stable order."""
    column = getattr(PlayerSeasonStats, column_name(stat))
    query = (
        select(PlayerSeasonStats, Player)
        .join(Player, Player.id == PlayerSeasonStats.player_id)
        .where(PlayerSeasonStats.season_year == season_year)
        .where(column.is_not(None))
    )
    if position is not None:
        query = query.where(Player.position == position)
    if team is not None:
        query = query.where(Player.team == team)
    query = query.order_by(column.desc(), PlayerSeasonStats.total_points.desc(), Player.name.asc())

    rows = session.exec(query).all()
    return [
        LeaderboardRow(
            player_id=player.id,
            name=player.name,
            team=player.team,
            position=player.position,
            value=getattr(stats, column_name(stat)),
            total_points=stats.total_points,
        )
        for stats, player in rows
    ]


# --- Watchlist (DETAIL-04) -------------------------------------------------


def get_watchlist_player_ids(session: Session) -> list[int]:
    """Oldest-added first, so the list reads in the order the owner built it.
    Player id breaks the (practically impossible) tie on identical stamps."""
    return list(
        session.exec(
            select(WatchlistEntry.player_id).order_by(
                WatchlistEntry.added_at, WatchlistEntry.player_id
            )
        ).all()
    )


def add_to_watchlist(session: Session, player_id: int) -> None:
    """Idempotent: re-adding keeps the original `added_at` rather than moving
    the player to the end, so a double click cannot reorder the list."""
    if session.get(WatchlistEntry, player_id) is not None:
        return
    session.add(WatchlistEntry(player_id=player_id, added_at=datetime.now(UTC)))
    session.commit()


def remove_from_watchlist(session: Session, player_id: int) -> bool:
    """`True` if an entry was removed, `False` if there was none — removing
    an absent player is a no-op, not an error."""
    entry = session.get(WatchlistEntry, player_id)
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True


# --- Fixture calendar (INGEST-04, restored 2026-09-27) ----------------------


def upsert_fixtures(session: Session, records) -> int:
    """Insert new fixtures / update existing ones in place, keyed on the
    source's own `fixture_id`.

    Keyed on `fixture_id` and never on `(matchday, slot)`: a postponed match
    keeps its original jornada number while moving to a date after a later
    jornada has begun, so any positional key would collide or reorder.
    Nothing is ever deleted — the source publishes a rolling five-jornada
    window, and a fixture that has scrolled out of it is history, not
    absence.
    """
    now = datetime.now(UTC)
    for record in records:
        row = session.get(Fixture, record.fixture_id)
        if row is None:
            row = Fixture(fixture_id=record.fixture_id, scraped_at=now)
        row.matchday = record.matchday
        row.kickoff_utc = record.kickoff_utc
        row.kickoff_confirmed = record.kickoff_confirmed
        row.is_final = record.is_final
        row.home_team = record.home_team
        row.away_team = record.away_team
        row.home_team_id = record.home_team_id
        row.away_team_id = record.away_team_id
        row.home_difficulty = record.home_difficulty
        row.away_difficulty = record.away_difficulty
        row.scraped_at = now
        session.add(row)
    session.commit()
    return len(records)


def get_fixtures(session: Session) -> list[Fixture]:
    """Every stored fixture, kickoffs normalised back to UTC-aware so no
    caller can compare a naive instant against `datetime.now(UTC)`."""
    rows = session.exec(select(Fixture).order_by(Fixture.kickoff_utc, Fixture.fixture_id)).all()
    for row in rows:
        row.kickoff_utc = as_utc(row.kickoff_utc)
    return list(rows)


def get_team_week_points(session: Session, season_year: int) -> dict[str, list[float]]:
    """Each team's total fantasy points per *final* jornada of a season, in
    week order — the input to `core.fixture_difficulty.team_strength`.

    Grouped on `Player.team`, i.e. each player's *current* club. The active
    jornada is excluded because its points still move — the season's highest
    week, when flagged. The flag alone is not trusted: ingest used to leave
    it set on finished weeks (2026/27 week 2), which silently dropped them.
    A club-week with fewer than `MIN_TEAM_ROWS` rows is a club that didn't
    play (or wasn't captured) and is left out rather than read as a low total.
    """
    rows = session.exec(
        select(Player.team, PlayerGameweekPoints.week,
               func.sum(PlayerGameweekPoints.points), func.count(),
               func.max(PlayerGameweekPoints.is_provisional))
        .join(Player, Player.id == PlayerGameweekPoints.player_id)
        .where(PlayerGameweekPoints.season_year == season_year)
        .group_by(Player.team, PlayerGameweekPoints.week)
        .order_by(Player.team, PlayerGameweekPoints.week)
    ).all()
    top = max((week for _t, week, *_ in rows), default=None)
    active = top if any(week == top and flag for _t, week, _s, _n, flag in rows) else None
    out: dict[str, list[float]] = {}
    for team, week, total, n, _flag in rows:
        if week == active or n < MIN_TEAM_ROWS:
            continue
        out.setdefault(team, []).append(float(total))
    return out
