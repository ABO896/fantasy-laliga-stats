"""deep ingestion

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the four tables everything downstream of the deep-ingestion
    parsers writes into: per-jornada points, deep season statistics, the
    source site's own predictions, and a per-dataset run record.

    `datasetrun` replaces `scraperun`'s single status for this phase: a
    refresh now covers five datasets that fail independently, and one
    status per run is how a partial failure becomes invisible — the
    condition that let the 2026-08-10 outage run eleven days.
    """
    op.create_table(
        'playergameweekpoints',
        sa.Column('season_year', sa.Integer(), nullable=False),
        sa.Column('week', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('is_provisional', sa.Boolean(), nullable=False),
        sa.Column('scrape_run_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.ForeignKeyConstraint(['scrape_run_id'], ['scraperun.id'], ),
        sa.PrimaryKeyConstraint('season_year', 'week', 'player_id'),
    )

    op.create_table(
        'playerseasonstats',
        sa.Column('season_year', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('matches_played', sa.Integer(), nullable=False),
        sa.Column('total_points', sa.Integer(), nullable=False),
        sa.Column('average_points', sa.Float(), nullable=False),
        sa.Column('market_value', sa.Integer(), nullable=False),
        sa.Column('ideal_formation_count', sa.Integer(), nullable=True),
        sa.Column('goals', sa.Integer(), nullable=False),
        sa.Column('goals_pts', sa.Integer(), nullable=False),
        sa.Column('goal_assist', sa.Integer(), nullable=False),
        sa.Column('goal_assist_pts', sa.Integer(), nullable=False),
        sa.Column('offtarget_att_assist', sa.Integer(), nullable=False),
        sa.Column('offtarget_att_assist_pts', sa.Integer(), nullable=False),
        sa.Column('total_scoring_att', sa.Integer(), nullable=False),
        sa.Column('total_scoring_att_pts', sa.Integer(), nullable=False),
        sa.Column('pen_area_entries', sa.Integer(), nullable=False),
        sa.Column('pen_area_entries_pts', sa.Integer(), nullable=False),
        sa.Column('penalty_won', sa.Integer(), nullable=False),
        sa.Column('penalty_won_pts', sa.Integer(), nullable=False),
        sa.Column('penalty_save', sa.Integer(), nullable=False),
        sa.Column('penalty_save_pts', sa.Integer(), nullable=False),
        sa.Column('penalty_failed', sa.Integer(), nullable=False),
        sa.Column('penalty_failed_pts', sa.Integer(), nullable=False),
        sa.Column('penalty_conceded', sa.Integer(), nullable=False),
        sa.Column('penalty_conceded_pts', sa.Integer(), nullable=False),
        sa.Column('saves', sa.Integer(), nullable=False),
        sa.Column('saves_pts', sa.Integer(), nullable=False),
        sa.Column('effective_clearance', sa.Integer(), nullable=False),
        sa.Column('effective_clearance_pts', sa.Integer(), nullable=False),
        sa.Column('own_goals', sa.Integer(), nullable=False),
        sa.Column('own_goals_pts', sa.Integer(), nullable=False),
        sa.Column('goals_conceded', sa.Integer(), nullable=False),
        sa.Column('goals_conceded_pts', sa.Integer(), nullable=False),
        sa.Column('won_contest', sa.Integer(), nullable=False),
        sa.Column('won_contest_pts', sa.Integer(), nullable=False),
        sa.Column('ball_recovery', sa.Integer(), nullable=False),
        sa.Column('ball_recovery_pts', sa.Integer(), nullable=False),
        sa.Column('poss_lost_all', sa.Integer(), nullable=False),
        sa.Column('poss_lost_all_pts', sa.Integer(), nullable=False),
        sa.Column('yellow_card', sa.Integer(), nullable=False),
        sa.Column('yellow_card_pts', sa.Integer(), nullable=False),
        sa.Column('second_yellow_card', sa.Integer(), nullable=False),
        sa.Column('second_yellow_card_pts', sa.Integer(), nullable=False),
        sa.Column('red_card', sa.Integer(), nullable=False),
        sa.Column('red_card_pts', sa.Integer(), nullable=False),
        sa.Column('mins_played', sa.Integer(), nullable=False),
        sa.Column('mins_played_pts', sa.Integer(), nullable=False),
        sa.Column('marca_points', sa.Integer(), nullable=False),
        sa.Column('marca_points_pts', sa.Integer(), nullable=False),
        sa.Column('raw_fields', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('scrape_run_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.ForeignKeyConstraint(['scrape_run_id'], ['scraperun.id'], ),
        sa.PrimaryKeyConstraint('season_year', 'player_id'),
    )

    op.create_table(
        'sourceprediction',
        sa.Column('as_of', sa.Date(), nullable=False),
        sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('raw_fields', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('scrape_run_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.ForeignKeyConstraint(['scrape_run_id'], ['scraperun.id'], ),
        sa.PrimaryKeyConstraint('as_of', 'source', 'player_id'),
    )

    op.create_table(
        'datasetrun',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scrape_run_id', sa.Integer(), nullable=False),
        sa.Column('dataset', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('skipped_count', sa.Integer(), nullable=False),
        sa.Column('season_year', sa.Integer(), nullable=True),
        sa.Column('errors', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['scrape_run_id'], ['scraperun.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_datasetrun_scrape_run_id'), 'datasetrun', ['scrape_run_id'], unique=False
    )


def downgrade() -> None:
    """Drop all four tables this added."""
    op.drop_index(op.f('ix_datasetrun_scrape_run_id'), table_name='datasetrun')
    op.drop_table('datasetrun')
    op.drop_table('sourceprediction')
    op.drop_table('playerseasonstats')
    op.drop_table('playergameweekpoints')
