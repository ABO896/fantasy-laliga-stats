"""ledger reversal link

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Batch mode is required: SQLite cannot ALTER TABLE ADD CONSTRAINT, so
    Alembic rebuilds the table to attach the self-referential foreign key.
    """
    with op.batch_alter_table('ledgerentry') as batch_op:
        batch_op.add_column(sa.Column('reverses_entry_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_ledgerentry_reverses_entry_id',
            'ledgerentry',
            ['reverses_entry_id'],
            ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ledgerentry') as batch_op:
        batch_op.drop_constraint('fk_ledgerentry_reverses_entry_id', type_='foreignkey')
        batch_op.drop_column('reverses_entry_id')
