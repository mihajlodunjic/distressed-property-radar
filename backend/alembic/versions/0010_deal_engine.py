"""Add deal engine profiles and results.

Revision ID: 0010_deal_engine
Revises: 0009_llm_seller_risk
Create Date: 2026-08-29 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010_deal_engine"
down_revision = "0009_llm_seller_risk"
branch_labels = None
depends_on = None

CURRENCY_CODES = ("EUR", "RSD")
DEAL_ANALYSIS_STATUSES = ("SUCCESS", "INSUFFICIENT_DATA")
DEAL_SCENARIO_TYPES = ("DOWNSIDE", "BASE", "UPSIDE")


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def upgrade() -> None:
    op.create_table(
        "cost_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "purchase_tax_rule_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "notary_rule_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "lawyer_rule_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "agency_rule_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "sale_cost_rule_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "holding_cost_rule_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "financing_rule_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "other_cost_rule_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(_check_in("currency", CURRENCY_CODES), name="ck_cost_profiles_currency"),
        sa.UniqueConstraint("code", name="uq_cost_profiles_code"),
    )
    op.create_index("ix_cost_profiles_active", "cost_profiles", ["is_active"])

    op.create_table(
        "investment_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("min_expected_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("min_downside_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("min_roi", sa.Numeric(10, 6), nullable=True),
        sa.Column("max_expected_holding_days", sa.Integer(), nullable=True),
        sa.Column("min_liquidity_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("min_valuation_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("default_risk_reserve", sa.Numeric(14, 2), nullable=False),
        sa.Column("desired_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "min_expected_profit IS NULL OR min_expected_profit >= 0",
            name="ck_investment_profiles_min_expected_profit",
        ),
        sa.CheckConstraint(
            "min_downside_profit IS NULL OR min_downside_profit >= 0",
            name="ck_investment_profiles_min_downside_profit",
        ),
        sa.CheckConstraint(
            "min_roi IS NULL OR min_roi >= 0",
            name="ck_investment_profiles_min_roi",
        ),
        sa.CheckConstraint(
            "max_expected_holding_days IS NULL OR max_expected_holding_days >= 0",
            name="ck_investment_profiles_holding_days",
        ),
        sa.CheckConstraint(
            "min_liquidity_score IS NULL OR "
            "(min_liquidity_score >= 0 AND min_liquidity_score <= 100)",
            name="ck_investment_profiles_min_liquidity_score",
        ),
        sa.CheckConstraint(
            "min_valuation_confidence IS NULL OR "
            "(min_valuation_confidence >= 0 AND min_valuation_confidence <= 100)",
            name="ck_investment_profiles_min_valuation_confidence",
        ),
        sa.CheckConstraint(
            "default_risk_reserve >= 0",
            name="ck_investment_profiles_default_risk_reserve",
        ),
        sa.CheckConstraint(
            "desired_profit IS NULL OR desired_profit >= 0",
            name="ck_investment_profiles_desired_profit",
        ),
    )
    op.create_index("ix_investment_profiles_default", "investment_profiles", ["is_default"])

    op.create_table(
        "deal_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("valuation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("liquidity_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fast_sale_estimate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cost_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("investment_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assumed_purchase_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("asking_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("purchase_costs", sa.Numeric(14, 2), nullable=True),
        sa.Column("renovation_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("sale_costs", sa.Numeric(14, 2), nullable=True),
        sa.Column("taxes", sa.Numeric(14, 2), nullable=True),
        sa.Column("financing_costs", sa.Numeric(14, 2), nullable=True),
        sa.Column("holding_costs", sa.Numeric(14, 2), nullable=True),
        sa.Column("risk_reserve", sa.Numeric(14, 2), nullable=True),
        sa.Column("other_costs", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_cost_basis", sa.Numeric(14, 2), nullable=True),
        sa.Column("expected_exit_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("max_buy_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("required_negotiation_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("required_negotiation_pct", sa.Numeric(10, 6), nullable=True),
        sa.Column("expected_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("downside_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("upside_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("roi", sa.Numeric(12, 6), nullable=True),
        sa.Column("annualized_roi", sa.Numeric(12, 6), nullable=True),
        sa.Column("expected_holding_days", sa.Integer(), nullable=True),
        sa.Column("capital_days", sa.Numeric(20, 2), nullable=True),
        sa.Column("profit_per_capital_day", sa.Numeric(18, 10), nullable=True),
        sa.Column("formula_version", sa.String(length=100), nullable=False),
        sa.Column(
            "input_summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "explanation_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("status", DEAL_ANALYSIS_STATUSES),
            name="ck_deal_analyses_status",
        ),
        sa.CheckConstraint(
            """
            assumed_purchase_price IS NULL
            OR assumed_purchase_price >= 0
            """,
            name="ck_deal_analyses_assumed_purchase_price",
        ),
        sa.CheckConstraint(
            "asking_price IS NULL OR asking_price >= 0",
            name="ck_deal_analyses_asking_price",
        ),
        sa.CheckConstraint(
            "purchase_costs IS NULL OR purchase_costs >= 0",
            name="ck_deal_analyses_purchase_costs",
        ),
        sa.CheckConstraint(
            "renovation_cost IS NULL OR renovation_cost >= 0",
            name="ck_deal_analyses_renovation_cost",
        ),
        sa.CheckConstraint(
            "sale_costs IS NULL OR sale_costs >= 0",
            name="ck_deal_analyses_sale_costs",
        ),
        sa.CheckConstraint("taxes IS NULL OR taxes >= 0", name="ck_deal_analyses_taxes"),
        sa.CheckConstraint(
            "financing_costs IS NULL OR financing_costs >= 0",
            name="ck_deal_analyses_financing_costs",
        ),
        sa.CheckConstraint(
            "holding_costs IS NULL OR holding_costs >= 0",
            name="ck_deal_analyses_holding_costs",
        ),
        sa.CheckConstraint(
            "risk_reserve IS NULL OR risk_reserve >= 0",
            name="ck_deal_analyses_risk_reserve",
        ),
        sa.CheckConstraint(
            "other_costs IS NULL OR other_costs >= 0",
            name="ck_deal_analyses_other_costs",
        ),
        sa.CheckConstraint(
            "expected_exit_price IS NULL OR expected_exit_price >= 0",
            name="ck_deal_analyses_expected_exit_price",
        ),
        sa.CheckConstraint(
            "max_buy_price IS NULL OR max_buy_price >= 0",
            name="ck_deal_analyses_max_buy_price",
        ),
        sa.CheckConstraint(
            "required_negotiation_amount IS NULL OR required_negotiation_amount >= 0",
            name="ck_deal_analyses_required_negotiation_amount",
        ),
        sa.CheckConstraint(
            "required_negotiation_pct IS NULL OR required_negotiation_pct >= 0",
            name="ck_deal_analyses_required_negotiation_pct",
        ),
        sa.CheckConstraint(
            "expected_holding_days IS NULL OR expected_holding_days >= 0",
            name="ck_deal_analyses_expected_holding_days",
        ),
        sa.CheckConstraint(
            "capital_days IS NULL OR capital_days >= 0",
            name="ck_deal_analyses_capital_days",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["valuation_id"], ["valuations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["liquidity_assessment_id"],
            ["liquidity_assessments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["fast_sale_estimate_id"],
            ["fast_sale_estimates.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["risk_assessment_id"],
            ["risk_assessments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cost_profile_id"],
            ["cost_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investment_profile_id"],
            ["investment_profiles.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_deal_analyses_property_as_of",
        "deal_analyses",
        ["property_id", "as_of"],
    )
    op.create_index("ix_deal_analyses_status", "deal_analyses", ["status"])
    op.create_index("ix_deal_analyses_valuation", "deal_analyses", ["valuation_id"])
    op.create_index(
        "ix_deal_analyses_fast_sale",
        "deal_analyses",
        ["fast_sale_estimate_id"],
    )

    op.create_table(
        "deal_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("deal_analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_type", sa.String(length=16), nullable=False),
        sa.Column("purchase_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("exit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("cost_basis", sa.Numeric(14, 2), nullable=False),
        sa.Column("profit", sa.Numeric(14, 2), nullable=False),
        sa.Column("roi", sa.Numeric(12, 6), nullable=True),
        sa.Column("holding_days", sa.Integer(), nullable=False),
        sa.Column(
            "assumptions_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("scenario_type", DEAL_SCENARIO_TYPES),
            name="ck_deal_scenarios_scenario_type",
        ),
        sa.CheckConstraint(
            "purchase_price >= 0",
            name="ck_deal_scenarios_purchase_price",
        ),
        sa.CheckConstraint("exit_price >= 0", name="ck_deal_scenarios_exit_price"),
        sa.CheckConstraint("cost_basis >= 0", name="ck_deal_scenarios_cost_basis"),
        sa.CheckConstraint("holding_days >= 0", name="ck_deal_scenarios_holding_days"),
        sa.ForeignKeyConstraint(
            ["deal_analysis_id"],
            ["deal_analyses.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "deal_analysis_id",
            "scenario_type",
            name="uq_deal_scenarios_analysis_type",
        ),
    )
    op.create_index(
        "ix_deal_scenarios_analysis",
        "deal_scenarios",
        ["deal_analysis_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_deal_scenarios_analysis", table_name="deal_scenarios")
    op.drop_table("deal_scenarios")

    op.drop_index("ix_deal_analyses_fast_sale", table_name="deal_analyses")
    op.drop_index("ix_deal_analyses_valuation", table_name="deal_analyses")
    op.drop_index("ix_deal_analyses_status", table_name="deal_analyses")
    op.drop_index("ix_deal_analyses_property_as_of", table_name="deal_analyses")
    op.drop_table("deal_analyses")

    op.drop_index("ix_investment_profiles_default", table_name="investment_profiles")
    op.drop_table("investment_profiles")

    op.drop_index("ix_cost_profiles_active", table_name="cost_profiles")
    op.drop_table("cost_profiles")
