"""external football data

Revision ID: 0011
Revises: 0013
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add `externalmatch`: LaLiga fixtures from an external source, with
    result, team match statistics and raw betting odds (INGEST-09/10).
    Keyed by (source, season, home, away) — see the model's docstring."""
    op.create_table(
        'externalmatch',
        sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('season_year', sa.Integer(), nullable=False),
        sa.Column('home_team', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('away_team', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('match_date', sa.Date(), nullable=False),
        sa.Column('kickoff_at', sa.DateTime(), nullable=True),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('source_home_team', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('source_away_team', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('home_goals', sa.Integer(), nullable=True),
        sa.Column('away_goals', sa.Integer(), nullable=True),
        sa.Column('home_xg', sa.Float(), nullable=True),
        sa.Column('away_xg', sa.Float(), nullable=True),
        sa.Column('home_shots', sa.Integer(), nullable=True),
        sa.Column('away_shots', sa.Integer(), nullable=True),
        sa.Column('home_shots_on_target', sa.Integer(), nullable=True),
        sa.Column('away_shots_on_target', sa.Integer(), nullable=True),
        sa.Column('odds_home', sa.Float(), nullable=True),
        sa.Column('odds_draw', sa.Float(), nullable=True),
        sa.Column('odds_away', sa.Float(), nullable=True),
        sa.Column('odds_over25', sa.Float(), nullable=True),
        sa.Column('odds_under25', sa.Float(), nullable=True),
        sa.Column('closing_odds_home', sa.Float(), nullable=True),
        sa.Column('closing_odds_draw', sa.Float(), nullable=True),
        sa.Column('closing_odds_away', sa.Float(), nullable=True),
        sa.Column('closing_odds_over25', sa.Float(), nullable=True),
        sa.Column('closing_odds_under25', sa.Float(), nullable=True),
        sa.Column('raw_fields', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('scrape_run_id', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['scrape_run_id'], ['scraperun.id'], ),
        sa.PrimaryKeyConstraint('source', 'season_year', 'home_team', 'away_team'),
    )
    op.create_index(
        op.f('ix_externalmatch_match_date'), 'externalmatch', ['match_date'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_externalmatch_match_date'), table_name='externalmatch')
    op.drop_table('externalmatch')
