"""Validation gate between parse and load — the only place a scraped
batch can be refused before it reaches durable storage (T-03-01).

Lives in `core/`, not the scraper adapter, because "what counts as a bad
batch" is a business rule that must stay reusable if a second source is
ever added, and because a pure function over already-parsed records is
testable without a live scraper or a live data store. Performs no
transport calls, no database access of any kind — it only reads plain
Python dicts and the already-loaded `Settings` object handed to it.

Implements the three D-02 rejection conditions, reading every threshold
from `Settings` rather than module constants, so they can be tuned after
watching real runs (01-RESEARCH.md Open Questions #1):

1. Row count below `settings.min_row_count`.
2. `price`/`points`/`position` null on more than `settings.max_null_rate`
   of rows.
3. Any row's price outside `[settings.price_min_eur, settings.price_max_eur]`.
"""

from dataclasses import dataclass, field

from core.config import Settings

# `parse_page` (scraper.sources.analiticafantasy) emits the price field as
# `market_value`; a hypothetical second source might call it `price`. This
# gate accepts either name so it stays a source-agnostic contract rather
# than hard-coding one adapter's column naming.
_PRICE_FIELD_NAMES = ("market_value", "price")


@dataclass
class ValidationResult:
    ok: bool
    row_count: int
    reasons: list[str] = field(default_factory=list)


def _price_of(record: dict) -> int | float | None:
    for name in _PRICE_FIELD_NAMES:
        value = record.get(name)
        if value is not None:
            return value
    return None


def validate_scrape(records: list[dict], settings: Settings) -> ValidationResult:
    """Pure gate over already-parsed records. Never raises on bad data —
    a malformed batch is reported via `ValidationResult.reasons`, never an
    exception, so callers can always finish the run with a named cause."""
    reasons: list[str] = []
    row_count = len(records)

    if row_count < settings.min_row_count:
        reasons.append(f"row_count {row_count} below minimum {settings.min_row_count}")

    if row_count > 0:
        required_checks = (
            ("price", _price_of),
            ("points", lambda r: r.get("points")),
            ("position", lambda r: r.get("position")),
        )
        for field_name, getter in required_checks:
            null_count = sum(1 for r in records if getter(r) is None)
            rate = null_count / row_count
            if rate > settings.max_null_rate:
                reasons.append(
                    f"{field_name} null on {rate:.0%} of rows (max {settings.max_null_rate:.0%})"
                )

        for r in records:
            price = _price_of(r)
            in_bounds = price is None or settings.price_min_eur <= price <= settings.price_max_eur
            if not in_bounds:
                reasons.append(
                    f"player {r.get('external_id')}: price {price} outside "
                    f"[{settings.price_min_eur}, {settings.price_max_eur}]"
                )

    return ValidationResult(ok=not reasons, row_count=row_count, reasons=reasons)


#: A 20-team round-robin is 38 jornadas — a structural fact about the
#: competition, not a tunable. A jornada outside this range means the
#: payload changed shape, not that the season grew.
SEASON_MATCHDAYS = 38


def validate_fixtures(records, settings: Settings) -> ValidationResult:
    """Gate between the calendar parse and the `fixture` table (INGEST-04).

    Same contract as `validate_scrape`: pure, never raises on bad data, and
    reports every reason so the dataset can be finished with a named cause.
    `records` are duck-typed `FixtureRecord`s — core never imports the
    scraper.
    """
    reasons: list[str] = []
    row_count = len(records)

    if row_count < settings.min_fixture_count:
        reasons.append(f"fixture_count {row_count} below minimum {settings.min_fixture_count}")

    for record in records:
        if record.kickoff_utc.tzinfo is None:
            reasons.append(f"fixture {record.fixture_id}: kickoff has no timezone")
        if not 1 <= record.matchday <= SEASON_MATCHDAYS:
            reasons.append(
                f"fixture {record.fixture_id}: matchday {record.matchday} outside "
                f"[1, {SEASON_MATCHDAYS}]"
            )
        if not record.home_team or not record.away_team:
            reasons.append(f"fixture {record.fixture_id}: missing a team name")

    return ValidationResult(ok=not reasons, row_count=row_count, reasons=reasons)
