"""player pages: daily market values, per-match stats, a fetch log, run mode

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Three tables for the player-page scraper: the source's own
    day-by-day market value, per-jornada match stats, and a last-attempt
    fetch log per player. Also tags every scrape run with its `mode`
    (quick | mine | complete), defaulting existing rows to 'quick' — today's
    refresh behaviour.
    """
    op.create_table(
        'playermarketdaily',
        sa.Column('season_year', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('market_value', sa.Integer(), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=True),
        sa.Column('scrape_run_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.ForeignKeyConstraint(['scrape_run_id'], ['scraperun.id'], ),
        sa.PrimaryKeyConstraint('season_year', 'day', 'player_id'),
    )

    op.create_table(
        'playermatchstats',
        sa.Column('season_year', sa.Integer(), nullable=False),
        sa.Column('week', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('appearance', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('components', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('scrape_run_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.ForeignKeyConstraint(['scrape_run_id'], ['scraperun.id'], ),
        sa.PrimaryKeyConstraint('season_year', 'week', 'player_id'),
    )

    op.create_table(
        'playerpagefetch',
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('weeks_checked_through', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.PrimaryKeyConstraint('player_id'),
    )

    with op.batch_alter_table('scraperun') as batch:
        batch.add_column(
            sa.Column(
                'mode', sa.String(), nullable=False, server_default='quick'
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('scraperun') as batch:
        batch.drop_column('mode')

    op.drop_table('playerpagefetch')
    op.drop_table('playermatchstats')
    op.drop_table('playermarketdaily')
