"""The league's premium toggles. One row, created by migration 0005 and
seeded from the config defaults, and from then on the only thing read at
runtime — `core/config.py` supplies the seed and nothing more.
"""

from sqlmodel import select

from storage.models import LeagueSettings
from storage.repository import get_league_settings, set_league_settings


def test_the_migration_seeds_exactly_one_row_with_premium_off(session):
    """Seeding from the config defaults means upgrading changes no
    behaviour — a league that was standard yesterday is standard today."""
    rows = session.exec(select(LeagueSettings)).all()
    assert len(rows) == 1
    assert rows[0].id == 1
    assert rows[0].premium_formations_enabled is False
    assert rows[0].premium_bench_enabled is False


def test_reading_the_settings_returns_that_row(session):
    settings = get_league_settings(session)
    assert settings.id == 1


def test_writing_updates_the_same_row_rather_than_adding_another(session):
    set_league_settings(
        session,
        premium_formations_enabled=False,
        premium_bench_enabled=True,
    )
    assert len(session.exec(select(LeagueSettings)).all()) == 1
    reread = get_league_settings(session)
    assert reread.premium_bench_enabled is True
    assert reread.premium_formations_enabled is False


def test_each_flag_moves_independently(session):
    """Two independent settings, not one master switch — a league admin can
    have the bench without the premium formations."""
    set_league_settings(
        session,
        premium_formations_enabled=False,
        premium_bench_enabled=True,
    )
    settings = get_league_settings(session)
    assert settings.premium_bench_enabled is True
    assert settings.premium_formations_enabled is False
