"""Add liquidity assessments and fast-sale estimates.

Revision ID: 0008_liquidity_fast_sale
Revises: 0007_comparable_valuation
Create Date: 2026-08-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_liquidity_fast_sale"
down_revision = "0007_comparable_valuation"
branch_labels = None
depends_on = None

ANALYSIS_STATUSES = ("SUCCESS", "INSUFFICIENT_DATA")


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def upgrade() -> None:
    op.create_table(
        "liquidity_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("valuation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("liquidity_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("probability_sale_30d", sa.Numeric(5, 4), nullable=True),
        sa.Column("probability_sale_60d", sa.Numeric(5, 4), nullable=True),
        sa.Column("probability_sale_90d", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "positive_factors_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "negative_factors_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("status", ANALYSIS_STATUSES),
            name="ck_liquidity_assessments_status",
        ),
        sa.CheckConstraint(
            "liquidity_score IS NULL OR (liquidity_score >= 0 AND liquidity_score <= 100)",
            name="ck_liquidity_assessments_score_range",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_liquidity_assessments_confidence_range",
        ),
        sa.CheckConstraint(
            "probability_sale_30d IS NULL",
            name="ck_liquidity_assessments_probability_30d_null",
        ),
        sa.CheckConstraint(
            "probability_sale_60d IS NULL",
            name="ck_liquidity_assessments_probability_60d_null",
        ),
        sa.CheckConstraint(
            "probability_sale_90d IS NULL",
            name="ck_liquidity_assessments_probability_90d_null",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["valuation_id"], ["valuations.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_liquidity_assessments_property_as_of",
        "liquidity_assessments",
        ["property_id", "as_of"],
    )
    op.create_index(
        "ix_liquidity_assessments_valuation",
        "liquidity_assessments",
        ["valuation_id"],
    )

    op.create_table(
        "fast_sale_estimates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("valuation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("liquidity_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("value_low", sa.Numeric(14, 2), nullable=True),
        sa.Column("value_base", sa.Numeric(14, 2), nullable=True),
        sa.Column("value_high", sa.Numeric(14, 2), nullable=True),
        sa.Column("target_days", sa.Integer(), nullable=False),
        sa.Column("target_probability", sa.Numeric(5, 4), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
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
            _check_in("status", ANALYSIS_STATUSES),
            name="ck_fast_sale_estimates_status",
        ),
        sa.CheckConstraint(
            "target_days > 0",
            name="ck_fast_sale_estimates_target_days_positive",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_fast_sale_estimates_confidence_range",
        ),
        sa.CheckConstraint(
            "target_probability IS NULL",
            name="ck_fast_sale_estimates_target_probability_null",
        ),
        sa.CheckConstraint(
            """
            (
                value_low IS NULL
                AND value_base IS NULL
                AND value_high IS NULL
            )
            OR (
                value_low IS NOT NULL
                AND value_base IS NOT NULL
                AND value_high IS NOT NULL
                AND value_low <= value_base
                AND value_base <= value_high
            )
            """,
            name="ck_fast_sale_estimates_value_order",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["valuation_id"], ["valuations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["liquidity_assessment_id"],
            ["liquidity_assessments.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_fast_sale_estimates_property_as_of",
        "fast_sale_estimates",
        ["property_id", "as_of"],
    )
    op.create_index(
        "ix_fast_sale_estimates_valuation",
        "fast_sale_estimates",
        ["valuation_id"],
    )
    op.create_index(
        "ix_fast_sale_estimates_liquidity",
        "fast_sale_estimates",
        ["liquidity_assessment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_fast_sale_estimates_liquidity", table_name="fast_sale_estimates")
    op.drop_index("ix_fast_sale_estimates_valuation", table_name="fast_sale_estimates")
    op.drop_index("ix_fast_sale_estimates_property_as_of", table_name="fast_sale_estimates")
    op.drop_table("fast_sale_estimates")

    op.drop_index("ix_liquidity_assessments_valuation", table_name="liquidity_assessments")
    op.drop_index(
        "ix_liquidity_assessments_property_as_of",
        table_name="liquidity_assessments",
    )
    op.drop_table("liquidity_assessments")
