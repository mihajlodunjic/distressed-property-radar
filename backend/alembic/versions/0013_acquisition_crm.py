"""Add acquisition CRM workflow tables.

Revision ID: 0013_acquisition_crm
Revises: 0012_watchlist_reanalysis
Create Date: 2026-08-29 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013_acquisition_crm"
down_revision = "0012_watchlist_reanalysis"
branch_labels = None
depends_on = None

PROPERTY_REVIEW_DECISIONS = ("INTERESTING", "NOT_INTERESTING", "UNSURE")
INTERACTION_TYPES = ("CALL", "MESSAGE", "VISIT", "DUE_DILIGENCE", "OFFER", "COUNTEROFFER", "OTHER")
ANALYSIS_LEVELS = ("LOW", "MEDIUM", "HIGH", "UNKNOWN")
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
CURRENCIES = ("EUR", "RSD")
OFFER_STATUSES = ("OPEN", "ACCEPTED", "REJECTED", "COUNTERED", "WITHDRAWN", "EXPIRED")
SKIP_REASON_CODES = (
    "OVERPRICED",
    "NO_MARGIN",
    "BAD_LEGAL",
    "LOW_LIQUIDITY",
    "BAD_LOCATION",
    "BAD_BUILDING",
    "HEAVY_RENOVATION",
    "SELLER_UNREALISTIC",
    "LOW_CONFIDENCE",
    "FAKE_LISTING",
    "OTHER",
)
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
DATA_SOURCE_KINDS = (
    "SCRAPED",
    "DERIVED",
    "LLM",
    "MANUAL",
    "VERIFIED_MANUAL",
    "TRANSACTION_DATA",
    "IMPORT",
)
PIPELINE_STATUSES = (
    "NEW",
    "REVIEWED",
    "CALLED",
    "VISIT_SCHEDULED",
    "VISITED",
    "DUE_DILIGENCE",
    "OFFERED",
    "NEGOTIATING",
    "WON",
    "LOST",
    "SKIPPED",
    "SOLD",
)


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def _nullable_check_in(column_name: str, values: tuple[str, ...]) -> str:
    return f"{column_name} IS NULL OR {_check_in(column_name, values)}"


def _non_negative(column_name: str) -> str:
    return f"{column_name} IS NULL OR {column_name} >= 0"


def _positive(column_name: str) -> str:
    return f"{column_name} > 0"


def _score_range(column_name: str) -> str:
    return f"{column_name} IS NULL OR ({column_name} >= 1 AND {column_name} <= 5)"


def _confidence_range(column_name: str) -> str:
    return f"{column_name} IS NULL OR ({column_name} >= 0 AND {column_name} <= 100)"


def upgrade() -> None:
    op.create_table(
        "property_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("manual_fmv", sa.Numeric(14, 2), nullable=True),
        sa.Column("manual_fast_sale_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("manual_max_buy_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            _check_in("decision", PROPERTY_REVIEW_DECISIONS),
            name="ck_property_reviews_decision",
        ),
        sa.CheckConstraint(_non_negative("manual_fmv"), name="ck_property_reviews_manual_fmv"),
        sa.CheckConstraint(
            _non_negative("manual_fast_sale_value"), name="ck_property_reviews_manual_fast_sale"
        ),
        sa.CheckConstraint(
            _non_negative("manual_max_buy_price"), name="ck_property_reviews_manual_max_buy"
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_property_reviews_property_reviewed",
        "property_reviews",
        ["property_id", "reviewed_at"],
    )

    op.create_table(
        "interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interaction_type", sa.String(length=24), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_notes", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("interaction_type", INTERACTION_TYPES),
            name="ck_interactions_interaction_type",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_interactions_property_occurred", "interactions", ["property_id", "occurred_at"]
    )
    op.create_index(
        "ix_interactions_type_occurred", "interactions", ["interaction_type", "occurred_at"]
    )

    op.create_table(
        "call_feedback",
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seller_motivation", sa.String(length=16), nullable=True),
        sa.Column("reason_for_sale", sa.String(length=40), nullable=True),
        sa.Column("lowest_indicated_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("cash_preferred", sa.Boolean(), nullable=True),
        sa.Column("desired_closing_days", sa.Integer(), nullable=True),
        sa.Column("viewing_available", sa.Boolean(), nullable=True),
        sa.Column("claimed_registered", sa.Boolean(), nullable=True),
        sa.Column("claimed_owner_1_1", sa.Boolean(), nullable=True),
        sa.Column("claimed_mortgage", sa.Boolean(), nullable=True),
        sa.Column("tenant_present", sa.Boolean(), nullable=True),
        sa.Column(
            "structured_notes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            _nullable_check_in("seller_motivation", ANALYSIS_LEVELS),
            name="ck_call_feedback_seller_motivation",
        ),
        sa.CheckConstraint(
            _nullable_check_in("reason_for_sale", REASONS_FOR_SALE),
            name="ck_call_feedback_reason_for_sale",
        ),
        sa.CheckConstraint(
            _non_negative("lowest_indicated_price"),
            name="ck_call_feedback_lowest_indicated_price",
        ),
        sa.CheckConstraint(
            _non_negative("desired_closing_days"),
            name="ck_call_feedback_desired_closing_days",
        ),
        sa.ForeignKeyConstraint(["interaction_id"], ["interactions.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "visit_feedback",
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("condition_category", sa.String(length=100), nullable=True),
        sa.Column("estimated_renovation_low", sa.Numeric(14, 2), nullable=True),
        sa.Column("estimated_renovation_base", sa.Numeric(14, 2), nullable=True),
        sa.Column("estimated_renovation_high", sa.Numeric(14, 2), nullable=True),
        sa.Column("layout_score", sa.Integer(), nullable=True),
        sa.Column("light_score", sa.Integer(), nullable=True),
        sa.Column("noise_score", sa.Integer(), nullable=True),
        sa.Column("building_score", sa.Integer(), nullable=True),
        sa.Column("entrance_score", sa.Integer(), nullable=True),
        sa.Column("parking_score", sa.Integer(), nullable=True),
        sa.Column("elevator_verified", sa.Boolean(), nullable=True),
        sa.Column(
            "visible_defects_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("manual_fmv", sa.Numeric(14, 2), nullable=True),
        sa.Column("manual_fast_sale_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("manual_max_buy_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            _non_negative("estimated_renovation_low"),
            name="ck_visit_feedback_renovation_low",
        ),
        sa.CheckConstraint(
            _non_negative("estimated_renovation_base"),
            name="ck_visit_feedback_renovation_base",
        ),
        sa.CheckConstraint(
            _non_negative("estimated_renovation_high"),
            name="ck_visit_feedback_renovation_high",
        ),
        sa.CheckConstraint(_score_range("layout_score"), name="ck_visit_feedback_layout_score"),
        sa.CheckConstraint(_score_range("light_score"), name="ck_visit_feedback_light_score"),
        sa.CheckConstraint(_score_range("noise_score"), name="ck_visit_feedback_noise_score"),
        sa.CheckConstraint(
            _score_range("building_score"),
            name="ck_visit_feedback_building_score",
        ),
        sa.CheckConstraint(
            _score_range("entrance_score"),
            name="ck_visit_feedback_entrance_score",
        ),
        sa.CheckConstraint(_score_range("parking_score"), name="ck_visit_feedback_parking_score"),
        sa.CheckConstraint(_non_negative("manual_fmv"), name="ck_visit_feedback_manual_fmv"),
        sa.CheckConstraint(
            _non_negative("manual_fast_sale_value"), name="ck_visit_feedback_manual_fast_sale"
        ),
        sa.CheckConstraint(
            _non_negative("manual_max_buy_price"), name="ck_visit_feedback_manual_max_buy"
        ),
        sa.ForeignKeyConstraint(["interaction_id"], ["interactions.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("offer_type", sa.String(length=40), nullable=True),
        sa.Column(
            "conditions_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("seller_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("counteroffer_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(_positive("amount"), name="ck_offers_amount_positive"),
        sa.CheckConstraint(_check_in("currency", CURRENCIES), name="ck_offers_currency"),
        sa.CheckConstraint(_check_in("status", OFFER_STATUSES), name="ck_offers_status"),
        sa.CheckConstraint(
            _non_negative("counteroffer_amount"), name="ck_offers_counteroffer_amount"
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_offers_property_offered", "offers", ["property_id", "offered_at"])
    op.create_index("ix_offers_status", "offers", ["status"])

    op.create_table(
        "skip_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            _check_in("reason_code", SKIP_REASON_CODES),
            name="ck_skip_records_reason_code",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_skip_records_property_skipped", "skip_records", ["property_id", "skipped_at"]
    )

    op.create_table(
        "property_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome_type", sa.String(length=32), nullable=False),
        sa.Column("outcome_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sale_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("source_kind", sa.String(length=32), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("outcome_type", PROPERTY_OUTCOME_TYPES),
            name="ck_property_outcomes_outcome_type",
        ),
        sa.CheckConstraint(
            _nullable_check_in("currency", CURRENCIES), name="ck_property_outcomes_currency"
        ),
        sa.CheckConstraint(_confidence_range("confidence"), name="ck_property_outcomes_confidence"),
        sa.CheckConstraint(
            _nullable_check_in("source_kind", DATA_SOURCE_KINDS),
            name="ck_property_outcomes_source_kind",
        ),
        sa.CheckConstraint(_non_negative("sale_price"), name="ck_property_outcomes_sale_price"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_property_outcomes_property_date",
        "property_outcomes",
        ["property_id", "outcome_date"],
    )

    op.create_table(
        "property_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
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
            _check_in("source_kind", ("MANUAL", "VERIFIED_MANUAL")),
            name="ck_property_overrides_source_kind_manual",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_property_overrides_property_field",
        "property_overrides",
        ["property_id", "field_name"],
    )

    op.create_table(
        "pipeline_status_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_status", sa.String(length=40), nullable=True),
        sa.Column("new_status", sa.String(length=40), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _nullable_check_in("old_status", PIPELINE_STATUSES),
            name="ck_pipeline_status_events_old_status",
        ),
        sa.CheckConstraint(
            _check_in("new_status", PIPELINE_STATUSES),
            name="ck_pipeline_status_events_new_status",
        ),
        sa.CheckConstraint(
            _check_in("source_kind", DATA_SOURCE_KINDS),
            name="ck_pipeline_status_events_source_kind",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_pipeline_status_events_property_occurred",
        "pipeline_status_events",
        ["property_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pipeline_status_events_property_occurred", table_name="pipeline_status_events"
    )
    op.drop_table("pipeline_status_events")
    op.drop_index("ix_property_overrides_property_field", table_name="property_overrides")
    op.drop_table("property_overrides")
    op.drop_index("ix_property_outcomes_property_date", table_name="property_outcomes")
    op.drop_table("property_outcomes")
    op.drop_index("ix_skip_records_property_skipped", table_name="skip_records")
    op.drop_table("skip_records")
    op.drop_index("ix_offers_status", table_name="offers")
    op.drop_index("ix_offers_property_offered", table_name="offers")
    op.drop_table("offers")
    op.drop_table("visit_feedback")
    op.drop_table("call_feedback")
    op.drop_index("ix_interactions_type_occurred", table_name="interactions")
    op.drop_index("ix_interactions_property_occurred", table_name="interactions")
    op.drop_table("interactions")
    op.drop_index("ix_property_reviews_property_reviewed", table_name="property_reviews")
    op.drop_table("property_reviews")
