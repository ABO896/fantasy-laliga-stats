"""football-data.co.uk parser, against committed captures.

What varies between fetches, and is therefore *not* pinned here: odds
values (they move daily until kickoff), which fixtures `fixtures.csv`
carries (a weekend with no LaLiga games carries none — the 2026-09-27
capture is exactly that), how many rows the season file has (grows twice a
week), and which columns exist (2026/27 added `HxG`/`AxG`; the 2025/26 file
has neither). Tests assert structure and invariants, and pin exact values
only on played rows, which are final.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from scraper.sources.football_data import (
    fixtures_csv_url,
    parse_matches,
    season_code,
    season_csv_url,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "external"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8-sig")


HEADER = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HxG,AxG,HS,AS,HST,AST,"
    "AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5,AvgCH,AvgCD,AvgCA,AvgC>2.5,AvgC<2.5"
)


def _csv(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def test_season_code_and_urls():
    assert season_code(2026) == "2627"
    assert season_code(1999) == "9900"
    assert season_csv_url("https://football-data.co.uk", 2026).endswith("/mmz4281/2627/SP1.csv")
    assert fixtures_csv_url("https://football-data.co.uk").endswith("/fixtures.csv")


def test_played_rows_from_the_2026_capture():
    parsed = parse_matches(_read("football-data-SP1-2627.csv"), expected_season=2026)
    assert parsed.skipped == []
    assert len(parsed.records) == 69
    first = parsed.records[0]
    # Played rows are final, so these values are safe to pin.
    assert first["home_team"] == "Alaves"
    assert first["away_team"] == "Getafe"
    assert first["source_home_team"] == "Alaves"
    assert first["season_year"] == 2026
    assert first["match_date"] == date(2026, 8, 15)
    # 18:30 UK (BST) is 17:30 UTC.
    assert first["kickoff_at"] == datetime(2026, 8, 15, 17, 30, tzinfo=UTC)
    assert first["status"] == "played"
    assert (first["home_goals"], first["away_goals"]) == (3, 0)
    assert (first["home_xg"], first["away_xg"]) == (1.93, 0.24)
    assert (first["home_shots"], first["away_shots"]) == (18, 6)
    assert (first["home_shots_on_target"], first["away_shots_on_target"]) == (8, 2)
    assert (first["odds_home"], first["odds_draw"], first["odds_away"]) == (2.33, 2.82, 3.62)
    assert (first["odds_over25"], first["odds_under25"]) == (3.08, 1.35)
    assert first["closing_odds_home"] is not None
    assert first["raw_fields"]["B365H"] == "2.35"


def test_every_2026_row_maps_both_clubs_and_is_unique():
    parsed = parse_matches(_read("football-data-SP1-2627.csv"), expected_season=2026)
    keys = {(r["home_team"], r["away_team"]) for r in parsed.records}
    assert len(keys) == len(parsed.records)
    assert not parsed.unmapped_teams


def test_a_season_without_xg_columns_parses_with_xg_absent():
    parsed = parse_matches(_read("football-data-SP1-2526.csv"), expected_season=2025)
    assert len(parsed.records) == 380
    assert all(r["home_xg"] is None and r["away_xg"] is None for r in parsed.records)
    assert all(r["home_shots"] is not None for r in parsed.records)


def test_the_wrong_season_file_is_rejected_whole():
    with pytest.raises(ValueError, match="season"):
        parse_matches(_read("football-data-SP1-2526.csv"), expected_season=2026)


def test_fixtures_file_keeps_only_laliga_and_marks_them_scheduled():
    parsed = parse_matches(_read("football-data-fixtures-with-sp1.csv"), expected_season=None)
    assert [(r["home_team"], r["away_team"]) for r in parsed.records] == [
        ("Barcelona", "Sevilla"),
        ("Real Madrid", "Villarreal"),
        ("Deportivo La Coruna", "Espanyol"),
    ]
    for r in parsed.records:
        assert r["status"] == "scheduled"
        assert r["home_goals"] is None and r["away_goals"] is None
        assert r["odds_home"] > 1 and r["odds_over25"] > 1
        assert r["closing_odds_home"] is None


def test_a_weekend_without_laliga_is_empty_not_an_error():
    parsed = parse_matches(_read("football-data-fixtures-no-sp1.csv"), expected_season=None)
    assert parsed.records == []
    assert parsed.skipped == []


def test_an_unmapped_club_is_skipped_and_named_never_guessed():
    text = _csv(
        "SP1,03/10/2026,15:00,Barcelona,Sevilla,,,,,,,,,2.0,3.5,3.8,1.9,1.9,,,,,",
        "SP1,03/10/2026,17:00,Nueva Club,Getafe,,,,,,,,,2.0,3.5,3.8,1.9,1.9,,,,,",
    )
    parsed = parse_matches(text, expected_season=None)
    assert len(parsed.records) == 1
    assert parsed.unmapped_teams == {"Nueva Club"}
    assert any("Nueva Club" in s for s in parsed.skipped)


def test_invalid_odds_become_absent_not_a_failure():
    text = _csv("SP1,03/10/2026,15:00,Barcelona,Sevilla,,,,,,,,,1.0,abc,,1.9,1.9,,,,,")
    [r] = parse_matches(text, expected_season=None).records
    assert r["odds_home"] is None and r["odds_draw"] is None and r["odds_away"] is None
    assert r["odds_over25"] == 1.9


def test_two_digit_years_are_read():
    text = _csv("SP1,03/10/26,15:00,Barcelona,Sevilla,,,,,,,,,2.0,3.5,3.8,,,,,,,")
    [r] = parse_matches(text, expected_season=None).records
    assert r["match_date"] == date(2026, 10, 3)
    assert r["season_year"] == 2026


def test_a_repeated_pairing_keeps_the_first_and_says_so():
    row = "SP1,03/10/2026,15:00,Barcelona,Sevilla,,,,,,,,,2.0,3.5,3.8,,,,,,,"
    parsed = parse_matches(_csv(row, row.replace("2.0", "2.1")), expected_season=None)
    assert len(parsed.records) == 1
    assert parsed.records[0]["odds_home"] == 2.0
    assert any("duplicate" in s for s in parsed.skipped)


def test_missing_required_columns_is_a_structure_error():
    with pytest.raises(ValueError, match="columns"):
        parse_matches("Div,Date,HomeTeam\nSP1,03/10/2026,Barcelona\n", expected_season=None)


def test_mostly_unreadable_rows_reject_the_file():
    rows = ["SP1,not-a-date,15:00,Barcelona,Sevilla,,,,,,,,,2,3,4,,,,,,," for _ in range(3)]
    with pytest.raises(ValueError, match="unreadable"):
        parse_matches(_csv(*rows), expected_season=None)
