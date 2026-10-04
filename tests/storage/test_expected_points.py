"""storage/expected_points.py — MODEL-02 persistence, target jornada, and
scoring stored predictions against actual points (MODEL-03 for xP)."""

import json
from datetime import UTC, date, datetime, timedelta

from sqlmodel import select

from core import expected_points as xp
from storage.expected_points import (
    compute_expected_points,
    expected_points_map,
    expected_points_payload,
    refresh_expected_points,
    score_expected_points,
    select_target,
    track_record_payload,
)
from storage.models import (
    ExpectedPointsPrediction,
    ExternalMatch,
    Fixture,
    Player,
    PlayerGameweekPoints,
    PlayerSnapshot,
    ScrapeRun,
)

NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)
SEASON = 2026


def _run(session):
    r = ScrapeRun(started_at=NOW, status="success")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _player(session, slug, team, position="DEL"):
    p = Player(external_id=slug, name=slug.title(), team=team, position=position,
               created_at=NOW, updated_at=NOW)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _snap(session, run, pid, starter=80.0, availability="available", day=date(2026, 10, 4)):
    session.add(PlayerSnapshot(as_of=day, player_id=pid, market_value=1_000_000, points=0,
                               starter_probability=starter, availability_status=availability,
                               raw_fields="{}", scrape_run_id=run.id))
    session.commit()


def _points(session, run, pid, week, pts, season=SEASON, provisional=False):
    session.add(PlayerGameweekPoints(season_year=season, week=week, player_id=pid, points=pts,
                                     is_provisional=provisional, scrape_run_id=run.id))
    session.commit()


def _fixture(session, fid, matchday, home, away, kickoff, final=False, season_year=SEASON):
    session.add(Fixture(fixture_id=fid, matchday=matchday, kickoff_utc=kickoff,
                        kickoff_confirmed=True, is_final=final, home_team=home, away_team=away,
                        scraped_at=NOW, season_year=season_year))
    session.commit()


def _odds(session, run, home, away):
    session.add(ExternalMatch(source="football-data", season_year=SEASON, home_team=home,
                              away_team=away, match_date=date(2026, 10, 10), status="scheduled",
                              source_home_team=home, source_away_team=away, odds_home=1.5,
                              odds_draw=4.2, odds_away=6.5, odds_over25=1.7, odds_under25=2.1,
                              raw_fields="{}", scrape_run_id=run.id, updated_at=NOW))
    session.commit()


def _team_week(session, run, team, week, n=6, start=0):
    """Filler teammates so the team counts as having played the week."""
    for i in range(n):
        p = _player(session, f"{team}-{week}-{start + i}".lower().replace(" ", "-"), team)
        _points(session, run, p.id, week, 2)


def _world(session):
    """Two teams with a priced J8 fixture, one team idle in J8 (but known to
    the calendar), one team the calendar has never heard of, and a lone
    postponed J6 fixture that must not become "next"."""
    run = _run(session)
    star = _player(session, "star", "Home FC")
    keeper = _player(session, "keeper", "Away FC", "POR")
    idle = _player(session, "idle", "Idle FC", "MED")
    stranger = _player(session, "stranger", "Nowhere CF", "DEF")
    for p in (star, keeper, idle, stranger):
        _snap(session, run, p.id)
    for week in (1, 2, 3):
        _points(session, run, star.id, week, 10)
        _points(session, run, keeper.id, week, 4)
        _team_week(session, run, "Home FC", week)
        _team_week(session, run, "Away FC", week)
    _fixture(session, 1, 6, "Idle FC", "Other FC", NOW + timedelta(days=20))  # postponed J6
    _fixture(session, 2, 6, "Home FC", "Away FC", NOW - timedelta(days=30), final=True)
    _fixture(session, 3, 8, "Home FC", "Away FC", NOW + timedelta(days=5))
    _fixture(session, 4, 8, "Other FC", "Third FC", NOW + timedelta(days=6))
    _fixture(session, 5, 9, "Idle FC", "Home FC", NOW + timedelta(days=12))
    _odds(session, run, "Home FC", "Away FC")
    return run, star, keeper, idle, stranger


def _stored(session):
    return {r.player_id: r for r in session.exec(select(ExpectedPointsPrediction)).all()}


def test_select_target_ignores_other_season_fixtures(session):
    """A 2025 fixture with a future kickoff must not become the 2026
    target — `matchday` repeats every season, so the calendar lookup must
    also filter on `season_year`."""
    _fixture(session, 1, 1, "Home FC", "Away FC", NOW + timedelta(days=5), season_year=2025)
    target = select_target(session, NOW, SEASON)
    assert target.fixtures == {}
    assert target.calendar_teams == frozenset()
    assert target.jornada == 1  # no 2026 calendar, no stored points yet


def test_next_jornada_is_the_first_one_not_yet_started(session):
    _world(session)
    target, _ = compute_expected_points(session, NOW, SEASON)
    assert target.jornada == 8  # not 6: its leftover postponed match is not "next"
    assert target.locks_at == NOW + timedelta(days=5)


def test_refresh_stores_one_prediction_per_player_with_basis_and_inputs(session):
    _, star, keeper, idle, stranger = _world(session)
    summary = refresh_expected_points(session, NOW)
    rows = _stored(session)
    assert summary.jornada == 8 and not summary.frozen

    assert rows[star.id].basis == "form+starter+odds"
    assert rows[star.id].opponent == "Away FC" and rows[star.id].is_home is True
    inputs = json.loads(rows[star.id].inputs)
    assert inputs["fixture"]["oddsSource"] == "football-data"
    assert inputs["rate"]["matches"] == 3
    assert inputs["naiveSeasonAverage"] == 10
    assert rows[star.id].predicted > rows[keeper.id].predicted > 0

    assert rows[idle.id].basis == "no_fixture" and rows[idle.id].predicted == 0
    # A team the calendar does not know is a name miss, not a blank week.
    assert rows[stranger.id].basis == "form+starter"
    assert rows[star.id].model_version == xp.MODEL_VERSION


def test_a_fixture_without_odds_degrades_and_says_so(session):
    _, star, *_ = _world(session)
    session.delete(session.exec(select(ExternalMatch)).one())
    session.commit()
    refresh_expected_points(session, NOW)
    assert _stored(session)[star.id].basis == "form+starter"


def test_without_a_calendar_the_target_is_the_week_after_the_latest_points(session):
    run = _run(session)
    p = _player(session, "solo", "Solo FC")
    _snap(session, run, p.id, starter=None)
    _points(session, run, p.id, 4, 6)
    summary = refresh_expected_points(session, NOW)
    row = _stored(session)[p.id]
    assert (summary.jornada, row.jornada, row.basis) == (5, 5, "form")
    assert row.locks_at is None


def test_predictions_freeze_at_the_first_kickoff(session):
    _, star, *_ = _world(session)
    refresh_expected_points(session, NOW)
    before = _stored(session)[star.id].predicted

    later = NOW + timedelta(days=5, minutes=1)  # J8 started; J9 is now "next"
    summary = refresh_expected_points(session, later)
    assert summary.jornada == 9
    assert _stored_for(session, 8)[star.id].predicted == before


def _stored_for(session, jornada):
    rows = session.exec(
        select(ExpectedPointsPrediction).where(ExpectedPointsPrediction.jornada == jornada)
    ).all()
    return {r.player_id: r for r in rows}


def test_a_locked_jornada_without_calendar_is_not_rewritten(session):
    run = _run(session)
    p = _player(session, "solo", "Solo FC")
    _snap(session, run, p.id)
    _points(session, run, p.id, 4, 6)
    refresh_expected_points(session, NOW)
    before = _stored_for(session, 5)[p.id].predicted
    # Week 5 points arrive (the jornada is under way): the next refresh
    # targets week 6 and leaves week 5's prediction as it was.
    _points(session, run, p.id, 5, 12, provisional=True)
    _snap(session, run, p.id, starter=5.0, day=date(2026, 10, 5))
    summary = refresh_expected_points(session, NOW)
    assert summary.jornada == 6
    assert _stored_for(session, 5)[p.id].predicted == before
    assert _stored_for(session, 6)[p.id].predicted != before


def test_expected_points_map_is_the_latest_jornada_without_blanks(session):
    _, star, keeper, idle, _ = _world(session)
    refresh_expected_points(session, NOW)
    m = expected_points_map(session, SEASON)
    assert star.id in m and keeper.id in m
    assert idle.id not in m


def test_scoring_against_actual_points(session):
    run, star, keeper, idle, stranger = _world(session)
    refresh_expected_points(session, NOW)
    pending = {s.row.player_id: s.status for s in score_expected_points(session)}
    assert pending[star.id] == "pending"

    _points(session, run, star.id, 8, 14)
    _team_week(session, run, "Home FC", 8)
    _team_week(session, run, "Away FC", 8)  # keeper has no row → he scored 0
    _points(session, run, _player(session, "later", "Home FC").id, 9, 1, provisional=True)
    scored = {s.row.player_id: s for s in score_expected_points(session)}
    assert (scored[star.id].status, scored[star.id].actual) == ("scored", 14)
    assert (scored[keeper.id].status, scored[keeper.id].actual) == ("scored", 0)
    assert scored[stranger.id].status == "unscorable"  # his team has no rows that week

    record = track_record_payload(session)
    assert record["counts"]["scored"] == 2
    assert record["counts"]["noFixture"] == 1
    assert record["overall"]["n"] == 2
    assert record["naiveSeasonAverage"]["n"] == 2
    assert record["byJornada"][0]["jornada"] == 8
    assert {b["basis"] for b in record["byBasis"]} == {"form+starter+odds"}


def test_scoring_ignores_stale_model_versions(session):
    """A prediction left over from a retired model version must not be
    scored or counted alongside the current `xp.MODEL_VERSION` row for the
    same player/jornada — the track record would otherwise mix versions."""
    run, star, *_ = _world(session)
    refresh_expected_points(session, NOW)
    current = _stored(session)[star.id]
    stale = ExpectedPointsPrediction(
        season_year=current.season_year, jornada=current.jornada, player_id=star.id,
        model_version="xp-1", predicted=999.0, basis=current.basis, inputs=current.inputs,
        created_at=NOW, updated_at=NOW,
    )
    session.add(stale)
    session.commit()

    _points(session, run, star.id, 8, 14)
    _team_week(session, run, "Home FC", 8)

    scored = [s for s in score_expected_points(session) if s.row.player_id == star.id]
    assert len(scored) == 1
    assert scored[0].row.model_version == xp.MODEL_VERSION
    assert scored[0].actual == 14

    record = track_record_payload(session)
    assert record["overall"]["n"] == 1  # the xp-1 row (predicted 999) must not be counted


def test_the_in_progress_jornada_is_pending(session):
    run, star, *_ = _world(session)
    refresh_expected_points(session, NOW)
    _points(session, run, star.id, 8, 3, provisional=True)
    _team_week(session, run, "Home FC", 8)
    scored = {s.row.player_id: s.status for s in score_expected_points(session)}
    assert scored[star.id] == "pending"


def test_payload_lists_the_latest_jornada_highest_first(session):
    _, star, *_ = _world(session)
    refresh_expected_points(session, NOW)
    payload = expected_points_payload(session, season=SEASON)
    assert payload["jornada"] == 8
    values = [p["expectedPoints"] for p in payload["predictions"]]
    assert values == sorted(values, reverse=True)
    assert payload["predictions"][0]["playerId"] == star.id
    assert payload["predictions"][0]["inputs"]["terms"]
    assert expected_points_payload(session, jornada=3, season=SEASON)["predictions"] == []
