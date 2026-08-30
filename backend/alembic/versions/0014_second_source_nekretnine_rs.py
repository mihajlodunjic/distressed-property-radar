"""Add Nekretnine.rs source.

Revision ID: 0014_second_source_nekretnine_rs
Revises: 0013_acquisition_crm
Create Date: 2026-08-30 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "0014_second_source_nekretnine_rs"
down_revision = "0013_acquisition_crm"
branch_labels = None
depends_on = None

NEKRETNINE_RS_SOURCE_ID = "00000000-0000-0000-0000-000000000003"


def upgrade() -> None:
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
            '{NEKRETNINE_RS_SOURCE_ID}',
            'Nekretnine.rs',
            'nekretnine_rs',
            'SCRAPED',
            'https://www.nekretnine.rs',
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
        WHERE code = 'nekretnine_rs'
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
            WHERE code = 'nekretnine_rs'
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
        WHERE code = 'nekretnine_rs'
        AND NOT EXISTS (
            SELECT 1
            FROM listings
            WHERE listings.source_id = sources.id
        )
        """
    )
