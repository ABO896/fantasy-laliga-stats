"""storage/verdict_backtest.py — the walk-forward verdict harness over
stored history, and `ModelReport` (Plan C, Task 4)."""

import json
from datetime import UTC, date, datetime, timedelta

from sqlmodel import select

from core.verdict import DISABLED_LABELS, LABELS
from storage.models import (
    ExternalMatch,
    Fixture,
    MarketPrediction,
    ModelReport,
    Player,
    PlayerGameweekPoints,
    PlayerMarketDaily,
    PlayerMatchStats,
    PlayerPageFetch,
    PlayerSnapshot,
    ScrapeRun,
)
from storage.verdict_backtest import (
    _observations_for,
    _select_dates,
    _static_context,
    load_session_data,
    run_backtest,
    verdicts_on,
    write_report,
)

SEASON = 2026
D0 = date(2026, 8, 1)
WEEKS = range(1, 8)  # 7 jornadas, one per week
WEEK_DATE = {w: D0 + timedelta(days=7 * (w - 1)) for w in WEEKS}
MARKET_DAYS = [D0 + timedelta(days=i) for i in range(50)]  # Aug 1 .. Sep 19
ODDS_SOURCE = "football-data"

CLUB_A, CLUB_B = "Club A", "Club B"
# A real `ExternalMatch`/`Fixture` pairing is unique per season (two clubs
# meet at most twice — home and away), so a 7-week schedule needs more than
# two clubs. Six extra, player-less clubs fill it out as a standard 8-team
# single round-robin (7 rounds, one match per team per round, no pairing
# repeated) — `week_end_dates` reads every team's k-th match date, so every
# team needs one fixture in every round.
_TEAMS = [CLUB_A, CLUB_B, "Club C", "Club D", "Club E", "Club F", "Club G", "Club H"]


def _round_robin(teams):
    teams = list(teams)
    n = len(teams)
    rounds = []
    for _ in range(n - 1):
        rounds.append([(teams[i], teams[n - 1 - i]) for i in range(n // 2)])
        teams = [teams[0], teams[-1], *teams[1:-1]]
    return rounds


_ROUNDS = _round_robin(_TEAMS)  # 7 rounds, indexed 0..6 for weeks 1..7


def _run(session):
    r = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _player(session, slug, position, team):
    now = datetime.now(UTC)
    p = Player(external_id=slug, name=slug.upper(), team=team, position=position,
               created_at=now, updated_at=now)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _schedule(session, run):
    """The 8-team round-robin as `Fixture` rows (every team, every week —
    what `week_end_dates` needs), plus `ExternalMatch` with a stable 1X2 +
    O/U book for the one week Club A meets Club B (so `historical_upcoming`
    has odds to read at least once)."""
    now = datetime.now(UTC)
    fid = 1
    for w, pairs in zip(WEEKS, _ROUNDS, strict=True):
        kickoff = datetime.combine(WEEK_DATE[w], datetime.min.time(), tzinfo=UTC)
        for home, away in pairs:
            session.add(Fixture(
                fixture_id=fid, matchday=w, season_year=SEASON, kickoff_utc=kickoff,
                kickoff_confirmed=True, is_final=True, home_team=home, away_team=away,
                scraped_at=now,
            ))
            fid += 1
            if {home, away} == {CLUB_A, CLUB_B}:
                session.add(ExternalMatch(
                    source=ODDS_SOURCE, season_year=SEASON, home_team=home, away_team=away,
                    match_date=WEEK_DATE[w], status="played", source_home_team=home,
                    source_away_team=away, raw_fields="{}", scrape_run_id=run.id,
                    updated_at=now, odds_home=2.0, odds_draw=3.2, odds_away=3.8,
                    odds_over25=1.9, odds_under25=1.9,
                ))
    session.commit()


def _snapshot(session, run, pid, price, availability="available"):
    session.add(PlayerSnapshot(
        as_of=D0, player_id=pid, market_value=price, points=0,
        availability_status=availability, raw_fields="{}", scrape_run_id=run.id,
    ))
    session.commit()


def _market_daily(session, run, pid, price):
    for day in MARKET_DAYS:
        session.add(PlayerMarketDaily(season_year=SEASON, day=day, player_id=pid,
                                       market_value=price, delta=0, scrape_run_id=run.id))
    session.commit()


def _points(session, run, pid, weekly_points):
    for w in WEEKS:
        session.add(PlayerGameweekPoints(season_year=SEASON, week=w, player_id=pid,
                                         points=weekly_points.get(w, 0), is_provisional=False,
                                         scrape_run_id=run.id))
    session.commit()


def _page(session, run, pid, lines):
    """`lines`: {week: (minutes, appearance)} — only the weeks that have a
    row; a missing week reads as `dnp` through `core.inputs.compute_inputs`'
    own fallback, not through this fixture."""
    session.add(PlayerPageFetch(player_id=pid, fetched_at=datetime.now(UTC), status="ok",
                                 weeks_checked_through=max(WEEKS)))
    for w, (minutes, appearance) in lines.items():
        session.add(PlayerMatchStats(
            season_year=SEASON, week=w, player_id=pid, minutes=minutes,
            points=minutes // 10, appearance=appearance, components="{}",
            scrape_run_id=run.id,
        ))
    session.commit()


def _weekly(value):
    return dict.fromkeys(WEEKS, value)


def _seed(session):
    """~30 players across MED/DEL, engineered so every one of the ten
    verdict labels is reachable somewhere across the processed dates:
    7 weeks of gameweek points, page match lines, 50 days of market value,
    a weekly Club A vs Club B schedule, and one stored market-v2 outlook
    per player. Returns `{slug: player_id}`."""
    run = _run(session)
    _schedule(session, run)
    ids: dict[str, int] = {}

    def make(slug, position, team, price, weekly_points, lines=None,
             availability="available", outlook=(0.0, "flat", False)):
        p = _player(session, slug, position, team)
        ids[slug] = p.id
        _snapshot(session, run, p.id, price, availability)
        _market_daily(session, run, p.id, price)
        _points(session, run, p.id, weekly_points)
        if lines is not None:
            _page(session, run, p.id, lines)
        _outlook(session, p.id, *outlook)
        return p.id

    # --- MED: 14 players -----------------------------------------------------------
    make("unproven_med", "MED", CLUB_A, 3_000_000, _weekly(0))  # no page data at all

    make("overpriced_med", "MED", CLUB_A, 8_000_000, _weekly(1),
         {w: (90, "start") for w in WEEKS})

    for i in range(8):
        make(f"filler_med_{i}", "MED", CLUB_A if i % 2 else CLUB_B, 3_000_000, _weekly(3),
             {w: (90, "start") for w in WEEKS})

    make("rising_med", "MED", CLUB_B, 2_000_000, _weekly(3),
         {w: (90, "start") for w in WEEKS}, outlook=(8.0, "rise", False))

    make("bargain_med", "MED", CLUB_B, 100_000, _weekly(4),
         {w: (90, "start") for w in WEEKS})

    make("filler_med_buffer", "MED", CLUB_B, 3_000_000, _weekly(7),
         {w: (90, "start") for w in WEEKS})

    make("elite_med", "MED", CLUB_A, 6_000_000, _weekly(10),
         {w: (90, "start") for w in WEEKS})

    # --- DEL: 14 players -------------------------------------------------------------
    make("rotation_del", "DEL", CLUB_A, 3_000_000, _weekly(4),
         {w: (20, "sub") for w in WEEKS})

    make("avoid_del", "DEL", CLUB_B, 1_000_000, {1: 1, 2: 1, 3: 1, 4: 0, 5: 0, 6: 0, 7: 0},
         {1: (10, "sub"), 2: (10, "sub"), 3: (10, "sub")}, outlook=(-5.0, "fall", False))

    make("sellhigh_del", "DEL", CLUB_A, 8_000_000,
         {1: 10, 2: 10, 3: 10, 4: 10, 5: 0, 6: 0, 7: 0},
         {1: (90, "start"), 2: (90, "start"), 3: (90, "start"), 4: (90, "start"),
          5: (10, "sub"), 6: (10, "sub"), 7: (10, "sub")},
         outlook=(-8.0, "fall", True))

    make("unavailable_del", "DEL", CLUB_B, 3_000_000, _weekly(3),
         {w: (90, "start") for w in WEEKS}, availability="injured")

    make("fair_del", "DEL", CLUB_A, 3_000_000, _weekly(3),
         {w: (90, "start") for w in WEEKS})

    for i in range(9):
        make(f"filler_del_{i}", "DEL", CLUB_A if i % 2 else CLUB_B, 3_000_000, _weekly(3),
             {w: (90, "start") for w in WEEKS})

    return ids


def _outlook(session, pid, predicted_pct, direction, drop_risk=False):
    """The same outlook stored for every market day — outlooks older than
    7 days are dropped (`storage.market_v2.OUTLOOK_MAX_AGE_DAYS`)."""
    for day in MARKET_DAYS:
        session.add(MarketPrediction(
            made_on=day, player_id=pid, model_version="market-v2",
            predicted_pct=predicted_pct, direction=direction, confidence="moderate",
            inputs=json.dumps({"lower": predicted_pct - 3, "upper": predicted_pct + 3,
                               "dropRisk": drop_risk, "basis": "ridge", "terms": {}}),
            generated_at=datetime.now(UTC),
        ))
    session.commit()


# --- test_report_has_every_label_row ----------------------------------------------------


def test_report_has_every_label_row(session):
    _seed(session)
    report = run_backtest(session, SEASON, disabled=frozenset())
    assert {row["label"] for row in report["labels"]} == set(LABELS)


# --- test_harness_ignores_the_future -----------------------------------------------------


def test_harness_ignores_the_future(session):
    ids = _seed(session)
    probe = date(2026, 8, 20)  # weeks 1-3 known; well before week 7 ends (Sep 12)

    before = load_session_data(session, SEASON)
    verdict_before = verdicts_on(before, probe)

    # A 40-point week-7 row, and a doubled price on the last stored day —
    # both strictly after `probe` and so invisible to it.
    row = session.exec(
        select(PlayerGameweekPoints)
        .where(PlayerGameweekPoints.season_year == SEASON)
        .where(PlayerGameweekPoints.week == 7)
        .where(PlayerGameweekPoints.player_id == ids["elite_med"])
    ).one()
    row.points = 40
    session.add(row)
    last_day_row = session.get(
        PlayerMarketDaily, (SEASON, MARKET_DAYS[-1], ids["elite_med"])
    )
    last_day_row.market_value *= 2
    session.add(last_day_row)
    session.commit()

    after = load_session_data(session, SEASON)
    verdict_after = verdicts_on(after, probe)

    assert verdict_before.keys() == verdict_after.keys()
    for pid in verdict_before:
        assert verdict_before[pid] == verdict_after[pid]


# --- test_points_outcomes_need_three_finished_weeks ---------------------------------------


def test_points_outcomes_need_three_finished_weeks(session):
    _seed(session)
    session_data = load_session_data(session, SEASON)
    ctx = _static_context(SEASON, session_data.data)
    dates = _select_dates(session_data.ends, ctx.days)
    observations, full_window_count = _observations_for(session_data, SEASON, ctx, dates)

    assert full_window_count < len(dates)  # some dates must NOT qualify
    last_date = dates[-1]
    last_date_obs = [o for o in observations if o.day == last_date]
    assert last_date_obs
    assert all(o.outcomes["points"] is None for o in last_date_obs)


# --- test_write_report_round_trips -------------------------------------------------------


def test_write_report_round_trips(session):
    _seed(session)
    report = run_backtest(session, SEASON)
    write_report(session, report)

    stored = session.get(ModelReport, "verdict-validation")
    assert stored is not None
    assert json.loads(stored.payload) == report


# --- the harness's outlooks follow the live per-player rule (final review #1) -------------


def _drop_outlooks_after(session, pid, day):
    for row in session.exec(
        select(MarketPrediction)
        .where(MarketPrediction.player_id == pid)
        .where(MarketPrediction.made_on > day)
    ).all():
        session.delete(row)
    session.commit()


def test_harness_keeps_a_players_outlook_on_a_part_filled_day(session):
    """Everyone else was refreshed on the probe day; rising_med last 3 days
    earlier — he keeps his own latest outlook, as live does."""
    ids = _seed(session)
    probe = date(2026, 8, 20)
    _drop_outlooks_after(session, ids["rising_med"], probe - timedelta(days=3))
    assert verdicts_on(load_session_data(session, SEASON), probe)[ids["rising_med"]].label == (
        "Rising"
    )


def test_harness_drops_an_outlook_older_than_seven_days(session):
    ids = _seed(session)
    probe = date(2026, 8, 20)
    _drop_outlooks_after(session, ids["rising_med"], probe - timedelta(days=8))
    assert verdicts_on(load_session_data(session, SEASON), probe)[ids["rising_med"]].label != (
        "Rising"
    )


# --- eligibility, momentum, and the live disabled set (final review #2-#4) ---------------


def test_observations_mark_ineligible_players_and_carry_momentum(session):
    ids = _seed(session)
    session_data = load_session_data(session, SEASON)
    ctx = _static_context(SEASON, session_data.data)
    dates = _select_dates(session_data.ends, ctx.days)
    observations, _ = _observations_for(session_data, SEASON, ctx, dates)

    by_pid = {}
    for o in observations:
        by_pid.setdefault(o.player_id, []).append(o)
    assert not any(o.eligible for o in by_pid[ids["unavailable_del"]])
    assert not any(o.eligible for o in by_pid[ids["unproven_med"]])
    assert all(o.eligible for o in by_pid[ids["elite_med"]])
    assert all(o.momentum is not None for o in by_pid[ids["elite_med"]])


def test_report_defaults_to_the_live_disabled_labels(session):
    _seed(session)
    report = run_backtest(session, SEASON)
    assert report["disabled"] == sorted(DISABLED_LABELS)


def test_price_label_rows_carry_a_momentum_baseline(session):
    _seed(session)
    report = run_backtest(session, SEASON, disabled=frozenset())
    rows = {row["label"]: row for row in report["labels"]}
    assert set(rows["Rising"]["momentumBaseline"]) == {"n", "hitRate", "meanDiff"}
    assert rows["Elite"]["momentumBaseline"] is None


def test_main_uses_the_live_disabled_set_unless_told_not_to(session, monkeypatch, capsys):
    import storage.verdict_backtest as vb

    seen = []
    monkeypatch.setattr(vb, "run_backtest",
                        lambda _s, _season, disabled: seen.append(disabled) or {
                            "season": SEASON, "dates": [], "disabled": sorted(disabled),
                            "labels": [], "notes": []})
    monkeypatch.setattr(vb, "create_engine", lambda _url: session.get_bind())
    vb.main(["--db", "unused.db"])
    vb.main(["--db", "unused.db", "--no-disabled"])
    assert seen == [DISABLED_LABELS, frozenset()]
