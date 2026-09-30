from pathlib import Path

from core.season_stats_schema import STAT_PAIRS, column_name
from scraper.sources.af_season_stats import fetch_season_stats, parse_season_stats

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "phase7"


def _html() -> str:
    return (FIXTURES / "estadisticas-2025.html").read_text(encoding="utf-8")


def test_reads_the_season_the_page_declares_rather_than_assuming_one():
    # The page serves the latest *published* season, which is last season
    # while the current one is young. Storing it under the configured
    # current season would file last season's numbers as this season's.
    assert parse_season_stats(_html()).season_year == 2025


def test_the_parser_keeps_rows_that_have_no_slug():
    """83 of 702 rows carry no `slug`, no `masterPlayerId` and no `id` —
    and they are the best players in the league. Dropping them at parse
    time would discard Lamine Yamal, Mbappe and Vini Jr. silently. The
    parser emits identity fields and lets Task 7 resolve them."""
    stats = parse_season_stats(_html())
    assert len(stats.records) == 702
    slugless = [r for r in stats.records if not r["slug"]]
    assert len(slugless) == 83
    assert any(r["nickname"] == "Lamine Yamal" for r in slugless)


def test_coaches_are_flagged_rather_than_silently_dropped():
    stats = parse_season_stats(_html())
    coaches = [r for r in stats.records if r["is_coach"]]
    assert len(coaches) == 29


def test_every_declared_stat_is_present_on_every_record():
    stats = parse_season_stats(_html())
    expected = {column_name(c) for pair in STAT_PAIRS for c in pair}
    assert expected <= set(stats.records[0])


def test_a_known_player_carries_its_counter_and_its_points_contribution():
    stats = parse_season_stats(_html())
    yamal = next(r for r in stats.records if r["nickname"] == "Lamine Yamal")
    assert yamal["goals"] == 16
    assert yamal["goals_pts"] == 64
    assert yamal["total_points"] == 330
    assert yamal["matches_played"] == 28
    assert yamal["slug"] is None, "this is exactly the row a slug-only join would lose"


def test_raw_payload_is_retained_verbatim():
    stats = parse_season_stats(_html())
    assert "playerId" in stats.records[0]["raw"]


def test_a_past_season_is_requested_by_path_segment(monkeypatch):
    """The statistics page is season-parameterized. Verified live on
    2026-08-27: `/estadisticas` served season 2026 while
    `/estadisticas/2025` served all 702 of last season's rows. Without the
    segment there is no way to reach a season once the site has moved on,
    and last season is exactly what Phase 10's models train on (D-01)."""
    requested: list[str] = []

    def fake_fetch_page(url, markers, settings=None):
        requested.append(url)
        return "<html></html>"

    monkeypatch.setattr("scraper.sources.af_season_stats.fetch_page", fake_fetch_page)

    fetch_season_stats()
    fetch_season_stats(season_year=2025)

    assert requested[0].endswith("/estadisticas")
    assert requested[1].endswith("/estadisticas/2025")
