from datetime import date
from pathlib import Path

import pytest

from scraper.sources.af_player_page import parse_player_page
from tests.scraper.player_page_html import html_with_payload

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "player-page"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_market_oldest_first_and_matches_week_ascending():
    payload = {
        "marketHistory": [
            {"day": 2, "date": "2026-08-15", "marketValue": 47412381, "delta": -1644084},
            {"day": 1, "date": "2026-08-14", "marketValue": 49056465, "delta": 0},
        ],
        "statsRows": [
            {
                "week": 2,
                "points": 4,
                "minutes": 90,
                "goals": 0,
                "assists": 0,
                "yellowCards": 0,
                "redCards": 0,
                "stats": {"mins_played": 90, "goals": 0},
                "fixture": "Team A - Team B",
            },
            {
                "week": 1,
                "points": 0,
                "minutes": 0,
                "goals": 0,
                "assists": 0,
                "yellowCards": 0,
                "redCards": 0,
                "stats": {},
                "fixture": "Team C - Team D",
            },
        ],
    }
    html = html_with_payload(payload)

    page = parse_player_page(html)

    assert [m.day for m in page.market] == [date(2026, 8, 14), date(2026, 8, 15)]
    assert page.market[0].market_value == 49056465
    assert page.market[0].delta == 0
    assert page.market[1].delta == -1644084

    assert [m.week for m in page.matches] == [1, 2]
    dnp, started = page.matches
    assert dnp.minutes == 0
    assert dnp.components == {}
    assert started.minutes == 90
    assert started.points == 4


def test_missing_market_history_raises_value_error():
    html = html_with_payload({"someOtherKey": [{"foo": "bar"}]})

    with pytest.raises(ValueError):
        parse_player_page(html)


def test_parses_the_captured_grimaldo_page():
    page = parse_player_page(_read("grimaldo.html"))

    assert len(page.market) == 48
    assert page.market[0].day == date(2026, 8, 14)
    assert len(page.matches) == 7
