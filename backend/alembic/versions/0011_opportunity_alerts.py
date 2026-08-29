"""Add opportunity assessments and alerts.

Revision ID: 0011_opportunity_alerts
Revises: 0010_deal_engine
Create Date: 2026-08-29 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011_opportunity_alerts"
down_revision = "0010_deal_engine"
branch_labels = None
depends_on = None

OPPORTUNITY_ACTIONS = ("IGNORE", "WATCH", "REVIEW", "CALL", "URGENT_CALL")
ALERT_CHANNELS = ("TELEGRAM",)
ALERT_TYPES = ("OPPORTUNITY", "OPERATIONAL")
ALERT_STATUSES = ("PENDING", "SENT", "FAILED", "SUPPRESSED")


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def upgrade() -> None:
    op.create_table(
        "opportunity_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recommended_action", sa.String(length=24), nullable=False),
        sa.Column("opportunity_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("ranking_value", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "reason_codes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "explanation_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("rules_version", sa.String(length=100), nullable=False),
        sa.Column("state_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("recommended_action", OPPORTUNITY_ACTIONS),
            name="ck_opportunity_assessments_recommended_action",
        ),
        sa.CheckConstraint(
            """
            opportunity_score IS NULL
            OR (opportunity_score >= 0 AND opportunity_score <= 100)
            """,
            name="ck_opportunity_assessments_score",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["deal_analysis_id"],
            ["deal_analyses.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_opportunity_assessments_property_as_of",
        "opportunity_assessments",
        ["property_id", "as_of"],
    )
    op.create_index(
        "ix_opportunity_assessments_property_created",
        "opportunity_assessments",
        ["property_id", "created_at"],
    )
    op.create_index(
        "ix_opportunity_assessments_deal",
        "opportunity_assessments",
        ["deal_analysis_id"],
    )
    op.create_index(
        "ix_opportunity_assessments_action",
        "opportunity_assessments",
        ["recommended_action"],
    )
    op.create_index(
        "ix_opportunity_assessments_state_hash",
        "opportunity_assessments",
        ["state_hash"],
    )

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("opportunity_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("send_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(_check_in("channel", ALERT_CHANNELS), name="ck_alerts_channel"),
        sa.CheckConstraint(_check_in("alert_type", ALERT_TYPES), name="ck_alerts_alert_type"),
        sa.CheckConstraint(_check_in("status", ALERT_STATUSES), name="ck_alerts_status"),
        sa.CheckConstraint("priority >= 0", name="ck_alerts_priority"),
        sa.CheckConstraint("send_attempt_count >= 0", name="ck_alerts_send_attempt_count"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["opportunity_assessment_id"],
            ["opportunity_assessments.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_alerts_dedupe_key"),
    )
    op.create_index("ix_alerts_status_created", "alerts", ["status", "created_at"])
    op.create_index("ix_alerts_property", "alerts", ["property_id"])
    op.create_index("ix_alerts_opportunity", "alerts", ["opportunity_assessment_id"])
    op.create_index("ix_alerts_type_status", "alerts", ["alert_type", "status"])


def downgrade() -> None:
    op.drop_index("ix_alerts_type_status", table_name="alerts")
    op.drop_index("ix_alerts_opportunity", table_name="alerts")
    op.drop_index("ix_alerts_property", table_name="alerts")
    op.drop_index("ix_alerts_status_created", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index(
        "ix_opportunity_assessments_state_hash",
        table_name="opportunity_assessments",
    )
    op.drop_index("ix_opportunity_assessments_action", table_name="opportunity_assessments")
    op.drop_index("ix_opportunity_assessments_deal", table_name="opportunity_assessments")
    op.drop_index(
        "ix_opportunity_assessments_property_created",
        table_name="opportunity_assessments",
    )
    op.drop_index(
        "ix_opportunity_assessments_property_as_of",
        table_name="opportunity_assessments",
    )
    op.drop_table("opportunity_assessments")
