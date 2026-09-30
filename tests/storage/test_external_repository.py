from datetime import UTC, date, datetime
from pathlib import Path

import sqlalchemy as sa

from scraper.sources.football_data import parse_matches
from storage.external_repository import (
    get_external_matches,
    get_roster_teams,
    upsert_external_matches,
)
from storage.models import ExternalMatch, Player, ScrapeRun

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "external"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8-sig")


def _run(session) -> int:
    r = ScrapeRun(started_at=datetime.now(UTC), status="running")
    session.add(r)
    session.commit()
    return r.id


def _record(**overrides) -> dict:
    record = {
        "season_year": 2026,
        "match_date": date(2026, 10, 3),
        "kickoff_at": datetime(2026, 10, 3, 14, 0, tzinfo=UTC),
        "home_team": "Barcelona",
        "away_team": "Sevilla",
        "source_home_team": "Barcelona",
        "source_away_team": "Sevilla",
        "status": "scheduled",
        "home_goals": None,
        "away_goals": None,
        "home_xg": None,
        "away_xg": None,
        "home_shots": None,
        "away_shots": None,
        "home_shots_on_target": None,
        "away_shots_on_target": None,
        "odds_home": 1.5,
        "odds_draw": 4.2,
        "odds_away": 6.0,
        "odds_over25": 1.6,
        "odds_under25": 2.3,
        "closing_odds_home": None,
        "closing_odds_draw": None,
        "closing_odds_away": None,
        "closing_odds_over25": None,
        "closing_odds_under25": None,
        "raw_fields": {"AvgH": "1.5"},
    }
    record.update(overrides)
    return record


def test_migration_columns_match_the_model(engine):
    cols = {c["name"] for c in sa.inspect(engine).get_columns("externalmatch")}
    assert cols == set(ExternalMatch.model_fields)


def test_upsert_writes_a_whole_season_file(session):
    run_id = _run(session)
    records = parse_matches(_read("football-data-SP1-2627.csv"), expected_season=2026).records
    result = upsert_external_matches(session, records, run_id)
    assert result.written == 69
    rows = get_external_matches(session, season_year=2026)
    assert len(rows) == 69
    assert rows[0].match_date <= rows[-1].match_date
    assert rows[0].raw_fields.startswith("{")


def test_rerunning_is_idempotent(session):
    run_id = _run(session)
    records = parse_matches(_read("football-data-SP1-2627.csv"), expected_season=2026).records
    upsert_external_matches(session, records, run_id)
    upsert_external_matches(session, records, run_id)
    assert len(get_external_matches(session, season_year=2026)) == 69


def test_a_scheduled_match_becomes_played_in_place(session):
    run_id = _run(session)
    upsert_external_matches(session, [_record()], run_id)
    played = _record(
        status="played",
        match_date=date(2026, 10, 4),  # postponed a day: same row regardless
        home_goals=2,
        away_goals=0,
        closing_odds_home=1.45,
    )
    upsert_external_matches(session, [played], run_id)
    [row] = get_external_matches(session, season_year=2026)
    assert row.status == "played"
    assert row.match_date == date(2026, 10, 4)
    assert (row.home_goals, row.away_goals) == (2, 0)
    assert row.closing_odds_home == 1.45


def test_a_scheduled_row_never_overwrites_a_played_one(session):
    run_id = _run(session)
    upsert_external_matches(session, [_record(status="played", home_goals=1, away_goals=1)], run_id)
    result = upsert_external_matches(session, [_record(odds_home=9.0)], run_id)
    assert result.kept_played == 1
    assert result.written == 0
    [row] = get_external_matches(session, season_year=2026)
    assert row.status == "played"
    assert row.odds_home == 1.5


def test_status_and_date_filters(session):
    run_id = _run(session)
    upsert_external_matches(
        session,
        [
            _record(),
            _record(
                home_team="Getafe",
                away_team="Elche",
                status="played",
                home_goals=0,
                away_goals=0,
                match_date=date(2026, 9, 20),
            ),
        ],
        run_id,
    )
    assert [m.home_team for m in get_external_matches(session, status="scheduled")] == ["Barcelona"]
    assert [m.home_team for m in get_external_matches(session, from_date=date(2026, 10, 1))] == [
        "Barcelona"
    ]


def test_roster_teams(session):
    now = datetime.now(UTC)
    for i, team in enumerate(["Getafe", "Getafe", "Elche"]):
        session.add(
            Player(
                external_id=f"p{i}",
                name=f"P{i}",
                team=team,
                position="DEF",
                created_at=now,
                updated_at=now,
            )
        )
    session.commit()
    assert get_roster_teams(session) == {"Getafe", "Elche"}
