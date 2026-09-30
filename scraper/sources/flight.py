"""Extraction of the Next.js flight-data payloads that analiticafantasy.com
embeds in its server-rendered HTML.

Every page this project scrapes hides its data the same way: one or more
`self.__next_f.push([1, "<chunk>"])` script tags whose concatenated
payloads carry the page's hydration JSON. This module owns that mechanic
so the four callers share one implementation — in particular one
implementation of `_FLIGHT_REF_PREFIX_RE`.

**That regex is load-bearing.** Next.js numbers its flight chunks in
hexadecimal and the value changes with every deploy of the target site.
An earlier `^\\d+:` form parsed on deploys whose id happened to contain no
hex letter and failed on the rest — a per-deploy coin flip that cost ten
of the first twenty-six daily runs. Do not narrow it.
"""

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

from bs4 import BeautifulSoup

_NEXT_F_PUSH_RE = re.compile(r"self\.__next_f\.push\((\[.*\])\)\s*$", re.S)
_FLIGHT_REF_PREFIX_RE = re.compile(r"^[0-9a-fA-F]+:(.*)$", re.S)


def iter_flight_chunks(html: str, must_contain: str | None = None) -> Iterator[Any]:
    """Yield each decoded flight chunk in document order.

    `must_contain` is a cheap textual pre-filter on the raw script text —
    skipping chunks that cannot hold the wanted key avoids parsing
    megabytes of unrelated JSON on every call.
    """
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script"):
        text = script.string
        if not text or "self.__next_f.push(" not in text:
            continue
        if must_contain is not None and must_contain not in text:
            continue

        match = _NEXT_F_PUSH_RE.search(text.strip())
        if not match:
            continue
        try:
            outer = json.loads(match.group(1))
            payload_str = outer[1]
            ref_match = _FLIGHT_REF_PREFIX_RE.match(payload_str)
            inner = ref_match.group(1) if ref_match else payload_str
            yield json.loads(inner)
        except (json.JSONDecodeError, IndexError, TypeError):
            # A chunk that isn't JSON, or isn't shaped like a flight
            # payload, is ordinary — the page has many. Skip it.
            continue


def find_key(obj: Any, key: str) -> Any | None:
    """First value stored under `key` anywhere in `obj`, depth-first.

    Kept for `analiticafantasy.py`, whose `initialPlayers` lookup has no
    ambiguity. Prefer `find_records` / `find_mapping` for new callers —
    see their docstrings for why first-match is not always enough.
    """
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = find_key(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_key(item, key)
            if found is not None:
                return found
    return None


def _search(obj: Any, key: str, accept: Callable[[Any], bool]) -> Any | None:
    """Depth-first search for `key` whose value satisfies `accept`.

    Unlike `find_key`, a match on the key name alone is not enough: the
    search continues past any value `accept` rejects. This exists because
    on the predictions page the first `"players"` in tree order is not
    the data — it is the i18n string `"players": "Jugadores"` — and the
    real payload of 492 rows is a second, later `"players"` key. A
    first-match search silently returns that string instead.
    """
    if isinstance(obj, dict):
        if key in obj and accept(obj[key]):
            return obj[key]
        for value in obj.values():
            found = _search(value, key, accept)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _search(item, key, accept)
            if found is not None:
                return found
    return None


def find_records(html: str, key: str, required_field: str) -> list[dict] | None:
    """A list of dicts stored under `key` whose first element carries
    `required_field`. `None` when no qualifying list exists."""

    def accept(value: Any) -> bool:
        return (
            isinstance(value, list)
            and len(value) > 0
            and isinstance(value[0], dict)
            and required_field in value[0]
        )

    for data in iter_flight_chunks(html, must_contain=key):
        found = _search(data, key, accept)
        if found is not None:
            return found
    return None


def find_mapping(html: str, key: str, required_field: str) -> dict | None:
    """A dict stored under `key` carrying `required_field`. `None` when no
    qualifying mapping exists."""

    def accept(value: Any) -> bool:
        return isinstance(value, dict) and required_field in value

    for data in iter_flight_chunks(html, must_contain=key):
        found = _search(data, key, accept)
        if found is not None:
            return found
    return None
