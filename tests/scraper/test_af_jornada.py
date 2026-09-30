import json
from pathlib import Path

import pytest

from scraper.sources.af_jornada import JornadaFallback, parse_jornada

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "phase7"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_a_real_jornada():
    snap = parse_jornada(_read("jornada-2026-w1.html"), requested_week=1)
    assert snap.season_year == 2026
    assert snap.week == 1
    # Every row is emitted, including the 12 club coaches and the 13 players
    # the payload gives no slug for. Filtering here would silently discard
    # real players — see test_slugless_players_are_kept.
    assert len(snap.records) == 248
    assert all(isinstance(r["points"], int) for r in snap.records)


def test_slugless_players_are_kept_not_dropped():
    """The payload omits `slug` for some players persistently — in season
    2025/26 that includes Bellingham, Pepe and Fornals. Dropping them at
    parse time deletes their points silently. Task 7 resolves them by
    (name, position); this parser's job is to not lose them first."""
    snap = parse_jornada(_read("jornada-2025-w38.html"), requested_week=38)
    slugless = [r for r in snap.records if not r["slug"] and not r["is_coach"]]
    assert len(slugless) == 31
    assert any(r["player_name"] == "Bellingham" for r in slugless)


def test_coaches_are_flagged_rather_than_dropped():
    snap = parse_jornada(_read("jornada-2026-w1.html"), requested_week=1)
    assert len([r for r in snap.records if r["is_coach"]]) == 12


def test_latest_is_parsed_when_no_week_is_requested():
    snap = parse_jornada(_read("jornada-2026-latest.html"), requested_week=None)
    assert snap.week == 2
    assert snap.rounds == (1, 2)


def test_rounds_lists_only_jornadas_that_exist():
    snap = parse_jornada(_read("jornada-2025-w38.html"), requested_week=38)
    assert len(snap.rounds) == 36
    assert 30 not in snap.rounds and 35 not in snap.rounds
    assert max(snap.rounds) == 38


def test_an_unplayed_week_in_the_current_season_is_rejected():
    # /2026/38 returns HTTP 200 and echoes week 38 in the props, but
    # activeWeek says 2 and the players are jornada 2's. Storing this
    # would write one jornada under 37 different numbers.
    with pytest.raises(JornadaFallback):
        parse_jornada(_read("jornada-2026-w38-fallback.html"), requested_week=38)


def test_a_week_past_the_end_of_a_finished_season_is_rejected():
    with pytest.raises(JornadaFallback):
        parse_jornada(_read("jornada-2025-w39-fallback.html"), requested_week=39)


def test_a_week_absent_from_rounds_is_rejected():
    with pytest.raises(JornadaFallback):
        parse_jornada(_read("jornada-2025-w30-absent.html"), requested_week=30)


def test_the_fallback_fixtures_would_pass_a_status_or_props_based_check():
    """Pins *why* the guard reads activeWeek. If this ever fails, the site
    changed its fallback behaviour and the guard needs rechecking."""
    snap = parse_jornada(_read("jornada-2026-w38-fallback.html"), requested_week=None)
    assert snap.week == 2, "the served data is jornada 2, whatever week 38 was asked for"


def test_active_week_mismatch_is_rejected_even_when_the_week_exists():
    """No committed fixture can represent this case: a jornada that IS in
    `rounds` (genuinely played) but whose data the site withheld for this
    specific request — e.g. a mid-jornada partial rollout. All three
    committed fallback fixtures represent an unplayed-or-absent week
    instead, so parsing them only ever reaches the `rounds` guard, never
    the `activeWeek` comparison. This hand-builds the minimal flight-chunk
    wrapper (`self.__next_f.push([...])`) the parser actually reads, so the
    `activeWeek != requested_week` clause — the guard the design document
    calls primary — gets exercised directly instead of staying dead code
    that every existing fixture-based test would pass around.
    """
    payload = {
        "fantasyLiveInitialSnapshot": {
            "activeWeek": 3,
            "rounds": [{"round": "Regular Season - 5", "week": 5}],
            "players": [],
        },
        "seasonYear": 2026,
    }
    inner = "1:" + json.dumps(payload)
    array_literal = json.dumps([1, inner])
    html = f"<html><body><script>self.__next_f.push({array_literal})</script></body></html>"

    with pytest.raises(JornadaFallback) as exc_info:
        parse_jornada(html, requested_week=5)

    # Names both numbers, not just "an exception happened" — a swapped
    # comparison or a mixed-up f-string would fail this even though *a*
    # JornadaFallback still fires.
    message = str(exc_info.value)
    assert "Requested jornada 5" in message
    assert "activeWeek 3" in message


def test_a_player_registered_to_both_clubs_yields_one_row():
    """The source lists a player once per club registration while a
    transfer is recent or pending, so one jornada can carry the same slug
    twice — observed live on 2025 week 16 (`alfon-gonzalez-119213`).
    `PlayerGameweekPoints`'s key is (season_year, week, player_id), so two
    rows for one player is a crash, and it crashed the first real
    backfill. The same collapse `parse_points_predictions` already does
    for the market page applies here: keep the highest-points row, which
    is the registration he actually played under.

    Hand-built rather than fixture-based for the reason
    `test_active_week_mismatch_is_rejected_even_when_the_week_exists`
    gives: none of the committed captures happens to contain a duplicate,
    which is precisely how this reached the live database.
    """
    payload = {
        "fantasyLiveInitialSnapshot": {
            "activeWeek": 16,
            "rounds": [{"round": "Regular Season - 16", "week": 16}],
            "players": [
                {"slug": "alfon-119213", "playerName": "Alfon", "positionId": 3, "weekPoints": 0},
                {"slug": "alfon-119213", "playerName": "Alfon", "positionId": 3, "weekPoints": 7},
            ],
        },
        "seasonYear": 2025,
    }
    inner = "1:" + json.dumps(payload)
    array_literal = json.dumps([1, inner])
    html = f"<html><body><script>self.__next_f.push({array_literal})</script></body></html>"

    snap = parse_jornada(html, requested_week=16)

    assert len(snap.records) == 1
    assert snap.records[0]["points"] == 7


def test_slugless_rows_are_never_collapsed_into_each_other():
    """The collapse is keyed on slug, and 31 real players carry none. Two
    slugless rows are two different players until the resolver says
    otherwise — merging them here would delete one silently."""
    payload = {
        "fantasyLiveInitialSnapshot": {
            "activeWeek": 16,
            "rounds": [{"round": "Regular Season - 16", "week": 16}],
            "players": [
                {"playerName": "Bellingham", "positionId": 3, "weekPoints": 9},
                {"playerName": "Pepe", "positionId": 2, "weekPoints": 4},
            ],
        },
        "seasonYear": 2025,
    }
    inner = "1:" + json.dumps(payload)
    array_literal = json.dumps([1, inner])
    html = f"<html><body><script>self.__next_f.push({array_literal})</script></body></html>"

    snap = parse_jornada(html, requested_week=16)

    assert len(snap.records) == 2
