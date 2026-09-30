"""SQUAD-04 read models: squad value reconstructed from actual holding
windows, and squad points summed across the current squad.

Schema comes from Alembic (see tests/conftest.py) — these tests fail loudly
if the migration and the models drift apart.
"""

from datetime import UTC, date, datetime

import pytest

from storage.models import Player, PlayerGameweekPoints, PlayerSnapshot, ScrapeRun, SquadMember
from storage.repository import get_squad_points_history, get_squad_value_history


@pytest.fixture()
def a_player(session):
    make_player(session, 1, "Galactico", "DEL")
    return session.get(Player, 1)


def make_player(session, player_id: int, name: str, position: str) -> None:
    now = datetime.now(UTC)
    session.add(
        Player(
            id=player_id,
            external_id=f"ext-{player_id}",
            name=name,
            team="Team",
            position=position,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def make_snapshot(session, player_id: int, as_of: date, market_value: int) -> None:
    run = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(run)
    session.commit()
    session.add(
        PlayerSnapshot(
            as_of=as_of,
            player_id=player_id,
            market_value=market_value,
            points=0,
            availability_status="available",
            raw_fields="{}",
            scrape_run_id=run.id,
        )
    )
    session.commit()


def make_gameweek_points(
    session, player_id: int, season_year: int, week: int, points: int, is_provisional: bool = False
) -> None:
    run = ScrapeRun(started_at=datetime.now(UTC), status="success")
    session.add(run)
    session.commit()
    session.add(
        PlayerGameweekPoints(
            season_year=season_year,
            week=week,
            player_id=player_id,
            points=points,
            is_provisional=is_provisional,
            scrape_run_id=run.id,
        )
    )
    session.commit()


# --- get_squad_value_history ---


def test_no_squad_members_returns_empty_value_history(session):
    assert get_squad_value_history(session) == []


def test_value_history_sums_market_value_across_held_members_per_date(session):
    make_player(session, 1, "One", "DEF")
    make_player(session, 2, "Two", "MED")
    session.add(SquadMember(player_id=1, purchase_price=1_000_000, acquired_on=date(2026, 8, 6)))
    session.add(SquadMember(player_id=2, purchase_price=2_000_000, acquired_on=date(2026, 8, 6)))
    session.commit()
    make_snapshot(session, 1, date(2026, 8, 6), 1_100_000)
    make_snapshot(session, 2, date(2026, 8, 6), 2_200_000)
    make_snapshot(session, 1, date(2026, 8, 7), 1_150_000)
    make_snapshot(session, 2, date(2026, 8, 7), 2_150_000)

    history = get_squad_value_history(session)

    assert history == [
        (date(2026, 8, 6), 1_100_000 + 2_200_000),
        (date(2026, 8, 7), 1_150_000 + 2_150_000),
    ]


def test_value_history_falls_back_to_purchase_price_when_snapshot_missing(session):
    make_player(session, 1, "One", "DEF")
    session.add(SquadMember(player_id=1, purchase_price=1_000_000, acquired_on=date(2026, 8, 6)))
    session.commit()
    # A snapshot exists for the date, but not for this player (a rejected
    # scrape for one player must not zero out the whole squad's value).
    make_player(session, 2, "Other", "MED")
    make_snapshot(session, 2, date(2026, 8, 6), 5_000_000)

    history = get_squad_value_history(session)

    assert history == [(date(2026, 8, 6), 1_000_000)]


def test_value_history_excludes_dates_before_a_member_was_acquired(session):
    make_player(session, 1, "One", "DEF")
    session.add(SquadMember(player_id=1, purchase_price=1_000_000, acquired_on=date(2026, 8, 7)))
    session.commit()
    make_snapshot(session, 1, date(2026, 8, 6), 900_000)
    make_snapshot(session, 1, date(2026, 8, 7), 1_000_000)

    history = get_squad_value_history(session)

    assert history == [(date(2026, 8, 7), 1_000_000)]


def test_sold_member_drops_out_of_value_history_after_the_sale_date(session):
    make_player(session, 1, "One", "DEF")
    member = SquadMember(player_id=1, purchase_price=1_000_000, acquired_on=date(2026, 8, 6))
    session.add(member)
    session.commit()
    make_snapshot(session, 1, date(2026, 8, 6), 1_000_000)
    make_snapshot(session, 1, date(2026, 8, 7), 1_100_000)

    member.sold_at = datetime(2026, 8, 7, tzinfo=UTC)
    member.sale_price = 1_100_000
    session.add(member)
    session.commit()

    history = get_squad_value_history(session)

    assert history == [(date(2026, 8, 6), 1_000_000)]


# --- get_squad_points_history ---


def test_no_current_squad_returns_empty_points_history(session):
    assert get_squad_points_history(session) == []


def test_points_history_sums_points_across_current_squad_members_per_week(session, a_player):
    make_player(session, 2, "Two", "MED")
    session.add(SquadMember(player_id=1, purchase_price=1_000_000, acquired_on=date(2026, 8, 6)))
    session.add(SquadMember(player_id=2, purchase_price=2_000_000, acquired_on=date(2026, 8, 6)))
    session.commit()
    make_gameweek_points(session, 1, 2026, 1, 5)
    make_gameweek_points(session, 2, 2026, 1, 7)

    history = get_squad_points_history(session)

    assert len(history) == 1
    assert history[0].season_year == 2026
    assert history[0].week == 1
    assert history[0].points == 12
    assert history[0].is_provisional is False


def test_points_history_marks_a_week_provisional_if_any_member_is_provisional(session, a_player):
    make_player(session, 2, "Two", "MED")
    session.add(SquadMember(player_id=1, purchase_price=1_000_000, acquired_on=date(2026, 8, 6)))
    session.add(SquadMember(player_id=2, purchase_price=2_000_000, acquired_on=date(2026, 8, 6)))
    session.commit()
    make_gameweek_points(session, 1, 2026, 2, 5, is_provisional=True)
    make_gameweek_points(session, 2, 2026, 2, 7, is_provisional=False)

    history = get_squad_points_history(session)

    assert history[0].is_provisional is True


def test_sold_member_is_excluded_from_points_history(session, a_player):
    member = SquadMember(player_id=1, purchase_price=1_000_000, acquired_on=date(2026, 8, 6))
    session.add(member)
    session.commit()
    make_gameweek_points(session, 1, 2026, 1, 9)

    member.sold_at = datetime(2026, 8, 8, tzinfo=UTC)
    session.add(member)
    session.commit()

    assert get_squad_points_history(session) == []
