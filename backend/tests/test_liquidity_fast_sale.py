from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import (
    ComparableSet,
    FastSaleEstimate,
    LiquidityAssessment,
    Listing,
    Property,
    Source,
    Valuation,
)
from app.domain.enums import (
    CurrencyCode,
    DataSourceKind,
    FastSaleStatus,
    LiquidityStatus,
    ListingStatus,
    PropertyType,
    SellerType,
    ValuationModelType,
    ValuationStatus,
)
from app.liquidity.liquidity_engine import (
    FAST_SALE_MODEL_VERSION,
    LIQUIDITY_MODEL_VERSION,
    assess_liquidity_and_fast_sale,
)

AS_OF = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def create_source(session: Session, code: str = "phase7") -> Source:
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
        "latitude": Decimal("44.805100"),
        "longitude": Decimal("20.400200"),
        "location_precision": "MICROZONE",
        "location_confidence": Decimal("0.9000"),
        "size_m2": Decimal("70.00"),
        "rooms": Decimal("3.00"),
        "floor": 4,
        "total_floors": 10,
        "elevator": True,
        "construction_year": 2010,
        "building_type": "standard",
        "heating_type": "central",
        "parking": True,
        "condition_category": "RENOVATED",
    }
    values.update(overrides)
    property_ = Property(**values)
    session.add(property_)
    session.flush()
    return property_


def create_current_listing(
    session: Session,
    source: Source,
    property_: Property,
    *,
    external_listing_id: str,
    asking_price: Decimal,
    parking: bool | None,
) -> Listing:
    listing = Listing(
        source=source,
        property=property_,
        external_listing_id=external_listing_id,
        url=f"https://example.test/{external_listing_id}",
        canonical_url=f"https://example.test/{external_listing_id}",
        title="Current target listing",
        description="A normal market listing with enough text for data quality scoring.",
        asking_price=asking_price,
        currency=CurrencyCode.EUR,
        city_raw=property_.city,
        location_raw=", ".join(
            value
            for value in (
                property_.micro_location,
                property_.neighborhood,
                property_.municipality,
                property_.city,
            )
            if value
        ),
        size_m2=property_.size_m2,
        rooms=property_.rooms,
        floor=property_.floor,
        total_floors=property_.total_floors,
        elevator=property_.elevator,
        construction_year=property_.construction_year,
        building_type=property_.building_type,
        heating_type=property_.heating_type,
        parking=parking,
        condition_raw=property_.condition_category,
        seller_type=SellerType.AGENCY,
        status=ListingStatus.ACTIVE,
        first_seen_at=AS_OF - timedelta(days=20),
        last_seen_at=AS_OF - timedelta(days=1),
    )
    session.add(listing)
    session.flush()
    return listing


def create_valuation(
    session: Session,
    property_: Property,
    *,
    fair_value_base: Decimal = Decimal("210000.00"),
    confidence: Decimal = Decimal("72.00"),
    included_comparable_count: int = 8,
    dispersion: Decimal = Decimal("0.04"),
    status: ValuationStatus = ValuationStatus.SUCCESS,
) -> Valuation:
    comparable_set = ComparableSet(
        property=property_,
        as_of=AS_OF,
        comparable_engine_version="test_comparable_engine",
        search_parameters_json={"source": "test"},
    )
    session.add(comparable_set)
    session.flush()

    has_fmv = status == ValuationStatus.SUCCESS
    valuation = Valuation(
        property=property_,
        comparable_set=comparable_set,
        as_of=AS_OF,
        status=status,
        fair_value_low=(fair_value_base * Decimal("0.90")).quantize(Decimal("0.01"))
        if has_fmv
        else None,
        fair_value_base=fair_value_base if has_fmv else None,
        fair_value_high=(fair_value_base * Decimal("1.10")).quantize(Decimal("0.01"))
        if has_fmv
        else None,
        currency=CurrencyCode.EUR,
        confidence=confidence if has_fmv else Decimal("0.00"),
        data_quality_at_analysis=Decimal("80.00") if has_fmv else Decimal("20.00"),
        model_type=ValuationModelType.LISTING_COMPS,
        model_version="valuation_v1",
        input_summary_json={
            "evidence_type": "ASKING_LISTING_COMPS",
            "included_comparable_count": included_comparable_count if has_fmv else 0,
            "candidate_count": included_comparable_count if has_fmv else 0,
        },
        explanation_json={
            "status": status.value,
            "price_dispersion": str(dispersion),
            "included_comparable_count": included_comparable_count if has_fmv else 0,
        },
    )
    session.add(valuation)
    session.flush()
    return valuation


def count_rows(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_phase7_liquidity_and_fast_sale_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {
        "liquidity_assessments",
        "fast_sale_estimates",
    }.issubset(set(inspector.get_table_names()))


def test_liquidity_profile_scores_better_for_common_good_property(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase7_profiles")
    strong_property = create_property(db_session)
    weak_property = create_property(
        db_session,
        city="Smederevo",
        municipality="Smederevo",
        neighborhood=None,
        micro_location=None,
        latitude=None,
        longitude=None,
        location_precision="MUNICIPALITY",
        location_confidence=Decimal("0.5000"),
        size_m2=Decimal("130.00"),
        rooms=Decimal("5.00"),
        floor=9,
        elevator=False,
        building_type="old",
        parking=False,
        condition_category="NEEDS_RENOVATION",
    )
    create_current_listing(
        db_session,
        source,
        strong_property,
        external_listing_id="strong-current",
        asking_price=Decimal("205000.00"),
        parking=True,
    )
    create_current_listing(
        db_session,
        source,
        weak_property,
        external_listing_id="weak-current",
        asking_price=Decimal("255000.00"),
        parking=False,
    )
    strong_valuation = create_valuation(db_session, strong_property)
    weak_valuation = create_valuation(
        db_session,
        weak_property,
        included_comparable_count=3,
        dispersion=Decimal("0.18"),
    )

    strong = assess_liquidity_and_fast_sale(
        db_session,
        strong_property,
        valuation=strong_valuation,
        as_of=AS_OF,
    )
    weak = assess_liquidity_and_fast_sale(
        db_session,
        weak_property,
        valuation=weak_valuation,
        as_of=AS_OF,
    )

    assert strong.liquidity_assessment.status == LiquidityStatus.SUCCESS
    assert weak.liquidity_assessment.status == LiquidityStatus.SUCCESS
    assert strong.liquidity_assessment.liquidity_score > weak.liquidity_assessment.liquidity_score
    assert strong.liquidity_assessment.confidence > weak.liquidity_assessment.confidence
    assert strong.liquidity_assessment.positive_factors_json["liquidity_level"] == "HIGH"
    assert weak.liquidity_assessment.positive_factors_json["liquidity_level"] == "LOW"
    assert strong.liquidity_assessment.probability_sale_30d is None
    assert strong.liquidity_assessment.probability_sale_60d is None
    assert strong.liquidity_assessment.probability_sale_90d is None


def test_unknown_parking_reduces_confidence_without_negative_score(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase7_unknown")
    unknown_parking_property = create_property(db_session, parking=None)
    no_parking_property = create_property(db_session, parking=False)
    create_current_listing(
        db_session,
        source,
        unknown_parking_property,
        external_listing_id="unknown-parking",
        asking_price=Decimal("205000.00"),
        parking=None,
    )
    create_current_listing(
        db_session,
        source,
        no_parking_property,
        external_listing_id="no-parking",
        asking_price=Decimal("205000.00"),
        parking=False,
    )
    unknown_valuation = create_valuation(db_session, unknown_parking_property)
    no_parking_valuation = create_valuation(db_session, no_parking_property)

    unknown_result = assess_liquidity_and_fast_sale(
        db_session,
        unknown_parking_property,
        valuation=unknown_valuation,
        as_of=AS_OF,
    )
    no_parking_result = assess_liquidity_and_fast_sale(
        db_session,
        no_parking_property,
        valuation=no_parking_valuation,
        as_of=AS_OF,
    )

    assert (
        unknown_result.liquidity_assessment.liquidity_score
        >= no_parking_result.liquidity_assessment.liquidity_score
    )
    assert (
        unknown_result.liquidity_assessment.confidence
        < no_parking_result.liquidity_assessment.confidence
    )
    assert (
        "parking"
        in unknown_result.liquidity_assessment.negative_factors_json["unknown_important_factors"]
    )
    assert not any(
        factor["code"] == "PARKING_NOT_CONFIRMED"
        for factor in unknown_result.liquidity_assessment.negative_factors_json["factors"]
    )


def test_fast_sale_estimate_uses_liquidity_and_preserves_value_order(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase7_fast_sale")
    strong_property = create_property(db_session)
    weak_property = create_property(
        db_session,
        city="Smederevo",
        municipality="Smederevo",
        neighborhood=None,
        micro_location=None,
        latitude=None,
        longitude=None,
        location_precision="MUNICIPALITY",
        location_confidence=Decimal("0.5000"),
        size_m2=Decimal("130.00"),
        rooms=Decimal("5.00"),
        floor=9,
        elevator=False,
        building_type="old",
        parking=False,
        condition_category="NEEDS_RENOVATION",
    )
    create_current_listing(
        db_session,
        source,
        strong_property,
        external_listing_id="strong-fast",
        asking_price=Decimal("205000.00"),
        parking=True,
    )
    create_current_listing(
        db_session,
        source,
        weak_property,
        external_listing_id="weak-fast",
        asking_price=Decimal("255000.00"),
        parking=False,
    )
    fair_value_base = Decimal("210000.00")
    strong_valuation = create_valuation(
        db_session, strong_property, fair_value_base=fair_value_base
    )
    weak_valuation = create_valuation(
        db_session,
        weak_property,
        fair_value_base=fair_value_base,
        included_comparable_count=3,
        dispersion=Decimal("0.18"),
    )

    strong = assess_liquidity_and_fast_sale(
        db_session,
        strong_property,
        valuation=strong_valuation,
        as_of=AS_OF,
    ).fast_sale_estimate
    weak = assess_liquidity_and_fast_sale(
        db_session,
        weak_property,
        valuation=weak_valuation,
        as_of=AS_OF,
    ).fast_sale_estimate

    assert strong.status == FastSaleStatus.SUCCESS
    assert weak.status == FastSaleStatus.SUCCESS
    assert strong.value_low <= strong.value_base <= strong.value_high
    assert weak.value_low <= weak.value_base <= weak.value_high
    assert strong.value_high <= fair_value_base
    assert weak.value_high <= fair_value_base
    assert strong.value_base > weak.value_base
    assert strong.target_probability is None
    assert strong.explanation_json["target_probability"] is None
    assert Decimal(strong.explanation_json["discounts"]["base"]) < Decimal(
        weak.explanation_json["discounts"]["base"]
    )


def test_target_days_changes_fast_sale_conservatism_without_probabilities(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase7_target_days")
    property_ = create_property(db_session)
    create_current_listing(
        db_session,
        source,
        property_,
        external_listing_id="target-days",
        asking_price=Decimal("205000.00"),
        parking=True,
    )
    valuation = create_valuation(db_session, property_)

    thirty_day = assess_liquidity_and_fast_sale(
        db_session,
        property_,
        valuation=valuation,
        as_of=AS_OF,
        target_days=30,
    ).fast_sale_estimate
    ninety_day = assess_liquidity_and_fast_sale(
        db_session,
        property_,
        valuation=valuation,
        as_of=AS_OF,
        target_days=90,
    ).fast_sale_estimate

    assert thirty_day.target_days == 30
    assert ninety_day.target_days == 90
    assert thirty_day.value_base < ninety_day.value_base
    assert thirty_day.target_probability is None
    assert ninety_day.target_probability is None
    assert thirty_day.explanation_json["target_day_context"] == "short_fast_sale_horizon"
    assert ninety_day.explanation_json["target_day_context"] == "extended_fast_sale_horizon"


def test_insufficient_valuation_creates_no_false_liquidity_or_fast_sale_values(
    db_session: Session,
) -> None:
    property_ = create_property(db_session)
    valuation = create_valuation(db_session, property_, status=ValuationStatus.INSUFFICIENT_DATA)

    result = assess_liquidity_and_fast_sale(
        db_session,
        property_,
        valuation=valuation,
        as_of=AS_OF,
    )

    assert result.liquidity_assessment.status == LiquidityStatus.INSUFFICIENT_DATA
    assert result.liquidity_assessment.liquidity_score is None
    assert result.liquidity_assessment.confidence == Decimal("0.00")
    assert result.fast_sale_estimate.status == FastSaleStatus.INSUFFICIENT_DATA
    assert result.fast_sale_estimate.value_low is None
    assert result.fast_sale_estimate.value_base is None
    assert result.fast_sale_estimate.value_high is None
    assert result.fast_sale_estimate.target_probability is None
    assert result.fast_sale_estimate.explanation_json["reason"] == "VALUATION_INSUFFICIENT_DATA"


def test_phase7_results_are_versioned_historical_rows(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase7_versioned")
    property_ = create_property(db_session)
    create_current_listing(
        db_session,
        source,
        property_,
        external_listing_id="versioned",
        asking_price=Decimal("205000.00"),
        parking=True,
    )
    valuation = create_valuation(db_session, property_)

    first = assess_liquidity_and_fast_sale(
        db_session,
        property_,
        valuation=valuation,
        as_of=AS_OF,
    )
    second = assess_liquidity_and_fast_sale(
        db_session,
        property_,
        valuation=valuation,
        as_of=AS_OF,
    )

    assert first.liquidity_assessment.id != second.liquidity_assessment.id
    assert first.fast_sale_estimate.id != second.fast_sale_estimate.id
    assert first.liquidity_assessment.model_version == LIQUIDITY_MODEL_VERSION
    assert first.fast_sale_estimate.model_version == FAST_SALE_MODEL_VERSION
    assert first.liquidity_assessment.valuation_id == valuation.id
    assert first.fast_sale_estimate.valuation_id == valuation.id
    assert first.fast_sale_estimate.liquidity_assessment_id == first.liquidity_assessment.id
    assert first.liquidity_assessment.as_of == AS_OF
    assert first.fast_sale_estimate.as_of == AS_OF
    assert count_rows(db_session, LiquidityAssessment) == 2
    assert count_rows(db_session, FastSaleEstimate) == 2
