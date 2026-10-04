"""fixture season column

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill from `kickoff_utc` using the same July-cutover rule as
    `core.seasons.season_of`, then tighten to NOT NULL."""
    with op.batch_alter_table('fixture') as batch:
        batch.add_column(sa.Column('season_year', sa.Integer(), nullable=True))

    op.execute(
        "UPDATE fixture SET season_year = CAST(strftime('%Y', kickoff_utc) AS INTEGER) - "
        "(CASE WHEN CAST(strftime('%m', kickoff_utc) AS INTEGER) < 7 THEN 1 ELSE 0 END)"
    )

    with op.batch_alter_table('fixture') as batch:
        batch.alter_column('season_year', existing_type=sa.Integer(), nullable=False)
        batch.create_index('ix_fixture_season_year', ['season_year'])


def downgrade() -> None:
    with op.batch_alter_table('fixture') as batch:
        batch.drop_index('ix_fixture_season_year')
        batch.drop_column('season_year')
