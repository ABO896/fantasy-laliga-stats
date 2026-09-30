import pytest

from core.parsing import (
    normalize_availability,
    normalize_position,
    parse_euro_price,
    parse_percentage,
)
from core.transform import compute_price_per_point


def test_parse_euro_price():
    assert parse_euro_price("66.770.014 €") == 66770014
    assert parse_euro_price("100.386.152 €") == 100386152
    assert parse_euro_price("+2.931.756 €") == 2931756


def test_parse_percentage():
    assert parse_percentage("4.59 %") == pytest.approx(4.59)
    assert parse_percentage("2.29 %") == pytest.approx(2.29)
    assert parse_percentage("-25%") == pytest.approx(-25.0)


def test_normalize_availability():
    assert normalize_availability("available") == "available"
    assert normalize_availability("injured") == "injured"
    assert normalize_availability("dudas") == "doubtful"
    assert normalize_availability("sancionados") == "suspended"


def test_normalize_position():
    assert normalize_position("Portero") == "POR"
    assert normalize_position("Defensa") == "DEF"
    assert normalize_position("Centrocampista") == "MED"
    assert normalize_position("Delantero") == "DEL"


def test_price_per_point_zero_points_is_none():
    assert compute_price_per_point(50_000_000, 0) is None


def test_price_per_point_is_unrounded():
    value = compute_price_per_point(10_000_000, 3)
    assert value is not None
    assert value != round(value, 2)
