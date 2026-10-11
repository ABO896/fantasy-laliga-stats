"""Scrape failure classification — three distinguishable outcomes so
retries and alerts behave correctly (PITFALLS.md Pitfall 2).

A 403/429/bot-challenge response is a *terminal* "blocked" outcome per
`docs/SCRAPING-POLICY.md` — never retried, since retrying only makes a
block worse. A structurally-changed page (loads fine, but no recognizable
player data) is also terminal — retrying will not make a redesigned page
parse. Only a transport/timeout failure is worth retrying.
"""

# Substrings that show up in common bot-challenge/interstitial pages
# (Cloudflare-style and similar). Matched case-insensitively against the
# response body. This is a heuristic, deliberately over-inclusive backstop
# — the row-count validation gate (core/validation.py) is the second line
# of defense if a novel challenge page slips past this list.
_CHALLENGE_MARKERS = (
    "captcha",
    "cloudflare",
    "checking your browser",
    "attention required",
    "access denied",
    "just a moment",
)


class ScrapeError(Exception):
    """Base class for every classified scrape failure. `html` carries the
    response body when there was one, so a refresh can keep the page that
    failed for diagnosis."""

    def __init__(self, message: str = "", html: str | None = None):
        super().__init__(message)
        self.html = html


def blocked_message(detail: str, html: str | None) -> str:
    """`Blocked by target site: <detail>`, plus the challenge marker that
    matched, when one did (a 403/429 needs none)."""
    marker = matched_marker(html)
    suffix = f' (marker: "{marker}")' if marker else ""
    return f"Blocked by target site: {detail}{suffix}"


def matched_marker(html: str | None) -> str | None:
    """The first `_CHALLENGE_MARKERS` entry found in `html`, or `None` —
    named in a block's message so a false match can be told from a real
    challenge."""
    lowered = (html or "").lower()
    return next((m for m in _CHALLENGE_MARKERS if m in lowered), None)


class ScrapeBlocked(ScrapeError):
    """HTTP 403, 429, or a 200 response whose body is a bot-challenge
    page. Terminal — never retried."""


class ScrapeStructureChanged(ScrapeError):
    """A 200 response that loads fine but contains no recognizable player
    table/data. Terminal — retrying will not make a redesigned page
    parse."""


class ScrapeNotPublished(ScrapeError):
    """HTTP 404 for an addressed season or jornada the source has not
    published. Terminal, and **not** a failure of this project — it is a
    fact about the source. Recorded as its own state so the health page
    does not sit permanently red on something no code change can fix."""


class ScrapeNetworkError(ScrapeError):
    """A transport-level failure or timeout. The only classification
    that's worth retrying."""


#: The player page's structural fingerprint. Kept as the default so the
#: existing caller's behaviour is unchanged by the calendar page's arrival.
_PLAYER_STRUCTURE_MARKERS = ("initialplayers", "<table")


def classify_response(
    status_code: int | None,
    html: str,
    structure_markers: tuple[str, ...] = _PLAYER_STRUCTURE_MARKERS,
) -> type[ScrapeError] | None:
    """Classify one fetched response.

    Returns the specific `ScrapeError` subclass the caller should raise,
    or `None` when the response looks healthy. Order matters: a
    bot-challenge body is checked before the "no data" structure check,
    since a challenge page also has no data but is a distinct (and
    higher-priority) failure mode.

    `structure_markers` is per-page because "looks structurally intact" is
    a property of the page being fetched, not of the site. The calendar
    page contains neither of the player page's markers meaningfully, so
    sharing one fingerprint would either misclassify a healthy calendar
    page or accept a redesigned one.
    """
    if status_code in (403, 429):
        return ScrapeBlocked

    if status_code == 404:
        return ScrapeNotPublished

    lowered = (html or "").lower()
    if any(marker in lowered for marker in _CHALLENGE_MARKERS):
        return ScrapeBlocked

    if not any(marker in lowered for marker in structure_markers):
        return ScrapeStructureChanged

    return None
