from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import ComparableSet, Listing, Property, Source, Valuation
from app.domain.enums import (
    ComparableType,
    CurrencyCode,
    DataSourceKind,
    ListingStatus,
    PropertyType,
    SellerType,
    ValuationModelType,
    ValuationStatus,
)
from app.features.property_dataset import build_effective_property_data
from app.valuation.comparable_engine import (
    COMPARABLE_ENGINE_VERSION,
    VALUATION_MODEL_VERSION,
    generate_listing_comparable_candidates,
    value_property,
)

AS_OF = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
TARGET_LAT = Decimal("44.805100")
TARGET_LON = Decimal("20.400200")


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
        "country_code": "RS",
        "city": "Beograd",
        "municipality": "Novi Beograd",
        "neighborhood": "Blok 45",
        "micro_location": "Blok 45",
        "latitude": TARGET_LAT,
        "longitude": TARGET_LON,
        "location_precision": "MICROZONE",
        "location_confidence": Decimal("0.9000"),
        "size_m2": Decimal("70.00"),
        "rooms": Decimal("3.00"),
        "floor": 5,
        "total_floors": 10,
        "elevator": True,
        "construction_year": 2010,
        "building_type": "standard",
        "heating_type": "central",
        "parking": False,
        "condition_category": "GOOD",
    }
    values.update(overrides)
    property_ = Property(**values)
    session.add(property_)
    session.flush()
    return property_


def create_listing_comp(
    session: Session,
    source: Source,
    external_listing_id: str,
    *,
    city: str = "Beograd",
    municipality: str = "Novi Beograd",
    neighborhood: str | None = "Blok 45",
    micro_location: str | None = "Blok 45",
    latitude: Decimal,
    longitude: Decimal = TARGET_LON,
    size_m2: Decimal = Decimal("70.00"),
    price_per_m2: Decimal = Decimal("3000.00"),
    rooms: Decimal = Decimal("3.00"),
    condition: str = "GOOD",
    first_seen_at: datetime | None = None,
    last_seen_at: datetime | None = None,
    status: ListingStatus = ListingStatus.ACTIVE,
    currency: CurrencyCode = CurrencyCode.EUR,
) -> Listing:
    comp_property = create_property(
        session,
        city=city,
        municipality=municipality,
        neighborhood=neighborhood,
        micro_location=micro_location,
        latitude=latitude,
        longitude=longitude,
        size_m2=size_m2,
        rooms=rooms,
        condition_category=condition,
    )
    listing = Listing(
        source=source,
        property=comp_property,
        external_listing_id=external_listing_id,
        url=f"https://example.test/{external_listing_id}",
        canonical_url=f"https://example.test/{external_listing_id}",
        title=f"Comparable {external_listing_id}",
        asking_price=(price_per_m2 * size_m2).quantize(Decimal("0.01")),
        currency=currency,
        city_raw=city,
        location_raw=f"{micro_location or municipality}, {municipality}, {city}",
        size_m2=size_m2,
        rooms=rooms,
        floor=5,
        total_floors=10,
        elevator=True,
        construction_year=2010,
        building_type="standard",
        heating_type="central",
        parking=False,
        condition_raw=condition,
        seller_type=SellerType.AGENCY,
        status=status,
        first_seen_at=first_seen_at or AS_OF - timedelta(days=30),
        last_seen_at=last_seen_at or AS_OF - timedelta(days=1),
    )
    session.add(listing)
    session.flush()
    return listing


def count_rows(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_phase6_valuation_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {
        "comparable_sets",
        "comparable_items",
        "valuations",
    }.issubset(set(inspector.get_table_names()))


def test_adaptive_radius_includes_reasonable_listing_comps_and_excludes_far_listing(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase6_radius")
    target = create_property(db_session)
    create_listing_comp(db_session, source, "within-100m", latitude=Decimal("44.805600"))
    create_listing_comp(db_session, source, "within-250m", latitude=Decimal("44.807300"))
    create_listing_comp(db_session, source, "within-400m", latitude=Decimal("44.808700"))
    create_listing_comp(db_session, source, "within-900m", latitude=Decimal("44.813200"))
    far_listing = create_listing_comp(
        db_session,
        source,
        "two-km-away",
        latitude=Decimal("44.823100"),
    )

    result = value_property(db_session, target, as_of=AS_OF)
    item_listing_ids = {item.listing_id for item in result.comparable_items}

    assert result.comparable_set.search_parameters_json["selected_radius_m"] == 1200
    assert far_listing.id not in item_listing_ids
    assert result.valuation.status == ValuationStatus.SUCCESS
    assert result.valuation.explanation_json["listing_comparable_count"] == 4


def test_size_filtering_and_similarity_ordering_use_target_like_comps(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase6_size_order")
    target = create_property(db_session)
    best = create_listing_comp(
        db_session,
        source,
        "best-size-room",
        latitude=Decimal("44.805600"),
        size_m2=Decimal("68.00"),
        rooms=Decimal("3.00"),
    )
    weaker = create_listing_comp(
        db_session,
        source,
        "weaker-size-room",
        latitude=Decimal("44.812000"),
        size_m2=Decimal("75.00"),
        rooms=Decimal("4.00"),
    )
    too_large = create_listing_comp(
        db_session,
        source,
        "too-large",
        latitude=Decimal("44.805700"),
        size_m2=Decimal("88.00"),
    )

    target_data = build_effective_property_data(db_session, target)
    candidates, selected_radius_m = generate_listing_comparable_candidates(
        db_session,
        target,
        target_data=target_data,
        as_of=AS_OF,
    )

    candidate_listing_ids = [candidate.listing.id for candidate in candidates]
    assert selected_radius_m == 1200
    assert candidate_listing_ids[0] == best.id
    assert weaker.id in candidate_listing_ids
    assert too_large.id not in candidate_listing_ids


def test_valuation_persists_listing_comparable_types_and_explainable_outlier(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase6_outlier")
    target = create_property(db_session)
    for index, price_per_m2 in enumerate(("3000.00", "3050.00", "3100.00", "3080.00")):
        create_listing_comp(
            db_session,
            source,
            f"normal-{index}",
            latitude=Decimal("44.805600") + (Decimal(index) * Decimal("0.0001")),
            price_per_m2=Decimal(price_per_m2),
        )
    outlier = create_listing_comp(
        db_session,
        source,
        "outlier",
        latitude=Decimal("44.805900"),
        price_per_m2=Decimal("9000.00"),
    )

    result = value_property(db_session, target, as_of=AS_OF)
    valuation = result.valuation
    outlier_item = next(item for item in result.comparable_items if item.listing_id == outlier.id)

    assert valuation.status == ValuationStatus.SUCCESS
    assert valuation.model_type == ValuationModelType.LISTING_COMPS
    assert valuation.model_version == VALUATION_MODEL_VERSION
    assert valuation.comparable_set.comparable_engine_version == COMPARABLE_ENGINE_VERSION
    assert valuation.fair_value_low <= valuation.fair_value_base <= valuation.fair_value_high
    assert {item.comparable_type for item in result.comparable_items} == {ComparableType.LISTING}
    assert valuation.explanation_json["transaction_comparable_count"] == 0
    assert valuation.explanation_json["price_basis"] == "asking_listing_price_per_m2"
    assert outlier_item.included_in_valuation is False
    assert outlier_item.exclusion_reason == "PRICE_OUTLIER"
    assert any(
        comp["listing_id"] == str(outlier.id) and comp["exclusion_reason"] == "PRICE_OUTLIER"
        for comp in valuation.explanation_json["excluded_comps"]
    )


def test_insufficient_data_creates_no_false_fmv(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase6_insufficient")
    target = create_property(db_session)
    create_listing_comp(db_session, source, "only-one", latitude=Decimal("44.805600"))
    create_listing_comp(db_session, source, "only-two", latitude=Decimal("44.805700"))

    result = value_property(db_session, target, as_of=AS_OF)
    valuation = result.valuation

    assert valuation.status == ValuationStatus.INSUFFICIENT_DATA
    assert valuation.fair_value_low is None
    assert valuation.fair_value_base is None
    assert valuation.fair_value_high is None
    assert valuation.explanation_json["reason"] == "NOT_ENOUGH_INCLUDED_COMPS"
    assert {item.exclusion_reason for item in result.comparable_items} == {
        "INSUFFICIENT_COMP_COUNT"
    }


def test_historical_as_of_excludes_future_comparable_without_lookahead(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase6_asof")
    target = create_property(db_session)
    for index in range(3):
        create_listing_comp(
            db_session,
            source,
            f"past-{index}",
            latitude=Decimal("44.805600") + (Decimal(index) * Decimal("0.0001")),
            first_seen_at=AS_OF - timedelta(days=30),
            last_seen_at=AS_OF - timedelta(days=1),
        )
    future_listing = create_listing_comp(
        db_session,
        source,
        "future",
        latitude=Decimal("44.805900"),
        first_seen_at=AS_OF + timedelta(days=10),
        last_seen_at=AS_OF + timedelta(days=10),
    )

    result = value_property(db_session, target, as_of=AS_OF)
    item_listing_ids = {item.listing_id for item in result.comparable_items}

    assert result.valuation.status == ValuationStatus.SUCCESS
    assert future_listing.id not in item_listing_ids
    assert result.comparable_set.as_of == AS_OF
    assert result.valuation.as_of == AS_OF


def test_valuation_reproducibility_and_immutable_rows_for_same_inputs(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase6_reproducible")
    target = create_property(db_session)
    for index, price_per_m2 in enumerate(("3000.00", "3050.00", "3100.00")):
        create_listing_comp(
            db_session,
            source,
            f"repro-{index}",
            latitude=Decimal("44.805600") + (Decimal(index) * Decimal("0.0001")),
            price_per_m2=Decimal(price_per_m2),
        )

    first = value_property(db_session, target, as_of=AS_OF)
    second = value_property(db_session, target, as_of=AS_OF)

    assert first.valuation.id != second.valuation.id
    assert first.comparable_set.id != second.comparable_set.id
    assert count_rows(db_session, Valuation) == 2
    assert count_rows(db_session, ComparableSet) == 2
    assert first.valuation.fair_value_low == second.valuation.fair_value_low
    assert first.valuation.fair_value_base == second.valuation.fair_value_base
    assert first.valuation.fair_value_high == second.valuation.fair_value_high
    assert first.valuation.confidence == second.valuation.confidence
    assert first.valuation.input_summary_json == second.valuation.input_summary_json


def test_confidence_reacts_to_comp_count_dispersion_and_critical_missing_data(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase6_confidence")
    strong_target = create_property(db_session)
    for index, price_per_m2 in enumerate(
        ("3000.00", "3010.00", "3020.00", "3030.00", "3040.00", "3050.00", "3060.00", "3070.00")
    ):
        create_listing_comp(
            db_session,
            source,
            f"strong-{index}",
            latitude=Decimal("44.805600") + (Decimal(index) * Decimal("0.0001")),
            price_per_m2=Decimal(price_per_m2),
        )

    weak_target = create_property(
        db_session,
        city="Zemun",
        municipality="Zemun",
        latitude=None,
        longitude=None,
        neighborhood=None,
        micro_location=None,
        location_precision="MUNICIPALITY",
        location_confidence=Decimal("0.5500"),
        condition_category=None,
    )
    for index, price_per_m2 in enumerate(("2500.00", "3100.00", "3900.00")):
        create_listing_comp(
            db_session,
            source,
            f"weak-{index}",
            city="Zemun",
            municipality="Zemun",
            neighborhood=None,
            micro_location=None,
            latitude=Decimal("44.806000") + (Decimal(index) * Decimal("0.0001")),
            price_per_m2=Decimal(price_per_m2),
            condition="UNKNOWN",
        )

    strong = value_property(db_session, strong_target, as_of=AS_OF).valuation
    weak = value_property(db_session, weak_target, as_of=AS_OF).valuation

    assert strong.status == ValuationStatus.SUCCESS
    assert weak.status == ValuationStatus.SUCCESS
    assert strong.confidence > weak.confidence
    assert Decimal(
        str(strong.explanation_json["confidence_factors"]["price_dispersion"])
    ) > Decimal(str(weak.explanation_json["confidence_factors"]["price_dispersion"]))
    assert weak.explanation_json["confidence_factors"]["penalties"] == "10"
