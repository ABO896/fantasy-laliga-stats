"""Tests for `scraper.errors` classification and the retry policy wired
around it in `scraper.sources.analiticafantasy._goto`.
"""

from pathlib import Path

import pytest

from scraper.errors import ScrapeBlocked, ScrapeStructureChanged, classify_response
from scraper.sources.analiticafantasy import _goto

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_403_is_classified_blocked():
    assert classify_response(403, "") is ScrapeBlocked


def test_429_is_classified_blocked():
    assert classify_response(429, "") is ScrapeBlocked


def test_challenge_page_body_is_classified_blocked():
    html = _read("challenge-page.html")
    assert classify_response(200, html) is ScrapeBlocked


def test_tableless_page_is_classified_structure_changed():
    html = "<html><body><p>Nothing recognizable here.</p></body></html>"
    assert classify_response(200, html) is ScrapeStructureChanged


def test_healthy_page_is_not_an_error():
    html = _read("puja-ideal-page1.html")
    assert classify_response(200, html) is None


class _FakeResponse:
    def __init__(self, status: int):
        self.status = status


class _FakePage:
    """Minimal stand-in for a Playwright `Page` — just enough surface for
    `_goto` to drive, with a call counter proving retry behavior without
    launching a real browser."""

    def __init__(self, status: int, html: str = ""):
        self.status = status
        self.html = html
        self.goto_calls = 0

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls += 1
        return _FakeResponse(self.status)

    def wait_for_selector(self, selector, timeout=None):
        pass

    def content(self):
        return self.html


def test_blocked_response_is_not_retried():
    fake_page = _FakePage(status=403)
    with pytest.raises(ScrapeBlocked):
        _goto(fake_page, "https://example.invalid/puja-ideal")
    assert fake_page.goto_calls == 1


def test_structure_changed_response_is_not_retried():
    fake_page = _FakePage(status=200, html="<html><body>no table</body></html>")
    with pytest.raises(ScrapeStructureChanged):
        _goto(fake_page, "https://example.invalid/puja-ideal")
    assert fake_page.goto_calls == 1


def test_healthy_response_returns_html():
    healthy_html = _read("puja-ideal-page1.html")
    fake_page = _FakePage(status=200, html=healthy_html)
    result = _goto(fake_page, "https://example.invalid/puja-ideal")
    assert result == healthy_html
    assert fake_page.goto_calls == 1
