"""Add comparable sets and valuation results.

Revision ID: 0007_comparable_valuation
Revises: 0006_market_dataset
Create Date: 2026-08-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_comparable_valuation"
down_revision = "0006_market_dataset"
branch_labels = None
depends_on = None

COMPARABLE_TYPES = ("TRANSACTION", "LISTING", "PROPERTY_HISTORY")
VALUATION_STATUSES = ("SUCCESS", "INSUFFICIENT_DATA")
VALUATION_MODEL_TYPES = ("LISTING_COMPS",)
CURRENCY_CODES = ("EUR", "RSD")


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def upgrade() -> None:
    op.create_table(
        "comparable_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comparable_engine_version", sa.String(length=100), nullable=False),
        sa.Column(
            "search_parameters_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_comparable_sets_property_as_of",
        "comparable_sets",
        ["property_id", "as_of"],
    )

    op.create_table(
        "comparable_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("comparable_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comparable_type", sa.String(length=24), nullable=False),
        sa.Column("transaction_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("similarity_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("distance_m", sa.Numeric(12, 2), nullable=True),
        sa.Column("age_days_at_analysis", sa.Integer(), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_per_m2", sa.Numeric(14, 2), nullable=True),
        sa.Column("weight", sa.Numeric(8, 4), nullable=True),
        sa.Column(
            "included_in_valuation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("exclusion_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("comparable_type", COMPARABLE_TYPES),
            name="ck_comparable_items_comparable_type",
        ),
        sa.ForeignKeyConstraint(
            ["comparable_set_id"],
            ["comparable_sets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_comparable_items_set",
        "comparable_items",
        ["comparable_set_id"],
    )
    op.create_index(
        "ix_comparable_items_listing",
        "comparable_items",
        ["listing_id"],
    )
    op.create_index(
        "ix_comparable_items_property",
        "comparable_items",
        ["property_id"],
    )

    op.create_table(
        "valuations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comparable_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fair_value_low", sa.Numeric(14, 2), nullable=True),
        sa.Column("fair_value_base", sa.Numeric(14, 2), nullable=True),
        sa.Column("fair_value_high", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("data_quality_at_analysis", sa.Numeric(5, 2), nullable=True),
        sa.Column("model_type", sa.String(length=40), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
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
        sa.CheckConstraint(_check_in("status", VALUATION_STATUSES), name="ck_valuations_status"),
        sa.CheckConstraint(_check_in("currency", CURRENCY_CODES), name="ck_valuations_currency"),
        sa.CheckConstraint(
            _check_in("model_type", VALUATION_MODEL_TYPES),
            name="ck_valuations_model_type",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["comparable_set_id"],
            ["comparable_sets.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_valuations_property_as_of",
        "valuations",
        ["property_id", "as_of"],
    )
    op.create_index("ix_valuations_status", "valuations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_valuations_status", table_name="valuations")
    op.drop_index("ix_valuations_property_as_of", table_name="valuations")
    op.drop_table("valuations")

    op.drop_index("ix_comparable_items_property", table_name="comparable_items")
    op.drop_index("ix_comparable_items_listing", table_name="comparable_items")
    op.drop_index("ix_comparable_items_set", table_name="comparable_items")
    op.drop_table("comparable_items")

    op.drop_index("ix_comparable_sets_property_as_of", table_name="comparable_sets")
    op.drop_table("comparable_sets")
