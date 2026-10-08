"""A blocked page is kept for diagnosis, and the error names what matched.

On 2026-10-08 the market page was "blocked" twice and then fine seconds
later, and nothing of the blocked responses was kept — so whether it was a
real challenge or a false match in `_CHALLENGE_MARKERS` could not be told.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scraper import run as run_mod
from scraper.errors import ScrapeBlocked, matched_marker
from scraper.sources import analiticafantasy as af
from storage.db import set_engine

CHALLENGE = "<html><title>Just a moment...</title></html>"


def test_matched_marker_names_the_marker():
    assert matched_marker(CHALLENGE) == "just a moment"
    assert matched_marker("<table>initialPlayers</table>") is None


def test_goto_attaches_the_page_and_names_the_marker():
    page = MagicMock()
    page.goto.return_value = MagicMock(status=200)
    page.wait_for_selector.side_effect = af.PlaywrightError("timeout")
    page.content.return_value = CHALLENGE

    with pytest.raises(ScrapeBlocked) as exc:
        af._goto.__wrapped__(page, "https://example.test/puja-ideal")

    assert exc.value.html == CHALLENGE
    assert 'marker: "just a moment"' in str(exc.value)


@pytest.fixture()
def quiet_later_steps(monkeypatch):
    for name in ("ingest_fixtures", "ingest_jornada_points", "ingest_season_stats",
                 "ingest_points_predictions", "ingest_market_predictions",
                 "ingest_player_pages", "ingest_football_data", "run_our_models",
                 "run_expected_points"):
        monkeypatch.setattr(run_mod, name, lambda *a, **k: None)


def test_a_blocked_market_page_is_written_to_the_run_dir(engine, quiet_later_steps):
    set_engine(engine)

    def blocked(*a, **k):
        raise ScrapeBlocked('Blocked by target site: HTTP 200 (marker: "just a moment")',
                            html=CHALLENGE)

    with patch("scraper.run.fetch_pages", side_effect=blocked):
        result = run_mod.run_daily_refresh()

    saved = Path(result.raw_snapshot_dir) / "blocked_market.html"
    assert saved.read_text(encoding="utf-8") == CHALLENGE
    assert "just a moment" in result.validation_errors
