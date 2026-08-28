"""Add continuous crawling state.

Revision ID: 0004_continuous_crawling_state
Revises: 0003_first_source_ingestion
Create Date: 2026-08-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_continuous_crawling_state"
down_revision = "0003_first_source_ingestion"
branch_labels = None
depends_on = None

SOURCE_HEALTH_STATUSES = ("HEALTHY", "DEGRADED", "FAILED", "DISABLED")


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def upgrade() -> None:
    op.add_column(
        "source_runtime_state",
        sa.Column(
            "consecutive_zero_result_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "source_runtime_state",
        sa.Column(
            "health_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'HEALTHY'"),
        ),
    )
    op.create_check_constraint(
        "ck_source_runtime_state_health_status",
        "source_runtime_state",
        _check_in("health_status", SOURCE_HEALTH_STATUSES),
    )

    op.add_column(
        "listings",
        sa.Column(
            "consecutive_not_seen_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.add_column(
        "job_runs",
        sa.Column("not_seen_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("job_runs", "not_seen_count")
    op.drop_column("listings", "consecutive_not_seen_count")
    op.drop_constraint(
        "ck_source_runtime_state_health_status",
        "source_runtime_state",
        type_="check",
    )
    op.drop_column("source_runtime_state", "health_status")
    op.drop_column("source_runtime_state", "consecutive_zero_result_count")
