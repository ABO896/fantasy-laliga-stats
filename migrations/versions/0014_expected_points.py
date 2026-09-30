"""expected points: our per-player, per-jornada predictions (MODEL-02)

Revision ID: 0014
Revises: 0012
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """One table: every expected-points prediction this app stores, scored
    later against `playergameweekpoints` at read time (no outcome columns —
    the actual points already live in their own table)."""
    op.create_table(
        'expectedpointsprediction',
        sa.Column('season_year', sa.Integer(), nullable=False),
        sa.Column('jornada', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('model_version', sa.String(), nullable=False),
        sa.Column('predicted', sa.Float(), nullable=False),
        sa.Column('basis', sa.String(), nullable=False),
        sa.Column('inputs', sa.String(), nullable=False),
        sa.Column('fixture_id', sa.Integer(), nullable=True),
        sa.Column('opponent', sa.String(), nullable=True),
        sa.Column('is_home', sa.Boolean(), nullable=True),
        sa.Column('locks_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.PrimaryKeyConstraint('season_year', 'jornada', 'player_id', 'model_version'),
    )


def downgrade() -> None:
    op.drop_table('expectedpointsprediction')
