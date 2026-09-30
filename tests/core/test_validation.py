"""Boundary coverage for the three `validate_scrape()` rejection rules
(D-02): row count, required-field null rate, and price bounds. Each rule
is exercised at its threshold and one step either side, per
01-03-PLAN.md's `must_haves.truths`.
"""

from core.config import Settings
from core.validation import validate_scrape


def _settings(**overrides) -> Settings:
    base = {
        "min_row_count": 300,
        "max_null_rate": 0.05,
        "price_min_eur": 0,
        "price_max_eur": 200_000_000,
    }
    base.update(overrides)
    return Settings(**base)


def _make_records(count: int, **field_overrides) -> list[dict]:
    records = []
    for i in range(count):
        record = {
            "external_id": f"player-{i}",
            "market_value": 1_000_000,
            "points": 10,
            "position": "DEF",
        }
        record.update(field_overrides)
        records.append(record)
    return records


# --- Row count ---------------------------------------------------------


def test_row_count_exactly_at_minimum_is_accepted():
    result = validate_scrape(_make_records(300), _settings())
    assert result.ok
    assert result.row_count == 300


def test_row_count_one_below_minimum_is_rejected():
    result = validate_scrape(_make_records(299), _settings())
    assert not result.ok
    assert any("row_count 299" in r and "300" in r for r in result.reasons)


def test_row_count_reason_names_observed_and_minimum():
    result = validate_scrape(_make_records(10), _settings())
    assert any("10" in r and "300" in r for r in result.reasons)


# --- Required-field null rate -------------------------------------------


def test_null_rate_exactly_at_max_is_accepted():
    records = _make_records(300)
    for r in records[:15]:  # 15 / 300 == 0.05
        r["market_value"] = None
    result = validate_scrape(records, _settings())
    assert result.ok


def test_null_rate_above_max_is_rejected():
    records = _make_records(300)
    for r in records[:18]:  # 18 / 300 == 0.06
        r["market_value"] = None
    result = validate_scrape(records, _settings())
    assert not result.ok
    assert any("price" in r for r in result.reasons)


def test_null_points_above_max_is_rejected():
    records = _make_records(300)
    for r in records[:18]:
        r["points"] = None
    result = validate_scrape(records, _settings())
    assert not result.ok
    assert any("points" in r for r in result.reasons)


def test_null_position_above_max_is_rejected():
    records = _make_records(300)
    for r in records[:18]:
        r["position"] = None
    result = validate_scrape(records, _settings())
    assert not result.ok
    assert any("position" in r for r in result.reasons)


# --- Price bounds --------------------------------------------------------


def test_price_exactly_zero_is_accepted():
    result = validate_scrape(_make_records(300, market_value=0), _settings())
    assert result.ok


def test_price_exactly_at_max_is_accepted():
    result = validate_scrape(_make_records(300, market_value=200_000_000), _settings())
    assert result.ok


def test_price_below_zero_is_rejected():
    records = _make_records(300)
    records[0]["market_value"] = -1
    result = validate_scrape(records, _settings())
    assert not result.ok
    assert any("outside" in r for r in result.reasons)


def test_price_above_max_is_rejected():
    records = _make_records(300)
    records[0]["market_value"] = 200_000_001
    result = validate_scrape(records, _settings())
    assert not result.ok
    assert any("outside" in r for r in result.reasons)


def test_price_reason_names_offending_player():
    records = _make_records(300)
    records[5]["market_value"] = -1
    result = validate_scrape(records, _settings())
    assert any("player-5" in r for r in result.reasons)


# --- Empty batch -----------------------------------------------------------


def test_empty_batch_is_rejected_on_row_count_only():
    result = validate_scrape([], _settings())
    assert not result.ok
    assert result.row_count == 0
    assert len(result.reasons) == 1
