"""Pure parsing functions — no I/O, no side effects.

Verified directly against analiticafantasy.com/fantasy-la-liga/puja-ideal
(see `01-RESEARCH.md`): prices are whole-euro integers with period
thousands-separators and no decimal component; percentages use a period
decimal, not a comma. No `locale`/`babel` dependency is needed or used —
these are plain string operations against the site's confirmed format. A
malformed value raises rather than silently coercing (T-02-03) — the
validation gate landing in plan 01-03 is the real safety net against
format drift, not a permissive parser.
"""

import re

_EURO_STRIP_RE = re.compile(r"[€+\s.]")
_PERCENT_STRIP_RE = re.compile(r"[%\s]")

_POSITION_MAP = {
    "portero": "POR",
    "defensa": "DEF",
    "centrocampista": "MED",
    "delantero": "DEL",
}

# The site's confirmed real status vocabulary (verified directly from the
# embedded player JSON: ok | doubtful | injured | suspended) is mapped
# alongside the Spanish nav-menu vocabulary this project's own research
# originally assumed (available | injured | dudas | sancionados) — both are
# supported so this function is correct against the real scraped data and
# against the documented interface contract.
_AVAILABILITY_MAP = {
    "available": "available",
    "ok": "available",
    "injured": "injured",
    "lesionado": "injured",
    "lesionados": "injured",
    "lesion": "injured",
    "doubtful": "doubtful",
    "duda": "doubtful",
    "dudas": "doubtful",
    "suspended": "suspended",
    "sancionado": "suspended",
    "sancionados": "suspended",
    "sancion": "suspended",
}


def parse_euro_price(text: str) -> int:
    """`"66.770.014 €"` -> `66770014`; `"+2.931.756 €"` -> `2931756`.

    Strips the euro sign, a leading `+`, whitespace and every `.`
    (thousands separator), then converts to `int`. No decimal component
    exists in this field on the source site.
    """
    cleaned = _EURO_STRIP_RE.sub("", text)
    return int(cleaned)


def parse_percentage(text: str) -> float:
    """`"4.59 %"` -> `4.59`; `"-25%"` -> `-25.0`.

    Strips `%` and whitespace and converts to `float`. The site uses a
    period decimal here, never a comma.
    """
    cleaned = _PERCENT_STRIP_RE.sub("", text)
    return float(cleaned)


def normalize_position(text: str) -> str:
    """`Portero|Defensa|Centrocampista|Delantero` -> `POR|DEF|MED|DEL`."""
    key = text.strip().lower()
    try:
        return _POSITION_MAP[key]
    except KeyError:
        raise ValueError(f"Unrecognized position: {text!r}") from None


def normalize_availability(text: str) -> str:
    """Site vocabulary -> `available|injured|doubtful|suspended`."""
    key = text.strip().lower()
    try:
        return _AVAILABILITY_MAP[key]
    except KeyError:
        raise ValueError(f"Unrecognized availability status: {text!r}") from None
