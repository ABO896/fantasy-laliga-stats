"""Which players' pages a refresh should fetch. Pure: storage builds the
`Candidate`s, the caller supplies the clock.

One page returns a player's whole season, so a fetch fills every gap he has;
selection only decides *who* and *in what order*. Never-fetched first, then
oldest fetch first, so a run cut short by its budget resumes where it
stopped."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

STARTER_MINUTES = 60


def appearance(minutes: int) -> str:
    """Start / sub / did-not-play, inferred from minutes — the page has no
    start flag. An early injury substitution reads as a sub; accepted."""
    if minutes >= STARTER_MINUTES:
        return "start"
    return "sub" if minutes > 0 else "dnp"


@dataclass(frozen=True)
class Candidate:
    player_id: int
    last_day: date | None
    missing_weeks: frozenset[int]
    last_fetched_at: datetime | None


def expected_last_day(now_local: datetime, update_hour: int) -> date:
    """The newest day the source can already publish: today once the daily
    market update has run, else yesterday. `now_local` is Madrid time."""
    today = now_local.date()
    return today if now_local.hour >= update_hour else today - timedelta(days=1)


def needs_fetch(c: Candidate, expected: date, now: datetime, sweep_days: int) -> bool:
    if c.last_fetched_at is None or c.last_day is None:
        return True
    if c.last_day < expected or c.missing_weeks:
        return True
    return now - c.last_fetched_at >= timedelta(days=sweep_days)


def select_players(
    candidates: Iterable[Candidate],
    expected: date,
    now: datetime,
    sweep_days: int,
    budget: int | None,
) -> list[int]:
    due = [c for c in candidates if needs_fetch(c, expected, now, sweep_days)]
    due.sort(key=lambda c: (c.last_fetched_at is not None,
                            c.last_fetched_at or datetime.min, c.player_id))
    ids = [c.player_id for c in due]
    return ids if budget is None else ids[:budget]
