import sqlalchemy as sa

from core.season_stats_schema import STAT_PAIRS, SUMMARY_FIELDS, column_name
from storage.models import DatasetRun, PlayerGameweekPoints, PlayerSeasonStats, SourcePrediction

#: (migration table name, SQLModel class) for every table this task added.
_NEW_TABLES = (
    ("playergameweekpoints", PlayerGameweekPoints),
    ("playerseasonstats", PlayerSeasonStats),
    ("sourceprediction", SourcePrediction),
    ("datasetrun", DatasetRun),
)


def test_column_name_converts_camel_to_snake():
    assert column_name("goalAssistPts") == "goal_assist_pts"
    assert column_name("possLostAll") == "poss_lost_all"
    assert column_name("saves") == "saves"


def test_every_declared_stat_field_exists_on_the_model():
    """The canonical list and the table must not drift. Plan 2 builds the
    browser's column registry from this list, so a name that exists in one
    and not the other produces a column that silently never sorts."""
    model_fields = set(PlayerSeasonStats.model_fields)
    expected = {column_name(f) for f in SUMMARY_FIELDS}
    for counter, points in STAT_PAIRS:
        expected.add(column_name(counter))
        expected.add(column_name(points))
    missing = expected - model_fields
    assert not missing, f"declared but not on the model: {sorted(missing)}"


def test_there_are_twenty_one_stat_pairs():
    assert len(STAT_PAIRS) == 21


def test_migration_columns_match_model_fields_for_every_new_table(engine):
    """The suite builds its database from the migration; the SQLModel
    classes are only used for reads. A column present on one and missing
    from the other fails at runtime, not in the suite -- on tables
    transcribed by hand in three places, that's the regression this task
    is most exposed to. Checked in both directions, for all four tables.
    """
    inspector = sa.inspect(engine)
    for table_name, model in _NEW_TABLES:
        migration_columns = {col["name"] for col in inspector.get_columns(table_name)}
        model_columns = set(model.model_fields)

        missing_from_migration = model_columns - migration_columns
        assert not missing_from_migration, (
            f"{table_name}: on the model but missing from the migration: "
            f"{sorted(missing_from_migration)}"
        )

        missing_from_model = migration_columns - model_columns
        assert not missing_from_model, (
            f"{table_name}: created by the migration but missing from the model: "
            f"{sorted(missing_from_model)}"
        )


def test_season_record_fields_is_24_and_every_one_maps_to_a_model_column():
    """The Records/Leaderboard allowlist must never silently drift from the
    table — a name here with no matching column raises AttributeError deep
    inside a repository query instead of failing this cheap check."""
    from core.season_stats_schema import SEASON_RECORD_FIELDS

    assert len(SEASON_RECORD_FIELDS) == 24
    model_fields = set(PlayerSeasonStats.model_fields)
    for camel in SEASON_RECORD_FIELDS:
        assert column_name(camel) in model_fields, camel


def test_season_record_fields_excludes_market_value_and_ideal_formation_count():
    from core.season_stats_schema import SEASON_RECORD_FIELDS

    assert "marketValue" not in SEASON_RECORD_FIELDS
    assert "idealFormationCount" not in SEASON_RECORD_FIELDS
