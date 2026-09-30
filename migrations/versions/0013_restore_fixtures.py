"""restore the fixture table (INGEST-04)

Revision ID: 0013
Revises: 0010
Create Date: 2026-09-27

Re-creates the `fixture` table that 0007 dropped with the lineup cut, for
TRANSFER-03's fixture difficulty and Phase 10's expected-points model.
Same shape as 0004's, plus `is_final` and the source's own team ids.

Chained after 0010 (watchlist) when the parallel branches were merged.
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fixture',
        sa.Column('fixture_id', sa.Integer(), nullable=False),
        sa.Column('matchday', sa.Integer(), nullable=False),
        sa.Column('kickoff_utc', sa.DateTime(), nullable=False),
        sa.Column('kickoff_confirmed', sa.Boolean(), nullable=False),
        sa.Column('is_final', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('home_team', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('away_team', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('home_team_id', sa.Integer(), nullable=True),
        sa.Column('away_team_id', sa.Integer(), nullable=True),
        sa.Column('home_difficulty', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('away_difficulty', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('scraped_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('fixture_id'),
    )
    op.create_index(op.f('ix_fixture_matchday'), 'fixture', ['matchday'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_fixture_matchday'), table_name='fixture')
    op.drop_table('fixture')
