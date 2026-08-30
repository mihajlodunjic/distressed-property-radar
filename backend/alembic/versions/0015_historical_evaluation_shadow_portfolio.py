"""Add historical evaluation and shadow portfolio tables.

Revision ID: 0015_historical_evaluation
Revises: 0014_second_source_nekretnine_rs
Create Date: 2026-08-30 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015_historical_evaluation"
down_revision = "0014_second_source_nekretnine_rs"
branch_labels = None
depends_on = None

OPPORTUNITY_ACTIONS = ("IGNORE", "WATCH", "REVIEW", "CALL", "URGENT_CALL")
PROPERTY_OUTCOME_TYPES = (
    "STILL_ACTIVE",
    "REMOVED_UNKNOWN",
    "RELISTED",
    "LIKELY_SOLD",
    "CONFIRMED_SOLD",
    "BOUGHT_BY_USER",
    "LOST_TO_OTHER_BUYER",
    "SALE_CANCELLED",
    "OTHER",
)
SHADOW_DEAL_STATUSES = ("OPEN", "CLOSED", "ABANDONED")
SHADOW_OUTCOME_STATUSES = ("OPEN", "MEASURED", "UNKNOWN")
HISTORICAL_EVALUATION_RUN_STATUSES = ("SUCCESS", "FAILED")
HISTORICAL_EVALUATION_CLASSIFICATIONS = (
    "TRUE_POSITIVE",
    "FALSE_POSITIVE",
    "FALSE_NEGATIVE",
    "TRUE_NEGATIVE",
    "UNKNOWN",
)


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def _nullable_check_in(column_name: str, values: tuple[str, ...]) -> str:
    return f"{column_name} IS NULL OR {_check_in(column_name, values)}"


def _non_negative(column_name: str) -> str:
    return f"{column_name} IS NULL OR {column_name} >= 0"


def upgrade() -> None:
    op.create_table(
        "shadow_deals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deal_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("simulated_buy_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("simulated_buy_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("assumed_total_cost_basis", sa.Numeric(14, 2), nullable=True),
        sa.Column("expected_exit_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("expected_holding_days", sa.Integer(), nullable=True),
        sa.Column("expected_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("decision_action", sa.String(length=24), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_versions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "simulated_buy_price > 0",
            name="ck_shadow_deals_simulated_buy_price_positive",
        ),
        sa.CheckConstraint(
            _non_negative("assumed_total_cost_basis"),
            name="ck_shadow_deals_cost_basis",
        ),
        sa.CheckConstraint(
            _non_negative("expected_exit_price"),
            name="ck_shadow_deals_expected_exit",
        ),
        sa.CheckConstraint(
            _non_negative("expected_holding_days"),
            name="ck_shadow_deals_expected_holding",
        ),
        sa.CheckConstraint(
            _nullable_check_in("decision_action", OPPORTUNITY_ACTIONS),
            name="ck_shadow_deals_decision_action",
        ),
        sa.CheckConstraint(
            _check_in("status", SHADOW_DEAL_STATUSES), name="ck_shadow_deals_status"
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["opportunity_assessment_id"],
            ["opportunity_assessments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["deal_analysis_id"],
            ["deal_analyses.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_shadow_deals_property_buy_date",
        "shadow_deals",
        ["property_id", "simulated_buy_date"],
    )
    op.create_index(
        "ix_shadow_deals_opportunity",
        "shadow_deals",
        ["opportunity_assessment_id"],
    )
    op.create_index("ix_shadow_deals_deal", "shadow_deals", ["deal_analysis_id"])
    op.create_index("ix_shadow_deals_status", "shadow_deals", ["status"])

    op.create_table(
        "shadow_deal_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shadow_deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_outcome_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome_status", sa.String(length=16), nullable=False),
        sa.Column("actual_observed_outcome", sa.String(length=32), nullable=True),
        sa.Column("actual_observed_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("actual_observed_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("simulated_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("simulated_roi", sa.Numeric(12, 6), nullable=True),
        sa.Column("evaluation_version", sa.String(length=100), nullable=False),
        sa.Column("outcome_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("outcome_status", SHADOW_OUTCOME_STATUSES),
            name="ck_shadow_deal_outcomes_status",
        ),
        sa.CheckConstraint(
            _nullable_check_in("actual_observed_outcome", PROPERTY_OUTCOME_TYPES),
            name="ck_shadow_deal_outcomes_actual_outcome",
        ),
        sa.CheckConstraint(
            _non_negative("actual_observed_price"),
            name="ck_shadow_deal_outcomes_actual_price",
        ),
        sa.ForeignKeyConstraint(["shadow_deal_id"], ["shadow_deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["property_outcome_id"],
            ["property_outcomes.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_shadow_deal_outcomes_shadow_as_of",
        "shadow_deal_outcomes",
        ["shadow_deal_id", "evaluation_as_of"],
    )
    op.create_index(
        "ix_shadow_deal_outcomes_property_outcome",
        "shadow_deal_outcomes",
        ["property_outcome_id"],
    )

    op.create_table(
        "historical_evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prediction_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input_scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "evaluation_as_of >= prediction_as_of",
            name="ck_historical_evaluation_runs_as_of_order",
        ),
        sa.CheckConstraint(
            _check_in("status", HISTORICAL_EVALUATION_RUN_STATUSES),
            name="ck_historical_evaluation_runs_status",
        ),
    )
    op.create_index(
        "ix_historical_evaluation_runs_prediction_eval",
        "historical_evaluation_runs",
        ["prediction_as_of", "evaluation_as_of"],
    )

    op.create_table(
        "historical_evaluation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deal_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("property_outcome_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recommended_action", sa.String(length=24), nullable=True),
        sa.Column("classification", sa.String(length=24), nullable=False),
        sa.Column("opportunity_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("ranking_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("expected_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("downside_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("roi", sa.Numeric(12, 6), nullable=True),
        sa.Column("outcome_type", sa.String(length=32), nullable=True),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _nullable_check_in("recommended_action", OPPORTUNITY_ACTIONS),
            name="ck_historical_evaluation_items_action",
        ),
        sa.CheckConstraint(
            _check_in("classification", HISTORICAL_EVALUATION_CLASSIFICATIONS),
            name="ck_historical_evaluation_items_classification",
        ),
        sa.CheckConstraint(
            _nullable_check_in("outcome_type", PROPERTY_OUTCOME_TYPES),
            name="ck_historical_evaluation_items_outcome_type",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["historical_evaluation_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["opportunity_assessment_id"],
            ["opportunity_assessments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["deal_analysis_id"],
            ["deal_analyses.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["property_outcome_id"],
            ["property_outcomes.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_historical_evaluation_items_run",
        "historical_evaluation_items",
        ["run_id"],
    )
    op.create_index(
        "ix_historical_evaluation_items_property",
        "historical_evaluation_items",
        ["property_id"],
    )
    op.create_index(
        "ix_historical_evaluation_items_opportunity",
        "historical_evaluation_items",
        ["opportunity_assessment_id"],
    )
    op.create_index(
        "ix_historical_evaluation_items_deal",
        "historical_evaluation_items",
        ["deal_analysis_id"],
    )
    op.create_index(
        "ix_historical_evaluation_items_outcome",
        "historical_evaluation_items",
        ["property_outcome_id"],
    )
    op.create_index(
        "ix_historical_evaluation_items_classification",
        "historical_evaluation_items",
        ["classification"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_historical_evaluation_items_classification",
        table_name="historical_evaluation_items",
    )
    op.drop_index(
        "ix_historical_evaluation_items_outcome",
        table_name="historical_evaluation_items",
    )
    op.drop_index("ix_historical_evaluation_items_deal", table_name="historical_evaluation_items")
    op.drop_index(
        "ix_historical_evaluation_items_opportunity",
        table_name="historical_evaluation_items",
    )
    op.drop_index(
        "ix_historical_evaluation_items_property",
        table_name="historical_evaluation_items",
    )
    op.drop_index("ix_historical_evaluation_items_run", table_name="historical_evaluation_items")
    op.drop_table("historical_evaluation_items")

    op.drop_index(
        "ix_historical_evaluation_runs_prediction_eval",
        table_name="historical_evaluation_runs",
    )
    op.drop_table("historical_evaluation_runs")

    op.drop_index(
        "ix_shadow_deal_outcomes_property_outcome",
        table_name="shadow_deal_outcomes",
    )
    op.drop_index("ix_shadow_deal_outcomes_shadow_as_of", table_name="shadow_deal_outcomes")
    op.drop_table("shadow_deal_outcomes")

    op.drop_index("ix_shadow_deals_status", table_name="shadow_deals")
    op.drop_index("ix_shadow_deals_deal", table_name="shadow_deals")
    op.drop_index("ix_shadow_deals_opportunity", table_name="shadow_deals")
    op.drop_index("ix_shadow_deals_property_buy_date", table_name="shadow_deals")
    op.drop_table("shadow_deals")
