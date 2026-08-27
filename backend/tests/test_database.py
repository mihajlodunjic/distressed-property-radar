from __future__ import annotations

from sqlalchemy import text

from app.db.session import get_engine


def test_database_connection_executes_query() -> None:
    with get_engine().connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_postgis_extension_is_available() -> None:
    with get_engine().connect() as connection:
        version = connection.execute(text("SELECT postgis_version()")).scalar_one()

    assert version
