"""storage/our_models.py — persistence and scoring of our predictions
(MODEL-01/03), divergence (MODEL-04), and per-player analytics assembly."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlmodel import select

from core import expected_points as xp
from core.analytics import AVAILABILITY_FACTOR, GameweekRow
from storage.models import (
    MarketPrediction,
    Player,
    PlayerGameweekPoints,
    PlayerSnapshot,
    ScrapeRun,
    SourcePrediction,
)
from storage.our_models import (
    calendar_final_weeks,
    compute_player_analytics,
    divergence_payload,
    market_predictions_payload,
    player_analytics_payload,
    refresh_market_predictions,
    score_fields,
    team_played_weeks,
    track_record_payload,
)
from tests.storage.helpers import seed_fixture as _fixture


def _player(session, slug, position="DEL"):
    now = datetime.now(UTC)
    p = Player(external_id=slug, name=slug.upper(), team="T", position=position,
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


def _snap(session, run, pid, day, mv, pct, points=0, availability="available", starter=50.0):
    session.add(
        PlayerSnapshot(
            as_of=day, player_id=pid, market_value=mv, price_change_pct=pct, points=points,
            starter_probability=starter, availability_status=availability, raw_fields="{}",
            scrape_run_id=run.id,
        )
    )
    session.commit()


def _preds(session):
    return session.exec(select(MarketPrediction).order_by(MarketPrediction.made_on)).all()


D1, D2, D3, D6 = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 6)
LATER = datetime(2026, 9, 20, 12, tzinfo=UTC)


def test_migration_matches_the_model(engine):
    cols = {c["name"] for c in sa.inspect(engine).get_columns("marketprediction")}
    assert cols == set(MarketPrediction.model_fields)


def test_first_refresh_backfills_every_date_retroactively_and_scores(session):
    run = _run(session)
    p = _player(session, "a")
    _snap(session, run, p.id, D1, 10_000_000, -1.0)
    _snap(session, run, p.id, D2, 9_900_000, -1.0)
    _snap(session, run, p.id, D6, 10_200_000, 0.5)

    summary = refresh_market_predictions(session, today=date(2026, 9, 20), now=LATER)

    assert summary.generated == 3
    preds = _preds(session)
    assert [x.retroactive for x in preds] == [True, True, True]
    first, second, last = preds
    assert (first.scoring, first.outcome_gap_days, first.hit) == ("exact", 1, True)
    assert (second.scoring, second.outcome_gap_days) == ("interval", 4)
    assert second.actual_direction == "rise" and second.hit is False
    assert last.outcome_as_of is None  # pending: nothing captured after it


def test_a_same_day_prediction_is_live_and_is_replaced_on_a_same_day_rerun(session):
    run = _run(session)
    p = _player(session, "a")
    _snap(session, run, p.id, D1, 10_000_000, -1.0)
    morning = datetime(2026, 9, 1, 9, tzinfo=UTC)
    refresh_market_predictions(session, today=D1, now=morning)
    assert _preds(session)[0].retroactive is False

    # Same-day re-run replaced today's snapshot with a different move.
    session.exec(sa.delete(PlayerSnapshot))
    _snap(session, run, p.id, D1, 10_000_000, 2.0)
    refresh_market_predictions(session, today=D1, now=morning)
    [pred] = _preds(session)
    assert pred.direction == "rise"


def test_a_scored_prediction_is_never_regenerated(session):
    run = _run(session)
    p = _player(session, "a")
    _snap(session, run, p.id, D1, 10_000_000, -1.0)
    refresh_market_predictions(session, today=D1, now=datetime(2026, 9, 1, 9, tzinfo=UTC))
    _snap(session, run, p.id, D2, 10_100_000, 1.0)
    # A later refresh whose market scrape failed: the latest date is D2, today is D3.
    refresh_market_predictions(session, today=D3, now=datetime(2026, 9, 3, 9, tzinfo=UTC))
    first, second = _preds(session)
    assert first.retroactive is False and first.hit is False
    assert second.retroactive is True


def test_a_later_refresh_on_an_old_latest_date_does_not_overwrite_live_calls(session):
    run = _run(session)
    p = _player(session, "a")
    _snap(session, run, p.id, D1, 10_000_000, -1.0)
    refresh_market_predictions(session, today=D1, now=datetime(2026, 9, 1, 9, tzinfo=UTC))
    refresh_market_predictions(session, today=D3, now=datetime(2026, 9, 3, 9, tzinfo=UTC))
    [pred] = _preds(session)
    assert pred.retroactive is False


def test_track_record_and_source_comparison(session):
    run = _run(session)
    a, b = _player(session, "a"), _player(session, "b")
    for pid, pct_1, pct_2 in [(a.id, -1.0, -0.8), (b.id, 0.8, -0.3)]:
        _snap(session, run, pid, D1, 10_000_000, pct_1)
        _snap(session, run, pid, D2, 10_000_000, pct_2)
    session.add_all([
        SourcePrediction(as_of=D1, source="market_top_fallers", player_id=a.id, value=-1,
                         raw_fields=json.dumps({"p": -0.02}), scrape_run_id=run.id),
        SourcePrediction(as_of=D1, source="market_possible_fallers", player_id=b.id, value=1,
                         raw_fields="{}", scrape_run_id=run.id),
        SourcePrediction(as_of=D1, source="points", player_id=b.id, value=5,
                         raw_fields="{}", scrape_run_id=run.id),
    ])
    session.commit()
    refresh_market_predictions(session, today=date(2026, 9, 20), now=LATER)

    record = track_record_payload(session)
    assert record["ours"]["retroactive"]["scored"] == 2
    assert record["ours"]["retroactive"]["hits"] == 1  # a: fall ✓, b: rise ✗
    assert record["ours"]["live"]["scored"] == 0
    assert record["source"]["scored"] == 2 and record["source"]["hits"] == 2
    assert record["source"]["oursOnSamePlayers"] == {"scored": 2, "hits": 1, "hitRate": 0.5}
    assert record["days"][0]["madeOn"] == "2026-09-01"

    div = divergence_payload(session)
    assert div["asOf"] == "2026-09-01"
    assert div["disagree"] == 1 and div["agree"] == 1
    assert div["rows"][0]["playerId"] == b.id  # disagreements first

    listing = market_predictions_payload(session)
    assert listing["madeOn"] == "2026-09-02"
    assert len(listing["predictions"]) == 2


def test_track_record_payload_rejects_unknown_model_version(session):
    with pytest.raises(ValueError, match="bogus"):
        track_record_payload(session, model_version="bogus")


def _v2_score(history, position, prior=None):
    a, c = xp.RATE_ONLY[position]
    return round(100 * max(0.0, a * xp.points_rate(history, prior, position).value + c) / 10, 1)


def test_analytics_scores_and_payload(session):
    run = _run(session)
    players = [_player(session, f"p{i}", position="MED") for i in range(20)]
    for i, pl in enumerate(players):
        _snap(session, run, pl.id, D1, 1_000_000 * (i + 1), 0.0)
        for week in range(1, 13):
            session.add(PlayerGameweekPoints(season_year=2026, week=week, player_id=pl.id,
                                             points=i % 7, scrape_run_id=run.id))
    session.commit()

    result = compute_player_analytics(session)
    assert len(result) == 20
    scores = score_fields(result[players[6].id])
    assert scores["powerScore"] == _v2_score([6] * 12, "MED")  # shrunk, calibrated 6s
    assert scores["powerScore"] < 60.0
    assert scores["economyScore"] is not None
    # scores all 0s: the raw recent mean is 0, so he is gated out even though
    # Power v2's shrinkage gives him a small positive quality_ppg.
    assert score_fields(result[players[0].id])["economyScore"] is None

    payload = player_analytics_payload(session, players[6].id, [1, 7])
    assert payload["form"]["window"] == 5
    assert payload["consistency"]["points"] == [6] * 10
    power = payload["power"]
    assert power["recentJornadas"] == 10
    assert power["rateMatches"] == 12
    assert power["priorSource"] == "position"
    assert power["availabilityFactor"] == 1.0
    assert power["powerPpg"] == power["qualityPpg"]
    assert {"formWeight", "consistencyWeight", "expectedPointsUsed"}.isdisjoint(power)
    # Players scoring 0 every week (i % 7 == 0: p0, p7, p14) are gated out by
    # recent_avg despite their shrunk quality_ppg being positive.
    assert payload["valuation"]["fit"]["n"] == 17
    assert [m["windowDays"] for m in payload["momentum"]] == [1, 7]


def test_power_uses_last_season_prior_and_charges_availability(session):
    run = _run(session)
    fit, hurt = _player(session, "fit"), _player(session, "hurt")
    for pl, status in [(fit, "available"), (hurt, "injured")]:
        _snap(session, run, pl.id, D1, 5_000_000, 0.0, availability=status)
        for week in range(1, 4):
            session.add(PlayerGameweekPoints(season_year=2025, week=week, player_id=pl.id,
                                             points=10, scrape_run_id=run.id))
        for week in range(1, 6):
            session.add(PlayerGameweekPoints(season_year=2026, week=week, player_id=pl.id,
                                             points=4, scrape_run_id=run.id))
    session.commit()
    result = compute_player_analytics(session)
    a_fit, a_hurt = result[fit.id], result[hurt.id]
    assert a_fit.power_inputs.prior_source == "last_season"
    assert a_fit.power_inputs.rate_matches == 5  # current season only
    assert a_fit.power.quality_ppg == pytest.approx(
        _v2_score([4] * 5, "DEL", prior=10.0) / 10, abs=0.01)
    assert a_hurt.power.quality_ppg == a_fit.power.quality_ppg
    assert a_hurt.power.power_ppg == pytest.approx(
        a_fit.power.power_ppg * AVAILABILITY_FACTOR["injured"])


# --- team_played_weeks / calendar_final_weeks ------------------------------------


def test_team_played_weeks_needs_min_team_rows():
    rows = [GameweekRow(2026, 1, pid, 2, False) for pid in range(1, 7)]   # 6 rows, team A
    rows += [GameweekRow(2026, 2, 1, 2, False)]                          # 1 row, team A
    team_of = {pid: "A" for pid in range(1, 7)}
    assert team_played_weeks(rows, team_of) == {"A": {(2026, 1)}}


def test_calendar_final_weeks(session):
    now = datetime(2026, 9, 30, 12, tzinfo=UTC)
    fid = 0

    def add(matchday, kickoff, final):
        nonlocal fid
        fid += 1
        _fixture(session, fid, matchday, kickoff, final)

    # Matchday 7: 10 fixtures, all final, kicked off before `now`.
    for i in range(10):
        add(7, datetime(2026, 9, 25, 19, tzinfo=UTC), True)
    # Matchday 6: 9 final before `now` + 1 not-final postponed fixture after `now`.
    for i in range(9):
        add(6, datetime(2026, 9, 18, 19, tzinfo=UTC), True)
    add(6, now + timedelta(days=5), False)
    # Matchday 8: 10 fixtures, none final, after `now`.
    for i in range(10):
        add(8, now + timedelta(days=2), False)
    # Matchday 5: 9 final + 1 not final that kicked off before `now` (live).
    for i in range(9):
        add(5, datetime(2026, 9, 11, 19, tzinfo=UTC), True)
    add(5, now - timedelta(hours=1), False)

    assert calendar_final_weeks(session, 2026, now) == {(2026, 6), (2026, 7)}


def test_other_season_fixtures_are_ignored(session):
    """A prior season's matchday 7 is long over; the current season's
    matchday 7 has not kicked off yet. `calendar_final_weeks` must not mix
    the two just because `matchday` repeats every season."""
    now = datetime(2026, 9, 30, 12, tzinfo=UTC)
    fid = 0

    def add(matchday, kickoff, final, season_year):
        nonlocal fid
        fid += 1
        _fixture(session, fid, matchday, kickoff, final, season_year=season_year)

    for i in range(10):
        add(7, datetime(2026, 3, 1, 19, tzinfo=UTC), True, 2025)
    for i in range(10):
        add(7, now + timedelta(days=5), False, 2026)

    assert calendar_final_weeks(session, 2026, now) == set()
