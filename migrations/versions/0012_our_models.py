"""our own models: market predictions and their outcomes

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """One table: every market prediction this app makes (MODEL-01), with
    the outcome it is later scored against (MODEL-03). Analytics
    (ANALYTICS-01…07) are computed at request time and need no table."""
    op.create_table(
        'marketprediction',
        sa.Column('made_on', sa.Date(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('model_version', sa.String(), nullable=False),
        sa.Column('predicted_pct', sa.Float(), nullable=False),
        sa.Column('direction', sa.String(), nullable=False),
        sa.Column('confidence', sa.String(), nullable=False),
        sa.Column('inputs', sa.String(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('retroactive', sa.Boolean(), nullable=False),
        sa.Column('outcome_as_of', sa.Date(), nullable=True),
        sa.Column('outcome_gap_days', sa.Integer(), nullable=True),
        sa.Column('actual_pct', sa.Float(), nullable=True),
        sa.Column('actual_direction', sa.String(), nullable=True),
        sa.Column('scoring', sa.String(), nullable=True),
        sa.Column('hit', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.PrimaryKeyConstraint('made_on', 'player_id', 'model_version'),
    )


def downgrade() -> None:
    op.drop_table('marketprediction')
