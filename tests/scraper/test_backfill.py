"""The historical backfill (INGEST-08).

`ingest_jornada_points` already fills gaps in the *current* season on every
refresh. This covers the other thing INGEST-08 asks for: a past season,
walked once, from its own round list.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlmodel import select

from scraper.backfill import backfill_season
from scraper.errors import ScrapeError
from scraper.sources.af_jornada import JornadaSnapshot
from scraper.sources.af_season_stats import SeasonStats
from storage.models import Player, PlayerSeasonStats, ScrapeRun
from storage.repository import (
    _SEASON_STATS_RECORD_FIELDS,
    Resolution,
    get_dataset_runs,
    get_last_successful_run,
    has_running_run,
    upsert_gameweek_points,
)

#: Season 2025/26's real round list, verified against the live payload on
#: 2026-08-23: 36 jornadas, with 30 and 35 absent.
REAL_ROUNDS = tuple(w for w in range(1, 39) if w not in (30, 35))


def _stats_record(total_points: int) -> dict:
    """A minimal but complete season-stats record — every field
    `upsert_season_stats` reads, zero-filled except `total_points`."""
    values = dict.fromkeys(_SEASON_STATS_RECORD_FIELDS, 0)
    values["total_points"] = total_points
    values["average_points"] = float(total_points)
    values["ideal_formation_count"] = None
    return {
        "slug": "a-1",
        "nickname": "A",
        "position": "MED",
        "team_name": "T",
        "is_coach": False,
        "raw": {"totalPoints": total_points},
        **values,
    }


@dataclass
class _Requested:
    """What the stubbed source was asked for. Both datasets are stubbed by
    one fixture so no test can reach the network by forgetting one — the
    suite's network guard would catch it, but a fixture that covers every
    fetch the code under test makes is the better place to stop it."""

    weeks: list[int | None] = field(default_factory=list)
    stats_seasons: list[int | None] = field(default_factory=list)


@pytest.fixture()
def stub_source(monkeypatch):
    """Answer every fetch with a snapshot that honours the request. The
    network is never touched."""
    requested = _Requested()

    def fake_fetch(season_year, week, settings=None):
        requested.weeks.append(week)
        return "<html></html>"

    def fake_parse(html, requested_week):
        return JornadaSnapshot(
            season_year=2025,
            week=requested_week if requested_week is not None else 38,
            rounds=REAL_ROUNDS,
            records=[{"slug": "a-1", "player_name": "A", "position": "MED", "points": 5}],
        )

    def fake_fetch_stats(settings=None, season_year=None):
        requested.stats_seasons.append(season_year)
        return "<html></html>"

    def fake_parse_stats(html):
        return SeasonStats(
            season_year=requested.stats_seasons[-1] or 2026,
            records=[_stats_record(40)],
        )

    monkeypatch.setattr("scraper.backfill.fetch_jornada", fake_fetch)
    monkeypatch.setattr("scraper.backfill.parse_jornada", fake_parse)
    monkeypatch.setattr("scraper.backfill.fetch_season_stats", fake_fetch_stats)
    monkeypatch.setattr("scraper.backfill.parse_season_stats", fake_parse_stats)
    return requested


def _seed_player(session) -> Player:
    now = datetime.now(UTC)
    p = Player(
        external_id="a-1", name="A", team="T", position="MED", created_at=now, updated_at=now
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_backfill_requests_only_weeks_that_exist(session, stub_source):
    """2025/26 has no jornada 30 or 35. Requesting them would return the
    site's fallback, which the guard rejects — not requesting them at all
    is better, and `rounds` is what makes that possible."""
    _seed_player(session)
    backfill_season(session, 2025)

    weeks = [w for w in stub_source.weeks if w is not None]
    assert 30 not in weeks
    assert 35 not in weeks
    assert sorted(weeks) == list(REAL_ROUNDS)


def test_backfill_writes_a_row_per_resolved_player(session, stub_source):
    _seed_player(session)
    result = backfill_season(session, 2025)
    assert result.weeks_written == len(REAL_ROUNDS)
    assert result.rows_written == len(REAL_ROUNDS)
    assert result.errors == []


def test_backfill_is_resumable(session, stub_source):
    """Weeks already stored are neither re-requested nor rewritten, so an
    interrupted backfill is re-run rather than restarted."""
    player = _seed_player(session)
    run = ScrapeRun(started_at=datetime.now(UTC), status="running")
    session.add(run)
    session.commit()
    session.refresh(run)
    upsert_gameweek_points(
        session,
        2025,
        1,
        False,
        [{"slug": "a-1", "points": 5}],
        Resolution(player_id_by_index={0: player.id}),
        run.id,
    )

    result = backfill_season(session, 2025)

    assert 1 not in [w for w in stub_source.weeks if w is not None]
    assert result.weeks_skipped == 1
    assert result.weeks_written == len(REAL_ROUNDS) - 1


def test_backfill_stops_at_its_request_budget(session, stub_source):
    """A bounded budget is a policy requirement, not a nicety: a loop that
    does not converge is a failure to report, not a reason to keep
    fetching."""
    _seed_player(session)
    from core.config import get_settings

    # `get_settings` is `@lru_cache`d, so mutating the instance it returns
    # would leak the shrunk budget into every later test in the session.
    # Copy instead of mutate.
    settings = get_settings().model_copy(update={"backfill_request_budget": 5})

    result = backfill_season(session, 2025, settings=settings)

    assert result.budget_exhausted is True
    assert len([w for w in stub_source.weeks if w is not None]) <= 5


def test_backfill_leaves_no_run_in_progress(session, stub_source):
    """`has_running_run` is the single-flight guard on the in-app "Refresh
    now" button. A backfill that starts a `ScrapeRun` and never finishes it
    would refuse every future refresh, permanently."""
    _seed_player(session)
    backfill_season(session, 2025)
    assert has_running_run(session) is False


def test_backfill_is_not_a_successful_market_scrape(session, stub_source):
    """The backfill writes last season's jornada points and not one
    `PlayerSnapshot`. If its run counted as `success`, `get_last_successful_run`
    would report fresh market data that was never fetched, and the stale
    banner would go quiet on the strength of it."""
    _seed_player(session)
    backfill_season(session, 2025)
    assert get_last_successful_run(session) is None


def test_an_unexpected_error_still_finishes_the_run(session, stub_source, monkeypatch):
    """An unclassified exception is a bug, not a gap, so it must stay loud
    — but a backfill that dies with its `ScrapeRun` still `running` trips
    `has_running_run` and refuses every future "Refresh now" click,
    permanently. The first real backfill did exactly that. Record the
    reason, finish the run, then re-raise: the pattern `run_daily_refresh`
    already uses for the same class of failure."""
    _seed_player(session)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("scraper.backfill.upsert_gameweek_points", boom)

    with pytest.raises(RuntimeError):
        backfill_season(session, 2025)

    assert has_running_run(session) is False
    run = session.exec(select(ScrapeRun).order_by(ScrapeRun.id.desc())).first()
    assert run.status == "failed"
    assert "RuntimeError: boom" in run.validation_errors


def test_backfill_stores_that_seasons_deep_statistics(session, stub_source):
    """INGEST-08's other half. A finished season's totals are final, so
    they are fetched once for the season being walked — under their own
    `DatasetRun`, because five datasets that fail independently is the
    rule this project already follows."""
    _seed_player(session)
    result = backfill_season(session, 2025)

    assert stub_source.stats_seasons == [2025]
    assert result.stats_rows_written == 1
    rows = session.exec(select(PlayerSeasonStats)).all()
    assert [(r.season_year, r.total_points) for r in rows] == [(2025, 40)]

    datasets = {d.dataset: d for d in get_dataset_runs(session, session.get(ScrapeRun, 1).id)}
    assert datasets["backfill_stats_2025"].status == "success"


def test_statistics_declaring_another_season_are_refused(session, stub_source, monkeypatch):
    """The same fallback class the jornada guard exists for: asking for
    2025 and being served 2026 must not file this season's totals under
    last season's label. `upsert_season_stats` deletes by season, so
    storing the wrong payload would also wipe whatever was there."""
    _seed_player(session)

    def fake_fetch(settings=None, season_year=None):
        return "<html></html>"

    def fake_parse(html):
        return SeasonStats(
            season_year=2026,
            records=[_stats_record(40)],
        )

    monkeypatch.setattr("scraper.backfill.fetch_season_stats", fake_fetch)
    monkeypatch.setattr("scraper.backfill.parse_season_stats", fake_parse)

    result = backfill_season(session, 2025)

    assert session.exec(select(PlayerSeasonStats)).all() == []
    assert any("2026" in e for e in result.errors)


def test_a_statistics_failure_does_not_cost_the_jornada_walk(session, stub_source, monkeypatch):
    """Independent outcomes, the same rule the refresh follows: a blocked
    statistics page must still leave 36 weeks of points backfilled."""
    _seed_player(session)

    def fake_fetch(settings=None, season_year=None):
        raise ScrapeError("blocked")

    monkeypatch.setattr("scraper.backfill.fetch_season_stats", fake_fetch)

    result = backfill_season(session, 2025)

    assert result.weeks_written == len(REAL_ROUNDS)
    assert result.stats_rows_written == 0
    assert any("ScrapeError" in e for e in result.errors)
