"""Is the data we hold older than the market that produced it?

Pure — no session, no HTTP type, no SQLModel import — so the one rule that
decides whether the owner is shown yesterday's prices is cheap to test at
every boundary that matters.

**Why this is not a number of hours.** The operator updates the market once
a day at 00:15 Europe/Madrid, and that update is the only event that makes
held prices wrong. Until Phase 13 the app scraped on a 09:00 schedule, so a
30-hour threshold worked as a *"did the schedule miss a day?"* detector and
the market cycle never had to be modelled. With the schedule gone there is
no cadence to miss, and elapsed hours answers a question nobody is asking: a
scrape at 18:00, read at 10:00 the next morning, is sixteen hours old — well
inside any sane threshold — and a full market cycle out of date.

**Why `started_at` rather than `finished_at`.** A run reads the source
shortly after it starts, so a run that began before the update fetched
pre-update prices however long it took to finish. Judging by start is
conservative in the safe direction: a spurious prompt costs a click, a
missed one costs a transfer decision made on yesterday's numbers.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

#: Where the market lives. The update is a wall-clock event in Madrid, so it
#: lands on a different UTC instant either side of a DST change — 22:15 UTC
#: in summer, 23:15 UTC in winter. Hardcoding a UTC hour would be right for
#: half the year.
MARKET_TIMEZONE = ZoneInfo("Europe/Madrid")

#: 00:15 Madrid, per the operator. Spain's DST transitions happen at
#: 02:00/03:00, so this time never falls in a skipped or repeated hour and
#: needs no `fold` handling.
MARKET_UPDATE_HOUR = 0
MARKET_UPDATE_MINUTE = 15


def _as_aware(moment: datetime) -> datetime:
    """SQLite drops `tzinfo`, so datetimes read back from the database are
    naive (`PROJECT-BRIEF.md`, Known gotchas). Everything written is UTC, so
    that is what a naive value means here — reading one as local time would
    be two hours wrong in summer, in the direction that hides staleness."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def madrid_date(now: datetime) -> date:
    """The market's calendar date at `now` — what a refresh stamps its rows
    with. A naive `now` is read as UTC (see `_as_aware`)."""
    return _as_aware(now).astimezone(MARKET_TIMEZONE).date()


def last_market_update(now: datetime) -> datetime:
    """The most recent market update at or before `now`.

    Returned in Madrid time; compare it against anything aware and the
    comparison resolves correctly regardless of either side's zone.
    """
    local = _as_aware(now).astimezone(MARKET_TIMEZONE)
    candidate = local.replace(
        hour=MARKET_UPDATE_HOUR, minute=MARKET_UPDATE_MINUTE, second=0, microsecond=0
    )
    # Before today's update, the newest prices are still yesterday's. Day
    # arithmetic on the wall clock is what we want: the update is 00:15 local
    # on each calendar day, whatever UTC offset that day happens to carry.
    if candidate > local:
        candidate -= timedelta(days=1)
    return candidate


def is_stale(last_success_started_at: datetime | None, now: datetime) -> bool:
    """True when no successful scrape has *begun* since the last market
    update — i.e. everything held predates prices that already exist.

    `None` (nothing ever scraped successfully) is stale: the app has no
    prices at all, which is the strongest case for prompting.
    """
    if last_success_started_at is None:
        return True
    return _as_aware(last_success_started_at) < last_market_update(now)
