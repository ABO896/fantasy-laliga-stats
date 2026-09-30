"""Parser tests for the fixture calendar.

Two kinds of input, deliberately:

* the saved capture of the real page (re-fetched 2026-09-27, when the
  window held jornadas 6, 8, 9, 10 and 11), and
* hand-built payloads for the shapes a capture happens not to contain.

The 2026-08-08 capture froze a coincidence: at the start of the season the
cell's `matchday` field (the *slot* in the five-jornada window, 1..5) was
numerically equal to the real jornada. By September the slot said 1 while
the jornada was 6. A test written against one capture could not tell the
two apart, so the hand-built payloads below vary every field that can vary.
Never touches the live site.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scraper.sources.analiticafantasy_calendar import FixtureRecord, parse_calendar

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "calendario-predictor.html"

#: Player.team as the market scrape writes it — the vocabulary every
#: consumer joins fixtures against.
MARKET_TEAM_NAMES = {
    "Alaves", "Athletic Club", "Atletico Madrid", "Barcelona", "Celta Vigo",
    "Deportivo La Coruna", "Elche", "Espanyol", "Getafe", "Levante", "Malaga",
    "Osasuna", "Racing Santander", "Rayo Vallecano", "Real Betis", "Real Madrid",
    "Real Sociedad", "Sevilla", "Valencia", "Villarreal",
}


@pytest.fixture(scope="module")
def records() -> list[FixtureRecord]:
    return parse_calendar(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_each_fixture_appears_once(records):
    """One cell per team per jornada — 20 teams over a five-jornada window —
    so every fixture is present twice and must be de-duplicated to 50."""
    assert len(records) == 50
    assert len({r.fixture_id for r in records}) == 50


def test_matchday_is_the_real_jornada_not_the_window_slot(records):
    """The capture's window is slots 1..5 holding jornadas 6, 8, 9, 10, 11."""
    by_matchday: dict[int, int] = {}
    for r in records:
        by_matchday[r.matchday] = by_matchday.get(r.matchday, 0) + 1
    assert by_matchday == {6: 10, 8: 10, 9: 10, 10: 10, 11: 10}


def test_kickoffs_are_timezone_aware_utc(records):
    assert all(r.kickoff_utc.utcoffset().total_seconds() == 0 for r in records)


def test_confirmation_is_decided_per_jornada(records):
    """Jornadas 10 and 11 carry two and one distinct kickoff times —
    placeholders, not a schedule."""
    assert {r.matchday for r in records if r.kickoff_confirmed} == {6, 8, 9}


def test_team_names_are_in_the_market_vocabulary(records):
    """The two sides of a cell disagree about naming ("Atlético de Madrid"
    as subject, "Atletico Madrid" as opponent). The opponent spelling is the
    one `Player.team` uses, so it is the one stored."""
    teams = {r.home_team for r in records} | {r.away_team for r in records}
    assert teams == MARKET_TEAM_NAMES


def test_a_finished_fixture_is_marked_final(records):
    """Fixture 100011981, read off the capture: Barcelona at home to Racing,
    jornada 6, already played."""
    fixture = next(r for r in records if r.fixture_id == 100011981)
    assert fixture.home_team == "Barcelona"
    assert fixture.away_team == "Racing Santander"
    assert fixture.home_team_id == 529
    assert fixture.away_team_id == 4665
    assert fixture.matchday == 6
    assert fixture.kickoff_utc == datetime(2026, 9, 16, 19, 30, tzinfo=UTC)
    assert fixture.is_final
    assert fixture.home_difficulty == "very_easy"


def test_a_postponed_fixture_keeps_its_jornada(records):
    """Levante v Athletic belongs to jornada 6 but kicks off on 21 October,
    after jornada 9 — jornada order is not chronological."""
    fixture = next(
        r for r in records if r.home_team == "Levante" and r.away_team == "Athletic Club"
    )
    assert fixture.matchday == 6
    assert not fixture.is_final
    assert fixture.kickoff_utc == datetime(2026, 10, 21, 18, 0, tzinfo=UTC)


def test_difficulty_is_recorded_per_side(records):
    assert any(r.home_difficulty != r.away_difficulty for r in records)
    assert all(r.home_difficulty and r.away_difficulty for r in records)


def test_a_page_without_fixture_data_raises():
    """Fail loud rather than return an empty list a caller might write as a
    successful zero-fixture scrape."""
    with pytest.raises(ValueError, match="No fixture data"):
        parse_calendar("<html><body><p>nothing here</p></body></html>")


# --- hand-built payloads ---------------------------------------------------


def _cell(
    fixture_id: int,
    *,
    slot: int = 1,
    round_label: str = "Regular Season - 7",
    team: tuple[int, str],
    opponent: tuple[int, str],
    is_home: bool,
    kickoff: str = "2026-10-03T19:00:00+00:00",
    is_final: bool = False,
    difficulty: str = "medium",
) -> dict:
    return {
        "matchday": {
            "matchday": slot,
            "round": round_label,
            "fixtureId": fixture_id,
            "fixtureDate": kickoff,
            "opponentId": opponent[0],
            "opponentName": opponent[1],
            "isHome": is_home,
            "difficulty": difficulty,
            "isFinal": is_final,
        },
        "teamId": team[0],
        "teamName": team[1],
    }


def _page(cells: list[dict], chunk_id: str = "1a") -> str:
    """Wrap cells the way the site does: a flight chunk whose payload string
    starts with a (hexadecimal, deploy-varying) reference id."""
    # Compact separators, as the site serialises — the parser anchors on
    # `{"matchday":{"matchday":` with no whitespace.
    body = json.dumps({"cells": cells}, separators=(",", ":"))
    payload = f'{chunk_id}:["$","$L2b",null,{body}]\n'
    push = json.dumps([1, payload])
    return f"<html><body><script>self.__next_f.push({push})</script></body></html>"


def _pair(fixture_id: int, **kwargs) -> list[dict]:
    home = (1, "Atlético de Madrid")
    away = (2, "Celta de Vigo")
    home_as_opp = (1, "Atletico Madrid")
    away_as_opp = (2, "Celta Vigo")
    return [
        _cell(fixture_id, team=home, opponent=away_as_opp, is_home=True, **kwargs),
        _cell(fixture_id, team=away, opponent=home_as_opp, is_home=False, **kwargs),
    ]


def test_the_jornada_comes_from_round_even_when_the_slot_disagrees():
    [record] = parse_calendar(_page(_pair(10, slot=1, round_label="Regular Season - 7")))
    assert record.matchday == 7


@pytest.mark.parametrize("chunk_id", ["1a", "ff", "3", "b0e"])
def test_any_hex_chunk_id_parses(chunk_id):
    """The flight chunk id is hexadecimal and changes every deploy; a parser
    that only accepted decimal ids failed ten of the first 26 daily runs."""
    assert len(parse_calendar(_page(_pair(10), chunk_id=chunk_id))) == 1


def test_a_repeated_cell_collapses_to_one_fixture():
    """The source lists a club twice while a registration is pending; a
    repeated identity must collapse, not duplicate."""
    cells = _pair(10) + _pair(10)
    assert len(parse_calendar(_page(cells))) == 1


def test_a_one_sided_fixture_still_names_both_teams_in_market_vocabulary():
    """With only the home side's cell, the away name comes from its
    `opponentName` — already market vocabulary. The home name falls back to
    the subject spelling, which is the best available."""
    [home_cell, _] = _pair(10)
    [record] = parse_calendar(_page([home_cell]))
    assert record.away_team == "Celta Vigo"
    assert record.home_team_id == 1
    assert record.away_team_id == 2
    assert record.away_difficulty is None


def test_a_cell_without_a_round_is_a_structure_change():
    cells = _pair(10)
    for cell in cells:
        del cell["matchday"]["round"]
    with pytest.raises(ValueError, match="round"):
        parse_calendar(_page(cells))
