"""Add watch rules and property analysis state.

Revision ID: 0012_watchlist_reanalysis
Revises: 0011_opportunity_alerts
Create Date: 2026-08-29 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012_watchlist_reanalysis"
down_revision = "0011_opportunity_alerts"
branch_labels = None
depends_on = None

ANALYSIS_STATUSES = (
    "NOT_RUN",
    "PENDING",
    "RUNNING",
    "SUCCESS",
    "FAILED",
    "STALE",
    "INSUFFICIENT_DATA",
)
WATCH_RULE_TYPES = (
    "ANY_PRICE_CHANGE",
    "PRICE_BELOW",
    "PRICE_DROP_PERCENT",
    "DESCRIPTION_CHANGE",
    "SELLER_CHANGE",
)


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def _nullable_check_in(column_name: str, values: tuple[str, ...]) -> str:
    return f"{column_name} IS NULL OR {_check_in(column_name, values)}"


def upgrade() -> None:
    op.create_table(
        "property_analysis_state",
        sa.Column("property_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "features_status", sa.String(length=20), nullable=False, server_default="NOT_RUN"
        ),
        sa.Column(
            "matching_status", sa.String(length=20), nullable=False, server_default="NOT_RUN"
        ),
        sa.Column(
            "comparable_status",
            sa.String(length=20),
            nullable=False,
            server_default="NOT_RUN",
        ),
        sa.Column(
            "valuation_status", sa.String(length=20), nullable=False, server_default="NOT_RUN"
        ),
        sa.Column(
            "liquidity_status", sa.String(length=20), nullable=False, server_default="NOT_RUN"
        ),
        sa.Column(
            "fast_sale_status", sa.String(length=20), nullable=False, server_default="NOT_RUN"
        ),
        sa.Column("llm_status", sa.String(length=20), nullable=False, server_default="NOT_RUN"),
        sa.Column("seller_status", sa.String(length=20), nullable=False, server_default="NOT_RUN"),
        sa.Column("risk_status", sa.String(length=20), nullable=False, server_default="NOT_RUN"),
        sa.Column("deal_status", sa.String(length=20), nullable=False, server_default="NOT_RUN"),
        sa.Column(
            "opportunity_status",
            sa.String(length=20),
            nullable=False,
            server_default="NOT_RUN",
        ),
        sa.Column("last_analysis_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_analysis_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("features_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_features_status",
        ),
        sa.CheckConstraint(
            _check_in("matching_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_matching_status",
        ),
        sa.CheckConstraint(
            _check_in("comparable_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_comparable_status",
        ),
        sa.CheckConstraint(
            _check_in("valuation_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_valuation_status",
        ),
        sa.CheckConstraint(
            _check_in("liquidity_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_liquidity_status",
        ),
        sa.CheckConstraint(
            _check_in("fast_sale_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_fast_sale_status",
        ),
        sa.CheckConstraint(
            _check_in("llm_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_llm_status",
        ),
        sa.CheckConstraint(
            _check_in("seller_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_seller_status",
        ),
        sa.CheckConstraint(
            _check_in("risk_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_risk_status",
        ),
        sa.CheckConstraint(
            _check_in("deal_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_deal_status",
        ),
        sa.CheckConstraint(
            _check_in("opportunity_status", ANALYSIS_STATUSES),
            name="ck_property_analysis_state_opportunity_status",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "watch_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rule_type", sa.String(length=32), nullable=True),
        sa.Column("threshold_numeric", sa.Numeric(14, 4), nullable=True),
        sa.Column(
            "rule_config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_triggered_change_key", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            _nullable_check_in("rule_type", WATCH_RULE_TYPES),
            name="ck_watch_rules_rule_type",
        ),
        sa.CheckConstraint(
            "threshold_numeric IS NULL OR threshold_numeric > 0",
            name="ck_watch_rules_threshold_positive",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_watch_rules_property_active", "watch_rules", ["property_id", "is_active"])
    op.create_index("ix_watch_rules_active", "watch_rules", ["is_active"])

    op.create_table(
        "watch_trigger_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("watch_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_type", sa.String(length=32), nullable=True),
        sa.Column("change_key", sa.String(length=255), nullable=False),
        sa.Column(
            "summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "invalidated_modules_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "reanalyzed_modules_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "previous_opportunity_assessment_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("new_opportunity_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _nullable_check_in("trigger_type", WATCH_RULE_TYPES),
            name="ck_watch_trigger_events_trigger_type",
        ),
        sa.ForeignKeyConstraint(["watch_rule_id"], ["watch_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_event_id"], ["listing_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["previous_opportunity_assessment_id"],
            ["opportunity_assessments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["new_opportunity_assessment_id"],
            ["opportunity_assessments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "watch_rule_id",
            "change_key",
            name="uq_watch_trigger_events_rule_change_key",
        ),
    )
    op.create_index(
        "ix_watch_trigger_events_property_triggered",
        "watch_trigger_events",
        ["property_id", "triggered_at"],
    )
    op.create_index(
        "ix_watch_trigger_events_listing_event",
        "watch_trigger_events",
        ["listing_event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_watch_trigger_events_listing_event",
        table_name="watch_trigger_events",
    )
    op.drop_index(
        "ix_watch_trigger_events_property_triggered",
        table_name="watch_trigger_events",
    )
    op.drop_table("watch_trigger_events")
    op.drop_index("ix_watch_rules_active", table_name="watch_rules")
    op.drop_index("ix_watch_rules_property_active", table_name="watch_rules")
    op.drop_table("watch_rules")
    op.drop_table("property_analysis_state")
