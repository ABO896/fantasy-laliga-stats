from datetime import date, timedelta

import pytest

from core import market_v2 as m2

D0 = date(2026, 8, 14)


def row(pid, pos, day, r7, target, **x):
    feats = dict.fromkeys(m2.FEATURES, 0.0) | {"r7": r7} | x
    return m2.Row(pid, pos, day, feats, target, day + timedelta(days=7))


def test_price_change_pct():
    values = {D0: 1_000_000, D0 + timedelta(days=7): 1_100_000}
    assert m2.price_change_pct(values, D0 + timedelta(days=7), 7) == pytest.approx(10.0)
    assert m2.price_change_pct(values, D0 + timedelta(days=3), 7) is None


def test_fit_uses_only_matured_rows():
    rows = [row(i, "DEF", D0, r7=1.0, target=2.0) for i in range(400)]
    late = [row(1000 + i, "DEF", D0 + timedelta(days=5), r7=1.0, target=-50.0)
            for i in range(400)]
    fits = m2.fit_models(rows + late, fit_date=D0 + timedelta(days=7))
    # The late rows mature on D0+12, after the fit date: they must not pull the mean down.
    out = m2.predict(row(1, "DEF", D0, 1.0, None), fits)
    assert out.expected_pct == pytest.approx(2.0, abs=0.2)


def test_ridge_learns_persistence_slope():
    rows = []
    for i in range(600):
        r7 = (i % 21) - 10.0
        rows.append(row(i, "MED", D0, r7=r7, target=0.8 * r7))
    fits = m2.fit_models(rows, fit_date=D0 + timedelta(days=30))
    out = m2.predict(row(1, "MED", D0, 5.0, None), fits)
    assert out.expected_pct == pytest.approx(4.0, abs=0.3)
    assert out.direction == "rise" and out.basis == "ridge"


def test_sparse_position_falls_back():
    rows = [row(i, "DEL", D0, r7=2.0, target=1.0) for i in range(350)]
    rows += [row(1000 + i, "POR", D0, r7=2.0, target=1.0) for i in range(5)]
    fits = m2.fit_models(rows, fit_date=D0 + timedelta(days=30))
    assert fits["POR"].pooled is True
    empty = m2.fit_models([], fit_date=D0)
    out = m2.predict(row(1, "POR", D0, 4.0, None), empty)
    assert out.basis == "persistence"
    assert out.expected_pct == pytest.approx(2.0)


def test_drop_risk_and_flat_band():
    o = m2.Outlook(0.3, "flat", -3.5, 2.0, True, "ridge", {})
    assert m2.confidence_for(o) == "weak"
    assert m2.score("fall", -0.2) == ("flat", False)
    assert m2.score("fall", -0.9) == ("fall", True)
    assert m2.confidence_for(m2.Outlook(-2.0, "fall", -4.0, -0.5, True, "ridge", {})) == "strong"


def test_fit_dates_weekly():
    assert m2.fit_dates(D0, D0 + timedelta(days=15)) == [
        D0, D0 + timedelta(days=7), D0 + timedelta(days=14)]
