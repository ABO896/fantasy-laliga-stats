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
        assert main([]) == 0


def test_main_returns_nonzero_on_rejected():
    with patch("scraper.run.run_daily_refresh", return_value=_fake_run("rejected", 5)):
        assert main([]) == 1


def test_main_returns_nonzero_on_failed():
    with patch("scraper.run.run_daily_refresh", return_value=_fake_run("failed", 0)):
        assert main([]) == 1


def _capture_mode(argv: list[str]) -> str:
    seen: dict = {}

    def fake(run_id=None, mode="quick"):
        seen["mode"] = mode
        return _fake_run("success")

    with patch("scraper.run.run_daily_refresh", side_effect=fake):
        main(argv)
    return seen["mode"]


def test_no_flag_runs_quick():
    assert _capture_mode([]) == "quick"


def test_mine_flag_runs_mine_mode():
    assert _capture_mode(["--mine"]) == "mine"


def test_full_flag_runs_complete_mode():
    assert _capture_mode(["--full"]) == "complete"


def test_mine_and_full_are_mutually_exclusive():
    import pytest

    with pytest.raises(SystemExit):
        main(["--mine", "--full"])
