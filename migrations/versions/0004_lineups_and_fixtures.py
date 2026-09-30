"""fixtures and lineups

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    All three tables land in one revision, including the two premium flag
    columns whose features arrive in Slice 2 — one migration over empty
    tables beats a second migration over a season of live lineups.
    """
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


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('lineupplayer')
    op.drop_table('lineup')
    op.drop_index(op.f('ix_fixture_matchday'), table_name='fixture')
    op.drop_table('fixture')
