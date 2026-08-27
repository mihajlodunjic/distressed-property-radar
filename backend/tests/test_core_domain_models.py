from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import JobRun, Listing, ListingEvent, Property, Source, SourceRuntimeState
from app.domain.enums import (
    CurrencyCode,
    DataSourceKind,
    ListingEventType,
    ListingStatus,
    PropertyType,
    SellerType,
)


def create_source(session: Session, code: str) -> Source:
    source = Source(
        name=f"Source {code}",
        code=code,
        source_type=DataSourceKind.SCRAPED,
        base_url=f"https://example.test/{code}",
        is_enabled=True,
        supports_discovery=True,
        supports_market_scan=True,
        supports_detail_fetch=True,
        runtime_state=SourceRuntimeState(),
    )
    session.add(source)
    session.flush()
    return source


def test_phase1_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {
        "sources",
        "source_runtime_state",
        "properties",
        "listings",
        "listing_events",
        "job_runs",
    }.issubset(set(inspector.get_table_names()))


def test_manual_source_is_bootstrapped(db_session: Session) -> None:
    manual_source = db_session.scalars(select(Source).where(Source.code == "manual")).one()

    assert manual_source.name == "Manual"
    assert manual_source.source_type == DataSourceKind.MANUAL
    assert manual_source.runtime_state is not None


def test_create_phase1_records_and_read_back(db_session: Session) -> None:
    source = create_source(db_session, "phase1_readback")
    detected_at = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    started_at = datetime(2026, 8, 27, 12, 1, tzinfo=UTC)
    finished_at = datetime(2026, 8, 27, 12, 2, tzinfo=UTC)

    property_ = Property(
        property_type=PropertyType.APARTMENT,
        country_code="RS",
        city="Belgrade",
        municipality="Novi Beograd",
        size_m2=Decimal("52.40"),
        rooms=Decimal("2.00"),
        elevator=None,
    )
    listing = Listing(
        source=source,
        external_listing_id="listing-1",
        property=property_,
        url="https://example.test/listing-1",
        title="Apartment listing",
        asking_price=Decimal("125000.00"),
        currency=CurrencyCode.EUR,
        size_m2=Decimal("52.40"),
        price_per_m2=Decimal("2385.50"),
        seller_type=SellerType.AGENCY,
        status=ListingStatus.ACTIVE,
    )
    event = ListingEvent(
        listing=listing,
        event_type=ListingEventType.DISCOVERED,
        detected_at=detected_at,
        old_value_json=None,
        new_value_json={"status": "ACTIVE"},
    )
    job_run = JobRun(
        job_type="phase1_test",
        source=source,
        started_at=started_at,
        finished_at=finished_at,
        status="SUCCESS",
        items_discovered=1,
        items_processed=1,
        items_changed=1,
        items_failed=0,
    )

    db_session.add_all([property_, listing, event, job_run])
    db_session.commit()

    saved_listing = db_session.scalars(
        select(Listing).where(
            Listing.source_id == source.id,
            Listing.external_listing_id == "listing-1",
        )
    ).one()
    saved_event = db_session.scalars(
        select(ListingEvent).where(ListingEvent.listing_id == listing.id)
    ).one()
    saved_job = db_session.scalars(select(JobRun).where(JobRun.source_id == source.id)).one()

    assert saved_listing.property_id == property_.id
    assert saved_listing.asking_price == Decimal("125000.00")
    assert saved_listing.currency == CurrencyCode.EUR
    assert saved_listing.status == ListingStatus.ACTIVE
    assert saved_event.event_type == ListingEventType.DISCOVERED
    assert saved_event.new_value_json == {"status": "ACTIVE"}
    assert saved_event.detected_at.tzinfo is not None
    assert saved_job.items_processed == 1


def test_duplicate_source_listing_identity_is_rejected(db_session: Session) -> None:
    source = create_source(db_session, "phase1_duplicate")
    db_session.add(
        Listing(
            source=source,
            external_listing_id="same-id",
            status=ListingStatus.ACTIVE,
        )
    )
    db_session.flush()
    db_session.add(
        Listing(
            source=source,
            external_listing_id="same-id",
            status=ListingStatus.ACTIVE,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_external_listing_id_is_scoped_by_source(db_session: Session) -> None:
    source_a = create_source(db_session, "phase1_scope_a")
    source_b = create_source(db_session, "phase1_scope_b")
    listing_a = Listing(source=source_a, external_listing_id="same-id", status=ListingStatus.ACTIVE)
    listing_b = Listing(source=source_b, external_listing_id="same-id", status=ListingStatus.ACTIVE)

    db_session.add_all([listing_a, listing_b])
    db_session.commit()

    listings = db_session.scalars(
        select(Listing).where(Listing.external_listing_id == "same-id").order_by(Listing.source_id)
    ).all()

    assert len(listings) == 2
    assert {listing.source_id for listing in listings} == {source_a.id, source_b.id}


def test_nullable_unknown_semantics_preserve_none_vs_false(db_session: Session) -> None:
    source = create_source(db_session, "phase1_unknown")
    listing = Listing(
        source=source,
        external_listing_id="unknown-fields",
        elevator=None,
        parking=False,
        status=ListingStatus.UNKNOWN,
    )

    db_session.add(listing)
    db_session.commit()

    saved_listing = db_session.scalars(
        select(Listing).where(Listing.external_listing_id == "unknown-fields")
    ).one()

    assert saved_listing.elevator is None
    assert saved_listing.parking is False


def test_money_and_area_use_decimal_precision(db_session: Session) -> None:
    source = create_source(db_session, "phase1_decimal")
    listing = Listing(
        source=source,
        external_listing_id="decimal-listing",
        asking_price=Decimal("123456.78"),
        price_per_m2=Decimal("2345.67"),
        size_m2=Decimal("52.63"),
        currency=CurrencyCode.EUR,
        status=ListingStatus.ACTIVE,
    )

    db_session.add(listing)
    db_session.commit()

    saved_listing = db_session.scalars(
        select(Listing).where(Listing.external_listing_id == "decimal-listing")
    ).one()

    assert saved_listing.asking_price == Decimal("123456.78")
    assert saved_listing.price_per_m2 == Decimal("2345.67")
    assert saved_listing.size_m2 == Decimal("52.63")


@pytest.mark.parametrize(
    "status",
    [
        ListingStatus.ACTIVE,
        ListingStatus.NOT_SEEN,
        ListingStatus.REMOVED,
        ListingStatus.UNKNOWN,
    ],
)
def test_listing_lifecycle_status_values_are_supported(
    db_session: Session,
    status: ListingStatus,
) -> None:
    source = create_source(db_session, f"phase1_status_{status.value.lower()}")
    listing = Listing(
        source=source,
        external_listing_id=f"listing-{status.value.lower()}",
        status=status,
    )

    db_session.add(listing)
    db_session.commit()

    saved_listing = db_session.get(Listing, listing.id)

    assert saved_listing is not None
    assert saved_listing.status == status


def test_created_timestamp_is_timezone_aware(db_session: Session) -> None:
    source = create_source(db_session, "phase1_timestamp")
    listing = Listing(
        source=source,
        external_listing_id="timestamp-listing",
        status=ListingStatus.ACTIVE,
    )

    db_session.add(listing)
    db_session.commit()

    saved_listing = db_session.get(Listing, listing.id)

    assert saved_listing is not None
    assert saved_listing.created_at.tzinfo is not None
    assert saved_listing.first_seen_at.tzinfo is not None
    assert saved_listing.last_seen_at.tzinfo is not None
