from datetime import UTC, date, datetime

from core.seasons import season_of


def test_season_starts_in_july():
    assert season_of(date(2026, 8, 14)) == 2026
    assert season_of(datetime(2027, 5, 30, 18, tzinfo=UTC)) == 2026
    assert season_of(date(2027, 7, 1)) == 2027
