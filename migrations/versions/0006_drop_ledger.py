"""drop the ledger

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the budget ledger.

    The balance this table existed to derive was wrong by construction: the
    game pays €100,000 a day if the manager claims it and forfeits it
    otherwise, which is unobservable in principle, so a one-directional
    drift was the expected state of a correctly-functioning ledger.
    Reconciliation already required reading the true figure off the official
    app — the feature approximated an input the owner already had.

    Dropped rather than left orphaned: a dead table carrying an append-only
    doctrine that nothing enforces any more is exactly what this cut exists
    to remove. The rows are preserved in a dated backup taken before this
    ran, per the data/fantasy.db.backup-pre-NNNN-<timestamp> convention.
    """
    op.drop_table('ledgerentry')


def downgrade() -> None:
    """Recreate the table's shape. It cannot recreate the rows — those live
    only in the pre-0006 backup."""
    op.create_table(
        'ledgerentry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entry_type', sa.String(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('occurred_on', sa.Date(), nullable=False),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reverses_entry_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['reverses_entry_id'],
            ['ledgerentry.id'],
            name='fk_ledgerentry_reverses_entry_id',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
