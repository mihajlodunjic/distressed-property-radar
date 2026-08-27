"""Create core database and domain foundation.

Revision ID: 0002_core_domain_foundation
Revises: 0001_enable_postgis
Create Date: 2026-08-27 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_core_domain_foundation"
down_revision = "0001_enable_postgis"
branch_labels = None
depends_on = None

MANUAL_SOURCE_ID = "00000000-0000-0000-0000-000000000001"

DATA_SOURCE_KINDS = (
    "SCRAPED",
    "DERIVED",
    "LLM",
    "MANUAL",
    "VERIFIED_MANUAL",
    "TRANSACTION_DATA",
    "IMPORT",
)
PROPERTY_TYPES = ("APARTMENT", "HOUSE", "LAND", "COMMERCIAL", "OTHER")
CURRENCY_CODES = ("EUR", "RSD")
LISTING_STATUSES = ("ACTIVE", "NOT_SEEN", "REMOVED", "UNKNOWN")
SELLER_TYPES = (
    "OWNER",
    "AGENCY",
    "INVESTOR",
    "BANK",
    "COURT_OR_ENFORCEMENT",
    "OTHER",
    "UNKNOWN",
)
PROPERTY_PIPELINE_STATUSES = (
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
LISTING_EVENT_TYPES = (
    "DISCOVERED",
    "PRICE_CHANGED",
    "TITLE_CHANGED",
    "DESCRIPTION_CHANGED",
    "SELLER_CHANGED",
    "STATUS_CHANGED",
    "REMOVED",
    "REAPPEARED",
    "DETAIL_CHANGED",
)


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "supports_discovery",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "supports_market_scan",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "supports_detail_fetch",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "supports_transaction_data",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
            _check_in("source_type", DATA_SOURCE_KINDS),
            name="ck_sources_source_type",
        ),
        sa.UniqueConstraint("code", name="uq_sources_code"),
    )

    op.create_table(
        "properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("property_type", sa.String(length=32), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("municipality", sa.String(length=120), nullable=True),
        sa.Column("neighborhood", sa.String(length=120), nullable=True),
        sa.Column("micro_location", sa.String(length=255), nullable=True),
        sa.Column("street", sa.String(length=255), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("location_precision", sa.String(length=50), nullable=True),
        sa.Column("location_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("size_m2", sa.Numeric(10, 2), nullable=True),
        sa.Column("rooms", sa.Numeric(5, 2), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("total_floors", sa.Integer(), nullable=True),
        sa.Column("elevator", sa.Boolean(), nullable=True),
        sa.Column("construction_year", sa.Integer(), nullable=True),
        sa.Column("building_type", sa.String(length=100), nullable=True),
        sa.Column("heating_type", sa.String(length=100), nullable=True),
        sa.Column("parking", sa.Boolean(), nullable=True),
        sa.Column("garage", sa.Boolean(), nullable=True),
        sa.Column("terrace", sa.Boolean(), nullable=True),
        sa.Column("condition_category", sa.String(length=100), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "active_listing_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("estimated_market_age_days", sa.Integer(), nullable=True),
        sa.Column("relist_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "pipeline_status",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'NEW'"),
        ),
        sa.Column("pipeline_status_updated_at", sa.DateTime(timezone=True), nullable=True),
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
            _check_in("property_type", PROPERTY_TYPES),
            name="ck_properties_property_type",
        ),
        sa.CheckConstraint(
            _check_in("pipeline_status", PROPERTY_PIPELINE_STATUSES),
            name="ck_properties_pipeline_status",
        ),
    )

    op.create_table(
        "source_runtime_state",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_discovery_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_market_scan_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.String(length=100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column(
            "recent_http_error_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "recent_parse_error_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_discovered_count", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_listing_id", sa.String(length=255), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("asking_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("size_m2", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_per_m2", sa.Numeric(14, 2), nullable=True),
        sa.Column("city_raw", sa.String(length=255), nullable=True),
        sa.Column("location_raw", sa.Text(), nullable=True),
        sa.Column("rooms", sa.Numeric(5, 2), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("total_floors", sa.Integer(), nullable=True),
        sa.Column("elevator", sa.Boolean(), nullable=True),
        sa.Column("construction_year", sa.Integer(), nullable=True),
        sa.Column("building_type", sa.String(length=100), nullable=True),
        sa.Column("heating_type", sa.String(length=100), nullable=True),
        sa.Column("parking", sa.Boolean(), nullable=True),
        sa.Column("garage", sa.Boolean(), nullable=True),
        sa.Column("terrace", sa.Boolean(), nullable=True),
        sa.Column("condition_raw", sa.String(length=255), nullable=True),
        sa.Column("legal_status_raw", sa.String(length=255), nullable=True),
        sa.Column(
            "seller_type",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'UNKNOWN'"),
        ),
        sa.Column("seller_name", sa.String(length=255), nullable=True),
        sa.Column("agency_name", sa.String(length=255), nullable=True),
        sa.Column("seller_phone", sa.String(length=100), nullable=True),
        sa.Column("seller_contact_raw", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'UNKNOWN'"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_detail_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_card_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("card_state_hash", sa.String(length=128), nullable=True),
        sa.Column("detail_state_hash", sa.String(length=128), nullable=True),
        sa.Column("llm_input_hash", sa.String(length=128), nullable=True),
        sa.Column("crawl_priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(_check_in("currency", CURRENCY_CODES), name="ck_listings_currency"),
        sa.CheckConstraint(_check_in("seller_type", SELLER_TYPES), name="ck_listings_seller_type"),
        sa.CheckConstraint(_check_in("status", LISTING_STATUSES), name="ck_listings_status"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "source_id",
            "external_listing_id",
            name="uq_listings_source_external_id",
        ),
    )

    op.create_table(
        "listing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("old_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("new_price", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("event_type", LISTING_EVENT_TYPES),
            name="ck_listing_events_event_type",
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("items_discovered", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_changed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_listings_property_id", "listings", ["property_id"])
    op.create_index("ix_listings_status", "listings", ["status"])
    op.create_index("ix_listings_next_check_at", "listings", ["next_check_at"])
    op.create_index("ix_listings_source_status", "listings", ["source_id", "status"])
    op.create_index("ix_listings_last_seen_at", "listings", ["last_seen_at"])

    op.create_index(
        "ix_listing_events_listing_detected",
        "listing_events",
        ["listing_id", "detected_at"],
    )
    op.create_index(
        "ix_listing_events_type_detected",
        "listing_events",
        ["event_type", "detected_at"],
    )

    op.create_index("ix_properties_property_type", "properties", ["property_type"])
    op.create_index("ix_properties_pipeline_status", "properties", ["pipeline_status"])
    op.create_index("ix_properties_city", "properties", ["city"])
    op.create_index("ix_properties_municipality", "properties", ["municipality"])
    op.create_index("ix_properties_micro_location", "properties", ["micro_location"])

    op.execute(
        f"""
        INSERT INTO sources (
            id,
            name,
            code,
            source_type,
            is_enabled,
            supports_discovery,
            supports_market_scan,
            supports_detail_fetch,
            supports_transaction_data
        )
        VALUES (
            '{MANUAL_SOURCE_ID}',
            'Manual',
            'manual',
            'MANUAL',
            true,
            false,
            false,
            false,
            false
        )
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO source_runtime_state (source_id)
        SELECT id
        FROM sources
        WHERE code = 'manual'
        ON CONFLICT (source_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_properties_micro_location", table_name="properties")
    op.drop_index("ix_properties_municipality", table_name="properties")
    op.drop_index("ix_properties_city", table_name="properties")
    op.drop_index("ix_properties_pipeline_status", table_name="properties")
    op.drop_index("ix_properties_property_type", table_name="properties")

    op.drop_index("ix_listing_events_type_detected", table_name="listing_events")
    op.drop_index("ix_listing_events_listing_detected", table_name="listing_events")

    op.drop_index("ix_listings_last_seen_at", table_name="listings")
    op.drop_index("ix_listings_source_status", table_name="listings")
    op.drop_index("ix_listings_next_check_at", table_name="listings")
    op.drop_index("ix_listings_status", table_name="listings")
    op.drop_index("ix_listings_property_id", table_name="listings")

    op.drop_table("job_runs")
    op.drop_table("listing_events")
    op.drop_table("listings")
    op.drop_table("source_runtime_state")
    op.drop_table("properties")
    op.drop_table("sources")
