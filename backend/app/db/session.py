from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def database_is_reachable() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        logger.exception("database health check failed")
        return False


def get_postgis_version() -> str | None:
    try:
        with get_engine().connect() as connection:
            return connection.execute(text("SELECT postgis_version()")).scalar_one()
    except SQLAlchemyError:
        logger.exception("postgis health check failed")
        return None
