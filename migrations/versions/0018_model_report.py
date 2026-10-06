"""model report: stored JSON reports from this app's own validation harnesses

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '0018'
down_revision: Union[str, Sequence[str], None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """One table for named validation-harness reports (JSON payload), kept
    as a single upserted row per `name` — the walk-forward verdict harness's
    `"verdict-validation"` report is the first of these."""
    op.create_table(
        'modelreport',
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('payload', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint('name'),
    )


def downgrade() -> None:
    op.drop_table('modelreport')
