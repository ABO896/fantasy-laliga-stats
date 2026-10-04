"""storage/market_v2.py — assembling rows, walk-forward generation, scoring
at 7 days, and the v2 track record (Plan B Task 4)."""

from datetime import UTC, datetime, timedelta
from datetime import date as date_cls

import pytest
from sqlmodel import select

from core import market_v2 as m2
from storage.market_v2 import build_rows, refresh_market_v2, v2_track_record
from storage.models import (
    ExternalMatch,
    MarketPrediction,
    Player,
    PlayerMarketDaily,
    PlayerSnapshot,
    ScrapeRun,
)

SEASON = 2026
D0 = date_cls(2026, 8, 1)
DAYS = [D0 + timedelta(days=i) for i in range(30)]
# Well after the data window — every row is retroactive, and the "regenerate
# today's rows" branch in refresh_market_v2 never fires, so re-running the
# refresh with the same `today` is a clean idempotency check.
TODAY = D0 + timedelta(days=60)
NOW = datetime.combine(TODAY, datetime.min.time(), tzinfo=UTC)

POSITIONS = ["POR", "DEF", "MED", "DEL"]


def _player(session, slug, position, team):
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


def _seed_players(session):
    """20 players per club, 5 per position each — 40 players total."""
    players = []
    for team in ("Club A", "Club B"):
        for position in POSITIONS:
            for i in range(5):
                players.append(_player(session, f"{team[-1]}-{position}-{i}", position, team))
    return players


def _seed_market_daily(session, run, players, riser, faller):
    base = 1_000_000
    for p in players:
        for i, day in enumerate(DAYS):
            if p.id == riser.id:
                value = round(base * (1.01**i))
            elif p.id == faller.id:
                value = round(base * (0.99**i))
            else:
                value = base
            session.add(
                PlayerMarketDaily(season_year=SEASON, day=day, player_id=p.id,
                                   market_value=value, scrape_run_id=run.id)
            )
    session.commit()


def _seed_snapshots(session, run, players):
    for p in players:
        for day in DAYS:
            session.add(
                PlayerSnapshot(
                    as_of=day, player_id=p.id, market_value=1_000_000, points=0,
                    availability_status="available", raw_fields="{}", scrape_run_id=run.id,
                )
            )
    session.commit()


def _seed_matches(session, run):
    now = datetime.now(UTC)
    session.add_all(
        [
            ExternalMatch(
                source="football-data", season_year=SEASON, home_team="Club A",
                away_team="Club B", match_date=D0 + timedelta(days=5), status="played",
                source_home_team="Club A", source_away_team="Club B", raw_fields="{}",
                scrape_run_id=run.id, updated_at=now,
            ),
            ExternalMatch(
                source="football-data", season_year=SEASON, home_team="Club B",
                away_team="Club A", match_date=D0 + timedelta(days=20), status="played",
                source_home_team="Club B", source_away_team="Club A", raw_fields="{}",
                scrape_run_id=run.id, updated_at=now,
            ),
        ]
    )
    session.commit()


def _seed_all(session):
    run = _run(session)
    players = _seed_players(session)
    riser, faller = players[0], players[1]
    _seed_market_daily(session, run, players, riser, faller)
    _seed_snapshots(session, run, players)
    _seed_matches(session, run)
    return players, riser, faller


def _v2_preds(session):
    return session.exec(
        select(MarketPrediction).where(MarketPrediction.model_version == m2.MODEL_VERSION)
    ).all()


def test_refresh_generates_one_row_per_player_day(session):
    players, _riser, _faller = _seed_all(session)

    summary = refresh_market_v2(session, today=TODAY, now=NOW)
    assert summary.generated == len(players) * len(DAYS)
    assert len(_v2_preds(session)) == len(players) * len(DAYS)

    summary2 = refresh_market_v2(session, today=TODAY, now=NOW)
    assert summary2.generated == 0


def test_days_with_outcomes_are_never_rewritten(session):
    _players, riser, _faller = _seed_all(session)
    refresh_market_v2(session, today=TODAY, now=NOW)

    target_day = D0 + timedelta(days=3)
    assert target_day < TODAY - timedelta(days=7)
    row = session.get(MarketPrediction, (target_day, riser.id, m2.MODEL_VERSION))
    row.predicted_pct = 999.0
    session.add(row)
    session.commit()

    refresh_market_v2(session, today=TODAY, now=NOW)
    row2 = session.get(MarketPrediction, (target_day, riser.id, m2.MODEL_VERSION))
    assert row2.predicted_pct == 999.0


def test_regenerate_today_branch_rewrites_only_the_latest_day(session):
    """When `today` equals the latest day in `PlayerMarketDaily` (the live
    case `test_days_with_outcomes_are_never_rewritten` deliberately avoids by
    using a `today` far past the data window), refresh_market_v2 deletes and
    regenerates only that day's rows every call — never a day whose 7-day
    outcome is already known — and the total row count stays stable."""
    _players, riser, _faller = _seed_all(session)
    live_today = DAYS[-1]
    now = datetime.combine(live_today, datetime.min.time(), tzinfo=UTC)

    refresh_market_v2(session, today=live_today, now=now)
    first_count = len(_v2_preds(session))

    older_day = D0 + timedelta(days=3)
    assert older_day <= DAYS[-1] - timedelta(days=7)  # its 7-day outcome is known
    older_row = session.get(MarketPrediction, (older_day, riser.id, m2.MODEL_VERSION))
    older_row.predicted_pct = 777.0
    session.add(older_row)

    today_row = session.get(MarketPrediction, (live_today, riser.id, m2.MODEL_VERSION))
    today_row.predicted_pct = 888.0
    session.add(today_row)
    session.commit()

    refresh_market_v2(session, today=live_today, now=now)

    assert len(_v2_preds(session)) == first_count

    older_row_again = session.get(MarketPrediction, (older_day, riser.id, m2.MODEL_VERSION))
    assert older_row_again.predicted_pct == 777.0

    today_row_again = session.get(MarketPrediction, (live_today, riser.id, m2.MODEL_VERSION))
    assert today_row_again.predicted_pct != 888.0


def test_scoring_after_seven_days(session):
    _seed_all(session)
    refresh_market_v2(session, today=TODAY, now=NOW)

    cutoff = DAYS[-1] - timedelta(days=7)
    scored = [p for p in _v2_preds(session) if p.made_on <= cutoff]
    pending = [p for p in _v2_preds(session) if p.made_on > cutoff]

    assert scored and all(p.scoring == "7d" and p.outcome_as_of is not None for p in scored)
    assert len({p.made_on for p in pending}) == 7
    assert pending and all(p.outcome_as_of is None for p in pending)


def test_features_use_only_past_data(session):
    _players, riser, _faller = _seed_all(session)
    day10 = D0 + timedelta(days=10)
    day11 = D0 + timedelta(days=11)

    rows = build_rows(session, SEASON)
    by_key = {(r.player_id, r.day): r for r in rows}
    row10 = by_key[(riser.id, day10)]

    values = {
        d.day: d.market_value
        for d in session.exec(
            select(PlayerMarketDaily).where(PlayerMarketDaily.player_id == riser.id)
        ).all()
    }
    expected_r7 = m2.price_change_pct(values, day10, 7)
    assert expected_r7 is not None
    assert row10.x["r7"] == pytest.approx(expected_r7)

    pmd11 = session.exec(
        select(PlayerMarketDaily)
        .where(PlayerMarketDaily.player_id == riser.id)
        .where(PlayerMarketDaily.day == day11)
    ).one()
    pmd11.market_value = 999_999_999
    session.add(pmd11)
    session.commit()

    rows2 = build_rows(session, SEASON)
    row10_again = {(r.player_id, r.day): r for r in rows2}[(riser.id, day10)]
    assert row10_again.x == row10.x


def test_track_record_reports_naive_baseline_and_coverage(session):
    _seed_all(session)
    refresh_market_v2(session, today=TODAY, now=NOW)

    record = v2_track_record(session)
    assert record["modelVersion"] == m2.MODEL_VERSION
    assert "hitRate" in record["naive"]
    assert "mae" in record["naive"]
    assert record["naive"]["rule"] == "next week repeats last week"
    assert "intervalCoverage" in record
    assert "live" in record["ours"] and "retroactive" in record["ours"]
    assert record["ours"]["retroactive"]["scored"] > 0
