"""One policy-compliant HTTP GET, shared by every httpx-based scraper.

`docs/SCRAPING-POLICY.md`'s conduct rules are correctness requirements,
not optional hardening, and they are implemented here exactly once:
an honest identifying User-Agent, a jittered pre-request delay, requests
issued one at a time, retries only for transport failures, and a terminal
outcome for 403/429/404 that is never retried into.

The Playwright path (`sources/analiticafantasy.py`) keeps its own `_goto`
because a browser navigation is a different operation; the *policy* is the
same and both honour it.
"""

import random
import time

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import Settings, get_settings
from scraper.errors import (
    ScrapeBlocked,
    ScrapeNetworkError,
    ScrapeNotPublished,
    ScrapeStructureChanged,
    classify_response,
)

_MIN_DELAY_SECONDS = 0.5
_MAX_DELAY_SECONDS = 2.0
_TIMEOUT_SECONDS = 30.0


@retry(
    retry=retry_if_exception_type(ScrapeNetworkError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _get(url: str, structure_markers: tuple[str, ...], settings: Settings) -> str:
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": settings.user_agent},
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        raise ScrapeNetworkError(str(exc)) from exc

    html = response.text
    error_type = classify_response(response.status_code, html, structure_markers)
    if error_type is ScrapeBlocked:
        raise ScrapeBlocked(f"Blocked by target site: HTTP {response.status_code} for {url}")
    if error_type is ScrapeNotPublished:
        raise ScrapeNotPublished(f"Not published by the source: HTTP 404 for {url}")
    if error_type is ScrapeStructureChanged:
        raise ScrapeStructureChanged(f"Expected data not found in response for {url}")
    return html


def fetch_page(
    url: str,
    structure_markers: tuple[str, ...],
    settings: Settings | None = None,
    *,
    min_delay: float = _MIN_DELAY_SECONDS,
    max_delay: float = _MAX_DELAY_SECONDS,
) -> str:
    """Fetch one page. The jittered delay lives here rather than in `_get`
    so unit tests exercising retry classification pay no real sleep.

    `min_delay`/`max_delay` let each source set its own pace: the policy's
    rate limit is per counterparty, and a second site should not inherit
    the first one's numbers by accident."""
    settings = settings or get_settings()
    time.sleep(random.uniform(min_delay, max(min_delay, max_delay)))
    return _get(url, structure_markers, settings)
