from pathlib import Path

from scraper.sources.flight import find_mapping, find_records

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "phase7"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_find_mapping_returns_the_jornada_snapshot():
    snapshot = find_mapping(
        _read("jornada-2026-w1.html"), "fantasyLiveInitialSnapshot", "activeWeek"
    )
    assert snapshot is not None
    assert snapshot["activeWeek"] == 1
    assert len(snapshot["players"]) == 248


def test_find_records_skips_a_same_named_match_that_lacks_the_required_field():
    # The predictions page's first "players" key in tree order is a React
    # element (9 entries, keys like "J") — not the data. A first-match search
    # returns that; find_records must keep looking for the 492 real rows.
    rows = find_records(_read("predicciones.html"), "players", "predictedPoints")
    assert rows is not None
    assert len(rows) == 492
    assert "predictedPoints" in rows[0]


def test_find_records_reads_the_season_stats_array():
    rows = find_records(_read("estadisticas-2025.html"), "initialPlayers", "totalPoints")
    assert rows is not None
    assert len(rows) == 702


def test_find_records_reads_a_market_prediction_list():
    rows = find_records(_read("prediccion-de-mercado.html"), "topSubidas", "n")
    assert rows is not None
    assert len(rows) == 10


def test_missing_key_returns_none_rather_than_raising():
    assert find_records(_read("predicciones.html"), "noSuchKey", "x") is None
