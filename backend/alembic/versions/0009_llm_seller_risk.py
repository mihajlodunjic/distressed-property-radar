"""Add LLM analyses, seller assessments, and risk results.

Revision ID: 0009_llm_seller_risk
Revises: 0008_liquidity_fast_sale
Create Date: 2026-08-29 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_llm_seller_risk"
down_revision = "0008_liquidity_fast_sale"
branch_labels = None
depends_on = None

ANALYSIS_LEVELS = ("LOW", "MEDIUM", "HIGH", "UNKNOWN")
DATA_SOURCE_KINDS = (
    "SCRAPED",
    "DERIVED",
    "LLM",
    "MANUAL",
    "VERIFIED_MANUAL",
    "TRANSACTION_DATA",
    "IMPORT",
)
LLM_ANALYSIS_STATUSES = ("PENDING", "SUCCESS", "FAILED", "INVALID_OUTPUT")
REASONS_FOR_SALE = (
    "MOVING",
    "MOVING_ABROAD",
    "NEEDS_LIQUIDITY",
    "INHERITANCE",
    "DIVORCE",
    "BUSINESS_LIQUIDITY",
    "BOUGHT_ANOTHER_PROPERTY",
    "VACANT_PROPERTY",
    "INVESTOR_EXIT",
    "TIME_DEADLINE",
    "OTHER",
    "UNKNOWN",
)
RISK_GATE_STATUSES = ("PASS", "VERIFY", "BLOCK")
RISK_SEVERITIES = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")
RISK_GATE_EFFECTS = ("NONE", "VERIFY", "BLOCK")


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def upgrade() -> None:
    op.create_table(
        "llm_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_hash", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("seller_motivation_level", sa.String(length=16), nullable=True),
        sa.Column("seller_motivation_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("cash_preferred", sa.Boolean(), nullable=True),
        sa.Column("cash_preference_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("negotiability_level", sa.String(length=16), nullable=True),
        sa.Column("negotiability_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("reason_for_sale", sa.String(length=40), nullable=True),
        sa.Column("reason_for_sale_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("condition_category", sa.String(length=100), nullable=True),
        sa.Column("condition_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "structured_output_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "evidence_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            _check_in("status", LLM_ANALYSIS_STATUSES),
            name="ck_llm_analyses_status",
        ),
        sa.CheckConstraint(
            "seller_motivation_level IS NULL OR "
            + _check_in("seller_motivation_level", ANALYSIS_LEVELS),
            name="ck_llm_analyses_seller_motivation_level",
        ),
        sa.CheckConstraint(
            "negotiability_level IS NULL OR " + _check_in("negotiability_level", ANALYSIS_LEVELS),
            name="ck_llm_analyses_negotiability_level",
        ),
        sa.CheckConstraint(
            "reason_for_sale IS NULL OR " + _check_in("reason_for_sale", REASONS_FOR_SALE),
            name="ck_llm_analyses_reason_for_sale",
        ),
        sa.CheckConstraint(
            """
            seller_motivation_confidence IS NULL
            OR (seller_motivation_confidence >= 0 AND seller_motivation_confidence <= 100)
            """,
            name="ck_llm_analyses_seller_motivation_confidence",
        ),
        sa.CheckConstraint(
            """
            cash_preference_confidence IS NULL
            OR (cash_preference_confidence >= 0 AND cash_preference_confidence <= 100)
            """,
            name="ck_llm_analyses_cash_preference_confidence",
        ),
        sa.CheckConstraint(
            """
            negotiability_confidence IS NULL
            OR (negotiability_confidence >= 0 AND negotiability_confidence <= 100)
            """,
            name="ck_llm_analyses_negotiability_confidence",
        ),
        sa.CheckConstraint(
            """
            reason_for_sale_confidence IS NULL
            OR (reason_for_sale_confidence >= 0 AND reason_for_sale_confidence <= 100)
            """,
            name="ck_llm_analyses_reason_for_sale_confidence",
        ),
        sa.CheckConstraint(
            """
            condition_confidence IS NULL
            OR (condition_confidence >= 0 AND condition_confidence <= 100)
            """,
            name="ck_llm_analyses_condition_confidence",
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_llm_analyses_cache_lookup",
        "llm_analyses",
        ["listing_id", "input_hash", "prompt_version", "model", "status"],
    )
    op.create_index("ix_llm_analyses_property", "llm_analyses", ["property_id"])

    op.create_table(
        "seller_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("primary_llm_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seller_motivation_level", sa.String(length=16), nullable=False),
        sa.Column("seller_motivation_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("seller_motivation_confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("negotiability_level", sa.String(length=16), nullable=False),
        sa.Column("negotiability_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("negotiability_confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("cash_preferred", sa.Boolean(), nullable=True),
        sa.Column("cash_preference_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("reason_for_sale", sa.String(length=40), nullable=False),
        sa.Column(
            "evidence_json",
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
            _check_in("seller_motivation_level", ANALYSIS_LEVELS),
            name="ck_seller_assessments_seller_motivation_level",
        ),
        sa.CheckConstraint(
            "seller_motivation_score IS NULL OR "
            "(seller_motivation_score >= 0 AND seller_motivation_score <= 100)",
            name="ck_seller_assessments_seller_motivation_score",
        ),
        sa.CheckConstraint(
            "seller_motivation_confidence >= 0 AND seller_motivation_confidence <= 100",
            name="ck_seller_assessments_seller_motivation_confidence",
        ),
        sa.CheckConstraint(
            _check_in("negotiability_level", ANALYSIS_LEVELS),
            name="ck_seller_assessments_negotiability_level",
        ),
        sa.CheckConstraint(
            "negotiability_score IS NULL OR "
            "(negotiability_score >= 0 AND negotiability_score <= 100)",
            name="ck_seller_assessments_negotiability_score",
        ),
        sa.CheckConstraint(
            "negotiability_confidence >= 0 AND negotiability_confidence <= 100",
            name="ck_seller_assessments_negotiability_confidence",
        ),
        sa.CheckConstraint(
            "cash_preference_confidence IS NULL OR "
            "(cash_preference_confidence >= 0 AND cash_preference_confidence <= 100)",
            name="ck_seller_assessments_cash_preference_confidence",
        ),
        sa.CheckConstraint(
            _check_in("reason_for_sale", REASONS_FOR_SALE),
            name="ck_seller_assessments_reason_for_sale",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["primary_llm_analysis_id"],
            ["llm_analyses.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_seller_assessments_property_as_of",
        "seller_assessments",
        ["property_id", "as_of"],
    )
    op.create_index(
        "ix_seller_assessments_llm_analysis",
        "seller_assessments",
        ["primary_llm_analysis_id"],
    )

    op.create_table(
        "risk_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hard_gate_status", sa.String(length=16), nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("rules_version", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("hard_gate_status", RISK_GATE_STATUSES),
            name="ck_risk_assessments_hard_gate_status",
        ),
        sa.CheckConstraint(
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)",
            name="ck_risk_assessments_risk_score",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_risk_assessments_confidence",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_risk_assessments_property_as_of",
        "risk_assessments",
        ["property_id", "as_of"],
    )
    op.create_index(
        "ix_risk_assessments_gate",
        "risk_assessments",
        ["hard_gate_status"],
    )

    op.create_table(
        "risk_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("risk_assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("gate_effect", sa.String(length=16), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "evidence_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint(_check_in("severity", RISK_SEVERITIES), name="ck_risk_flags_severity"),
        sa.CheckConstraint(
            _check_in("gate_effect", RISK_GATE_EFFECTS),
            name="ck_risk_flags_gate_effect",
        ),
        sa.CheckConstraint(
            _check_in("source_kind", DATA_SOURCE_KINDS),
            name="ck_risk_flags_source_kind",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_risk_flags_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["risk_assessment_id"],
            ["risk_assessments.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_risk_flags_assessment",
        "risk_flags",
        ["risk_assessment_id"],
    )
    op.create_index("ix_risk_flags_code", "risk_flags", ["code"])
    op.create_index("ix_risk_flags_gate_effect", "risk_flags", ["gate_effect"])


def downgrade() -> None:
    op.drop_index("ix_risk_flags_gate_effect", table_name="risk_flags")
    op.drop_index("ix_risk_flags_code", table_name="risk_flags")
    op.drop_index("ix_risk_flags_assessment", table_name="risk_flags")
    op.drop_table("risk_flags")

    op.drop_index("ix_risk_assessments_gate", table_name="risk_assessments")
    op.drop_index("ix_risk_assessments_property_as_of", table_name="risk_assessments")
    op.drop_table("risk_assessments")

    op.drop_index("ix_seller_assessments_llm_analysis", table_name="seller_assessments")
    op.drop_index("ix_seller_assessments_property_as_of", table_name="seller_assessments")
    op.drop_table("seller_assessments")

    op.drop_index("ix_llm_analyses_property", table_name="llm_analyses")
    op.drop_index("ix_llm_analyses_cache_lookup", table_name="llm_analyses")
    op.drop_table("llm_analyses")
