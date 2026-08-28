from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import (
    DataQualityAssessment,
    Listing,
    ListingEvent,
    ListingRawRecord,
    Property,
    PropertyFeature,
    Source,
)
from app.domain.enums import (
    CurrencyCode,
    DataSourceKind,
    ListingEventType,
    ListingRawRecordType,
    ListingStatus,
    PropertyType,
    SellerType,
)
from app.features.property_dataset import (
    DATA_QUALITY_RULES_VERSION,
    FEATURE_VERSION,
    build_effective_property_data,
    recalculate_market_dataset,
    recalculate_property_market_dataset,
)

AS_OF = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def create_source(session: Session, code: str) -> Source:
    source = Source(
        name=f"Source {code}",
        code=code,
        source_type=DataSourceKind.SCRAPED,
        is_enabled=True,
        supports_discovery=True,
        supports_market_scan=True,
        supports_detail_fetch=True,
    )
    session.add(source)
    session.flush()
    return source


def create_property(session: Session, **overrides: object) -> Property:
    values = {
        "property_type": PropertyType.APARTMENT,
        "country_code": None,
        "city": None,
        "municipality": None,
        "neighborhood": None,
        "micro_location": None,
    }
    values.update(overrides)
    property_ = Property(**values)
    session.add(property_)
    session.flush()
    return property_


def create_listing(
    session: Session,
    source: Source,
    external_listing_id: str,
    property_: Property,
    **overrides: object,
) -> Listing:
    first_seen_at = overrides.pop("first_seen_at", AS_OF - timedelta(days=10))
    last_seen_at = overrides.pop("last_seen_at", AS_OF)
    values = {
        "source": source,
        "property": property_,
        "external_listing_id": external_listing_id,
        "url": f"https://example.test/{external_listing_id}",
        "canonical_url": f"https://example.test/{external_listing_id}",
        "title": "Apartment listing",
        "asking_price": Decimal("150000.00"),
        "currency": CurrencyCode.EUR,
        "city_raw": "Beograd",
        "location_raw": "Blok 45, Novi Beograd, Beograd",
        "status": ListingStatus.ACTIVE,
        "seller_type": SellerType.AGENCY,
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
    }
    values.update(overrides)
    listing = Listing(**values)
    session.add(listing)
    session.flush()
    return listing


def add_price_cut(
    session: Session,
    listing: Listing,
    *,
    days_ago: int,
    old_price: str,
    new_price: str,
) -> ListingEvent:
    event = ListingEvent(
        listing=listing,
        event_type=ListingEventType.PRICE_CHANGED,
        detected_at=AS_OF - timedelta(days=days_ago),
        old_price=Decimal(old_price),
        new_price=Decimal(new_price),
        old_value_json={"asking_price": old_price},
        new_value_json={"asking_price": new_price},
    )
    session.add(event)
    session.flush()
    return event


def add_detail_raw_record(
    session: Session,
    listing: Listing,
    *,
    image_urls: list[str] | None = None,
) -> ListingRawRecord:
    raw_record = ListingRawRecord(
        listing=listing,
        record_type=ListingRawRecordType.DETAIL,
        source_url=listing.canonical_url,
        raw_payload={"image_urls": image_urls or []},
        content_type="application/json",
        content_hash=f"detail-{listing.external_listing_id}",
        parser_version="test_parser_v1",
        captured_at=AS_OF,
    )
    session.add(raw_record)
    session.flush()
    return raw_record


def count_rows(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_phase5_market_dataset_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {
        "property_features",
        "data_quality_assessments",
    }.issubset(set(inspector.get_table_names()))


def test_location_normalization_updates_existing_matched_property(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase5_location")
    property_ = create_property(
        db_session,
        latitude=Decimal("44.805100"),
        longitude=Decimal("20.400200"),
    )
    create_listing(
        db_session,
        source,
        "phase5-location-listing",
        property_,
        location_raw="Blok 45, Novi Beograd, Beograd",
        title="Stan u Bloku 45",
    )

    result = recalculate_property_market_dataset(db_session, property_, as_of=AS_OF)

    assert property_.country_code == "RS"
    assert property_.city == "Beograd"
    assert property_.municipality == "Novi Beograd"
    assert property_.neighborhood == "Blok 45"
    assert property_.micro_location == "Blok 45"
    assert property_.location_precision == "MICROZONE"
    assert property_.location_confidence == Decimal("0.9000")
    assert result.effective_data.latitude == Decimal("44.805100")
    assert result.effective_data.longitude == Decimal("20.400200")
    assert result.effective_data.provenance["city"] == "property"
    assert result.effective_data.provenance["micro_location"] == "property"
    assert result.effective_data.provenance["latitude"] == "property"


def test_market_features_keep_property_market_age_across_relisted_listing(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase5_features")
    property_ = create_property(db_session, size_m2=Decimal("72.00"))
    first_listing = create_listing(
        db_session,
        source,
        "phase5-first-listing",
        property_,
        asking_price=Decimal("180000.00"),
        first_seen_at=AS_OF - timedelta(days=70),
    )
    create_listing(
        db_session,
        source,
        "phase5-relisted-listing",
        property_,
        asking_price=Decimal("182000.00"),
        first_seen_at=AS_OF - timedelta(days=20),
    )
    add_price_cut(
        db_session,
        first_listing,
        days_ago=40,
        old_price="200000.00",
        new_price="190000.00",
    )
    add_price_cut(
        db_session,
        first_listing,
        days_ago=30,
        old_price="190000.00",
        new_price="180000.00",
    )

    result = recalculate_property_market_dataset(db_session, property_, as_of=AS_OF)
    feature = result.feature

    assert feature.feature_version == FEATURE_VERSION
    assert feature.price_per_m2 == Decimal("2500.00")
    assert feature.listing_age_days == 20
    assert feature.property_market_age_days == 70
    assert feature.active_listing_count == 2
    assert feature.known_listing_count == 2
    assert feature.relist_count == 1
    assert feature.current_lowest_asking_price == Decimal("180000.00")
    assert feature.current_highest_asking_price == Decimal("182000.00")
    assert feature.price_cut_count == 2
    assert feature.total_price_drop_pct == Decimal("10.0000")
    assert feature.price_drop_30d_pct == Decimal("5.2632")
    assert feature.days_since_last_price_cut == 30
    assert feature.largest_price_cut_pct == Decimal("5.2632")
    assert property_.first_seen_at == AS_OF - timedelta(days=70)
    assert property_.active_listing_count == 2
    assert property_.relist_count == 1


def test_effective_property_data_prefers_property_values_and_fills_unknowns(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase5_effective")
    property_ = create_property(
        db_session,
        size_m2=Decimal("70.00"),
        rooms=None,
        condition_category=None,
    )
    create_listing(
        db_session,
        source,
        "phase5-effective-listing",
        property_,
        size_m2=Decimal("72.00"),
        rooms=Decimal("3.00"),
        condition_raw="renovated",
    )

    effective_data = build_effective_property_data(db_session, property_)

    assert effective_data.size_m2 == Decimal("70.00")
    assert effective_data.rooms == Decimal("3.00")
    assert effective_data.condition_category == "renovated"
    assert effective_data.provenance["size_m2"] == "property"
    assert effective_data.provenance["rooms"].startswith("listing:")
    assert effective_data.provenance["condition_category"].startswith("listing:")

    recalculate_property_market_dataset(db_session, property_, as_of=AS_OF)

    assert property_.size_m2 == Decimal("70.00")
    assert property_.rooms == Decimal("3.00")
    assert property_.condition_category == "renovated"


def test_data_quality_scores_known_fields_and_reports_critical_missing_fields(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase5_quality")
    high_quality_property = create_property(
        db_session,
        size_m2=Decimal("64.00"),
        rooms=Decimal("2.00"),
        floor=6,
        total_floors=12,
        elevator=True,
        construction_year=2012,
        building_type="newer_building",
        heating_type="central",
        parking=True,
        condition_category="renovated",
    )
    high_quality_listing = create_listing(
        db_session,
        source,
        "phase5-high-quality-listing",
        high_quality_property,
        description=(
            "Bright apartment with organized rooms, maintained building, clear legal notes, "
            "and enough structured detail for a practical comparable analysis."
        ),
        legal_status_raw="registered",
    )
    add_detail_raw_record(
        db_session,
        high_quality_listing,
        image_urls=["https://example.test/image-1.jpg"],
    )

    low_quality_property = create_property(db_session, city="Beograd")
    create_listing(
        db_session,
        source,
        "phase5-low-quality-listing",
        low_quality_property,
        location_raw="Beograd",
        size_m2=None,
        rooms=None,
        floor=None,
        elevator=None,
        condition_raw=None,
    )

    high_quality = recalculate_property_market_dataset(
        db_session,
        high_quality_property,
        as_of=AS_OF,
    ).data_quality
    low_quality = recalculate_property_market_dataset(
        db_session,
        low_quality_property,
        as_of=AS_OF,
    ).data_quality

    assert high_quality.rules_version == DATA_QUALITY_RULES_VERSION
    assert high_quality.score == Decimal("100.00")
    assert high_quality.missing_critical_fields_json == []
    assert high_quality.positive_factors_json["rules_version"] == DATA_QUALITY_RULES_VERSION
    assert low_quality.score < high_quality.score
    assert "usable_micro_location" in low_quality.missing_critical_fields_json
    assert "size_m2" in low_quality.missing_critical_fields_json
    assert "condition" in low_quality.missing_critical_fields_json


def test_recalculation_updates_existing_feature_and_quality_rows(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase5_recalculate")
    property_ = create_property(db_session, size_m2=Decimal("60.00"))
    listing = create_listing(
        db_session,
        source,
        "phase5-recalculate-listing",
        property_,
        asking_price=Decimal("150000.00"),
    )

    first = recalculate_property_market_dataset(db_session, property_, as_of=AS_OF)
    feature_id = first.feature.id
    assessment_id = first.data_quality.id

    add_price_cut(
        db_session,
        listing,
        days_ago=3,
        old_price="150000.00",
        new_price="145000.00",
    )
    listing.asking_price = Decimal("145000.00")
    property_.condition_category = "renovated"

    second = recalculate_property_market_dataset(db_session, property_, as_of=AS_OF)

    assert second.feature.id == feature_id
    assert second.data_quality.id == assessment_id
    assert count_rows(db_session, PropertyFeature) == 1
    assert count_rows(db_session, DataQualityAssessment) == 1
    assert second.feature.price_cut_count == 1
    assert second.feature.price_per_m2 == Decimal("2416.67")
    assert second.data_quality.missing_critical_fields_json == []


def test_batch_recalculation_processes_existing_properties(db_session: Session) -> None:
    source = create_source(db_session, "phase5_batch")
    property_ = create_property(db_session)
    create_listing(db_session, source, "phase5-batch-listing", property_)

    summary = recalculate_market_dataset(db_session, as_of=AS_OF)

    assert summary.processed == 1
    assert count_rows(db_session, PropertyFeature) == 1
    assert count_rows(db_session, DataQualityAssessment) == 1
    assert property_.micro_location == "Blok 45"
