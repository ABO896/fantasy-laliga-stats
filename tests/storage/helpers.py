"""Small seeding helpers shared across `tests/storage/*` test modules.

Not a test module itself — nothing here is collected by pytest.
"""

from datetime import UTC, datetime

from storage.models import Fixture


def seed_fixture(session, fid: int, matchday: int, kickoff: datetime, final: bool) -> None:
    """One `Fixture` row, home Sevilla FC vs away Getafe — the two clubs
    `tests/storage/test_ingestion_repository.py` and
    `tests/storage/test_our_models.py` seed their players under."""
    session.add(
        Fixture(
            fixture_id=fid, matchday=matchday, kickoff_utc=kickoff, kickoff_confirmed=True,
            is_final=final, home_team="Sevilla FC", away_team="Getafe",
            scraped_at=datetime.now(UTC),
        )
    )
    session.commit()
