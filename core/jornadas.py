"""When a jornada's results became knowable — for point-in-time work (the
verdict harness, market-v2 features), where the calendar table only holds a
rolling window and cannot say when week 3 ended.

A team's k-th match is jornada k except around a postponement, so each
jornada's end is read from the majority: the k-th match dates of every team,
kept only within `MAX_SPREAD_DAYS` of their median (a postponed match far
from it is dropped), and the latest kept date is the end."""

import statistics
from collections.abc import Mapping, Sequence
from datetime import date

MAX_SPREAD_DAYS = 4


def week_end_dates(team_dates: Mapping[str, Sequence[date]]) -> dict[int, date]:
    by_k: dict[int, list[date]] = {}
    for dates in team_dates.values():
        for k, day in enumerate(sorted(dates), start=1):
            by_k.setdefault(k, []).append(day)
    out: dict[int, date] = {}
    for k, days in by_k.items():
        median = date.fromordinal(round(statistics.median(d.toordinal() for d in days)))
        kept = [d for d in days if abs((d - median).days) <= MAX_SPREAD_DAYS]
        out[k] = max(kept)
    return out


def known_weeks(week_ends: Mapping[int, date], as_of: date) -> set[int]:
    return {w for w, end in week_ends.items() if end < as_of}
