from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import ComparableItem, ComparableSet, Listing, Property, Valuation
from app.domain.enums import (
    ComparableType,
    CurrencyCode,
    ListingStatus,
    PropertyType,
    ValuationModelType,
    ValuationStatus,
)
from app.features.property_dataset import (
    EffectivePropertyData,
    build_effective_property_data,
    recalculate_property_market_dataset,
)

COMPARABLE_ENGINE_VERSION = "comparable_engine_v1"
VALUATION_MODEL_VERSION = "valuation_v1"

SCORE_QUANTIZER = Decimal("0.0001")
MONEY_QUANTIZER = Decimal("0.01")
CONFIDENCE_QUANTIZER = Decimal("0.01")
RADIUS_STEPS_M = (300, 500, 800, 1200)
MAX_SIZE_DIFF_PCT = Decimal("0.25")
MIN_SIMILARITY_SCORE = Decimal("0.4500")
MIN_COMPS_FOR_VALUATION = 3
TARGET_COMPS_BEFORE_RADIUS_STOP = 4
MAX_COMPARABLE_ITEMS = 12
LISTING_SOURCE_QUALITY_WEIGHT = Decimal("0.6000")
MAX_COMP_AGE_DAYS = 365
MAX_POSITIVE_ADJUSTMENT_PCT = Decimal("15.0000")
MAX_NEGATIVE_ADJUSTMENT_PCT = Decimal("-25.0000")

SIMILARITY_WEIGHTS: dict[str, Decimal] = {
    "location": Decimal("0.25"),
    "size": Decimal("0.20"),
    "condition": Decimal("0.15"),
    "rooms": Decimal("0.10"),
    "building_type": Decimal("0.10"),
    "floor_elevator": Decimal("0.08"),
    "construction_age": Decimal("0.05"),
    "parking": Decimal("0.03"),
    "heating": Decimal("0.02"),
    "other": Decimal("0.02"),
}


@dataclass
class ComparableCandidate:
    listing: Listing
    comparable_property: Property
    effective_data: EffectivePropertyData
    distance_m: Decimal | None
    age_days_at_analysis: int | None
    price: Decimal
    price_per_m2: Decimal
    scores: dict[str, Decimal]
    similarity_score: Decimal
    recency_weight: Decimal
    weight: Decimal
    included_in_valuation: bool = True
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class ValuationRunResult:
    comparable_set: ComparableSet
    comparable_items: list[ComparableItem]
    valuation: Valuation


def value_property(
    session: Session,
    property_: Property,
    *,
    as_of: datetime | None = None,
    commit: bool = False,
) -> ValuationRunResult:
    analysis_as_of = _aware_datetime(as_of or _utcnow())
    market_dataset = recalculate_property_market_dataset(session, property_, as_of=analysis_as_of)
    target_data = market_dataset.effective_data
    data_quality_score = market_dataset.data_quality.score
    input_issue = _input_issue(target_data)

    candidates: list[ComparableCandidate] = []
    selected_radius_m: int | None = None
    if input_issue is None:
        candidates, selected_radius_m = generate_listing_comparable_candidates(
            session,
            property_,
            target_data=target_data,
            as_of=analysis_as_of,
        )
        apply_outlier_exclusions(candidates)
        if _included_count(candidates) < MIN_COMPS_FOR_VALUATION:
            _mark_included_candidates_excluded(candidates, "INSUFFICIENT_COMP_COUNT")

    comparable_set = ComparableSet(
        property=property_,
        as_of=analysis_as_of,
        comparable_engine_version=COMPARABLE_ENGINE_VERSION,
        search_parameters_json=_search_parameters(
            target_data=target_data,
            selected_radius_m=selected_radius_m,
            input_issue=input_issue,
        ),
    )
    session.add(comparable_set)
    session.flush()
    comparable_items = [
        _persist_comparable_item(session, comparable_set, candidate) for candidate in candidates
    ]

    included_candidates = [candidate for candidate in candidates if candidate.included_in_valuation]
    if input_issue is not None:
        valuation = _persist_insufficient_data_valuation(
            session,
            property_,
            comparable_set,
            as_of=analysis_as_of,
            data_quality_score=data_quality_score,
            reason=input_issue,
            candidates=candidates,
        )
    elif len(included_candidates) < MIN_COMPS_FOR_VALUATION:
        valuation = _persist_insufficient_data_valuation(
            session,
            property_,
            comparable_set,
            as_of=analysis_as_of,
            data_quality_score=data_quality_score,
            reason="NOT_ENOUGH_INCLUDED_COMPS",
            candidates=candidates,
        )
    else:
        valuation = _persist_success_valuation(
            session,
            property_,
            comparable_set,
            target_data=target_data,
            candidates=candidates,
            included_candidates=included_candidates,
            as_of=analysis_as_of,
            data_quality_score=data_quality_score,
        )

    if commit:
        session.commit()
    return ValuationRunResult(
        comparable_set=comparable_set,
        comparable_items=comparable_items,
        valuation=valuation,
    )


def generate_listing_comparable_candidates(
    session: Session,
    property_: Property,
    *,
    target_data: EffectivePropertyData,
    as_of: datetime,
) -> tuple[list[ComparableCandidate], int | None]:
    raw_candidates = _raw_listing_candidates(session, property_, target_data, as_of)
    candidates = [
        _score_listing_candidate(session, target_data, listing, distance_m, as_of)
        for listing, distance_m in raw_candidates
    ]
    candidates = [candidate for candidate in candidates if candidate.price_per_m2 > 0]

    if _has_coordinates(target_data):
        selected_radius_m = _selected_radius(candidates)
        candidates = [
            candidate
            for candidate in candidates
            if candidate.distance_m is not None and candidate.distance_m <= selected_radius_m
        ]
    else:
        selected_radius_m = None

    for candidate in candidates:
        if (
            candidate.age_days_at_analysis is not None
            and candidate.age_days_at_analysis > MAX_COMP_AGE_DAYS
        ):
            candidate.included_in_valuation = False
            candidate.exclusion_reason = "TOO_OLD"
        elif candidate.similarity_score < MIN_SIMILARITY_SCORE:
            candidate.included_in_valuation = False
            candidate.exclusion_reason = "LOW_SIMILARITY"

    return _rank_candidates(candidates)[:MAX_COMPARABLE_ITEMS], selected_radius_m


def apply_outlier_exclusions(candidates: list[ComparableCandidate]) -> None:
    included = [candidate for candidate in candidates if candidate.included_in_valuation]
    if len(included) < 5:
        return

    values = sorted(candidate.price_per_m2 for candidate in included)
    q1 = _percentile(values, Decimal("0.25"))
    q3 = _percentile(values, Decimal("0.75"))
    iqr = q3 - q1
    if iqr <= 0:
        return

    lower_bound = q1 - (iqr * Decimal("1.5"))
    upper_bound = q3 + (iqr * Decimal("1.5"))
    for candidate in included:
        if candidate.price_per_m2 < lower_bound or candidate.price_per_m2 > upper_bound:
            candidate.included_in_valuation = False
            candidate.exclusion_reason = "PRICE_OUTLIER"


def _included_count(candidates: list[ComparableCandidate]) -> int:
    return sum(1 for candidate in candidates if candidate.included_in_valuation)


def _mark_included_candidates_excluded(
    candidates: list[ComparableCandidate],
    reason: str,
) -> None:
    for candidate in candidates:
        if candidate.included_in_valuation:
            candidate.included_in_valuation = False
            candidate.exclusion_reason = reason


def _raw_listing_candidates(
    session: Session,
    property_: Property,
    target_data: EffectivePropertyData,
    as_of: datetime,
) -> list[tuple[Listing, Decimal | None]]:
    if target_data.size_m2 is None or target_data.size_m2 <= 0:
        return []

    min_size = target_data.size_m2 * (Decimal("1") - MAX_SIZE_DIFF_PCT)
    max_size = target_data.size_m2 * (Decimal("1") + MAX_SIZE_DIFF_PCT)
    stmt = (
        select(Listing)
        .join(Property, Listing.property_id == Property.id)
        .where(
            Listing.property_id.is_not(None),
            Listing.property_id != property_.id,
            Property.property_type == PropertyType.APARTMENT,
            Listing.status == ListingStatus.ACTIVE,
            Listing.currency == CurrencyCode.EUR,
            Listing.asking_price.is_not(None),
            Listing.asking_price > 0,
            Listing.size_m2.is_not(None),
            Listing.size_m2 > 0,
            Listing.size_m2 >= min_size,
            Listing.size_m2 <= max_size,
            Listing.first_seen_at <= as_of,
            Listing.last_seen_at <= as_of,
        )
        .order_by(Listing.last_seen_at.desc(), Listing.id)
    )
    if target_data.city is not None:
        stmt = stmt.where(
            or_(
                Property.city == target_data.city,
                Listing.city_raw.ilike(f"%{target_data.city}%"),
                Listing.location_raw.ilike(f"%{target_data.city}%"),
            )
        )

    if _has_coordinates(target_data):
        distance_expr = func.ST_DistanceSphere(
            func.ST_MakePoint(Property.longitude, Property.latitude),
            func.ST_MakePoint(float(target_data.longitude), float(target_data.latitude)),
        )
        stmt = (
            select(Listing, distance_expr.label("distance_m"))
            .join(Property, Listing.property_id == Property.id)
            .where(
                Listing.property_id.is_not(None),
                Listing.property_id != property_.id,
                Property.property_type == PropertyType.APARTMENT,
                Property.latitude.is_not(None),
                Property.longitude.is_not(None),
                Listing.status == ListingStatus.ACTIVE,
                Listing.currency == CurrencyCode.EUR,
                Listing.asking_price.is_not(None),
                Listing.asking_price > 0,
                Listing.size_m2.is_not(None),
                Listing.size_m2 > 0,
                Listing.size_m2 >= min_size,
                Listing.size_m2 <= max_size,
                Listing.first_seen_at <= as_of,
                Listing.last_seen_at <= as_of,
                distance_expr <= RADIUS_STEPS_M[-1],
            )
            .order_by(distance_expr, Listing.last_seen_at.desc(), Listing.id)
        )
        if target_data.city is not None:
            stmt = stmt.where(
                or_(
                    Property.city == target_data.city,
                    Listing.city_raw.ilike(f"%{target_data.city}%"),
                    Listing.location_raw.ilike(f"%{target_data.city}%"),
                )
            )
        return [
            (listing, Decimal(str(round(float(distance_m), 2))).quantize(MONEY_QUANTIZER))
            for listing, distance_m in session.execute(stmt).all()
        ]

    return [(listing, None) for listing in session.scalars(stmt).all()]


def _score_listing_candidate(
    session: Session,
    target_data: EffectivePropertyData,
    listing: Listing,
    distance_m: Decimal | None,
    as_of: datetime,
) -> ComparableCandidate:
    comparable_property = listing.property
    if comparable_property is None:
        raise ValueError("listing comparable must have a property")
    effective_data = build_effective_property_data(
        session,
        comparable_property,
        linked_listings=[listing],
    )
    price = listing.asking_price
    size_m2 = listing.size_m2
    if price is None or size_m2 is None or size_m2 <= 0:
        raise ValueError("listing comparable must have price and size")
    price_per_m2 = (price / size_m2).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    scores = {
        "location": _location_score(target_data, effective_data, distance_m),
        "size": _size_score(target_data.size_m2, size_m2),
        "condition": _condition_score(
            target_data.condition_category, effective_data.condition_category
        ),
        "rooms": _rooms_score(target_data.rooms, effective_data.rooms),
        "building_type": _same_text_score(target_data.building_type, effective_data.building_type),
        "floor_elevator": _floor_elevator_score(target_data, effective_data),
        "construction_age": _construction_age_score(
            target_data.construction_year,
            effective_data.construction_year,
        ),
        "parking": _boolean_score(target_data.parking, effective_data.parking),
        "heating": _same_text_score(target_data.heating_type, effective_data.heating_type),
        "other": Decimal("0.7000"),
    }
    similarity_score = _weighted_score(scores, SIMILARITY_WEIGHTS)
    age_days_at_analysis = _days_between(as_of, listing.last_seen_at)
    recency_weight = _listing_recency_weight(age_days_at_analysis)
    weight = (similarity_score * LISTING_SOURCE_QUALITY_WEIGHT * recency_weight).quantize(
        SCORE_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )

    return ComparableCandidate(
        listing=listing,
        comparable_property=comparable_property,
        effective_data=effective_data,
        distance_m=distance_m,
        age_days_at_analysis=age_days_at_analysis,
        price=price,
        price_per_m2=price_per_m2,
        scores=scores,
        similarity_score=similarity_score,
        recency_weight=recency_weight,
        weight=weight,
    )


def _persist_comparable_item(
    session: Session,
    comparable_set: ComparableSet,
    candidate: ComparableCandidate,
) -> ComparableItem:
    item = ComparableItem(
        comparable_set=comparable_set,
        comparable_type=ComparableType.LISTING,
        listing=candidate.listing,
        comparable_property=candidate.comparable_property,
        similarity_score=candidate.similarity_score,
        distance_m=candidate.distance_m,
        age_days_at_analysis=candidate.age_days_at_analysis,
        price=candidate.price,
        price_per_m2=candidate.price_per_m2,
        weight=candidate.weight,
        included_in_valuation=candidate.included_in_valuation,
        exclusion_reason=candidate.exclusion_reason,
    )
    session.add(item)
    session.flush()
    return item


def _persist_success_valuation(
    session: Session,
    property_: Property,
    comparable_set: ComparableSet,
    *,
    target_data: EffectivePropertyData,
    candidates: list[ComparableCandidate],
    included_candidates: list[ComparableCandidate],
    as_of: datetime,
    data_quality_score: Decimal,
) -> Valuation:
    base_price_per_m2 = _weighted_median(
        [(candidate.price_per_m2, candidate.weight) for candidate in included_candidates]
    )
    if base_price_per_m2 is None:
        return _persist_insufficient_data_valuation(
            session,
            property_,
            comparable_set,
            as_of=as_of,
            data_quality_score=data_quality_score,
            reason="NO_WEIGHTED_PRICE",
            candidates=candidates,
        )

    adjustment = _target_adjustment_pct(target_data, included_candidates)
    adjustment_total_pct = Decimal(str(adjustment["total_pct"]))
    adjusted_price_per_m2 = (
        base_price_per_m2 * (Decimal("1") + adjustment_total_pct / Decimal("100"))
    ).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    fair_value_base = (adjusted_price_per_m2 * target_data.size_m2).quantize(
        MONEY_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )
    dispersion = _price_dispersion(included_candidates)
    confidence, confidence_factors = _valuation_confidence(
        included_candidates,
        data_quality_score=data_quality_score,
        target_data=target_data,
        dispersion=dispersion,
    )
    range_width_pct = _range_width_pct(
        confidence=confidence,
        included_count=len(included_candidates),
        dispersion=dispersion,
        data_quality_score=data_quality_score,
    )
    fair_value_low = (fair_value_base * (Decimal("1") - range_width_pct)).quantize(
        MONEY_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )
    fair_value_high = (fair_value_base * (Decimal("1") + range_width_pct)).quantize(
        MONEY_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )

    valuation = Valuation(
        property=property_,
        comparable_set=comparable_set,
        as_of=as_of,
        status=ValuationStatus.SUCCESS,
        fair_value_low=fair_value_low,
        fair_value_base=fair_value_base,
        fair_value_high=fair_value_high,
        currency=CurrencyCode.EUR,
        confidence=confidence,
        data_quality_at_analysis=data_quality_score,
        model_type=ValuationModelType.LISTING_COMPS,
        model_version=VALUATION_MODEL_VERSION,
        input_summary_json=_input_summary(
            target_data=target_data,
            candidates=candidates,
            included_candidates=included_candidates,
            selected_radius_m=comparable_set.search_parameters_json.get("selected_radius_m"),
        ),
        explanation_json=_success_explanation(
            candidates=candidates,
            included_candidates=included_candidates,
            base_price_per_m2=base_price_per_m2,
            adjusted_price_per_m2=adjusted_price_per_m2,
            adjustment=adjustment,
            range_width_pct=range_width_pct,
            confidence_factors=confidence_factors,
            dispersion=dispersion,
        ),
    )
    session.add(valuation)
    session.flush()
    return valuation


def _persist_insufficient_data_valuation(
    session: Session,
    property_: Property,
    comparable_set: ComparableSet,
    *,
    as_of: datetime,
    data_quality_score: Decimal | None,
    reason: str,
    candidates: list[ComparableCandidate],
) -> Valuation:
    valuation = Valuation(
        property=property_,
        comparable_set=comparable_set,
        as_of=as_of,
        status=ValuationStatus.INSUFFICIENT_DATA,
        fair_value_low=None,
        fair_value_base=None,
        fair_value_high=None,
        currency=CurrencyCode.EUR,
        confidence=Decimal("0.00"),
        data_quality_at_analysis=data_quality_score,
        model_type=ValuationModelType.LISTING_COMPS,
        model_version=VALUATION_MODEL_VERSION,
        input_summary_json={
            "evidence_type": "ASKING_LISTING_COMPS",
            "included_comparable_count": 0,
            "candidate_count": len(candidates),
            "minimum_required_comps": MIN_COMPS_FOR_VALUATION,
            "reason": reason,
        },
        explanation_json={
            "status": ValuationStatus.INSUFFICIENT_DATA.value,
            "reason": reason,
            "model_version": VALUATION_MODEL_VERSION,
            "comparable_engine_version": COMPARABLE_ENGINE_VERSION,
            "transaction_comparable_count": 0,
            "listing_comparable_count": len(candidates),
            "included_comparable_count": 0,
            "excluded_comps": _candidate_refs(
                [candidate for candidate in candidates if not candidate.included_in_valuation]
            ),
        },
    )
    session.add(valuation)
    session.flush()
    return valuation


def _search_parameters(
    *,
    target_data: EffectivePropertyData,
    selected_radius_m: int | None,
    input_issue: str | None,
) -> dict[str, object]:
    return {
        "comparable_types": [ComparableType.LISTING.value],
        "evidence_type": "ASKING_LISTING_COMPS",
        "radius_steps_m": list(RADIUS_STEPS_M),
        "selected_radius_m": selected_radius_m,
        "max_size_diff_pct": _decimal_to_string(MAX_SIZE_DIFF_PCT),
        "min_similarity_score": _decimal_to_string(MIN_SIMILARITY_SCORE),
        "target_comps_before_radius_stop": TARGET_COMPS_BEFORE_RADIUS_STOP,
        "min_comps_for_valuation": MIN_COMPS_FOR_VALUATION,
        "max_comparable_items": MAX_COMPARABLE_ITEMS,
        "has_target_coordinates": _has_coordinates(target_data),
        "input_issue": input_issue,
    }


def _input_summary(
    *,
    target_data: EffectivePropertyData,
    candidates: list[ComparableCandidate],
    included_candidates: list[ComparableCandidate],
    selected_radius_m: object,
) -> dict[str, object]:
    return {
        "property_id": target_data.property_id,
        "property_type": target_data.property_type,
        "target_size_m2": _decimal_to_string(target_data.size_m2),
        "target_city": target_data.city,
        "target_micro_location": target_data.micro_location,
        "selected_radius_m": selected_radius_m,
        "candidate_count": len(candidates),
        "included_comparable_count": len(included_candidates),
        "transaction_comparable_count": 0,
        "listing_comparable_count": len(candidates),
        "evidence_type": "ASKING_LISTING_COMPS",
    }


def _success_explanation(
    *,
    candidates: list[ComparableCandidate],
    included_candidates: list[ComparableCandidate],
    base_price_per_m2: Decimal,
    adjusted_price_per_m2: Decimal,
    adjustment: dict[str, object],
    range_width_pct: Decimal,
    confidence_factors: dict[str, object],
    dispersion: Decimal,
) -> dict[str, object]:
    return {
        "status": ValuationStatus.SUCCESS.value,
        "model_version": VALUATION_MODEL_VERSION,
        "comparable_engine_version": COMPARABLE_ENGINE_VERSION,
        "price_basis": "asking_listing_price_per_m2",
        "transaction_comparable_count": 0,
        "listing_comparable_count": len(candidates),
        "included_comparable_count": len(included_candidates),
        "top_comps": _candidate_refs(included_candidates[:5]),
        "excluded_comps": _candidate_refs(
            [candidate for candidate in candidates if not candidate.included_in_valuation]
        ),
        "robust_base_price_per_m2": _decimal_to_string(base_price_per_m2),
        "adjusted_price_per_m2": _decimal_to_string(adjusted_price_per_m2),
        "target_adjustments": adjustment,
        "range_width_pct": _decimal_to_string(range_width_pct * Decimal("100")),
        "range_reason": (
            "range reflects listing-only evidence, comp count, dispersion, recency, "
            "and data quality"
        ),
        "confidence_factors": confidence_factors,
        "price_dispersion": _decimal_to_string(dispersion),
    }


def _candidate_refs(candidates: list[ComparableCandidate]) -> list[dict[str, object]]:
    return [
        {
            "type": ComparableType.LISTING.value,
            "listing_id": str(candidate.listing.id),
            "property_id": str(candidate.comparable_property.id),
            "similarity": _decimal_to_string(candidate.similarity_score),
            "distance_m": _decimal_to_string(candidate.distance_m),
            "age_days_at_analysis": candidate.age_days_at_analysis,
            "price_per_m2": _decimal_to_string(candidate.price_per_m2),
            "weight": _decimal_to_string(candidate.weight),
            "included_in_valuation": candidate.included_in_valuation,
            "exclusion_reason": candidate.exclusion_reason,
        }
        for candidate in candidates
    ]


def _input_issue(target_data: EffectivePropertyData) -> str | None:
    if target_data.property_type != PropertyType.APARTMENT.value:
        return "UNSUPPORTED_PROPERTY_TYPE"
    if target_data.size_m2 is None or target_data.size_m2 <= 0:
        return "MISSING_TARGET_SIZE"
    if not _has_coordinates(target_data) and not any(
        (
            target_data.micro_location,
            target_data.neighborhood,
            target_data.municipality,
            target_data.city,
        )
    ):
        return "MISSING_TARGET_LOCATION"
    return None


def _selected_radius(candidates: list[ComparableCandidate]) -> int:
    for radius_m in RADIUS_STEPS_M:
        quality_count = sum(
            1
            for candidate in candidates
            if candidate.distance_m is not None
            and candidate.distance_m <= radius_m
            and candidate.similarity_score >= MIN_SIMILARITY_SCORE
            and (
                candidate.age_days_at_analysis is None
                or candidate.age_days_at_analysis <= MAX_COMP_AGE_DAYS
            )
        )
        if quality_count >= TARGET_COMPS_BEFORE_RADIUS_STOP:
            return radius_m
    return RADIUS_STEPS_M[-1]


def _rank_candidates(candidates: list[ComparableCandidate]) -> list[ComparableCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.included_in_valuation,
            candidate.similarity_score,
            candidate.weight,
            -(candidate.distance_m or Decimal("999999")),
        ),
        reverse=True,
    )


def _location_score(
    target_data: EffectivePropertyData,
    comp_data: EffectivePropertyData,
    distance_m: Decimal | None,
) -> Decimal:
    if distance_m is not None:
        if distance_m <= 100:
            return Decimal("1.0000")
        if distance_m <= 300:
            return Decimal("0.9000")
        if distance_m <= 500:
            return Decimal("0.7500")
        if distance_m <= 800:
            return Decimal("0.6000")
        if distance_m <= 1200:
            return Decimal("0.4500")
        return Decimal("0.0000")
    if _same_text(target_data.micro_location, comp_data.micro_location):
        return Decimal("0.8500")
    if _same_text(target_data.neighborhood, comp_data.neighborhood):
        return Decimal("0.6500")
    if _same_text(target_data.municipality, comp_data.municipality):
        return Decimal("0.4000")
    if _same_text(target_data.city, comp_data.city):
        return Decimal("0.2500")
    return Decimal("0.0000")


def _size_score(target_size: Decimal | None, comp_size: Decimal | None) -> Decimal:
    if target_size is None or comp_size is None or target_size <= 0 or comp_size <= 0:
        return Decimal("0.0000")
    size_diff_pct = abs(comp_size - target_size) / target_size
    if size_diff_pct <= Decimal("0.05"):
        return Decimal("1.0000")
    if size_diff_pct <= Decimal("0.10"):
        return Decimal("0.9000")
    if size_diff_pct <= Decimal("0.15"):
        return Decimal("0.7500")
    if size_diff_pct <= Decimal("0.20"):
        return Decimal("0.5500")
    if size_diff_pct <= Decimal("0.25"):
        return Decimal("0.3000")
    return Decimal("0.0000")


def _rooms_score(target_rooms: Decimal | None, comp_rooms: Decimal | None) -> Decimal:
    if target_rooms is None or comp_rooms is None:
        return Decimal("0.3500")
    diff = abs(target_rooms - comp_rooms)
    if diff == 0:
        return Decimal("1.0000")
    if diff <= Decimal("0.50"):
        return Decimal("0.8000")
    if diff <= Decimal("1.00"):
        return Decimal("0.5000")
    return Decimal("0.2000")


def _condition_score(target_condition: str | None, comp_condition: str | None) -> Decimal:
    target_level = _condition_level(target_condition)
    comp_level = _condition_level(comp_condition)
    if target_level is None or comp_level is None:
        return Decimal("0.3500")
    diff = abs(target_level - comp_level)
    if diff == 0:
        return Decimal("1.0000")
    if diff == 1:
        return Decimal("0.7000")
    if diff == 2:
        return Decimal("0.4000")
    return Decimal("0.2000")


def _same_text_score(target_value: str | None, comp_value: str | None) -> Decimal:
    if not _has_text(target_value) or not _has_text(comp_value):
        return Decimal("0.4000")
    return Decimal("1.0000") if _same_text(target_value, comp_value) else Decimal("0.4000")


def _floor_elevator_score(
    target_data: EffectivePropertyData,
    comp_data: EffectivePropertyData,
) -> Decimal:
    floor_score = _floor_score(target_data.floor, comp_data.floor)
    elevator_score = _boolean_score(target_data.elevator, comp_data.elevator)
    return ((floor_score * Decimal("0.55")) + (elevator_score * Decimal("0.45"))).quantize(
        SCORE_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


def _floor_score(target_floor: int | None, comp_floor: int | None) -> Decimal:
    if target_floor is None or comp_floor is None:
        return Decimal("0.4000")
    diff = abs(target_floor - comp_floor)
    if diff == 0:
        return Decimal("1.0000")
    if diff <= 1:
        return Decimal("0.8500")
    if diff <= 3:
        return Decimal("0.5500")
    return Decimal("0.2500")


def _construction_age_score(target_year: int | None, comp_year: int | None) -> Decimal:
    if target_year is None or comp_year is None:
        return Decimal("0.4500")
    diff = abs(target_year - comp_year)
    if diff <= 5:
        return Decimal("1.0000")
    if diff <= 15:
        return Decimal("0.7000")
    if diff <= 30:
        return Decimal("0.4500")
    return Decimal("0.2500")


def _boolean_score(target_value: bool | None, comp_value: bool | None) -> Decimal:
    if target_value is None or comp_value is None:
        return Decimal("0.4000")
    return Decimal("1.0000") if target_value is comp_value else Decimal("0.2500")


def _weighted_score(
    scores: dict[str, Decimal],
    weights: dict[str, Decimal],
) -> Decimal:
    score = sum(scores[key] * weights[key] for key in weights)
    return score.quantize(SCORE_QUANTIZER, rounding=ROUND_HALF_UP)


def _listing_recency_weight(age_days: int | None) -> Decimal:
    if age_days is None:
        return Decimal("0.5000")
    if age_days <= 90:
        return Decimal("1.0000")
    if age_days <= 180:
        return Decimal("0.8500")
    if age_days <= 365:
        return Decimal("0.6000")
    return Decimal("0.2500")


def _target_adjustment_pct(
    target_data: EffectivePropertyData,
    included_candidates: list[ComparableCandidate],
) -> dict[str, object]:
    factors: list[dict[str, str]] = []
    total_pct = Decimal("0.0000")
    condition_pct = _condition_adjustment_pct(target_data, included_candidates)
    if condition_pct != 0:
        total_pct += condition_pct
        factors.append({"factor": "condition", "pct": _decimal_to_string(condition_pct)})

    parking_pct = _parking_adjustment_pct(target_data, included_candidates)
    if parking_pct != 0:
        total_pct += parking_pct
        factors.append({"factor": "parking", "pct": _decimal_to_string(parking_pct)})

    capped_total = min(MAX_POSITIVE_ADJUSTMENT_PCT, max(MAX_NEGATIVE_ADJUSTMENT_PCT, total_pct))
    return {
        "factors": factors,
        "uncapped_total_pct": _decimal_to_string(total_pct),
        "total_pct": _decimal_to_string(capped_total),
        "max_positive_pct": _decimal_to_string(MAX_POSITIVE_ADJUSTMENT_PCT),
        "max_negative_pct": _decimal_to_string(MAX_NEGATIVE_ADJUSTMENT_PCT),
        "was_capped": capped_total != total_pct,
    }


def _condition_adjustment_pct(
    target_data: EffectivePropertyData,
    included_candidates: list[ComparableCandidate],
) -> Decimal:
    target_level = _condition_level(target_data.condition_category)
    comp_level = _weighted_average_condition_level(included_candidates)
    if target_level is None or comp_level is None:
        return Decimal("0.0000")
    return ((Decimal(target_level) - comp_level) * Decimal("3.0000")).quantize(
        SCORE_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


def _weighted_average_condition_level(
    included_candidates: list[ComparableCandidate],
) -> Decimal | None:
    weighted_sum = Decimal("0")
    total_weight = Decimal("0")
    for candidate in included_candidates:
        level = _condition_level(candidate.effective_data.condition_category)
        if level is None or candidate.weight <= 0:
            continue
        weighted_sum += Decimal(level) * candidate.weight
        total_weight += candidate.weight
    if total_weight <= 0:
        return None
    return (weighted_sum / total_weight).quantize(SCORE_QUANTIZER, rounding=ROUND_HALF_UP)


def _parking_adjustment_pct(
    target_data: EffectivePropertyData,
    included_candidates: list[ComparableCandidate],
) -> Decimal:
    if target_data.parking is None:
        return Decimal("0.0000")
    known = [
        candidate
        for candidate in included_candidates
        if candidate.effective_data.parking is not None
    ]
    if not known:
        return Decimal("0.0000")
    parking_share = sum(
        candidate.weight for candidate in known if candidate.effective_data.parking
    ) / sum(candidate.weight for candidate in known)
    if target_data.parking and parking_share < Decimal("0.50"):
        return Decimal("2.0000")
    if not target_data.parking and parking_share > Decimal("0.50"):
        return Decimal("-2.0000")
    return Decimal("0.0000")


def _weighted_median(values: list[tuple[Decimal, Decimal]]) -> Decimal | None:
    weighted_values = [(value, weight) for value, weight in values if weight > 0]
    if not weighted_values:
        return None
    total_weight = sum((weight for _value, weight in weighted_values), Decimal("0"))
    midpoint = total_weight / Decimal("2")
    running_weight = Decimal("0")
    for value, weight in sorted(weighted_values, key=lambda item: item[0]):
        running_weight += weight
        if running_weight >= midpoint:
            return value
    return weighted_values[-1][0]


def _valuation_confidence(
    included_candidates: list[ComparableCandidate],
    *,
    data_quality_score: Decimal,
    target_data: EffectivePropertyData,
    dispersion: Decimal,
) -> tuple[Decimal, dict[str, object]]:
    count_points = _count_quality_points(len(included_candidates))
    similarity_points = _average(
        [candidate.similarity_score for candidate in included_candidates]
    ) * Decimal("25")
    transaction_share_points = Decimal("0")
    data_quality_points = data_quality_score / Decimal("100") * Decimal("15")
    dispersion_points = _dispersion_points(dispersion)
    recency_points = _average(
        [candidate.recency_weight for candidate in included_candidates]
    ) * Decimal("10")
    penalty_points = _confidence_penalty_points(target_data)
    raw_score = (
        count_points
        + similarity_points
        + transaction_share_points
        + data_quality_points
        + dispersion_points
        + recency_points
        - penalty_points
    )
    score = min(Decimal("100"), max(Decimal("0"), raw_score)).quantize(
        CONFIDENCE_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )
    factors = {
        "comparable_count_quality": _decimal_to_string(count_points),
        "comparable_similarity": _decimal_to_string(similarity_points),
        "transaction_data_share": _decimal_to_string(transaction_share_points),
        "data_quality": _decimal_to_string(data_quality_points),
        "price_dispersion": _decimal_to_string(dispersion_points),
        "recency": _decimal_to_string(recency_points),
        "penalties": _decimal_to_string(penalty_points),
        "category": _confidence_category(score),
    }
    return score, factors


def _count_quality_points(count: int) -> Decimal:
    if count >= 8:
        return Decimal("20.0000")
    if count >= 4:
        return Decimal("14.0000")
    if count >= 1:
        return Decimal("8.0000")
    return Decimal("0.0000")


def _dispersion_points(dispersion: Decimal) -> Decimal:
    if dispersion <= Decimal("0.03"):
        return Decimal("10.0000")
    if dispersion <= Decimal("0.08"):
        return Decimal("7.0000")
    if dispersion <= Decimal("0.15"):
        return Decimal("4.0000")
    return Decimal("1.0000")


def _confidence_penalty_points(target_data: EffectivePropertyData) -> Decimal:
    penalties = Decimal("0")
    if target_data.location_precision in {"CITY", "MUNICIPALITY"}:
        penalties += Decimal("5")
    if _condition_level(target_data.condition_category) is None:
        penalties += Decimal("5")
    return penalties


def _confidence_category(score: Decimal) -> str:
    if score <= 39:
        return "LOW"
    if score <= 59:
        return "LIMITED"
    if score <= 74:
        return "MODERATE"
    if score <= 89:
        return "HIGH"
    return "VERY_HIGH"


def _range_width_pct(
    *,
    confidence: Decimal,
    included_count: int,
    dispersion: Decimal,
    data_quality_score: Decimal,
) -> Decimal:
    width = Decimal("0.10")
    if confidence < Decimal("40"):
        width += Decimal("0.12")
    elif confidence < Decimal("60"):
        width += Decimal("0.08")
    elif confidence < Decimal("75"):
        width += Decimal("0.05")

    if included_count < 4:
        width += Decimal("0.08")
    elif included_count < 8:
        width += Decimal("0.04")

    width += min(Decimal("0.10"), dispersion)
    if data_quality_score < Decimal("60"):
        width += Decimal("0.05")
    return min(Decimal("0.35"), max(Decimal("0.08"), width)).quantize(
        SCORE_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


def _price_dispersion(candidates: list[ComparableCandidate]) -> Decimal:
    values = [candidate.price_per_m2 for candidate in candidates]
    if len(values) < 2:
        return Decimal("1.0000")
    median = _median(values)
    if median is None or median <= 0:
        return Decimal("1.0000")
    q1 = _percentile(sorted(values), Decimal("0.25"))
    q3 = _percentile(sorted(values), Decimal("0.75"))
    return ((q3 - q1) / median).copy_abs().quantize(SCORE_QUANTIZER, rounding=ROUND_HALF_UP)


def _percentile(sorted_values: list[Decimal], percentile: Decimal) -> Decimal:
    if not sorted_values:
        return Decimal("0")
    if len(sorted_values) == 1:
        return sorted_values[0]
    raw_index = Decimal(len(sorted_values) - 1) * percentile
    lower_index = int(raw_index)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = raw_index - Decimal(lower_index)
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    return lower_value + ((upper_value - lower_value) * fraction)


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    sorted_values = sorted(values)
    middle = len(sorted_values) // 2
    if len(sorted_values) % 2 == 1:
        return sorted_values[middle]
    return (sorted_values[middle - 1] + sorted_values[middle]) / Decimal("2")


def _has_coordinates(data: EffectivePropertyData) -> bool:
    return data.latitude is not None and data.longitude is not None


def _days_between(later: datetime, earlier: datetime | None) -> int | None:
    if earlier is None:
        return None
    delta = _aware_datetime(later) - _aware_datetime(earlier)
    return max(delta.days, 0)


def _average(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _condition_level(value: str | None) -> int | None:
    if not _has_text(value):
        return None
    normalized = value.strip().upper()
    if normalized in {"MAJOR_RENOVATION", "RUIN"}:
        return 0
    if normalized in {"NEEDS_RENOVATION", "FOR_RENOVATION"}:
        return 1
    if normalized in {"DATED_HABITABLE", "HABITABLE"}:
        return 2
    if normalized in {"GOOD", "ORIGINAL"}:
        return 3
    if normalized in {"RENOVATED", "REFURBISHED"}:
        return 4
    if normalized in {"NEW_OR_LUXURY", "NEW", "LUXURY"}:
        return 5

    lowered = value.lower()
    if "renov" in lowered:
        return 4
    if "lux" in lowered or "new" in lowered or "nov" in lowered:
        return 5
    if "good" in lowered or "dob" in lowered:
        return 3
    if "habitable" in lowered or "usel" in lowered:
        return 2
    if "needs" in lowered or "renoviranje" in lowered or "adapt" in lowered:
        return 1
    return None


def _same_text(left: str | None, right: str | None) -> bool:
    if not _has_text(left) or not _has_text(right):
        return False
    return left.strip().casefold() == right.strip().casefold()


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _decimal_to_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _utcnow() -> datetime:
    return datetime.now(UTC)
