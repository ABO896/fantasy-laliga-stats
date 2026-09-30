"""watchlist

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """DETAIL-04: the players the owner is keeping an eye on.

    Adds one table and touches nothing else. `player_id` is the primary key
    because membership is a set — a player is watchlisted or not.
    """
    op.create_table(
        'watchlistentry',
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['player.id']),
        sa.PrimaryKeyConstraint('player_id'),
    )


def downgrade() -> None:
    op.drop_table('watchlistentry')
