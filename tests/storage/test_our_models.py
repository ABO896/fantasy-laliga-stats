"""storage/our_models.py — persistence and scoring of our predictions
(MODEL-01/03), divergence (MODEL-04), and per-player analytics assembly."""

import json
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlmodel import select

from storage.models import (
    MarketPrediction,
    Player,
    PlayerGameweekPoints,
    PlayerSnapshot,
    ScrapeRun,
    SourcePrediction,
)
from storage.our_models import (
    compute_player_analytics,
    divergence_payload,
    market_predictions_payload,
    player_analytics_payload,
    refresh_market_predictions,
    score_fields,
    track_record_payload,
)


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
    assert scores["powerScore"] == 60.0  # steady 6s → 6 ppg
    assert scores["economyScore"] is not None
    assert score_fields(result[players[0].id])["economyScore"] is None  # scores 0s: no valuation

    payload = player_analytics_payload(session, players[6].id, [1, 7])
    assert payload["form"]["window"] == 5
    assert payload["consistency"]["points"] == [6] * 10
    assert payload["power"]["recentJornadas"] == 10
    assert payload["valuation"]["fit"]["n"] == 17
    assert [m["windowDays"] for m in payload["momentum"]] == [1, 7]


def test_expected_points_hook_changes_power(session):
    run = _run(session)
    p = _player(session, "a")
    _snap(session, run, p.id, D1, 5_000_000, 0.0)
    for week in range(1, 6):
        session.add(PlayerGameweekPoints(season_year=2026, week=week, player_id=p.id,
                                         points=4, scrape_run_id=run.id))
    session.commit()
    base = compute_player_analytics(session)[p.id].power
    hooked = compute_player_analytics(session, expected_points={p.id: 8.0})[p.id].power
    assert base.power_ppg == 4.0
    assert hooked.expected_points_used and hooked.power_ppg == 6.0
