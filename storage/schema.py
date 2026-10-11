"""Is the database's schema the one this code expects?

The schema changes only through Alembic, and nothing applies a migration
automatically — so after a pull, the database can sit a revision behind the
code (13 days at 0008 in September; 0018 under 0019 on 2026-10-11). Then
any query touching a new column fails. This module lets the API, the
refresh CLI and the UI say so plainly instead.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIX = (
    "The database is behind the code. Stop the app, back up data/fantasy.db, "
    "run `uv run alembic upgrade head`, and start it again."
)


@dataclass(frozen=True)
class SchemaStatus:
    current: str | None
    head: str

    @property
    def up_to_date(self) -> bool:
        return self.current == self.head


@lru_cache
def head_revision() -> str:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def schema_status(engine) -> SchemaStatus:
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return SchemaStatus(current, head_revision())
