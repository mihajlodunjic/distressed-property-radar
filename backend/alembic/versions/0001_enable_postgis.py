"""Enable PostGIS extension.

Revision ID: 0001_enable_postgis
Revises:
Create Date: 2026-08-27 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "0001_enable_postgis"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS postgis")
