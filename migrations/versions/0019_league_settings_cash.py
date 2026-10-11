"""league settings: the owner's saved budget (cash available)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0019'
down_revision: Union[str, Sequence[str], None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """One nullable column on the single settings row: the cash the owner
    says they have, typed in by hand (the game exposes no balance). Null
    means "not entered", and Transfers then applies no price limit."""
    with op.batch_alter_table('leaguesettings') as batch:
        batch.add_column(sa.Column('cash_available', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('leaguesettings') as batch:
        batch.drop_column('cash_available')
