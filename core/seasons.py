"""LaLiga seasons run August–May. A season is named by the year it starts,
the convention every table here already uses (`season_year`)."""

from datetime import date, datetime

#: First month of a new season. July, not August: pre-season fixtures and
#: the calendar's first publication land in July.
SEASON_START_MONTH = 7


def season_of(moment: date | datetime) -> int:
    return moment.year if moment.month >= SEASON_START_MONTH else moment.year - 1
