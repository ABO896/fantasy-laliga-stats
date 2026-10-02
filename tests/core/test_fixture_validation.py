"""`validate_fixtures` — the gate between the calendar parse and the
`fixture` table. Same contract as `validate_scrape`: pure, never raises on
bad data, reports every reason."""

from datetime import UTC, datetime

from core.config import Settings
from core.validation import validate_fixtures
from scraper.sources.analiticafantasy_calendar import FixtureRecord


def _fixture(fixture_id: int, matchday: int = 8, **overrides) -> FixtureRecord:
    defaults = dict(
        fixture_id=fixture_id,
        matchday=matchday,
        season_year=2026,
        kickoff_utc=datetime(2026, 10, 9, 19, 0, tzinfo=UTC),
        kickoff_confirmed=True,
        is_final=False,
        home_team="Barcelona",
        away_team="Athletic Club",
        home_team_id=529,
        away_team_id=531,
        home_difficulty="easy",
        away_difficulty="very_hard",
    )
    defaults.update(overrides)
    return FixtureRecord(**defaults)


def _window() -> list[FixtureRecord]:
    return [_fixture(i, matchday=6 + (i % 5)) for i in range(50)]


def _settings() -> Settings:
    return Settings(min_fixture_count=30)


def test_a_full_window_is_accepted():
    result = validate_fixtures(_window(), _settings())
    assert result.ok
    assert result.row_count == 50


def test_too_few_fixtures_is_rejected():
    result = validate_fixtures([_fixture(i) for i in range(5)], _settings())
    assert not result.ok
    assert any("below minimum" in reason for reason in result.reasons)


def test_a_naive_kickoff_is_rejected():
    """Every reader compares kickoffs against `datetime.now(UTC)`; a naive
    instant would raise there, or compare two hours wrong in summer."""
    records = _window()
    records[0] = _fixture(999, kickoff_utc=datetime(2026, 10, 9, 19, 0))
    result = validate_fixtures(records, _settings())
    assert not result.ok
    assert any("timezone" in reason for reason in result.reasons)


def test_a_jornada_outside_the_season_is_rejected():
    records = _window()
    records[0] = _fixture(999, matchday=41)
    result = validate_fixtures(records, _settings())
    assert not result.ok
    assert any("matchday" in reason for reason in result.reasons)


def test_a_missing_team_name_is_rejected():
    records = _window()
    records[0] = _fixture(999, home_team="")
    result = validate_fixtures(records, _settings())
    assert not result.ok
    assert any("team" in reason for reason in result.reasons)
