# tests/scraper/test_af_predictions.py
import json
from pathlib import Path

from scraper.sources.af_predictions import parse_market_predictions, parse_points_predictions

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "phase7"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_points_predictions_find_the_data_not_the_markup():
    # The first "players" key in tree order is not the data -- it is the
    # i18n string "players": "Jugadores". Reading it would break the parser;
    # the real array is a second, later "players" key with 492 rows -- one
    # per player per fixture, which collapse to 490 distinct players (two
    # players are listed once per club registration during a transfer).
    records, skipped = parse_points_predictions(_read("predicciones.html"))
    assert len(records) == 490
    assert all(r["source"] == "points" for r in records)
    assert all(isinstance(r["value"], float) for r in records)


def test_a_player_registered_to_both_clubs_yields_one_prediction():
    # Hector Fort appears twice in the raw payload (same fixtureId, same
    # predictedPoints) -- once for Barcelona (chance 30) and once for Elche
    # (chance 0), the club he is not turning out for. The parser must keep
    # only the higher-chance registration, and -- the general guarantee --
    # no slug may repeat in the output at all, whichever players the source
    # next lists twice.
    records, skipped = parse_points_predictions(_read("predicciones.html"))
    slugs = [r["external_id"] for r in records]
    assert len(slugs) == len(set(slugs))

    fort = [r for r in records if r["external_id"] == "hector-fort-386859"]
    assert len(fort) == 1
    assert fort[0]["raw"]["chance"] == 30


def test_market_predictions_cover_all_four_lists():
    records, skipped, found_sources = parse_market_predictions(_read("prediccion-de-mercado.html"))
    sources = {r["source"] for r in records}
    assert sources == {
        "market_top_risers",
        "market_top_fallers",
        "market_possible_risers",
        "market_possible_fallers",
    }
    assert found_sources == sources


def test_market_rows_without_a_slug_are_skipped_and_counted():
    # Some rows carry neither `id` nor `slug` and cannot be joined to a
    # player. They must not be dropped silently.
    records, skipped, found_sources = parse_market_predictions(_read("prediccion-de-mercado.html"))
    assert skipped >= 1
    assert all(r["external_id"] for r in records)


def test_a_missing_market_list_is_reported_not_raised():
    """A quiet market day can legitimately empty any one of the four
    lists -- nothing in the payload distinguishes that from the site
    having dropped the list. So a payload missing one list (here,
    topBajadas) must still parse the other three, report topBajadas as
    absent from `found_sources`, and must not raise. Hand-built rather
    than a fixture, per the task: no fixture represents this case."""
    payload = {
        "topSubidas": [{"n": "Riser", "slug": "riser-slug", "su": 1.5}],
        "posiblesCambiosAlAlza": [{"n": "Maybe Up", "slug": "up-slug", "su": 0.5}],
        "posiblesCambiosALaBaja": [{"n": "Maybe Down", "slug": "down-slug", "su": -0.5}],
        # topBajadas intentionally omitted.
    }
    inner = "1:" + json.dumps(payload)
    array_literal = json.dumps([1, inner])
    html = f"<html><body><script>self.__next_f.push({array_literal})</script></body></html>"

    records, skipped, found_sources = parse_market_predictions(html)

    assert found_sources == {
        "market_top_risers",
        "market_possible_risers",
        "market_possible_fallers",
    }
    assert "market_top_fallers" not in found_sources
    assert skipped == 0
    assert len(records) == 3
