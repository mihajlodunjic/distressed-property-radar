from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://distressed_property_radar:change-me-local-only"
    "@localhost:55432/distressed_property_radar_test"
)

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL),
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database() -> None:
    command.upgrade(alembic_config(), "head")


@pytest.fixture
def client() -> TestClient:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
