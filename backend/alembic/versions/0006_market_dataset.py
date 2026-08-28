"""Add market dataset feature and quality tables.

Revision ID: 0006_market_dataset
Revises: 0005_property_matching
Create Date: 2026-08-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_market_dataset"
down_revision = "0005_property_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "property_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("price_per_m2", sa.Numeric(14, 2), nullable=True),
        sa.Column("listing_age_days", sa.Integer(), nullable=True),
        sa.Column("property_market_age_days", sa.Integer(), nullable=True),
        sa.Column(
            "active_listing_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("known_listing_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("relist_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("current_lowest_asking_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("current_highest_asking_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_price_drop_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column("price_drop_7d_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column("price_drop_30d_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column("price_cut_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("days_since_last_price_cut", sa.Integer(), nullable=True),
        sa.Column("largest_price_cut_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column(
            "owner_listing_present",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "agency_listing_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_version", sa.String(length=100), nullable=False),
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
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "property_id",
            "feature_version",
            name="uq_property_features_property_version",
        ),
    )
    op.create_index(
        "ix_property_features_property_computed",
        "property_features",
        ["property_id", "computed_at"],
    )

    op.create_table(
        "data_quality_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "missing_critical_fields_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "positive_factors_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("rules_version", sa.String(length=100), nullable=False),
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
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "property_id",
            "rules_version",
            name="uq_data_quality_assessments_property_rules",
        ),
    )
    op.create_index(
        "ix_data_quality_assessments_property_as_of",
        "data_quality_assessments",
        ["property_id", "as_of"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_data_quality_assessments_property_as_of",
        table_name="data_quality_assessments",
    )
    op.drop_table("data_quality_assessments")

    op.drop_index("ix_property_features_property_computed", table_name="property_features")
    op.drop_table("property_features")
