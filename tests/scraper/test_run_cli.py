"""`python -m scraper.run` must signal failure through its process exit
status, not just its printed message — so a shell caller (`make scrape`)
can detect a non-success run without parsing stdout. This mattered for the
scheduled agent too, until Phase 13 removed it; it still matters, because
the exit code is what tells you a hand-run scrape failed.

`main()` returns the exit code directly (rather than calling `sys.exit()`
itself) specifically so it stays trivially testable here without needing
`pytest.raises(SystemExit)` around every case.
"""

from datetime import UTC, datetime
from unittest.mock import patch

from scraper.run import main
from storage.models import ScrapeRun


def _fake_run(status: str, row_count: int = 0) -> ScrapeRun:
    return ScrapeRun(
        id=1,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        status=status,
        row_count=row_count,
    )


def test_main_returns_zero_on_success():
    with patch("scraper.run.run_daily_refresh", return_value=_fake_run("success", 342)):
        assert main() == 0


def test_main_returns_nonzero_on_rejected():
    with patch("scraper.run.run_daily_refresh", return_value=_fake_run("rejected", 5)):
        assert main() == 1


def test_main_returns_nonzero_on_failed():
    with patch("scraper.run.run_daily_refresh", return_value=_fake_run("failed", 0)):
        assert main() == 1
