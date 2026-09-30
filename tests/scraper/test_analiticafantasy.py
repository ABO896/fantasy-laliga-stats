from pathlib import Path

from scraper.sources.analiticafantasy import parse_page

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "puja-ideal-page1.html"


def _load_fixture_html() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_page_row_count():
    # Regression guard for PITFALLS.md Pitfall 1: a silent reversion to
    # page-one-only rendered-table parsing (10 rows) must fail this
    # assertion, not quietly pass with a fraction of the roster. The real
    # fixture's embedded roster JSON carries 342 real players once club
    # coaches (`positionId` 5) are filtered out.
    records = parse_page(_load_fixture_html())
    assert len(records) > 50
    assert len(records) == 342


def test_coaches_are_excluded_from_parsed_records():
    # `positionId == 5` entries (club coaches) are a real, expected part
    # of the embedded roster JSON but are not fantasy players.
    records = parse_page(_load_fixture_html())
    assert all(r["position"] in {"POR", "DEF", "MED", "DEL"} for r in records)


def test_parse_player_row():
    records = parse_page(_load_fixture_html())
    first = records[0]

    assert isinstance(first["external_id"], str) and first["external_id"]
    assert isinstance(first["name"], str) and first["name"]
    assert isinstance(first["team"], str) and first["team"]
    assert first["position"] in {"POR", "DEF", "MED", "DEL"}
    assert isinstance(first["points"], int)
    assert isinstance(first["ideal_bid"], int)
    assert isinstance(first["max_bid"], int)
    assert isinstance(first["price_change_abs"], int)
    assert isinstance(first["price_change_pct"], float)
    assert isinstance(first["market_value"], int) and first["market_value"] > 0
    assert first["availability_status"] in {"available", "injured", "doubtful", "suspended"}
    assert first["starter_probability"] is None or isinstance(first["starter_probability"], float)


def test_parse_player_row_external_id_is_the_url_slug():
    # external_id continues to be derived from the player's URL slug (see
    # 01-02-SUMMARY.md), now read directly from the embedded JSON's own
    # `slug` key rather than parsed out of an `<a href>`.
    records = parse_page(_load_fixture_html())
    cucurella = next(r for r in records if r["external_id"] == "marc-cucurella-47380")
    assert cucurella["name"] == "Cucurella"
    assert cucurella["team"] == "Real Madrid"
    assert cucurella["position"] == "DEF"


def _restamp_flight_chunk_id(html: str, new_id: str) -> str:
    """Re-stamp the Next.js flight chunk id prefixing the pushed payload
    that carries `initialPlayers`.

    The id is a per-deploy counter rendered in **hexadecimal**, so it is
    all-digits only some of the time. The saved fixture happens to carry
    an all-digit one, which is exactly why the suite could not see this
    failure mode until it was reproduced by hand.
    """
    marker = html.index("initialPlayers")
    push = html.rindex('self.__next_f.push([1,"', 0, marker)
    open_quote = push + len('self.__next_f.push([1,"')
    colon = html.index(":", open_quote)
    return html[:open_quote] + new_id + html[colon:]


def test_parse_page_reads_a_hexadecimal_flight_chunk_id():
    # Next.js numbers its flight chunks in hex and the value changes with
    # every deploy of the target site. A chunk id containing a hex letter
    # (`6a`) must parse exactly like an all-digit one (`67`) — otherwise
    # the daily scrape succeeds or fails on what amounts to a coin flip,
    # which is what it did for ten of its first twenty-four runs.
    #
    # DO NOT "simplify" this by asserting against the raw fixture: the
    # fixture's own id is all-digits, so this test only has teeth while it
    # re-stamps the id first.
    html = _restamp_flight_chunk_id(_load_fixture_html(), "6a")
    assert 'self.__next_f.push([1,"6a:' in html, "the re-stamp did not land"

    records = parse_page(html)

    assert len(records) == 342
