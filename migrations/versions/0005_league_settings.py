"""league settings

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the single-row settings table and seed it.

    The seed is written here rather than lazily on first read so that the
    row's existence is a schema guarantee: every reader can assume it is
    there, and none of them needs a create-if-missing branch that would
    quietly diverge between callers.

    Seeded all-False to match the `core/config.py` defaults, which is the
    conservative direction — wrongly on would call a forward-less squad
    fieldable when the league scores it zero.
    """
    league_settings = op.create_table(
        'leaguesettings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('premium_formations_enabled', sa.Boolean(), nullable=False),
        sa.Column('premium_captain_enabled', sa.Boolean(), nullable=False),
        sa.Column('premium_bench_enabled', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.bulk_insert(
        league_settings,
        [{
            'id': 1,
            'premium_formations_enabled': False,
            'premium_captain_enabled': False,
            'premium_bench_enabled': False,
        }],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('leaguesettings')
