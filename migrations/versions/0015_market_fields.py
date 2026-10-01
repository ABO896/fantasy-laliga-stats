"""market fields: starter flag, market updates to next match, next fixture id

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Three nullable columns; history before this migration has no source
    object in `raw_fields`, so there is nothing to backfill."""
    with op.batch_alter_table('playersnapshot') as batch:
        batch.add_column(sa.Column('is_starter', sa.Boolean(), nullable=True))
        batch.add_column(sa.Column('market_updates_to_next_match', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('next_fixture_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('playersnapshot') as batch:
        batch.drop_column('next_fixture_id')
        batch.drop_column('market_updates_to_next_match')
        batch.drop_column('is_starter')
