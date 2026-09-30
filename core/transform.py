"""Raw parsed record -> canonical `PlayerSnapshot`.

Efficiency (`price_per_point`) is computed independently from raw
`market_value` and `points` here — never derived from the site's own "Puja
ideal" column, which is stored only as the `ideal_bid` reference field
(see `docs/SCRAPING-POLICY.md` and `01-RESEARCH.md` Anti-Patterns).
"""

import json
from datetime import date

from storage.models import PlayerSnapshot


def compute_price_per_point(market_value: int, points: int) -> float | None:
    """`None` when `points <= 0` — never infinity, never an exception.

    Deliberately left unrounded: rounding to 2 decimals happens only at
    display time, never before storage.
    """
    if points <= 0:
        return None
    return market_value / points


def to_snapshot(
    record: dict,
    player_id: int,
    as_of: date,
    scrape_run_id: int,
) -> PlayerSnapshot:
    """Assemble a `PlayerSnapshot` from one parsed record.

    `raw_fields` stores every key `parse_page` produced, verbatim, as JSON
    — including keys with no dedicated typed column — so a field promoted
    to a typed column later can be backfilled from existing history rather
    than losing it permanently.
    """
    market_value = record["market_value"]
    points = record["points"]

    return PlayerSnapshot(
        as_of=as_of,
        player_id=player_id,
        market_value=market_value,
        ideal_bid=record.get("ideal_bid"),
        max_bid=record.get("max_bid"),
        price_change_abs=record.get("price_change_abs"),
        price_change_pct=record.get("price_change_pct"),
        points=points,
        price_per_point=compute_price_per_point(market_value, points),
        starter_probability=record.get("starter_probability"),
        availability_status=record["availability_status"],
        next_opponent=record.get("next_opponent"),
        raw_fields=json.dumps(record, ensure_ascii=False),
        scrape_run_id=scrape_run_id,
    )
