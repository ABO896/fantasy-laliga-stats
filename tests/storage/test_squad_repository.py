"""Squad persistence. Schema comes from Alembic (see tests/conftest.py) —
these tests fail loudly if the migration and the models drift apart."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import inspect
from sqlmodel import select

from storage.models import Player, PlayerSnapshot, ScrapeRun, SquadMember, SquadSetup
from storage.repository import (
    add_squad_member,
    get_squad_members,
    get_squad_roles,
    get_squad_setup,
    remove_squad_member,
    save_xi,
)


@pytest.fixture()
def a_player(session):
    make_player(session, 1, "Galactico", "DEL")
    return session.get(Player, 1)


def test_squad_member_round_trips(session):
    session.add(SquadMember(player_id=1, purchase_price=5_000_000, acquired_on=date(2026, 8, 6)))
    session.commit()
    stored = session.exec(select(SquadMember)).one()
    assert stored.purchase_price == 5_000_000
    assert stored.sold_at is None
    assert stored.sale_price is None


def test_squad_member_records_a_sale_without_being_deleted(session):
    member = SquadMember(player_id=1, purchase_price=5_000_000, acquired_on=date(2026, 8, 6))
    session.add(member)
    session.commit()

    member.sold_at = datetime(2026, 8, 7, tzinfo=UTC)
    member.sale_price = 6_000_000
    session.add(member)
    session.commit()

    stored = session.exec(select(SquadMember)).one()
    assert stored.sale_price == 6_000_000
    assert stored.sold_at is not None


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


def test_added_member_comes_back_with_identity_and_latest_market_value(session):
    make_player(session, 1, "Keeper", "POR")
    make_snapshot(session, 1, date(2026, 8, 5), 4_000_000)
    make_snapshot(session, 1, date(2026, 8, 6), 5_000_000)

    add_squad_member(session, player_id=1, purchase_price=3_000_000)

    members = get_squad_members(session)
    assert len(members) == 1
    assert members[0].name == "Keeper"
    assert members[0].position == "POR"
    assert members[0].purchase_price == 3_000_000
    assert members[0].market_value == 5_000_000


def test_member_with_no_snapshot_survives_with_a_null_market_value(session):
    """A squad must survive a player having no snapshot on a given day. The
    member must appear, not vanish from an inner join."""
    make_player(session, 1, "Ghost", "DEF")
    add_squad_member(session, player_id=1, purchase_price=2_000_000)

    members = get_squad_members(session)
    assert len(members) == 1
    assert members[0].market_value is None
    assert members[0].effective_value == 2_000_000


def test_removed_member_leaves_the_squad_but_keeps_its_row(session):
    make_player(session, 1, "Sold", "DEL")
    add_squad_member(session, player_id=1, purchase_price=1_000_000)

    assert remove_squad_member(session, player_id=1, sale_price=1_500_000) is True
    assert get_squad_members(session) == []

    stored = session.exec(select(SquadMember)).one()
    assert stored.sale_price == 1_500_000
    assert stored.sold_at is not None


def test_removing_a_player_not_in_the_squad_reports_false(session):
    assert remove_squad_member(session, player_id=42) is False


def test_a_player_can_be_rebought_after_being_sold(session):
    make_player(session, 1, "Boomerang", "MED")
    add_squad_member(session, player_id=1, purchase_price=1_000_000)
    remove_squad_member(session, player_id=1, sale_price=1_200_000)
    add_squad_member(session, player_id=1, purchase_price=1_300_000)

    members = get_squad_members(session)
    assert len(members) == 1
    assert members[0].purchase_price == 1_300_000
    assert len(session.exec(select(SquadMember)).all()) == 2


def test_adding_an_unknown_player_raises(session):
    with pytest.raises(ValueError, match="unknown player"):
        add_squad_member(session, player_id=999, purchase_price=1)


def _table_names(session) -> list[str]:
    return inspect(session.connection()).get_table_names()


def test_the_ledger_table_is_gone(session):
    # Task 3 proved nothing writes to it. This proves it no longer exists:
    # conftest runs `alembic upgrade head`, so a fresh test database now
    # reflects 0006.
    assert "ledgerentry" not in _table_names(session)


def test_adding_a_player_records_the_price_but_no_ledger_entry(session, a_player):
    # purchase_price is a fact about a player and survives the ledger cut.
    # What is gone is aggregating those facts into a running balance.
    add_squad_member(session, player_id=a_player.id, purchase_price=1_500_000)

    member = session.exec(select(SquadMember).where(SquadMember.player_id == a_player.id)).one()
    assert member.purchase_price == 1_500_000


def test_removing_a_player_records_the_sale_price_but_no_ledger_entry(session, a_player):
    add_squad_member(session, player_id=a_player.id, purchase_price=1_500_000)

    assert remove_squad_member(session, player_id=a_player.id, sale_price=2_000_000)

    member = session.exec(select(SquadMember).where(SquadMember.player_id == a_player.id)).one()
    assert member.sale_price == 2_000_000
    assert member.sold_at is not None


def _column_names(session, table: str) -> list[str]:
    return [c["name"] for c in inspect(session.connection()).get_columns(table)]


def test_the_lineup_tables_are_gone(session):
    """`fixture` also went in 0007 but came back in 0013 (INGEST-04, for
    TRANSFER-03); the lineup tables stay cut."""
    names = _table_names(session)
    for table in ("lineup", "lineupplayer"):
        assert table not in names, f"{table} survived migration 0007"
    assert "fixture" in names


def test_league_settings_no_longer_carries_a_captain_column(session):
    assert "premium_captain_enabled" not in _column_names(session, "leaguesettings")


def test_the_squad_setup_row_is_seeded_with_a_standard_formation(session):
    setups = session.exec(select(SquadSetup)).all()
    assert len(setups) == 1
    assert setups[0].id == 1
    # 4-4-2 is standard, not premium: a fresh database must be able to field
    # its seeded shape without the league admin having switched anything on.
    assert setups[0].formation == "4-4-2"


def test_a_new_squad_member_starts_as_a_reserve(session, a_player):
    add_squad_member(session, player_id=a_player.id, purchase_price=1_000_000)
    member = session.exec(select(SquadMember).where(SquadMember.player_id == a_player.id)).one()
    assert member.role == "reserve"


def _squad_of(session) -> dict[int, str]:
    """player_id -> role, straight from the table rather than through the
    function under test."""
    return {
        m.player_id: m.role
        for m in session.exec(select(SquadMember).where(SquadMember.sold_at.is_(None))).all()
    }


@pytest.fixture()
def three_players(session):
    for player_id, position in ((1, "POR"), (2, "DEF"), (3, "DEF")):
        make_player(session, player_id, f"P{player_id}", position)
        add_squad_member(session, player_id=player_id, purchase_price=1_000_000)
    return [1, 2, 3]


def test_saving_an_xi_writes_the_formation_and_every_role(session, three_players):
    save_xi(session, formation="5-3-2", starter_ids=[1, 2], bench_ids=[3])

    assert get_squad_setup(session).formation == "5-3-2"
    assert _squad_of(session) == {1: "starter", 2: "starter", 3: "bench"}


def test_a_player_named_in_neither_list_is_reset_to_reserve(session, three_players):
    save_xi(session, formation="4-4-2", starter_ids=[1, 2, 3], bench_ids=[])
    save_xi(session, formation="4-4-2", starter_ids=[1], bench_ids=[2])

    assert _squad_of(session) == {1: "starter", 2: "bench", 3: "reserve"}


def test_get_squad_roles_reports_only_the_current_squad(session, three_players):
    save_xi(session, formation="4-4-2", starter_ids=[1, 2, 3], bench_ids=[])
    remove_squad_member(session, player_id=3)

    assert get_squad_roles(session) == {1: "starter", 2: "starter"}


def test_removing_a_player_resets_their_role(session, three_players):
    save_xi(session, formation="4-4-2", starter_ids=[1, 2, 3], bench_ids=[])
    remove_squad_member(session, player_id=3)

    sold = session.exec(select(SquadMember).where(SquadMember.player_id == 3)).one()
    assert sold.sold_at is not None
    assert sold.role == "reserve", "a re-added player would return holding a slot"
