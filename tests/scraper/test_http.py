import httpx
import pytest

from scraper.errors import ScrapeBlocked, ScrapeNetworkError, ScrapeNotPublished, classify_response
from scraper.http import fetch_page

MARKERS = ("fantasyliveinitialsnapshot",)


def test_404_classifies_as_not_published():
    assert classify_response(404, "<html>nope</html>", MARKERS) is ScrapeNotPublished


def test_403_still_classifies_as_blocked():
    assert classify_response(403, "<html>x</html>", MARKERS) is ScrapeBlocked


def test_fetch_page_returns_html_on_a_healthy_response(monkeypatch):
    def fake_get(url, **kwargs):
        return httpx.Response(200, text="<html>fantasyLiveInitialSnapshot</html>")

    monkeypatch.setattr("scraper.http.httpx.get", fake_get)
    monkeypatch.setattr("scraper.http.time.sleep", lambda _: None)
    assert "fantasyLive" in fetch_page("https://example.test/x", MARKERS)


def test_fetch_page_raises_not_published_on_404_without_retrying(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return httpx.Response(404, text="<html>Página no encontrada</html>")

    monkeypatch.setattr("scraper.http.httpx.get", fake_get)
    monkeypatch.setattr("scraper.http.time.sleep", lambda _: None)
    with pytest.raises(ScrapeNotPublished):
        fetch_page("https://example.test/missing", MARKERS)
    assert len(calls) == 1, "a 404 is terminal — it must not be retried"


def test_fetch_page_never_retries_into_a_block(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return httpx.Response(429, text="<html>slow down</html>")

    monkeypatch.setattr("scraper.http.httpx.get", fake_get)
    monkeypatch.setattr("scraper.http.time.sleep", lambda _: None)
    with pytest.raises(ScrapeBlocked):
        fetch_page("https://example.test/x", MARKERS)
    assert len(calls) == 1, "docs/SCRAPING-POLICY.md: never retry into a block"


def test_fetch_page_retries_a_transport_failure(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("scraper.http.httpx.get", fake_get)
    monkeypatch.setattr("scraper.http.time.sleep", lambda _: None)
    with pytest.raises(ScrapeNetworkError):
        fetch_page("https://example.test/x", MARKERS)
    assert len(calls) == 3, "only a network failure is worth retrying"
