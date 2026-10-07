"""Freshness is measured against the market's own update cycle, not against
elapsed hours.

The 30-hour threshold this replaces was calibrated for a daily 09:00 scrape:
it detected *"did the schedule miss a day?"*. With the schedule removed
(Phase 13) there is no cadence to miss, and elapsed hours answers the wrong
question — a scrape at 18:00 read at 10:00 the next morning is 16 hours old,
comfortably inside any sane threshold, and a full market cycle out of date.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from core.freshness import is_stale, last_market_update

MADRID = ZoneInfo("Europe/Madrid")


def madrid(year, month, day, hour, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=MADRID)


class TestLastMarketUpdate:
    def test_after_the_update_returns_today(self):
        now = madrid(2026, 8, 22, 10, 0)
        assert last_market_update(now) == madrid(2026, 8, 22, 0, 15)

    def test_before_the_update_returns_yesterday(self):
        """00:10 Madrid is *before* the day's update — the newest prices are
        still the previous day's."""
        now = madrid(2026, 8, 22, 0, 10)
        assert last_market_update(now) == madrid(2026, 8, 21, 0, 15)

    def test_exactly_at_the_update_returns_today(self):
        now = madrid(2026, 8, 22, 0, 15)
        assert last_market_update(now) == madrid(2026, 8, 22, 0, 15)

    def test_summer_update_is_2215_utc_the_previous_day(self):
        """CEST is UTC+2, so 00:15 Madrid is 22:15 UTC on the day before —
        the reason this cannot be a hardcoded UTC hour."""
        result = last_market_update(madrid(2026, 8, 22, 10, 0)).astimezone(UTC)
        assert result == datetime(2026, 8, 21, 22, 15, tzinfo=UTC)

    def test_winter_update_is_2315_utc_the_previous_day(self):
        """CET is UTC+1. Same wall-clock instant, a different UTC one."""
        result = last_market_update(madrid(2026, 1, 15, 10, 0)).astimezone(UTC)
        assert result == datetime(2026, 1, 14, 23, 15, tzinfo=UTC)

    def test_accepts_a_utc_now_and_converts(self):
        """Callers pass `datetime.now(UTC)`; the conversion happens here so no
        caller has to know the market's timezone."""
        now = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)  # 10:00 Madrid
        assert last_market_update(now) == madrid(2026, 8, 22, 0, 15)


class TestIsStale:
    def test_no_successful_scrape_is_stale(self):
        assert is_stale(None, now=madrid(2026, 8, 22, 10, 0)) is True

    def test_scrape_started_after_the_update_is_fresh(self):
        assert (
            is_stale(madrid(2026, 8, 22, 9, 0), now=madrid(2026, 8, 22, 10, 0)) is False
        )

    def test_scrape_started_before_the_update_is_stale(self):
        """The case the hour-based threshold got wrong: sixteen hours old, and
        a whole market cycle behind."""
        assert is_stale(madrid(2026, 8, 21, 18, 0), now=madrid(2026, 8, 22, 10, 0)) is True

    def test_scrape_started_exactly_at_the_update_is_fresh(self):
        assert (
            is_stale(madrid(2026, 8, 22, 0, 15), now=madrid(2026, 8, 22, 10, 0)) is False
        )

    def test_a_scrape_straddling_the_update_is_stale(self):
        """Started 00:10, so it fetched pre-update prices however long it ran.
        Conservative on purpose: a spurious prompt costs a click, a missed one
        costs a transfer decision made on yesterday's prices."""
        assert is_stale(madrid(2026, 8, 22, 0, 10), now=madrid(2026, 8, 22, 0, 30)) is True

    def test_a_scrape_minutes_old_but_before_todays_update_is_stale(self):
        """Elapsed time is irrelevant — five minutes old and already behind."""
        assert is_stale(madrid(2026, 8, 22, 0, 10), now=madrid(2026, 8, 22, 0, 16)) is True

    def test_naive_datetimes_are_treated_as_utc(self):
        """SQLite drops tzinfo, so what comes back out of the database is naive
        (`PROJECT-BRIEF.md`, Known gotchas). Reading one as local time would be
        two hours wrong in summer."""
        naive = datetime(2026, 8, 21, 16, 0)  # 18:00 Madrid
        assert is_stale(naive, now=madrid(2026, 8, 22, 10, 0)) is True


def test_madrid_date_leads_utc_after_midnight():
    from datetime import date

    from core.freshness import madrid_date

    assert madrid_date(datetime(2026, 9, 20, 22, 30, tzinfo=UTC)) == date(2026, 9, 21)  # CEST
    assert madrid_date(datetime(2026, 12, 20, 22, 30, tzinfo=UTC)) == date(2026, 12, 20)  # CET
    assert madrid_date(datetime(2026, 12, 20, 23, 30)) == date(2026, 12, 21)  # naive = UTC
