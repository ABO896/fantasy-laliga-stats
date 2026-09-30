"""squad and ledger tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
import sqlmodel

revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'squadmember',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('purchase_price', sa.Integer(), nullable=False),
        sa.Column('acquired_on', sa.Date(), nullable=False),
        sa.Column('sale_price', sa.Integer(), nullable=True),
        sa.Column('sold_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['player.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_squadmember_player_id'), 'squadmember', ['player_id'], unique=False)
    op.create_table(
        'ledgerentry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entry_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('occurred_on', sa.Date(), nullable=False),
        sa.Column('note', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('ledgerentry')
    op.drop_index(op.f('ix_squadmember_player_id'), table_name='squadmember')
    op.drop_table('squadmember')
