from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    DataQualityAssessment,
    Listing,
    ListingEvent,
    Property,
    PropertyFeature,
)
from app.domain.enums import (
    ListingEventType,
    ListingRawRecordType,
    ListingStatus,
    SellerType,
)
from app.locations.normalization import NormalizedLocation, normalize_location_text

FEATURE_VERSION = "property_features_v1"
DATA_QUALITY_RULES_VERSION = "data_quality_v1"
EFFECTIVE_DATA_VERSION = "effective_property_data_v1"

PERCENT_QUANTIZER = Decimal("0.0001")
MONEY_QUANTIZER = Decimal("0.01")
QUALITY_QUANTIZER = Decimal("0.01")

DATA_QUALITY_WEIGHTS: dict[str, int] = {
    "location_precision": 20,
    "size": 15,
    "rooms": 10,
    "floor": 8,
    "elevator": 7,
    "building_type": 7,
    "condition": 10,
    "heating": 4,
    "parking": 4,
    "construction_year": 3,
    "description_quality": 5,
    "images": 4,
    "legal_claims": 3,
}


@dataclass(frozen=True)
class EffectivePropertyData:
    property_id: str
    property_type: str
    country_code: str | None
    city: str | None
    municipality: str | None
    neighborhood: str | None
    micro_location: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    location_precision: str | None
    location_confidence: Decimal | None
    size_m2: Decimal | None
    rooms: Decimal | None
    bedrooms: int | None
    floor: int | None
    total_floors: int | None
    elevator: bool | None
    building_type: str | None
    heating_type: str | None
    parking: bool | None
    construction_year: int | None
    condition_category: str | None
    description: str | None
    legal_status_raw: str | None
    has_images: bool
    seller_type: str | None
    provenance: dict[str, str]
    version: str = EFFECTIVE_DATA_VERSION


@dataclass(frozen=True)
class MarketDatasetResult:
    property_id: str
    effective_data: EffectivePropertyData
    feature: PropertyFeature
    data_quality: DataQualityAssessment


@dataclass
class MarketDatasetSummary:
    processed: int = 0


def recalculate_market_dataset(
    session: Session,
    *,
    limit: int | None = None,
    as_of: datetime | None = None,
    commit: bool = False,
) -> MarketDatasetSummary:
    stmt = select(Property).order_by(Property.created_at, Property.id)
    if limit is not None:
        stmt = stmt.limit(limit)
    properties = session.scalars(stmt).all()

    summary = MarketDatasetSummary()
    for property_ in properties:
        recalculate_property_market_dataset(session, property_, as_of=as_of)
        summary.processed += 1

    if commit:
        session.commit()
    return summary


def recalculate_property_market_dataset(
    session: Session,
    property_: Property,
    *,
    as_of: datetime | None = None,
    feature_version: str = FEATURE_VERSION,
    data_quality_rules_version: str = DATA_QUALITY_RULES_VERSION,
    commit: bool = False,
) -> MarketDatasetResult:
    effective_as_of = as_of or _utcnow()
    linked_listings = _linked_listings(session, property_)
    normalized_location = _normalize_and_apply_property_location(property_, linked_listings)
    effective_data = build_effective_property_data(
        session,
        property_,
        linked_listings=linked_listings,
        normalized_location=normalized_location,
    )
    _fill_property_unknowns_from_effective(property_, effective_data)
    _refresh_property_summary(property_, linked_listings)

    feature = upsert_property_features(
        session,
        property_,
        linked_listings=linked_listings,
        effective_data=effective_data,
        as_of=effective_as_of,
        feature_version=feature_version,
    )
    data_quality = upsert_data_quality_assessment(
        session,
        property_,
        effective_data=effective_data,
        as_of=effective_as_of,
        rules_version=data_quality_rules_version,
    )
    if commit:
        session.commit()
    return MarketDatasetResult(
        property_id=str(property_.id),
        effective_data=effective_data,
        feature=feature,
        data_quality=data_quality,
    )


def build_effective_property_data(
    session: Session,
    property_: Property,
    *,
    linked_listings: list[Listing] | None = None,
    normalized_location: NormalizedLocation | None = None,
) -> EffectivePropertyData:
    listings = (
        linked_listings if linked_listings is not None else _linked_listings(session, property_)
    )
    location = normalized_location or _normalize_and_apply_property_location(property_, listings)

    provenance: dict[str, str] = {}
    description, description_source = _best_text(listings, "description")
    legal_status_raw, legal_source = _best_text(listings, "legal_status_raw")
    seller_type, seller_source = _best_seller_type(listings)
    has_images = _has_images(listings)

    values: dict[str, tuple[Any, str | None]] = {
        "country_code": _property_or_location(property_.country_code, location.country_code),
        "city": _property_or_location(property_.city, location.city),
        "municipality": _property_or_location(property_.municipality, location.municipality),
        "neighborhood": _property_or_location(property_.neighborhood, location.neighborhood),
        "micro_location": _property_or_location(property_.micro_location, location.micro_location),
        "latitude": _property_or_existing(property_.latitude),
        "longitude": _property_or_existing(property_.longitude),
        "location_precision": _property_or_location(
            property_.location_precision,
            location.location_precision,
        ),
        "location_confidence": _property_or_location(
            property_.location_confidence,
            location.location_confidence,
        ),
        "size_m2": _property_or_listing(property_, listings, "size_m2"),
        "rooms": _property_or_listing(property_, listings, "rooms"),
        "bedrooms": _property_or_listing(property_, listings, "bedrooms"),
        "floor": _property_or_listing(property_, listings, "floor"),
        "total_floors": _property_or_listing(property_, listings, "total_floors"),
        "elevator": _property_or_listing(property_, listings, "elevator"),
        "building_type": _property_or_listing(property_, listings, "building_type"),
        "heating_type": _property_or_listing(property_, listings, "heating_type"),
        "parking": _property_or_listing(property_, listings, "parking"),
        "construction_year": _property_or_listing(property_, listings, "construction_year"),
        "condition_category": _property_or_listing(
            property_,
            listings,
            "condition_category",
            listing_field_name="condition_raw",
        ),
    }
    for field_name, (_value, source) in values.items():
        if source is not None:
            provenance[field_name] = source
    if description_source is not None:
        provenance["description"] = description_source
    if legal_source is not None:
        provenance["legal_status_raw"] = legal_source
    if seller_source is not None:
        provenance["seller_type"] = seller_source
    if has_images:
        provenance["has_images"] = "listing_raw_records"

    return EffectivePropertyData(
        property_id=str(property_.id),
        property_type=property_.property_type.value,
        country_code=values["country_code"][0],
        city=values["city"][0],
        municipality=values["municipality"][0],
        neighborhood=values["neighborhood"][0],
        micro_location=values["micro_location"][0],
        latitude=values["latitude"][0],
        longitude=values["longitude"][0],
        location_precision=values["location_precision"][0],
        location_confidence=values["location_confidence"][0],
        size_m2=values["size_m2"][0],
        rooms=values["rooms"][0],
        bedrooms=values["bedrooms"][0],
        floor=values["floor"][0],
        total_floors=values["total_floors"][0],
        elevator=values["elevator"][0],
        building_type=values["building_type"][0],
        heating_type=values["heating_type"][0],
        parking=values["parking"][0],
        construction_year=values["construction_year"][0],
        condition_category=values["condition_category"][0],
        description=description,
        legal_status_raw=legal_status_raw,
        has_images=has_images,
        seller_type=seller_type.value if seller_type is not None else None,
        provenance=provenance,
    )


def upsert_property_features(
    session: Session,
    property_: Property,
    *,
    linked_listings: list[Listing],
    effective_data: EffectivePropertyData,
    as_of: datetime,
    feature_version: str = FEATURE_VERSION,
) -> PropertyFeature:
    values = _feature_values(
        session,
        property_,
        linked_listings=linked_listings,
        effective_data=effective_data,
        as_of=as_of,
    )
    feature = session.scalars(
        select(PropertyFeature).where(
            PropertyFeature.property_id == property_.id,
            PropertyFeature.feature_version == feature_version,
        )
    ).one_or_none()
    if feature is None:
        feature = PropertyFeature(
            property=property_,
            feature_version=feature_version,
            computed_at=as_of,
        )
        session.add(feature)
        session.flush()

    for field_name, value in values.items():
        setattr(feature, field_name, value)
    feature.computed_at = as_of
    feature.feature_version = feature_version
    return feature


def upsert_data_quality_assessment(
    session: Session,
    property_: Property,
    *,
    effective_data: EffectivePropertyData,
    as_of: datetime,
    rules_version: str = DATA_QUALITY_RULES_VERSION,
) -> DataQualityAssessment:
    score, missing_critical_fields, positive_factors = assess_data_quality(
        effective_data,
        rules_version=rules_version,
    )
    assessment = session.scalars(
        select(DataQualityAssessment).where(
            DataQualityAssessment.property_id == property_.id,
            DataQualityAssessment.rules_version == rules_version,
        )
    ).one_or_none()
    if assessment is None:
        assessment = DataQualityAssessment(
            property=property_,
            rules_version=rules_version,
            as_of=as_of,
            score=score,
            missing_critical_fields_json=missing_critical_fields,
            positive_factors_json=positive_factors,
        )
        session.add(assessment)
        session.flush()
        return assessment

    assessment.as_of = as_of
    assessment.score = score
    assessment.missing_critical_fields_json = missing_critical_fields
    assessment.positive_factors_json = positive_factors
    return assessment


def assess_data_quality(
    effective_data: EffectivePropertyData,
    *,
    rules_version: str = DATA_QUALITY_RULES_VERSION,
) -> tuple[Decimal, list[str], dict[str, object]]:
    factors: dict[str, Decimal] = {}
    factors["location_precision"] = _location_quality_points(effective_data)
    factors["size"] = _points_if_known(effective_data.size_m2, "size")
    factors["rooms"] = _points_if_known(effective_data.rooms, "rooms")
    factors["floor"] = _points_if_known(effective_data.floor, "floor")
    factors["elevator"] = _points_if_known(effective_data.elevator, "elevator")
    factors["building_type"] = _points_if_text(effective_data.building_type, "building_type")
    factors["condition"] = _points_if_text(effective_data.condition_category, "condition")
    factors["heating"] = _points_if_text(effective_data.heating_type, "heating")
    factors["parking"] = _points_if_known(effective_data.parking, "parking")
    factors["construction_year"] = _points_if_known(
        effective_data.construction_year,
        "construction_year",
    )
    factors["description_quality"] = _description_points(effective_data.description)
    factors["images"] = (
        Decimal(DATA_QUALITY_WEIGHTS["images"]) if effective_data.has_images else Decimal("0")
    )
    factors["legal_claims"] = _points_if_text(effective_data.legal_status_raw, "legal_claims")

    score = sum(factors.values(), Decimal("0")).quantize(
        QUALITY_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )
    missing_critical_fields: list[str] = []
    if not _has_usable_micro_location(effective_data):
        missing_critical_fields.append("usable_micro_location")
    if effective_data.size_m2 is None:
        missing_critical_fields.append("size_m2")
    if not _has_text(effective_data.condition_category):
        missing_critical_fields.append("condition")

    positive_factors = {
        "rules_version": rules_version,
        "weights": DATA_QUALITY_WEIGHTS,
        "points": {field: _decimal_to_string(value) for field, value in factors.items()},
    }
    return score, missing_critical_fields, positive_factors


def _normalize_and_apply_property_location(
    property_: Property,
    linked_listings: list[Listing],
) -> NormalizedLocation:
    location = normalize_location_text(
        property_.micro_location,
        property_.neighborhood,
        property_.municipality,
        property_.city,
        *(listing.location_raw for listing in linked_listings),
        *(listing.title for listing in linked_listings),
        *(listing.canonical_url for listing in linked_listings),
    )
    if property_.country_code is None and location.country_code is not None:
        property_.country_code = location.country_code
    if property_.city is None and location.city is not None:
        property_.city = location.city
    if property_.municipality is None and location.municipality is not None:
        property_.municipality = location.municipality
    if property_.neighborhood is None and location.neighborhood is not None:
        property_.neighborhood = location.neighborhood
    if property_.micro_location is None and location.micro_location is not None:
        property_.micro_location = location.micro_location
    if _should_update_location_confidence(property_, location):
        property_.location_precision = location.location_precision
        property_.location_confidence = location.location_confidence
    return location


def _feature_values(
    session: Session,
    property_: Property,
    *,
    linked_listings: list[Listing],
    effective_data: EffectivePropertyData,
    as_of: datetime,
) -> dict[str, object]:
    active_listings = [
        listing for listing in linked_listings if listing.status == ListingStatus.ACTIVE
    ]
    price_listings = [
        listing
        for listing in active_listings
        if listing.asking_price is not None and listing.asking_price > 0
    ]
    current_prices = [listing.asking_price for listing in price_listings if listing.asking_price]
    lowest_price = min(current_prices) if current_prices else None
    highest_price = max(current_prices) if current_prices else None

    price_events = _price_events(session, linked_listings)
    price_cuts = [
        event
        for event in price_events
        if event.old_price is not None
        and event.new_price is not None
        and event.new_price < event.old_price
    ]
    latest_cut_at = max((event.detected_at for event in price_cuts), default=None)

    return {
        "price_per_m2": _price_per_m2(lowest_price, effective_data.size_m2),
        "listing_age_days": _listing_age_days(active_listings or linked_listings, as_of),
        "property_market_age_days": _property_market_age_days(linked_listings, as_of),
        "active_listing_count": len(active_listings),
        "known_listing_count": len(linked_listings),
        "relist_count": max(len(linked_listings) - 1, 0),
        "current_lowest_asking_price": lowest_price,
        "current_highest_asking_price": highest_price,
        "total_price_drop_pct": _total_price_drop_pct(price_cuts),
        "price_drop_7d_pct": _window_price_drop_pct(price_cuts, as_of, days=7),
        "price_drop_30d_pct": _window_price_drop_pct(price_cuts, as_of, days=30),
        "price_cut_count": len(price_cuts),
        "days_since_last_price_cut": _days_between(as_of, latest_cut_at)
        if latest_cut_at is not None
        else None,
        "largest_price_cut_pct": max(
            (_price_drop_pct(event.old_price, event.new_price) for event in price_cuts),
            default=None,
        ),
        "owner_listing_present": any(
            listing.seller_type == SellerType.OWNER for listing in active_listings
        ),
        "agency_listing_count": sum(
            1 for listing in active_listings if listing.seller_type == SellerType.AGENCY
        ),
    }


def _linked_listings(session: Session, property_: Property) -> list[Listing]:
    return session.scalars(
        select(Listing).where(Listing.property_id == property_.id).order_by(Listing.created_at)
    ).all()


def _refresh_property_summary(property_: Property, linked_listings: list[Listing]) -> None:
    if not linked_listings:
        property_.active_listing_count = 0
        property_.relist_count = 0
        return

    first_seen_values = [
        listing.first_seen_at for listing in linked_listings if listing.first_seen_at is not None
    ]
    last_seen_values = [
        listing.last_seen_at for listing in linked_listings if listing.last_seen_at is not None
    ]
    if first_seen_values:
        property_.first_seen_at = min(first_seen_values)
    if last_seen_values:
        property_.last_seen_at = max(last_seen_values)
    property_.active_listing_count = sum(
        1 for listing in linked_listings if listing.status == ListingStatus.ACTIVE
    )
    property_.relist_count = max(len(linked_listings) - 1, 0)


def _fill_property_unknowns_from_effective(
    property_: Property,
    effective_data: EffectivePropertyData,
) -> None:
    for field_name in (
        "country_code",
        "city",
        "municipality",
        "neighborhood",
        "micro_location",
        "latitude",
        "longitude",
        "size_m2",
        "rooms",
        "bedrooms",
        "floor",
        "total_floors",
        "elevator",
        "building_type",
        "heating_type",
        "parking",
        "construction_year",
        "condition_category",
    ):
        if getattr(property_, field_name) is None:
            setattr(property_, field_name, getattr(effective_data, field_name))
    if _should_update_location_confidence_from_effective(property_, effective_data):
        property_.location_precision = effective_data.location_precision
        property_.location_confidence = effective_data.location_confidence


def _property_or_location(
    property_value: Any,
    location_value: Any,
) -> tuple[Any, str | None]:
    if property_value is not None:
        return property_value, "property"
    if location_value is not None:
        return location_value, "location_rules_v1"
    return None, None


def _property_or_existing(property_value: Any) -> tuple[Any, str | None]:
    if property_value is not None:
        return property_value, "property"
    return None, None


def _property_or_listing(
    property_: Property,
    listings: list[Listing],
    field_name: str,
    *,
    listing_field_name: str | None = None,
) -> tuple[Any, str | None]:
    property_value = getattr(property_, field_name, None)
    if property_value is not None:
        return property_value, "property"

    source_field_name = listing_field_name or field_name
    best_listing = _best_listing_for_field(listings, source_field_name)
    if best_listing is None:
        return None, None
    return getattr(best_listing, source_field_name), f"listing:{best_listing.id}"


def _best_listing_for_field(listings: list[Listing], field_name: str) -> Listing | None:
    candidates = [listing for listing in listings if getattr(listing, field_name, None) is not None]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda listing: (
            listing.status == ListingStatus.ACTIVE,
            _aware_datetime(listing.last_seen_at),
        ),
    )


def _best_text(listings: list[Listing], field_name: str) -> tuple[str | None, str | None]:
    values = [
        (getattr(listing, field_name), listing)
        for listing in listings
        if _has_text(getattr(listing, field_name, None))
    ]
    if not values:
        return None, None
    value, listing = max(values, key=lambda item: len(str(item[0])))
    return str(value), f"listing:{listing.id}"


def _best_seller_type(listings: list[Listing]) -> tuple[SellerType | None, str | None]:
    for preferred in (SellerType.OWNER, SellerType.AGENCY, SellerType.INVESTOR):
        for listing in listings:
            if listing.seller_type == preferred:
                return preferred, f"listing:{listing.id}"
    for listing in listings:
        if listing.seller_type != SellerType.UNKNOWN:
            return listing.seller_type, f"listing:{listing.id}"
    return None, None


def _has_images(listings: list[Listing]) -> bool:
    for listing in listings:
        for raw_record in listing.raw_records:
            if raw_record.record_type != ListingRawRecordType.DETAIL:
                continue
            image_urls = raw_record.raw_payload.get("image_urls")
            if isinstance(image_urls, list) and image_urls:
                return True
    return False


def _price_events(session: Session, listings: list[Listing]) -> list[ListingEvent]:
    listing_ids = [listing.id for listing in listings]
    if not listing_ids:
        return []
    return session.scalars(
        select(ListingEvent)
        .where(
            ListingEvent.listing_id.in_(listing_ids),
            ListingEvent.event_type == ListingEventType.PRICE_CHANGED,
        )
        .order_by(ListingEvent.detected_at, ListingEvent.id)
    ).all()


def _price_per_m2(price: Decimal | None, size_m2: Decimal | None) -> Decimal | None:
    if price is None or size_m2 is None or size_m2 <= 0:
        return None
    return (price / size_m2).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def _listing_age_days(listings: list[Listing], as_of: datetime) -> int | None:
    first_seen_values = [listing.first_seen_at for listing in listings if listing.first_seen_at]
    if not first_seen_values:
        return None
    return _days_between(as_of, max(first_seen_values))


def _property_market_age_days(listings: list[Listing], as_of: datetime) -> int | None:
    first_seen_values = [listing.first_seen_at for listing in listings if listing.first_seen_at]
    if not first_seen_values:
        return None
    return _days_between(as_of, min(first_seen_values))


def _total_price_drop_pct(price_cuts: list[ListingEvent]) -> Decimal:
    if not price_cuts:
        return Decimal("0.0000")
    first_price = price_cuts[0].old_price
    lowest_price = min(
        (event.new_price for event in price_cuts if event.new_price is not None),
        default=None,
    )
    return _price_drop_pct(first_price, lowest_price)


def _window_price_drop_pct(
    price_cuts: list[ListingEvent],
    as_of: datetime,
    *,
    days: int,
) -> Decimal:
    window_start = _aware_datetime(as_of) - timedelta(days=days)
    window_cuts = [
        event for event in price_cuts if _aware_datetime(event.detected_at) >= window_start
    ]
    if not window_cuts:
        return Decimal("0.0000")
    first_price = window_cuts[0].old_price
    lowest_price = min(
        (event.new_price for event in window_cuts if event.new_price is not None),
        default=None,
    )
    return _price_drop_pct(first_price, lowest_price)


def _price_drop_pct(
    old_price: Decimal | None,
    new_price: Decimal | None,
) -> Decimal:
    if old_price is None or new_price is None or old_price <= 0 or new_price >= old_price:
        return Decimal("0.0000")
    return ((old_price - new_price) / old_price * Decimal("100")).quantize(
        PERCENT_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


def _days_between(later: datetime, earlier: datetime | None) -> int | None:
    if earlier is None:
        return None
    delta = _aware_datetime(later) - _aware_datetime(earlier)
    return max(delta.days, 0)


def _location_quality_points(effective_data: EffectivePropertyData) -> Decimal:
    if _has_usable_micro_location(effective_data):
        return Decimal(DATA_QUALITY_WEIGHTS["location_precision"])
    if _has_text(effective_data.neighborhood):
        return Decimal("14")
    if _has_text(effective_data.municipality):
        return Decimal("8")
    if _has_text(effective_data.city):
        return Decimal("4")
    return Decimal("0")


def _has_usable_micro_location(effective_data: EffectivePropertyData) -> bool:
    confidence = effective_data.location_confidence or Decimal("0")
    return _has_text(effective_data.micro_location) and confidence >= Decimal("0.7500")


def _points_if_known(value: object, weight_key: str) -> Decimal:
    return Decimal(DATA_QUALITY_WEIGHTS[weight_key]) if value is not None else Decimal("0")


def _points_if_text(value: str | None, weight_key: str) -> Decimal:
    return Decimal(DATA_QUALITY_WEIGHTS[weight_key]) if _has_text(value) else Decimal("0")


def _description_points(value: str | None) -> Decimal:
    if not _has_text(value):
        return Decimal("0")
    text_length = len(value.strip())
    if text_length >= 80:
        return Decimal(DATA_QUALITY_WEIGHTS["description_quality"])
    if text_length >= 20:
        return Decimal("3")
    return Decimal("1")


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _should_update_location_confidence(
    property_: Property,
    location: NormalizedLocation,
) -> bool:
    if property_.location_confidence is None or property_.location_precision is None:
        return location.location_confidence > Decimal("0")
    return _precision_rank(location.location_precision) > _precision_rank(
        property_.location_precision
    )


def _should_update_location_confidence_from_effective(
    property_: Property,
    effective_data: EffectivePropertyData,
) -> bool:
    if effective_data.location_confidence is None or effective_data.location_precision is None:
        return False
    if property_.location_confidence is None or property_.location_precision is None:
        return effective_data.location_confidence > Decimal("0")
    return _precision_rank(effective_data.location_precision) > _precision_rank(
        property_.location_precision
    )


def _precision_rank(value: str | None) -> int:
    ranks = {
        "UNKNOWN": 0,
        "CITY": 1,
        "MUNICIPALITY": 2,
        "NEIGHBORHOOD": 3,
        "MICROZONE": 4,
        "MICRO_LOCATION": 4,
    }
    return ranks.get(value or "UNKNOWN", 0)


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _decimal_to_string(value: Decimal) -> str:
    return format(value, "f")


def _utcnow() -> datetime:
    return datetime.now(UTC)
