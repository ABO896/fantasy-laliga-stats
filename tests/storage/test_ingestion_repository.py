from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from scraper.sources.af_season_stats import parse_season_stats
from storage.models import (
    Fixture,
    Player,
    PlayerGameweekPoints,
    PlayerSeasonStats,
    ScrapeRun,
    SourcePrediction,
)
from storage.repository import (
    _SEASON_STATS_RECORD_FIELDS,
    finish_dataset_run,
    get_dataset_runs,
    latest_dataset_runs,
    replace_predictions,
    resolve_player_ids,
    resolve_players,
    start_dataset_run,
    stored_weeks,
    upsert_gameweek_points,
    upsert_season_stats,
    weeks_to_refetch,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "phase7"


def _player(session, slug: str) -> Player:
    now = datetime.now(UTC)
    p = Player(
        external_id=slug, name=slug, team="T", position="MED", created_at=now, updated_at=now
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _run(session) -> ScrapeRun:
    r = ScrapeRun(started_at=datetime.now(UTC), status="running")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _rec(slug, name, position, points, is_coach=False):
    return {
        "slug": slug,
        "player_name": name,
        "position": position,
        "team_name": "T",
        "is_coach": is_coach,
        "points": points,
    }


def test_unknown_players_are_skipped_and_counted(session):
    _player(session, "known-1")
    run = _run(session)
    records = [_rec("known-1", "known-1", "MED", 9), _rec("departed-2", "Departed", "DEL", 12)]
    res = resolve_players(session, records, name_field="player_name")
    written = upsert_gameweek_points(session, 2025, 7, False, records, res, run.id)
    assert written == 1
    assert (res.by_slug, res.unresolved) == (1, 1)


def test_a_slugless_player_resolves_by_name_and_position(session):
    """The jornada payload omits `slug` for real players — Bellingham among
    them last season. Resolving by (name, position) is what keeps their
    points; without it a successful-looking run drops them."""
    now = datetime.now(UTC)
    session.add(
        Player(
            external_id="j-bellingham-129718",
            name="Bellingham",
            team="Real Madrid",
            position="MED",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    res = resolve_players(session, [_rec(None, "Bellingham", "MED", 10)], name_field="player_name")
    assert res.by_name == 1 and res.unresolved == 0


def test_a_contradicting_position_refuses_the_match(session):
    """Position is the corroborating field precisely so a same-name player
    in a different position is not silently credited with the points."""
    now = datetime.now(UTC)
    session.add(
        Player(
            external_id="somebody-1",
            name="Bellingham",
            team="Real Madrid",
            position="DEL",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    res = resolve_players(session, [_rec(None, "Bellingham", "MED", 10)], name_field="player_name")
    assert res.by_name == 0 and res.unresolved == 1


def test_a_coach_is_never_resolved_to_a_same_named_player(session):
    now = datetime.now(UTC)
    session.add(
        Player(
            external_id="coach-name-1",
            name="Same Name",
            team="T",
            position="MED",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    res = resolve_players(
        session, [_rec(None, "Same Name", "MED", 0, is_coach=True)], name_field="player_name"
    )
    assert res.coaches == 1 and res.by_name == 0


def test_rewriting_a_week_replaces_rather_than_duplicates(session):
    _player(session, "known-1")
    run = _run(session)
    r3 = [_rec("known-1", "known-1", "MED", 3)]
    r8 = [_rec("known-1", "known-1", "MED", 8)]
    res = resolve_players(session, r3, name_field="player_name")
    upsert_gameweek_points(session, 2026, 2, True, r3, res, run.id)
    upsert_gameweek_points(session, 2026, 2, True, r8, res, run.id)
    assert stored_weeks(session, 2026) == {2}
    from sqlmodel import select

    from storage.models import PlayerGameweekPoints

    rows = session.exec(select(PlayerGameweekPoints)).all()
    assert len(rows) == 1 and rows[0].points == 8


def test_stored_weeks_is_scoped_to_its_season(session):
    _player(session, "known-1")
    run = _run(session)
    r1 = [_rec("known-1", "known-1", "MED", 1)]
    r2 = [_rec("known-1", "known-1", "MED", 2)]
    res = resolve_players(session, r1, name_field="player_name")
    upsert_gameweek_points(session, 2025, 4, False, r1, res, run.id)
    upsert_gameweek_points(session, 2026, 1, False, r2, res, run.id)
    assert stored_weeks(session, 2025) == {4}
    assert stored_weeks(session, 2026) == {1}


def test_stats_records_use_the_same_resolver_with_their_own_name_field(session):
    """One resolver serves both datasets; only the name field differs.
    This is what keeps Lamine Yamal — whose statistics row has no slug."""
    now = datetime.now(UTC)
    session.add(
        Player(
            external_id="lamine-yamal-386828",
            name="Lamine Yamal",
            team="Barcelona",
            position="DEL",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    records = [
        {
            "slug": None,
            "nickname": "Lamine Yamal",
            "position": "DEL",
            "team_name": "Barcelona",
            "is_coach": False,
        },
        {
            "slug": None,
            "nickname": "Some Coach",
            "position": None,
            "team_name": "Barcelona",
            "is_coach": True,
        },
        {
            "slug": None,
            "nickname": "Departed Guy",
            "position": "MED",
            "team_name": "Getafe",
            "is_coach": False,
        },
    ]
    res = resolve_players(session, records, name_field="nickname")
    assert res.player_id_by_index.keys() == {0}
    assert (res.by_slug, res.by_name, res.coaches, res.unresolved) == (0, 1, 1, 1)


def test_an_ambiguous_name_and_position_pair_is_not_guessed(session):
    now = datetime.now(UTC)
    for ext in ("dupe-1", "dupe-2"):
        session.add(
            Player(
                external_id=ext,
                name="Same Name",
                team="Barcelona",
                position="MED",
                created_at=now,
                updated_at=now,
            )
        )
    session.commit()
    res = resolve_players(
        session,
        [
            {
                "slug": None,
                "nickname": "Same Name",
                "position": "MED",
                "team_name": "Barcelona",
                "is_coach": False,
            }
        ],
        name_field="nickname",
    )
    assert res.player_id_by_index == {}
    assert res.unresolved == 1


def test_latest_dataset_runs_returns_the_most_recent_per_dataset(session):
    run = _run(session)
    first = start_dataset_run(session, run.id, "jornada_points")
    finish_dataset_run(session, first, "failed", errors=["nope"])
    second = start_dataset_run(session, run.id, "jornada_points")
    finish_dataset_run(session, second, "success", row_count=248)
    latest = latest_dataset_runs(session)
    assert latest["jornada_points"].status == "success"
    assert latest["jornada_points"].row_count == 248


def _navarro_players(session):
    """Two different footballers who share a name and position: one has a
    `Player` row (matched by slug), one does not (would only ever be
    found via the name/position fallback) — the real defect this guards
    against."""
    now = datetime.now(UTC)
    session.add(
        Player(
            external_id="navarro-athletic",
            name="Navarro",
            team="Athletic Club",
            position="MED",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_a_slug_match_is_never_displaced_by_a_colliding_fallback(session):
    """The Navarro case: an exact slug match for the Athletic Club Navarro,
    and a slugless Valencia Navarro (same name, same position, no `Player`
    row of his own) whose fallback would otherwise land on the same
    player. The fallback must be refused, not silently attributed."""
    _navarro_players(session)
    records = [
        _rec("navarro-athletic", "Navarro", "MED", 5),
        _rec(None, "Navarro", "MED", 7),
    ]
    res = resolve_players(session, records, name_field="player_name")
    assert res.player_id_by_index.keys() == {0}
    assert (res.by_slug, res.by_name, res.unresolved) == (1, 0, 1)


def test_a_slug_match_wins_even_when_the_fallback_record_comes_first(session):
    """Same scenario, opposite record order — proves the slug match's
    victory does not depend on which record the resolver happens to see
    first."""
    _navarro_players(session)
    records = [
        _rec(None, "Navarro", "MED", 7),
        _rec("navarro-athletic", "Navarro", "MED", 5),
    ]
    res = resolve_players(session, records, name_field="player_name")
    assert res.player_id_by_index.keys() == {1}
    assert (res.by_slug, res.by_name, res.unresolved) == (1, 0, 1)


def test_two_colliding_fallbacks_refuse_each_other(session):
    """Two slugless records that both resolve, unambiguously, to the same
    single player: neither is stored, since storing either would be an
    arbitrary pick between two records that both claim the same player."""
    _navarro_players(session)
    records = [
        _rec(None, "Navarro", "MED", 7),
        _rec(None, "Navarro", "MED", 3),
    ]
    res = resolve_players(session, records, name_field="player_name")
    assert res.player_id_by_index == {}
    assert (res.by_name, res.unresolved) == (0, 2)


def test_a_second_record_with_the_same_slug_claims_the_player_once(session):
    """Injectivity is documented as a property of this resolver, but was
    enforced only for name/position fallbacks — two records carrying the
    *same* slug both claimed the player, and `PlayerGameweekPoints`'s
    (season_year, week, player_id) key then refused the insert. That is
    what killed the first real backfill, on 2025 week 16, where the source
    listed `alfon-gonzalez-119213` under both of his club registrations.

    A repeat of a slug is the same player seen twice, so it is counted
    `duplicates` — not `unresolved`, which means "no player of his own in
    the market" and drives the run summary's skipped count.
    """
    _player(session, "known-1")
    run = _run(session)
    records = [_rec("known-1", "known-1", "MED", 9), _rec("known-1", "known-1", "MED", 9)]

    res = resolve_players(session, records, name_field="player_name")

    assert list(res.player_id_by_index) == [0]
    assert (res.by_slug, res.duplicates, res.unresolved) == (1, 1, 0)
    assert upsert_gameweek_points(session, 2025, 16, False, records, res, run.id) == 1


def test_resolution_counts_always_partition_the_batch(session):
    _navarro_players(session)
    records = [
        _rec("navarro-athletic", "Navarro", "MED", 5),  # by_slug
        _rec("navarro-athletic", "Navarro", "MED", 5),  # duplicate: same slug again
        _rec(None, "Navarro", "MED", 7),  # refused: collides with the slug match
        _rec(None, "Nobody Knows", "DEL", 1),  # unresolved: no player at all
        _rec(None, "Coach Man", "MED", 0, is_coach=True),  # coach
    ]
    res = resolve_players(session, records, name_field="player_name")
    assert res.by_slug + res.by_name + res.coaches + res.unresolved + res.duplicates == len(records)
    assert (res.by_slug, res.by_name, res.coaches, res.unresolved, res.duplicates) == (
        1,
        0,
        1,
        2,
        1,
    )


def test_upsert_gameweek_points_does_not_touch_a_sibling_week(session):
    """The delete in `upsert_gameweek_points` is scoped to `(season_year,
    week)`. Varying season and week together (as in
    `test_rewriting_a_week_replaces_rather_than_duplicates`) would still
    pass even if the `week` predicate were dropped from the delete,
    because the two writes would then land in different seasons anyway.
    This test holds the season fixed and varies only the week, so a
    missing `week` predicate — which would wipe the whole season on every
    write — fails here."""
    _player(session, "known-1")
    run = _run(session)
    r1 = [_rec("known-1", "known-1", "MED", 4)]
    r2 = [_rec("known-1", "known-1", "MED", 6)]
    res = resolve_players(session, r1, name_field="player_name")
    upsert_gameweek_points(session, 2025, 10, False, r1, res, run.id)
    upsert_gameweek_points(session, 2025, 11, False, r2, res, run.id)
    assert stored_weeks(session, 2025) == {10, 11}


def _stats_record(slug, nickname, position, total_points, is_coach=False):
    """A minimal but complete season-stats record — every field
    `upsert_season_stats` reads, zero-filled except the ones asserted on."""
    values = dict.fromkeys(_SEASON_STATS_RECORD_FIELDS, 0)
    values["total_points"] = total_points
    values["average_points"] = float(total_points)
    values["ideal_formation_count"] = None
    return {
        "slug": slug,
        "nickname": nickname,
        "position": position,
        "team_name": "T",
        "is_coach": is_coach,
        "raw": {"totalPoints": total_points},
        **values,
    }


def test_upsert_season_stats_does_not_touch_a_sibling_season(session):
    """Mirrors `test_stored_weeks_is_scoped_to_its_season` for the season
    dimension: two different `season_year` writes must both survive, so a
    delete that forgets to scope by `season_year` (wiping every season on
    each write) fails here rather than passing by accident."""
    _player(session, "known-1")
    run = _run(session)
    r2025 = [_stats_record("known-1", "known-1", "MED", 100)]
    r2026 = [_stats_record("known-1", "known-1", "MED", 5)]
    res = resolve_players(session, r2025, name_field="nickname")
    written_2025 = upsert_season_stats(session, 2025, r2025, res, run.id)
    written_2026 = upsert_season_stats(session, 2026, r2026, res, run.id)
    assert (written_2025, written_2026) == (1, 1)

    from sqlmodel import select

    rows = {row.season_year: row.total_points for row in session.exec(select(PlayerSeasonStats))}
    assert rows == {2025: 100, 2026: 5}


def test_replace_predictions_same_as_of_rerun_replaces_not_duplicates(session):
    """Predictions are a daily snapshot — a same-day re-run (e.g. the
    scraper retried after a transient failure) must replace the day's
    rows rather than accumulate them."""
    _player(session, "known-1")
    run = _run(session)
    as_of = date(2026, 8, 23)
    player_ids = resolve_player_ids(session, ["known-1"])
    records = [{"external_id": "known-1", "source": "points", "value": 5.5, "raw": {"a": 1}}]

    written1, skipped1 = replace_predictions(
        session, as_of, records, player_ids, run.id, {"points"}
    )
    assert (written1, skipped1) == (1, 0)

    records_rerun = [{"external_id": "known-1", "source": "points", "value": 9.0, "raw": {"a": 2}}]
    written2, skipped2 = replace_predictions(
        session, as_of, records_rerun, player_ids, run.id, {"points"}
    )
    assert (written2, skipped2) == (1, 0)

    from sqlmodel import select

    rows = session.exec(select(SourcePrediction)).all()
    assert len(rows) == 1 and rows[0].value == 9.0


def test_replace_predictions_skips_an_unresolved_slug(session):
    _player(session, "known-1")
    run = _run(session)
    player_ids = resolve_player_ids(session, ["known-1", "departed-2"])
    records = [
        {"external_id": "known-1", "source": "points", "value": 5.5, "raw": {}},
        {"external_id": "departed-2", "source": "points", "value": 1.0, "raw": {}},
    ]
    written, skipped = replace_predictions(
        session, date(2026, 8, 23), records, player_ids, run.id, {"points"}
    )
    assert (written, skipped) == (1, 1)


def test_replace_predictions_does_not_touch_a_sibling_datasets_sources(session):
    """`ingest_points_predictions` and `ingest_market_predictions` both
    write `SourcePrediction` rows for the same `as_of`, one after the
    other. A delete scoped to `as_of` alone therefore lets the second
    dataset silently wipe the first: the live refresh on 2026-08-27
    recorded `points_predictions` as success with 495 rows written, and
    zero of them survived the `market_predictions` ingest that followed.
    Both datasets still reported success, so the loss was invisible.

    Same defect shape as the one
    `test_upsert_gameweek_points_does_not_touch_a_sibling_week` guards:
    the delete must be scoped to everything the write is keyed on, not
    just the part that varies between days. A caller declares which
    sources it owns rather than the sources being inferred from
    `records`, because a market list can legitimately be empty on a quiet
    day and an inferred scope would then leave that source's stale rows
    behind.
    """
    _player(session, "known-1")
    run = _run(session)
    as_of = date(2026, 8, 23)
    player_ids = resolve_player_ids(session, ["known-1"])

    points = [{"external_id": "known-1", "source": "points", "value": 5.5, "raw": {}}]
    replace_predictions(session, as_of, points, player_ids, run.id, {"points"})

    market = [
        {"external_id": "known-1", "source": "market_top_risers", "value": 1.0, "raw": {}},
    ]
    replace_predictions(
        session,
        as_of,
        market,
        player_ids,
        run.id,
        {"market_top_risers", "market_top_fallers"},
    )

    from sqlmodel import select

    sources = {row.source for row in session.exec(select(SourcePrediction))}
    assert sources == {"points", "market_top_risers"}


def test_replace_predictions_clears_a_source_that_is_empty_on_a_rerun(session):
    """A source this call owns but has no rows for must still be cleared —
    otherwise a market list that goes empty between two same-day runs
    leaves the earlier run's rows standing as if they were today's."""
    _player(session, "known-1")
    run = _run(session)
    as_of = date(2026, 8, 23)
    player_ids = resolve_player_ids(session, ["known-1"])
    owned = {"market_top_risers", "market_top_fallers"}

    first = [
        {"external_id": "known-1", "source": "market_top_risers", "value": 1.0, "raw": {}},
        {"external_id": "known-1", "source": "market_top_fallers", "value": 2.0, "raw": {}},
    ]
    replace_predictions(session, as_of, first, player_ids, run.id, owned)

    second = [{"external_id": "known-1", "source": "market_top_fallers", "value": 3.0, "raw": {}}]
    replace_predictions(session, as_of, second, player_ids, run.id, owned)

    from sqlmodel import select

    rows = [(r.source, r.value) for r in session.exec(select(SourcePrediction))]
    assert rows == [("market_top_fallers", 3.0)]


def test_resolve_player_ids_is_a_slug_only_lookup(session):
    _player(session, "known-1")
    ids = resolve_player_ids(session, ["known-1", "unknown-2"])
    assert set(ids) == {"known-1"}


def test_get_dataset_runs_returns_only_this_scrape_runs_datasets(session):
    run = _run(session)
    other_run = _run(session)
    start_dataset_run(session, run.id, "jornada_points")
    start_dataset_run(session, other_run.id, "season_stats")
    runs = get_dataset_runs(session, run.id)
    assert [r.dataset for r in runs] == ["jornada_points"]


def test_season_stats_record_fields_match_what_the_parser_emits(session):
    """The parser (`af_season_stats.py`) and this repository are tested in
    separate files, so a field rename on either side would not be caught
    by either suite alone — only a real parse, checked against
    `_SEASON_STATS_RECORD_FIELDS`, catches it. This uses the committed
    fixture, no network."""
    html = (FIXTURES / "estadisticas-2025.html").read_text(encoding="utf-8")
    stats = parse_season_stats(html)
    record = stats.records[0]
    missing = [name for name in _SEASON_STATS_RECORD_FIELDS if name not in record]
    assert missing == []


def _seed_week(session, week, provisional, started_at):
    now = datetime.now(UTC)
    player = session.get(Player, 1) or Player(
        id=1, external_id="p-1", name="P", team="Sevilla FC", position="DEF",
        created_at=now, updated_at=now,
    )
    session.add(player)
    run = ScrapeRun(started_at=started_at, status="success")
    session.add(run)
    session.commit()
    session.refresh(run)
    session.add(PlayerGameweekPoints(season_year=2026, week=week, player_id=1, points=3,
                                     is_provisional=provisional, scrape_run_id=run.id))
    session.commit()


def _fixture(session, fid, matchday, kickoff, final):
    session.add(Fixture(fixture_id=fid, matchday=matchday, kickoff_utc=kickoff,
                        kickoff_confirmed=True, is_final=final, home_team="Sevilla FC",
                        away_team="Getafe", scraped_at=datetime.now(UTC)))
    session.commit()


def test_provisional_weeks_are_refetched(session):
    t = datetime(2026, 9, 16, 10, tzinfo=UTC)
    _seed_week(session, 5, False, t)
    _seed_week(session, 6, True, t)
    assert weeks_to_refetch(session, 2026) == {6}


def test_a_week_with_a_late_final_fixture_is_refetched(session):
    captured = datetime(2026, 10, 1, 9, tzinfo=UTC)
    _seed_week(session, 6, False, captured)
    _fixture(session, 1, 6, datetime(2026, 9, 20, 19, tzinfo=UTC), True)   # before capture
    assert weeks_to_refetch(session, 2026) == set()
    _fixture(session, 2, 6, captured + timedelta(days=20), True)            # postponed, now final
    assert weeks_to_refetch(session, 2026) == {6}


def test_a_postponed_fixture_not_yet_final_does_not_trigger_a_refetch(session):
    captured = datetime(2026, 10, 1, 9, tzinfo=UTC)
    _seed_week(session, 6, False, captured)
    _fixture(session, 2, 6, captured + timedelta(days=20), False)
    assert weeks_to_refetch(session, 2026) == set()
