from __future__ import annotations

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.db.session import get_engine
from tests.conftest import alembic_config


def test_database_is_at_alembic_head() -> None:
    config = alembic_config()
    script = ScriptDirectory.from_config(config)

    with get_engine().connect() as connection:
        migration_context = MigrationContext.configure(connection)
        current_heads = set(migration_context.get_current_heads())

    assert current_heads == set(script.get_heads())
