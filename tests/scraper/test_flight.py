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


def _push(payload: str) -> str:
    import json

    return f"<script>self.__next_f.push({json.dumps([1, payload])})</script>"


def test_a_chunk_packing_several_rows_yields_each_row():
    """Since 2026-10-11 the site packs several flight rows into one push,
    newline-separated: `94:"…"\\n95:I[…]\\n93:{…}`. Decoding the chunk as one
    JSON document failed, and the market scrape found no roster."""
    from scraper.sources.flight import find_key, iter_flight_chunks

    html = _push('94:"/_next/static/a.js"\n95:I[1,["$2"]]\n93:{"initialPlayers":[{"slug":"x"}]}')
    chunks = list(iter_flight_chunks(html, must_contain="initialPlayers"))
    assert find_key(chunks, "initialPlayers") == [{"slug": "x"}]


def test_a_single_row_chunk_still_decodes():
    from scraper.sources.flight import iter_flight_chunks

    assert list(iter_flight_chunks(_push('1a:{"k":1}'))) == [{"k": 1}]


def test_a_text_row_is_read_by_its_byte_length_not_a_newline():
    """React text rows (`id:T<hex byte length>,<text>`) carry no newline;
    the next row follows straight after. The site packs one (a JSON-LD
    breadcrumb, with multi-byte characters) ahead of the player page's
    marketHistory row since 2026-10-11."""
    from scraper.sources.flight import flight_rows, iter_flight_chunks

    text = '{"name":"Peñarol – ñ"}'
    n = len(text.encode("utf-8"))
    payload = f'1:"a"\n2:T{n:x},{text}3:{{"marketHistory":[{{"marketValue":1}}]}}\n'
    assert flight_rows(payload) == ['"a"', text, '{"marketHistory":[{"marketValue":1}]}']
    chunks = list(iter_flight_chunks(_push(payload), must_contain="marketHistory"))
    assert {"marketHistory": [{"marketValue": 1}]} in chunks
