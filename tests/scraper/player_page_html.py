"""Synthetic player-page HTML for tests — never a scraped capture.

Shared by `tests/scraper/test_af_player_page.py` (parser) and
`tests/integration/test_player_pages_ingest.py` (refresh). Not a test
module itself — nothing here is collected by pytest.
"""

import json


def html_with_payload(payload: dict) -> str:
    """Wrap `payload` the way the site's flight stream carries it: one
    `self.__next_f.push([1, "1:{...}"])` script."""
    inner = "1:" + json.dumps(payload)
    array_literal = json.dumps([1, inner])
    return f"<html><body><script>self.__next_f.push({array_literal})</script></body></html>"


def minimal_player_page(day: str = "2026-09-01", week: int = 1) -> str:
    """A page with one market day and one played match."""
    return html_with_payload(
        {
            "marketHistory": [
                {"day": 1, "date": day, "marketValue": 1_000_000, "delta": 0},
            ],
            "statsRows": [
                {
                    "week": week,
                    "points": 5,
                    "minutes": 90,
                    "goals": 0,
                    "assists": 0,
                    "yellowCards": 0,
                    "redCards": 0,
                    "stats": {"mins_played": 90},
                    "fixture": "Team A - Team B",
                },
            ],
        }
    )
