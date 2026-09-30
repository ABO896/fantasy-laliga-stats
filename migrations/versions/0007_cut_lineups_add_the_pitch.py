"""cut lineups, add the pitch

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace the per-gameweek lineup record with one current XI.

    Migration 0004 created `lineup`, `lineupplayer` and `fixture` together,
    so this reverses it wholesale. The lineup tables never held a row; the
    50 fixture rows are lost knowingly (see the 2026-08-22 spec, §3).

    `squadmember.role` replaces the two independent id lists the deleted
    code carried, which permitted a player to sit in both at once — the
    engine had a `duplicate_selection` refusal for exactly that. One column
    per player turns a runtime check into a schema guarantee.

    `squadsetup` holds the formation, which cannot be derived from who is
    assigned: three defenders in a 4-4-2 with an empty slot must stay
    distinguishable from a 3-x-x shape. One row, `id=1`, mirroring the
    `leaguesettings` singleton — same pattern, same seeding-by-migration.
    """
    op.add_column(
        'squadmember',
        sa.Column(
            'role',
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default='reserve',
        ),
    )

    squad_setup = op.create_table(
        'squadsetup',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('formation', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # 4-4-2 is standard rather than premium, so a fresh database can field
    # its seeded shape before the owner has told the app anything about
    # their league.
    op.bulk_insert(squad_setup, [{'id': 1, 'formation': '4-4-2'}])

    op.drop_table('lineupplayer')
    op.drop_table('lineup')
    op.drop_index(op.f('ix_fixture_matchday'), table_name='fixture')
    op.drop_table('fixture')

    # SQLite gained native DROP COLUMN in 3.35, but batch mode is Alembic's
    # supported path for it and works on either — the table is rebuilt and
    # its one seeded row copied across.
    with op.batch_alter_table('leaguesettings') as batch_op:
        batch_op.drop_column('premium_captain_enabled')


def downgrade() -> None:
    """Recreate every shape this dropped. It cannot recreate the rows — the
    fixtures live only in the pre-0007 backup."""
    with op.batch_alter_table('leaguesettings') as batch_op:
        batch_op.add_column(
            sa.Column(
                'premium_captain_enabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    op.create_table(
        'fixture',
        sa.Column('fixture_id', sa.Integer(), nullable=False),
        sa.Column('matchday', sa.Integer(), nullable=False),
        sa.Column('kickoff_utc', sa.DateTime(), nullable=False),
        sa.Column('kickoff_confirmed', sa.Boolean(), nullable=False),
        sa.Column('home_team', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('away_team', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('home_difficulty', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('away_difficulty', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('scraped_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('fixture_id'),
    )
    op.create_index(op.f('ix_fixture_matchday'), 'fixture', ['matchday'], unique=False)

    op.create_table(
        'lineup',
        sa.Column('gameweek', sa.Integer(), nullable=False),
        sa.Column('formation', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('captain_player_id', sa.Integer(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('recorded_late', sa.Boolean(), nullable=False),
        sa.Column('premium_formations_enabled', sa.Boolean(), nullable=False),
        sa.Column('premium_captain_enabled', sa.Boolean(), nullable=False),
        sa.Column('premium_bench_enabled', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['captain_player_id'], ['player.id']),
        sa.PrimaryKeyConstraint('gameweek'),
    )

    op.create_table(
        'lineupplayer',
        sa.Column('lineup_gameweek', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(['lineup_gameweek'], ['lineup.gameweek']),
        sa.ForeignKeyConstraint(['player_id'], ['player.id']),
        sa.PrimaryKeyConstraint('lineup_gameweek', 'player_id'),
    )

    op.drop_table('squadsetup')
    with op.batch_alter_table('squadmember') as batch_op:
        batch_op.drop_column('role')
