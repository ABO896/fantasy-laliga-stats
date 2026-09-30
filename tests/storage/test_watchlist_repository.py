"""Watchlist persistence (DETAIL-04). Schema comes from Alembic (see
tests/conftest.py), so these also fail if migration 0010 and the model drift."""

from datetime import UTC, datetime

from sqlalchemy import inspect

from storage.models import Player
from storage.repository import (
    add_to_watchlist,
    get_watchlist_player_ids,
    remove_from_watchlist,
)


def make_player(session, player_id: int) -> None:
    now = datetime.now(UTC)
    session.add(
        Player(
            id=player_id,
            external_id=f"ext-{player_id}",
            name=f"Player {player_id}",
            team="Team",
            position="DEL",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_migration_creates_the_watchlist_table(engine):
    columns = {c["name"] for c in inspect(engine).get_columns("watchlistentry")}
    assert columns == {"player_id", "added_at"}


def test_an_empty_watchlist_is_an_empty_list(session):
    assert get_watchlist_player_ids(session) == []


def test_added_players_come_back_oldest_first(session):
    for pid in (3, 1, 2):
        make_player(session, pid)
    add_to_watchlist(session, 3)
    add_to_watchlist(session, 1)
    add_to_watchlist(session, 2)
    assert get_watchlist_player_ids(session) == [3, 1, 2]


def test_adding_twice_is_a_no_op(session):
    make_player(session, 1)
    add_to_watchlist(session, 1)
    add_to_watchlist(session, 1)
    assert get_watchlist_player_ids(session) == [1]


def test_removing_reports_whether_anything_was_removed(session):
    make_player(session, 1)
    add_to_watchlist(session, 1)
    assert remove_from_watchlist(session, 1) is True
    assert remove_from_watchlist(session, 1) is False
    assert get_watchlist_player_ids(session) == []
