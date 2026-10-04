"""storage/inputs.py — live inputs loaded once per request, computed for
today (Plan B Task 6)."""

import json
from datetime import UTC, date, datetime

from storage.inputs import compute_live_inputs, live_upcoming
from storage.market_v2 import MODEL_VERSION
from storage.models import (
    Fixture,
    MarketPrediction,
    Player,
    PlayerGameweekPoints,
    PlayerMatchStats,
    PlayerPageFetch,
    PlayerSnapshot,
    ScrapeRun,
)
from storage.our_models import compute_player_analytics
from tests.storage.helpers import seed_fixture

SEASON = 2026


def _player(session, slug, position="DEL", team="T1"):
    now = datetime.now(UTC)
    p = Player(external_id=slug, name=slug.upper(), team=team, position=position,
               created_at=now, updated_at=now)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _run(session):
    r = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _snap(session, run, pid, day, mv=5_000_000, availability="available", starter=70.0,
          points=0):
    session.add(
        PlayerSnapshot(
            as_of=day, player_id=pid, market_value=mv, points=points,
            starter_probability=starter, availability_status=availability, raw_fields="{}",
            scrape_run_id=run.id,
        )
    )
    session.commit()


def _points(session, run, pid, weeks_points, season=SEASON):
    for week, pts in weeks_points.items():
        session.add(PlayerGameweekPoints(season_year=season, week=week, player_id=pid,
                                         points=pts, is_provisional=False, scrape_run_id=run.id))
    session.commit()


# --- test_live_power_matches_analytics -------------------------------------------------


def test_live_power_matches_analytics(session):
    run = _run(session)
    as_of = date(2026, 9, 20)
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)

    players = [_player(session, f"p{i}", position="MED") for i in range(3)]
    fillers = [_player(session, f"f{i}") for i in range(4)]  # team T1 reaches 5 rows/week

    for pl in players:
        _points(session, run, pl.id, {1: 4, 2: 6, 3: 5})
        _snap(session, run, pl.id, as_of, mv=5_000_000 + pl.id)
    for pl in fillers:
        _points(session, run, pl.id, {1: 1, 2: 1, 3: 1})

    live = compute_live_inputs(session, now=now)
    analytics = compute_player_analytics(session, now=now, season=SEASON)

    for pl in players:
        assert live[pl.id].power.score == analytics[pl.id].power.score


# --- test_page_players_get_match_based_reliability --------------------------------------


def test_page_players_get_match_based_reliability(session):
    run = _run(session)
    as_of = date(2026, 9, 20)
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)

    with_page = _player(session, "with-page", position="DEF")
    without_page = _player(session, "without-page", position="DEF")
    fillers = [_player(session, f"g{i}", position="DEF") for i in range(3)]

    for pl in (with_page, without_page, *fillers):
        _points(session, run, pl.id, {1: 2, 2: 2, 3: 2})
        _snap(session, run, pl.id, as_of)

    session.add(PlayerPageFetch(player_id=with_page.id, fetched_at=now, status="ok",
                                 weeks_checked_through=3))
    for week in (1, 2, 3):
        session.add(PlayerMatchStats(season_year=SEASON, week=week, player_id=with_page.id,
                                      minutes=90, points=2, appearance="start",
                                      components="{}", scrape_run_id=run.id))
    session.commit()

    live = compute_live_inputs(session, now=now)
    assert live[with_page.id].reliability.basis == "matches"
    assert live[without_page.id].reliability.basis == "source-only"


# --- test_upcoming_from_calendar ---------------------------------------------------------


def test_upcoming_from_calendar(session):
    now = datetime(2026, 10, 1, tzinfo=UTC)
    for i, matchday in enumerate((8, 9, 10)):
        seed_fixture(session, fid=i + 1, matchday=matchday,
                     kickoff=datetime(2026, 10, 5 + 7 * i, 19, tzinfo=UTC), final=False)
    # A pairing whose only fixture falls well outside the 3-jornada window.
    session.add(Fixture(
        fixture_id=100, matchday=25, season_year=SEASON,
        kickoff_utc=datetime(2027, 1, 10, 19, tzinfo=UTC), kickoff_confirmed=True,
        is_final=False, home_team="Real Betis", away_team="Villarreal CF",
        scraped_at=datetime.now(UTC),
    ))
    session.commit()

    upcoming = live_upcoming(session, SEASON, now, horizon=3)

    assert len(upcoming["Sevilla FC"]) == 3
    assert all(m.opponent == "Getafe" and m.is_home for m in upcoming["Sevilla FC"])
    assert len(upcoming["Getafe"]) == 3
    assert all(m.opponent == "Sevilla FC" and not m.is_home for m in upcoming["Getafe"])
    assert upcoming["Real Betis"] == []
    assert upcoming["Villarreal CF"] == []


# --- test_outlook_comes_from_stored_v2 ---------------------------------------------------


def test_outlook_comes_from_stored_v2(session):
    run = _run(session)
    as_of = date(2026, 9, 20)
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    pl = _player(session, "outlooked")
    _snap(session, run, pl.id, as_of)

    session.add(MarketPrediction(
        made_on=as_of, player_id=pl.id, model_version=MODEL_VERSION, predicted_pct=3.5,
        direction="rise", confidence="moderate",
        inputs=json.dumps({"lower": 1.0, "upper": 6.0, "dropRisk": False, "basis": "ridge",
                           "terms": {}}),
        generated_at=now,
    ))
    session.commit()

    live = compute_live_inputs(session, now=now)
    assert live[pl.id].outlook is not None
    assert live[pl.id].outlook.expected_pct == 3.5
    assert live[pl.id].outlook.made_on == as_of
