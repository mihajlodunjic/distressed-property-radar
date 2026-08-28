from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import (
    Listing,
    Property,
    PropertyListingLink,
    PropertyMatchCandidate,
    Source,
    SourceRuntimeState,
)
from app.domain.enums import (
    CurrencyCode,
    DataSourceKind,
    ListingStatus,
    MatchCandidateStatus,
    MatchDecision,
    PropertyType,
    SellerType,
)
from app.matching.property_resolution import (
    MATCHING_VERSION,
    manually_match_listing_to_property,
    reject_match_candidate,
    resolve_listing_to_property,
    resolve_listings_to_properties,
)


def create_source(session: Session, code: str = "matching_source") -> Source:
    source = Source(
        name=f"Source {code}",
        code=code,
        source_type=DataSourceKind.SCRAPED,
        is_enabled=True,
        supports_discovery=True,
        supports_market_scan=True,
        supports_detail_fetch=True,
        runtime_state=SourceRuntimeState(),
    )
    session.add(source)
    session.flush()
    return source


def create_listing(
    session: Session,
    source: Source,
    external_listing_id: str,
    *,
    location: str,
    size_m2: str,
    rooms: str,
    floor: int | None,
    title: str | None = None,
    first_seen_offset_days: int = 0,
) -> Listing:
    seen_at = datetime(2026, 8, 28, 12, 0, tzinfo=UTC) + timedelta(days=first_seen_offset_days)
    listing = Listing(
        source=source,
        external_listing_id=external_listing_id,
        url=f"https://example.test/{external_listing_id}",
        canonical_url=f"https://example.test/{external_listing_id}",
        title=title or location,
        asking_price=Decimal("150000.00"),
        currency=CurrencyCode.EUR,
        size_m2=Decimal(size_m2),
        rooms=Decimal(rooms),
        city_raw="Belgrade",
        location_raw=location,
        floor=floor,
        seller_type=SellerType.AGENCY,
        status=ListingStatus.ACTIVE,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
    )
    session.add(listing)
    session.flush()
    return listing


def create_property(
    session: Session,
    *,
    micro_location: str,
    size_m2: str,
    rooms: str,
    floor: int | None,
) -> Property:
    property_ = Property(
        property_type=PropertyType.APARTMENT,
        country_code="RS",
        city="Belgrade",
        municipality="Palilula",
        micro_location=micro_location,
        size_m2=Decimal(size_m2),
        rooms=Decimal(rooms),
        floor=floor,
    )
    session.add(property_)
    session.flush()
    return property_


def count_rows(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_phase4_matching_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {
        "property_listing_links",
        "property_match_candidates",
    }.issubset(set(inspector.get_table_names()))


def test_obvious_duplicate_listings_auto_match_to_one_property_idempotently(
    db_session: Session,
) -> None:
    source = create_source(db_session, "matching_obvious")
    listing_a = create_listing(
        db_session,
        source,
        "listing-a",
        location="Takovska 10, Palilula",
        size_m2="72.00",
        rooms="3.00",
        floor=2,
    )
    listing_b = create_listing(
        db_session,
        source,
        "listing-b",
        location="Takovska 10, Palilula",
        size_m2="72.00",
        rooms="3.00",
        floor=2,
        title="Takovska 10 apartment",
        first_seen_offset_days=1,
    )

    first = resolve_listing_to_property(db_session, listing_a)
    second = resolve_listing_to_property(db_session, listing_b)
    link_count = count_rows(db_session, PropertyListingLink)
    candidate_count = count_rows(db_session, PropertyMatchCandidate)
    property_count = count_rows(db_session, Property)

    rerun_first = resolve_listing_to_property(db_session, listing_a)
    rerun_second = resolve_listing_to_property(db_session, listing_b)

    assert first.action == "NEW_PROPERTY"
    assert second.action == "AUTO_MATCH"
    assert listing_a.property_id == listing_b.property_id
    assert count_rows(db_session, Listing) == 2
    assert count_rows(db_session, Property) == property_count == 1
    assert count_rows(db_session, PropertyListingLink) == link_count == 2
    assert count_rows(db_session, PropertyMatchCandidate) == candidate_count == 1
    assert rerun_first.action == "EXISTING_LINK"
    assert rerun_second.action == "EXISTING_LINK"

    property_ = db_session.get(Property, listing_a.property_id)
    assert property_ is not None
    assert property_.active_listing_count == 2
    assert property_.relist_count == 1


def test_batch_resolution_is_idempotent_for_duplicate_listings(db_session: Session) -> None:
    source = create_source(db_session, "matching_batch")
    create_listing(
        db_session,
        source,
        "batch-listing-a",
        location="Gandijeva 44, Novi Beograd",
        size_m2="64.00",
        rooms="2.00",
        floor=6,
    )
    create_listing(
        db_session,
        source,
        "batch-listing-b",
        location="Gandijeva 44, Novi Beograd",
        size_m2="64.00",
        rooms="2.00",
        floor=6,
    )

    first_summary = resolve_listings_to_properties(db_session)
    second_summary = resolve_listings_to_properties(db_session)

    assert first_summary.processed == 2
    assert first_summary.new_properties == 1
    assert first_summary.auto_matched == 1
    assert second_summary.processed == 2
    assert second_summary.existing_links == 2
    assert count_rows(db_session, Property) == 1
    assert count_rows(db_session, PropertyListingLink) == 2
    assert count_rows(db_session, PropertyMatchCandidate) == 1


def test_ambiguous_candidate_is_left_pending_without_canonical_link(
    db_session: Session,
) -> None:
    source = create_source(db_session, "matching_ambiguous")
    property_ = create_property(
        db_session,
        micro_location="Bircaninova 15, Savski Venac",
        size_m2="72.00",
        rooms="3.00",
        floor=None,
    )
    listing = create_listing(
        db_session,
        source,
        "ambiguous-listing",
        location="Bircaninova 15, Savski Venac",
        size_m2="73.00",
        rooms="3.00",
        floor=None,
    )

    result = resolve_listing_to_property(db_session, listing)

    candidate = db_session.scalars(select(PropertyMatchCandidate)).one()
    assert result.action == "POSSIBLE_MATCH"
    assert listing.property_id is None
    assert candidate.listing_id == listing.id
    assert candidate.candidate_property_id == property_.id
    assert candidate.status == MatchCandidateStatus.PENDING
    assert count_rows(db_session, PropertyListingLink) == 0


def test_obvious_non_match_creates_new_property_and_records_rejected_candidate(
    db_session: Session,
) -> None:
    source = create_source(db_session, "matching_non_match")
    existing_property = create_property(
        db_session,
        micro_location="Takovska 10, Palilula",
        size_m2="95.00",
        rooms="4.00",
        floor=8,
    )
    listing = create_listing(
        db_session,
        source,
        "non-match-listing",
        location="Takovska 10, Palilula",
        size_m2="72.00",
        rooms="3.00",
        floor=2,
    )

    result = resolve_listing_to_property(db_session, listing)

    candidate = db_session.scalars(select(PropertyMatchCandidate)).one()
    assert result.action == "NEW_PROPERTY"
    assert listing.property_id is not None
    assert listing.property_id != existing_property.id
    assert candidate.status == MatchCandidateStatus.REJECTED
    assert candidate.candidate_property_id == existing_property.id
    assert count_rows(db_session, Property) == 2
    assert count_rows(db_session, Listing) == 1


def test_manual_match_precedence_blocks_automatic_reassignment(db_session: Session) -> None:
    source = create_source(db_session, "matching_manual")
    manual_property = create_property(
        db_session,
        micro_location="Manual confirmed address",
        size_m2="80.00",
        rooms="3.00",
        floor=5,
    )
    automatic_candidate = create_property(
        db_session,
        micro_location="Njegoseva 20, Vracar",
        size_m2="72.00",
        rooms="3.00",
        floor=2,
    )
    listing = create_listing(
        db_session,
        source,
        "manual-listing",
        location="Njegoseva 20, Vracar",
        size_m2="72.00",
        rooms="3.00",
        floor=2,
    )

    automatic = resolve_listing_to_property(db_session, listing)
    manual_link = manually_match_listing_to_property(
        db_session,
        listing=listing,
        property_=manual_property,
    )
    link_count = count_rows(db_session, PropertyListingLink)
    result = resolve_listing_to_property(db_session, listing)

    assert automatic.action == "AUTO_MATCH"
    assert automatic.property_id == str(automatic_candidate.id)
    assert manual_link.decision == MatchDecision.MANUAL_MATCH
    assert result.action == "MANUAL_PRESERVED"
    assert listing.property_id == manual_property.id
    assert count_rows(db_session, PropertyListingLink) == link_count == 2
    assert db_session.scalars(
        select(PropertyListingLink).where(
            PropertyListingLink.property_id == automatic_candidate.id,
            PropertyListingLink.decision == MatchDecision.AUTO_MATCH,
        )
    ).one()


def test_rejected_candidate_is_not_recreated_as_pending_on_rerun(
    db_session: Session,
) -> None:
    source = create_source(db_session, "matching_rejected")
    candidate_property = create_property(
        db_session,
        micro_location="Kralja Milana 30, Stari Grad",
        size_m2="72.00",
        rooms="3.00",
        floor=None,
    )
    listing = create_listing(
        db_session,
        source,
        "rejected-listing",
        location="Kralja Milana 30, Stari Grad",
        size_m2="73.00",
        rooms="3.00",
        floor=None,
    )
    possible = resolve_listing_to_property(db_session, listing)
    candidate = db_session.scalars(select(PropertyMatchCandidate)).one()

    reject_match_candidate(db_session, candidate=candidate)
    after_reject = resolve_listing_to_property(db_session, listing)
    link_count = count_rows(db_session, PropertyListingLink)
    candidate_count = count_rows(db_session, PropertyMatchCandidate)
    after_link = resolve_listing_to_property(db_session, listing)

    candidate = db_session.scalars(select(PropertyMatchCandidate)).one()
    assert possible.action == "POSSIBLE_MATCH"
    assert after_reject.action == "NEW_PROPERTY"
    assert after_link.action == "EXISTING_LINK"
    assert listing.property_id is not None
    assert listing.property_id != candidate_property.id
    assert candidate.status == MatchCandidateStatus.REJECTED
    assert candidate.candidate_property_id == candidate_property.id
    assert count_rows(db_session, PropertyMatchCandidate) == candidate_count == 1
    assert count_rows(db_session, PropertyListingLink) == link_count == 1
    assert candidate.matching_version == MATCHING_VERSION
