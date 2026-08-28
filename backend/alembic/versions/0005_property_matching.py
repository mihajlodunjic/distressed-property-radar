"""Add property resolution matching persistence.

Revision ID: 0005_property_matching
Revises: 0004_continuous_crawling_state
Create Date: 2026-08-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_property_matching"
down_revision = "0004_continuous_crawling_state"
branch_labels = None
depends_on = None

MATCH_DECISIONS = (
    "AUTO_MATCH",
    "MANUAL_MATCH",
    "POSSIBLE_MATCH",
    "REJECTED_MATCH",
)
MATCH_CANDIDATE_STATUSES = ("PENDING", "ACCEPTED", "REJECTED", "EXPIRED")


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def upgrade() -> None:
    op.create_table(
        "property_listing_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("match_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("matching_method", sa.String(length=100), nullable=False),
        sa.Column("matching_version", sa.String(length=100), nullable=False),
        sa.Column("reason_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            _check_in("decision", MATCH_DECISIONS),
            name="ck_property_listing_links_decision",
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "listing_id",
            "property_id",
            "decision",
            "matching_version",
            name="uq_property_listing_links_listing_property_decision_version",
        ),
    )
    op.create_index(
        "ix_property_listing_links_listing_created",
        "property_listing_links",
        ["listing_id", "created_at"],
    )
    op.create_index(
        "ix_property_listing_links_property_created",
        "property_listing_links",
        ["property_id", "created_at"],
    )

    op.create_table(
        "property_match_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("similarity_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("location_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("size_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("rooms_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("image_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("text_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("other_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("matching_version", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            _check_in("status", MATCH_CANDIDATE_STATUSES),
            name="ck_property_match_candidates_status",
        ),
        sa.ForeignKeyConstraint(["candidate_property_id"], ["properties.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "listing_id",
            "candidate_property_id",
            "matching_version",
            name="uq_property_match_candidates_listing_property_version",
        ),
    )
    op.create_index(
        "ix_property_match_candidates_listing_status",
        "property_match_candidates",
        ["listing_id", "status"],
    )
    op.create_index(
        "ix_property_match_candidates_candidate_status",
        "property_match_candidates",
        ["candidate_property_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_property_match_candidates_candidate_status",
        table_name="property_match_candidates",
    )
    op.drop_index(
        "ix_property_match_candidates_listing_status",
        table_name="property_match_candidates",
    )
    op.drop_table("property_match_candidates")

    op.drop_index(
        "ix_property_listing_links_property_created",
        table_name="property_listing_links",
    )
    op.drop_index(
        "ix_property_listing_links_listing_created",
        table_name="property_listing_links",
    )
    op.drop_table("property_listing_links")
