"""SQLModel/SQLAlchemy engine and session management.

The schema is created exclusively by Alembic revisions (see `migrations/`).
Nothing in this module — or anywhere in application/test startup — creates
tables directly from SQLModel metadata. Tests build their schema by running
the migrations against a throwaway database, exercising the same migration
path that production uses.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlmodel import Session, create_engine

from core.config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            f"sqlite:///{settings.db_path}",
            connect_args={"check_same_thread": False},
        )
    return _engine


def set_engine(engine) -> None:
    """Override the module-level engine — used by tests to point at an
    in-memory database built from the Alembic migrations."""
    global _engine
    _engine = engine


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def as_utc(value: datetime) -> datetime:
    """Re-attach UTC to a datetime that SQLite round-tripped as naive.

    Every datetime this project writes is UTC-aware, but SQLite has no
    offset-carrying type, so reads come back naive and comparing one against
    `datetime.now(UTC)` raises. Normalising here — at the storage boundary
    that owns SQLite's quirks — keeps the pure engines free of it: they
    receive aware values and never learn the database has this property.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
