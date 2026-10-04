"""Storage side of per-player pages: candidate selection, upsert of a
fetched page, the fetch log, and the coverage read-model.

Kept beside `storage/our_models.py`'s helpers (`calendar_final_weeks`,
`team_played_weeks`, `load_gameweek_rows`) rather than re-deriving the week
rules — this module reuses them.
"""

import json
from collections import defaultdict
from datetime import date, datetime

from sqlmodel import Session, func, select

from core import analytics as an
from core.player_pages import Candidate, appearance
from scraper.sources.af_player_page import PlayerPage
from storage.db import as_utc
from storage.models import (
    Player,
    PlayerMarketDaily,
    PlayerMatchStats,
    PlayerPageFetch,
    PlayerSnapshot,
    SquadMember,
)
from storage.our_models import calendar_final_weeks, load_gameweek_rows, team_played_weeks
from storage.repository import get_watchlist_player_ids


def _default_player_ids(session: Session) -> list[int]:
    """Every player in the latest market snapshot."""
    latest = session.exec(select(func.max(PlayerSnapshot.as_of))).one()
    if latest is None:
        return []
    return list(
        session.exec(
            select(PlayerSnapshot.player_id).where(PlayerSnapshot.as_of == latest)
        ).all()
    )


def finished_weeks(
    session: Session, season: int, now: datetime, gw_rows: list[an.GameweekRow] | None = None
) -> set[int]:
    """This season's finished jornadas — every week with jornada rows except
    the one still in progress (see `core.analytics.build_timeline`)."""
    rows = gw_rows if gw_rows is not None else load_gameweek_rows(session)
    timeline = an.build_timeline(rows, calendar_final_weeks(session, season, now))
    return {w for s, w in timeline if s == season}


def max_finished_week(session: Session, season: int, now: datetime) -> int | None:
    """The newest finished jornada this season, or `None` before the first.
    Stored on an ok fetch as `PlayerPageFetch.weeks_checked_through`."""
    return max(finished_weeks(session, season, now), default=None)


def build_candidates(
    session: Session, season: int, now: datetime, player_ids: list[int] | None
) -> list[Candidate]:
    """One `Candidate` per requested player (or every player in the latest
    market snapshot when `player_ids` is `None`).

    Three queries cover every candidate's per-player data regardless of how
    many players there are — a grouped max-day query, one query for every
    `(player_id, week)` row this season grouped into a dict in Python, and
    one fetch-log query — rather than two queries plus a `session.get` *per
    player*. The per-player loop before this fix made `/api/health` issue
    roughly 1,700 queries on every poll (~550 players × 3)."""
    ids = player_ids if player_ids is not None else _default_player_ids(session)
    if not ids:
        return []

    team_of = dict(session.exec(select(Player.id, Player.team)).all())
    gw_rows = load_gameweek_rows(session)
    season_weeks = finished_weeks(session, season, now, gw_rows)
    played = team_played_weeks(gw_rows, team_of)

    last_day_by_player = dict(
        session.exec(
            select(PlayerMarketDaily.player_id, func.max(PlayerMarketDaily.day))
            .where(PlayerMarketDaily.season_year == season)
            .group_by(PlayerMarketDaily.player_id)
        ).all()
    )

    have_weeks_by_player: dict[int, set[int]] = defaultdict(set)
    for pid, week in session.exec(
        select(PlayerMatchStats.player_id, PlayerMatchStats.week).where(
            PlayerMatchStats.season_year == season
        )
    ).all():
        have_weeks_by_player[pid].add(week)

    fetch_rows = session.exec(
        select(PlayerPageFetch).where(PlayerPageFetch.player_id.in_(ids))
    ).all()
    fetched_at_by_player = {f.player_id: as_utc(f.fetched_at) for f in fetch_rows}
    checked_through = {f.player_id: f.weeks_checked_through or 0 for f in fetch_rows}

    candidates = []
    for pid in ids:
        last_day = last_day_by_player.get(pid)
        club_weeks = {w for s, w in played.get(team_of.get(pid), set()) if s == season}
        have_weeks = have_weeks_by_player.get(pid, set())
        # An ok fetch is authoritative for every week final when it ran.
        floor = checked_through.get(pid, 0)
        missing_weeks = frozenset(
            w for w in (season_weeks & club_weeks) - have_weeks if w > floor
        )
        last_fetched_at = fetched_at_by_player.get(pid)
        candidates.append(Candidate(pid, last_day, missing_weeks, last_fetched_at))
    return candidates


def upsert_player_page(
    session: Session, season: int, player_id: int, page: PlayerPage, run_id: int
) -> tuple[int, int]:
    """Insert-or-update every day and match row the page carries — never
    delete, so a page that no longer lists an old day leaves that day's row
    untouched."""
    days_written = 0
    for dv in page.market:
        row = session.get(PlayerMarketDaily, (season, dv.day, player_id))
        if row is None:
            row = PlayerMarketDaily(
                season_year=season, day=dv.day, player_id=player_id,
                market_value=dv.market_value, delta=dv.delta, scrape_run_id=run_id,
            )
        else:
            row.market_value = dv.market_value
            row.delta = dv.delta
            row.scrape_run_id = run_id
        session.add(row)
        days_written += 1

    matches_written = 0
    for m in page.matches:
        row = session.get(PlayerMatchStats, (season, m.week, player_id))
        components = json.dumps(m.components)
        kind = appearance(m.minutes)
        if row is None:
            row = PlayerMatchStats(
                season_year=season, week=m.week, player_id=player_id,
                minutes=m.minutes, points=m.points, appearance=kind,
                components=components, scrape_run_id=run_id,
            )
        else:
            row.minutes = m.minutes
            row.points = m.points
            row.appearance = kind
            row.components = components
            row.scrape_run_id = run_id
        session.add(row)
        matches_written += 1

    session.commit()
    return days_written, matches_written


def record_fetch(
    session: Session,
    player_id: int,
    now: datetime,
    status: str,
    error: str | None = None,
    weeks_checked_through: int | None = None,
) -> None:
    """Overwrite the one row this player gets — the fetch log is "last
    attempt per player", not a history. `weeks_checked_through` is stored
    only on an ok fetch; a gap fetch keeps the previous value."""
    row = session.get(PlayerPageFetch, player_id)
    if row is None:
        row = PlayerPageFetch(player_id=player_id, fetched_at=now, status=status, error=error)
    else:
        row.fetched_at = now
        row.status = status
        row.error = error
    if status == "ok":
        row.weeks_checked_through = weeks_checked_through
    session.add(row)
    session.commit()


def coverage(session: Session, season: int, expected: date, now: datetime) -> dict:
    """A snapshot of player-page freshness across every tracked player: a
    player counts as complete only when his daily values reach `expected`
    *and* he has no missing finished-week match row — built on the same
    `Candidate`s `build_candidates` selection reads from, so the two never
    disagree about what a gap is. The weekly re-sweep interval plays no
    part here — a page that is otherwise complete is not a gap just
    because it is due for its periodic re-check.

    `withMatchGaps` counts only players never fetched or still missing a
    finished week's match row — unlike `withGaps`, not the ordinary
    one-day lag of market values before the next daily fetch."""
    candidates = build_candidates(session, season, now, None)
    with_gaps = sum(
        1 for c in candidates if c.last_day is None or c.last_day < expected or c.missing_weeks
    )
    with_match_gaps = sum(
        1 for c in candidates if c.last_fetched_at is None or c.missing_weeks
    )
    known_days = [c.last_day for c in candidates if c.last_day is not None]
    return {
        "players": len(candidates),
        "complete": len(candidates) - with_gaps,
        "withGaps": with_gaps,
        "withMatchGaps": with_match_gaps,
        "oldestLastDay": min(known_days) if known_days else None,
    }


def my_player_ids(session: Session) -> list[int]:
    """The current squad (`sold_at IS NULL`) union the watchlist, squad
    first, de-duplicated, order preserved."""
    squad_ids = session.exec(
        select(SquadMember.player_id).where(SquadMember.sold_at.is_(None))
    ).all()
    watch_ids = get_watchlist_player_ids(session)
    seen: dict[int, None] = {}
    for pid in (*squad_ids, *watch_ids):
        seen.setdefault(pid, None)
    return list(seen)
