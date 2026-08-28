"""Add first-source ingestion persistence.

Revision ID: 0003_first_source_ingestion
Revises: 0002_core_domain_foundation
Create Date: 2026-08-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_first_source_ingestion"
down_revision = "0002_core_domain_foundation"
branch_labels = None
depends_on = None

FOUR_ZIDA_SOURCE_ID = "00000000-0000-0000-0000-000000000002"
RAW_RECORD_TYPES = ("CARD", "DETAIL")


def _check_in(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def upgrade() -> None:
    op.create_table(
        "listing_raw_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_type", sa.String(length=16), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            _check_in("record_type", RAW_RECORD_TYPES),
            name="ck_listing_raw_records_record_type",
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "listing_id",
            "record_type",
            "content_hash",
            name="uq_listing_raw_records_listing_type_hash",
        ),
    )
    op.create_index(
        "ix_listing_raw_records_listing_captured",
        "listing_raw_records",
        ["listing_id", "captured_at"],
    )

    job_metric_columns = (
        "pages_requested",
        "cards_seen",
        "cards_parsed",
        "new_listings",
        "changed_listings",
        "details_fetched",
        "parse_errors",
        "http_errors",
    )
    for column_name in job_metric_columns:
        op.add_column(
            "job_runs",
            sa.Column(
                column_name,
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    op.execute(
        f"""
        INSERT INTO sources (
            id,
            name,
            code,
            source_type,
            base_url,
            is_enabled,
            supports_discovery,
            supports_market_scan,
            supports_detail_fetch,
            supports_transaction_data
        )
        VALUES (
            '{FOUR_ZIDA_SOURCE_ID}',
            '4zida',
            'four_zida',
            'SCRAPED',
            'https://www.4zida.rs',
            true,
            true,
            true,
            true,
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
        WHERE code = 'four_zida'
        ON CONFLICT (source_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM source_runtime_state
        WHERE source_id IN (
            SELECT id
            FROM sources
            WHERE code = 'four_zida'
            AND NOT EXISTS (
                SELECT 1
                FROM listings
                WHERE listings.source_id = sources.id
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM sources
        WHERE code = 'four_zida'
        AND NOT EXISTS (
            SELECT 1
            FROM listings
            WHERE listings.source_id = sources.id
        )
        """
    )

    for column_name in (
        "http_errors",
        "parse_errors",
        "details_fetched",
        "changed_listings",
        "new_listings",
        "cards_parsed",
        "cards_seen",
        "pages_requested",
    ):
        op.drop_column("job_runs", column_name)

    op.drop_index("ix_listing_raw_records_listing_captured", table_name="listing_raw_records")
    op.drop_table("listing_raw_records")
