from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    FastSaleEstimate,
    LiquidityAssessment,
    Property,
    PropertyFeature,
    Valuation,
)
from app.domain.enums import (
    FastSaleStatus,
    LiquidityStatus,
    PropertyType,
    ValuationStatus,
)
from app.features.property_dataset import (
    EffectivePropertyData,
    MarketDatasetResult,
    recalculate_property_market_dataset,
)

LIQUIDITY_MODEL_VERSION = "liquidity_rules_v1"
FAST_SALE_MODEL_VERSION = "fast_sale_v1"
DEFAULT_TARGET_DAYS = 60

SCORE_QUANTIZER = Decimal("0.01")
MONEY_QUANTIZER = Decimal("0.01")

HIGH_LIQUIDITY_THRESHOLD = Decimal("75.00")
MEDIUM_LIQUIDITY_THRESHOLD = Decimal("50.00")

HIGH_LIQUIDITY_DISCOUNTS = {
    "low": Decimal("0.08"),
    "base": Decimal("0.06"),
    "high": Decimal("0.04"),
}
MEDIUM_LIQUIDITY_DISCOUNTS = {
    "low": Decimal("0.12"),
    "base": Decimal("0.09"),
    "high": Decimal("0.07"),
}
LOW_LIQUIDITY_DISCOUNTS = {
    "low": Decimal("0.18"),
    "base": Decimal("0.14"),
    "high": Decimal("0.10"),
}

HIGH_DEMAND_MICRO_LOCATIONS = {
    "a blok",
    "belville",
    "blok 21",
    "blok 30",
    "blok 45",
    "blok 63",
    "retencija",
    "savski kej",
    "yubc",
}

COMMON_BUILDING_TYPES = {
    "new",
    "new_building",
    "newer_building",
    "novogradnja",
    "standard",
}
WEAK_BUILDING_TYPES = {
    "baraka",
    "old",
    "stara gradnja",
    "suteren",
}


@dataclass(frozen=True)
class LiquidityRunResult:
    liquidity_assessment: LiquidityAssessment
    fast_sale_estimate: FastSaleEstimate


@dataclass(frozen=True)
class LiquidityScoreResult:
    liquidity_score: Decimal
    confidence: Decimal
    level: str
    positive_factors: list[dict[str, object]]
    negative_factors: list[dict[str, object]]
    unknown_important_factors: list[str]
    input_summary: dict[str, object]


def assess_liquidity_and_fast_sale(
    session: Session,
    property_: Property,
    *,
    valuation: Valuation | None = None,
    as_of: datetime | None = None,
    target_days: int = DEFAULT_TARGET_DAYS,
    commit: bool = False,
) -> LiquidityRunResult:
    if target_days <= 0:
        raise ValueError("target_days must be positive")

    if as_of is not None:
        analysis_as_of = _aware_datetime(as_of)
    elif valuation is not None:
        analysis_as_of = _aware_datetime(valuation.as_of)
    else:
        analysis_as_of = _utcnow()
    selected_valuation = valuation or _latest_successful_valuation(
        session, property_, analysis_as_of
    )
    if not _has_successful_valuation(selected_valuation):
        reason = _insufficient_reason(selected_valuation)
        liquidity_assessment = _persist_insufficient_liquidity(
            session,
            property_,
            selected_valuation,
            as_of=analysis_as_of,
            reason=reason,
        )
        fast_sale_estimate = _persist_insufficient_fast_sale(
            session,
            property_,
            selected_valuation,
            liquidity_assessment,
            as_of=analysis_as_of,
            target_days=target_days,
            reason=reason,
        )
    else:
        market_dataset = recalculate_property_market_dataset(
            session,
            property_,
            as_of=analysis_as_of,
        )
        score_result = score_liquidity(market_dataset, selected_valuation)
        liquidity_assessment = _persist_success_liquidity(
            session,
            property_,
            selected_valuation,
            as_of=analysis_as_of,
            score_result=score_result,
        )
        fast_sale_estimate = _persist_success_fast_sale(
            session,
            property_,
            selected_valuation,
            liquidity_assessment,
            score_result=score_result,
            as_of=analysis_as_of,
            target_days=target_days,
        )

    if commit:
        session.commit()
    return LiquidityRunResult(
        liquidity_assessment=liquidity_assessment,
        fast_sale_estimate=fast_sale_estimate,
    )


def score_liquidity(
    market_dataset: MarketDatasetResult,
    valuation: Valuation,
) -> LiquidityScoreResult:
    data = market_dataset.effective_data
    feature = market_dataset.feature
    score = Decimal("50.00")
    positive: list[dict[str, object]] = []
    negative: list[dict[str, object]] = []
    unknown: list[str] = []

    score += _score_location(data, positive, negative, unknown)
    score += _score_size(data, positive, negative, unknown)
    score += _score_rooms(data, positive, negative, unknown)
    score += _score_floor_elevator(data, positive, negative, unknown)
    score += _score_condition(data, positive, negative, unknown)
    score += _score_parking(data, positive, negative, unknown)
    score += _score_building_type(data, positive, negative, unknown)
    score += _score_asking_vs_fmv(feature, valuation, positive, negative, unknown)
    score += _score_inventory(valuation, positive, negative)

    liquidity_score = _clamp_score(score)
    confidence = _liquidity_confidence(
        market_dataset,
        valuation,
        unknown_important_factors=unknown,
    )
    level = _liquidity_level(liquidity_score)
    return LiquidityScoreResult(
        liquidity_score=liquidity_score,
        confidence=confidence,
        level=level,
        positive_factors=positive,
        negative_factors=negative,
        unknown_important_factors=unknown,
        input_summary=_liquidity_input_summary(data, feature, valuation),
    )


def _latest_successful_valuation(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> Valuation | None:
    return session.scalars(
        select(Valuation)
        .where(
            Valuation.property_id == property_.id,
            Valuation.as_of <= as_of,
            Valuation.status == ValuationStatus.SUCCESS,
        )
        .order_by(Valuation.as_of.desc(), Valuation.created_at.desc(), Valuation.id.desc())
    ).first()


def _has_successful_valuation(valuation: Valuation | None) -> bool:
    return (
        valuation is not None
        and valuation.status == ValuationStatus.SUCCESS
        and valuation.fair_value_base is not None
        and valuation.fair_value_base > 0
    )


def _insufficient_reason(valuation: Valuation | None) -> str:
    if valuation is None:
        return "MISSING_SUCCESSFUL_VALUATION"
    if valuation.status != ValuationStatus.SUCCESS:
        return "VALUATION_INSUFFICIENT_DATA"
    return "MISSING_FAIR_VALUE_BASE"


def _persist_success_liquidity(
    session: Session,
    property_: Property,
    valuation: Valuation,
    *,
    as_of: datetime,
    score_result: LiquidityScoreResult,
) -> LiquidityAssessment:
    assessment = LiquidityAssessment(
        property=property_,
        valuation=valuation,
        as_of=as_of,
        status=LiquidityStatus.SUCCESS,
        liquidity_score=score_result.liquidity_score,
        confidence=score_result.confidence,
        probability_sale_30d=None,
        probability_sale_60d=None,
        probability_sale_90d=None,
        positive_factors_json={
            "model_version": LIQUIDITY_MODEL_VERSION,
            "liquidity_level": score_result.level,
            "factors": score_result.positive_factors,
            "input_summary": score_result.input_summary,
        },
        negative_factors_json={
            "model_version": LIQUIDITY_MODEL_VERSION,
            "factors": score_result.negative_factors,
            "unknown_important_factors": score_result.unknown_important_factors,
            "probability_fields": "not_available_until_outcome_model_exists",
        },
        model_version=LIQUIDITY_MODEL_VERSION,
    )
    session.add(assessment)
    session.flush()
    return assessment


def _persist_insufficient_liquidity(
    session: Session,
    property_: Property,
    valuation: Valuation | None,
    *,
    as_of: datetime,
    reason: str,
) -> LiquidityAssessment:
    assessment = LiquidityAssessment(
        property=property_,
        valuation=valuation,
        as_of=as_of,
        status=LiquidityStatus.INSUFFICIENT_DATA,
        liquidity_score=None,
        confidence=Decimal("0.00"),
        probability_sale_30d=None,
        probability_sale_60d=None,
        probability_sale_90d=None,
        positive_factors_json={
            "model_version": LIQUIDITY_MODEL_VERSION,
            "factors": [],
        },
        negative_factors_json={
            "model_version": LIQUIDITY_MODEL_VERSION,
            "factors": [{"code": reason, "label": reason, "points": "0.00"}],
            "unknown_important_factors": [],
            "reason": reason,
            "probability_fields": "not_available_until_outcome_model_exists",
        },
        model_version=LIQUIDITY_MODEL_VERSION,
    )
    session.add(assessment)
    session.flush()
    return assessment


def _persist_success_fast_sale(
    session: Session,
    property_: Property,
    valuation: Valuation,
    liquidity_assessment: LiquidityAssessment,
    *,
    score_result: LiquidityScoreResult,
    as_of: datetime,
    target_days: int,
) -> FastSaleEstimate:
    fair_value_base = _required_money(valuation.fair_value_base)
    discounts = _fast_sale_discounts(
        score_result.level,
        valuation=valuation,
        target_days=target_days,
    )
    value_low = _discounted_value(fair_value_base, discounts["low"])
    value_base = _discounted_value(fair_value_base, discounts["base"])
    value_high = _discounted_value(fair_value_base, discounts["high"])
    confidence = _fast_sale_confidence(
        liquidity_confidence=score_result.confidence,
        valuation_confidence=valuation.confidence,
        target_days=target_days,
    )
    estimate = FastSaleEstimate(
        property=property_,
        valuation=valuation,
        liquidity_assessment=liquidity_assessment,
        as_of=as_of,
        status=FastSaleStatus.SUCCESS,
        value_low=value_low,
        value_base=value_base,
        value_high=value_high,
        target_days=target_days,
        target_probability=None,
        confidence=confidence,
        model_version=FAST_SALE_MODEL_VERSION,
        explanation_json={
            "status": FastSaleStatus.SUCCESS.value,
            "model_version": FAST_SALE_MODEL_VERSION,
            "valuation_id": str(valuation.id),
            "liquidity_assessment_id": str(liquidity_assessment.id),
            "liquidity_model_version": LIQUIDITY_MODEL_VERSION,
            "valuation_model_version": valuation.model_version,
            "fair_value_base": _decimal_to_string(fair_value_base),
            "liquidity_score": _decimal_to_string(score_result.liquidity_score),
            "liquidity_level": score_result.level,
            "liquidity_confidence": _decimal_to_string(score_result.confidence),
            "valuation_confidence": _decimal_to_string(valuation.confidence),
            "valuation_price_dispersion": _decimal_to_string(_valuation_dispersion(valuation)),
            "target_days": target_days,
            "target_day_context": _target_day_context(target_days),
            "discounts": {
                key: _decimal_to_string(value * Decimal("100")) for key, value in discounts.items()
            },
            "target_probability": None,
            "probability_reason": "not_available_until_outcome_model_exists",
        },
    )
    session.add(estimate)
    session.flush()
    return estimate


def _persist_insufficient_fast_sale(
    session: Session,
    property_: Property,
    valuation: Valuation | None,
    liquidity_assessment: LiquidityAssessment,
    *,
    as_of: datetime,
    target_days: int,
    reason: str,
) -> FastSaleEstimate:
    estimate = FastSaleEstimate(
        property=property_,
        valuation=valuation,
        liquidity_assessment=liquidity_assessment,
        as_of=as_of,
        status=FastSaleStatus.INSUFFICIENT_DATA,
        value_low=None,
        value_base=None,
        value_high=None,
        target_days=target_days,
        target_probability=None,
        confidence=Decimal("0.00"),
        model_version=FAST_SALE_MODEL_VERSION,
        explanation_json={
            "status": FastSaleStatus.INSUFFICIENT_DATA.value,
            "model_version": FAST_SALE_MODEL_VERSION,
            "reason": reason,
            "target_days": target_days,
            "target_probability": None,
            "probability_reason": "not_available_until_outcome_model_exists",
        },
    )
    session.add(estimate)
    session.flush()
    return estimate


def _score_location(
    data: EffectivePropertyData,
    positive: list[dict[str, object]],
    negative: list[dict[str, object]],
    unknown: list[str],
) -> Decimal:
    if _has_text(data.micro_location):
        normalized_micro = data.micro_location.strip().casefold()
        if normalized_micro in HIGH_DEMAND_MICRO_LOCATIONS:
            return _factor(
                positive,
                code="HIGH_DEMAND_MICRO_LOCATION",
                label="High-demand micro-location",
                points=Decimal("14.00"),
            )
        return _factor(
            positive,
            code="KNOWN_MICRO_LOCATION",
            label="Known micro-location",
            points=Decimal("8.00"),
        )
    if _has_text(data.neighborhood):
        return _factor(
            positive,
            code="KNOWN_NEIGHBORHOOD",
            label="Known neighborhood",
            points=Decimal("5.00"),
        )
    if _has_text(data.municipality) or _has_text(data.city):
        return _factor(
            negative,
            code="COARSE_LOCATION",
            label="Only coarse location is known",
            points=Decimal("-8.00"),
        )
    unknown.append("location")
    return Decimal("0.00")


def _score_size(
    data: EffectivePropertyData,
    positive: list[dict[str, object]],
    negative: list[dict[str, object]],
    unknown: list[str],
) -> Decimal:
    if data.size_m2 is None:
        unknown.append("size_m2")
        return Decimal("0.00")
    if data.property_type == PropertyType.APARTMENT.value:
        if Decimal("35") <= data.size_m2 <= Decimal("90"):
            return _factor(
                positive,
                code="COMMON_APARTMENT_SIZE",
                label="Common apartment size segment",
                points=Decimal("12.00"),
            )
        if Decimal("25") <= data.size_m2 < Decimal("35") or Decimal("90") < data.size_m2 <= Decimal(
            "110"
        ):
            return _factor(
                positive,
                code="ACCEPTABLE_APARTMENT_SIZE",
                label="Acceptable apartment size segment",
                points=Decimal("4.00"),
            )
        return _factor(
            negative,
            code="UNUSUAL_APARTMENT_SIZE",
            label="Unusual apartment size segment",
            points=Decimal("-10.00"),
        )
    return Decimal("0.00")


def _score_rooms(
    data: EffectivePropertyData,
    positive: list[dict[str, object]],
    negative: list[dict[str, object]],
    unknown: list[str],
) -> Decimal:
    if data.rooms is None:
        unknown.append("rooms")
        return Decimal("0.00")
    if Decimal("1.50") <= data.rooms <= Decimal("3.50"):
        return _factor(
            positive,
            code="COMMON_ROOM_COUNT",
            label="Common room count",
            points=Decimal("6.00"),
        )
    if data.rooms <= Decimal("1.00") or data.rooms >= Decimal("5.00"):
        return _factor(
            negative,
            code="UNUSUAL_ROOM_COUNT",
            label="Unusual room count",
            points=Decimal("-4.00"),
        )
    return Decimal("0.00")


def _score_floor_elevator(
    data: EffectivePropertyData,
    positive: list[dict[str, object]],
    negative: list[dict[str, object]],
    unknown: list[str],
) -> Decimal:
    if data.floor is None:
        unknown.append("floor")
        if data.elevator is None:
            unknown.append("elevator")
        return Decimal("0.00")
    if data.elevator is None:
        unknown.append("elevator")
        if 1 <= data.floor <= 6:
            return _factor(
                positive,
                code="NORMAL_FLOOR",
                label="Normal floor",
                points=Decimal("3.00"),
            )
        return Decimal("0.00")
    if data.floor >= 7 and not data.elevator:
        return _factor(
            negative,
            code="HIGH_FLOOR_NO_ELEVATOR",
            label="High floor without elevator",
            points=Decimal("-12.00"),
        )
    if data.floor >= 4 and not data.elevator:
        return _factor(
            negative,
            code="UPPER_FLOOR_NO_ELEVATOR",
            label="Upper floor without elevator",
            points=Decimal("-8.00"),
        )
    if 1 <= data.floor <= 6:
        return _factor(
            positive,
            code="NORMAL_FLOOR_WITH_ELEVATOR_SIGNAL",
            label="Normal floor/elevator profile",
            points=Decimal("6.00"),
        )
    if data.floor == 0:
        return _factor(
            negative,
            code="GROUND_FLOOR",
            label="Ground-floor liquidity penalty",
            points=Decimal("-3.00"),
        )
    if data.floor >= 7 and data.elevator:
        return _factor(
            positive,
            code="HIGH_FLOOR_WITH_ELEVATOR",
            label="High floor has elevator",
            points=Decimal("2.00"),
        )
    return Decimal("0.00")


def _score_condition(
    data: EffectivePropertyData,
    positive: list[dict[str, object]],
    negative: list[dict[str, object]],
    unknown: list[str],
) -> Decimal:
    condition_level = _condition_level(data.condition_category)
    if condition_level is None:
        unknown.append("condition")
        return Decimal("0.00")
    if condition_level >= 4:
        return _factor(
            positive,
            code="STRONG_CONDITION",
            label="Strong condition",
            points=Decimal("10.00"),
        )
    if condition_level == 3:
        return _factor(
            positive,
            code="GOOD_CONDITION",
            label="Good condition",
            points=Decimal("6.00"),
        )
    if condition_level == 2:
        return _factor(
            negative,
            code="DATED_BUT_HABITABLE",
            label="Dated but habitable condition",
            points=Decimal("-3.00"),
        )
    if condition_level == 1:
        return _factor(
            negative,
            code="NEEDS_RENOVATION",
            label="Needs renovation",
            points=Decimal("-8.00"),
        )
    return _factor(
        negative,
        code="MAJOR_RENOVATION",
        label="Major renovation required",
        points=Decimal("-14.00"),
    )


def _score_parking(
    data: EffectivePropertyData,
    positive: list[dict[str, object]],
    negative: list[dict[str, object]],
    unknown: list[str],
) -> Decimal:
    if data.parking is None:
        unknown.append("parking")
        return Decimal("0.00")
    if data.parking:
        return _factor(
            positive,
            code="PARKING_AVAILABLE",
            label="Parking available",
            points=Decimal("3.00"),
        )
    return _factor(
        negative,
        code="PARKING_NOT_CONFIRMED",
        label="Parking not confirmed",
        points=Decimal("-2.00"),
    )


def _score_building_type(
    data: EffectivePropertyData,
    positive: list[dict[str, object]],
    negative: list[dict[str, object]],
    unknown: list[str],
) -> Decimal:
    if not _has_text(data.building_type):
        unknown.append("building_type")
        return Decimal("0.00")
    normalized = data.building_type.strip().casefold()
    if normalized in COMMON_BUILDING_TYPES:
        return _factor(
            positive,
            code="COMMON_BUILDING_TYPE",
            label="Common building type",
            points=Decimal("4.00"),
        )
    if normalized in WEAK_BUILDING_TYPES:
        return _factor(
            negative,
            code="WEAK_BUILDING_TYPE",
            label="Weak building type signal",
            points=Decimal("-4.00"),
        )
    return Decimal("0.00")


def _score_asking_vs_fmv(
    feature: PropertyFeature,
    valuation: Valuation,
    positive: list[dict[str, object]],
    negative: list[dict[str, object]],
    unknown: list[str],
) -> Decimal:
    asking_price = feature.current_lowest_asking_price
    fair_value_base = valuation.fair_value_base
    if asking_price is None or fair_value_base is None or fair_value_base <= 0:
        unknown.append("asking_price_to_fair_value")
        return Decimal("0.00")
    ratio = asking_price / fair_value_base
    if ratio <= Decimal("1.00"):
        return _factor(
            positive,
            code="ASKING_AT_OR_BELOW_FMV",
            label="Asking price is at or below FMV",
            points=Decimal("3.00"),
        )
    if ratio <= Decimal("1.05"):
        return _factor(
            positive,
            code="ASKING_NEAR_FMV",
            label="Asking price is near FMV",
            points=Decimal("1.00"),
        )
    if ratio > Decimal("1.15"):
        return _factor(
            negative,
            code="ASKING_WELL_ABOVE_FMV",
            label="Asking price is materially above FMV",
            points=Decimal("-10.00"),
        )
    return Decimal("0.00")


def _score_inventory(
    valuation: Valuation,
    positive: list[dict[str, object]],
    negative: list[dict[str, object]],
) -> Decimal:
    included_count = _included_comparable_count(valuation)
    if included_count >= 8:
        return _factor(
            positive,
            code="DEEP_COMPARABLE_INVENTORY",
            label="Deep similar-property inventory",
            points=Decimal("5.00"),
        )
    if included_count >= 4:
        return _factor(
            positive,
            code="ADEQUATE_COMPARABLE_INVENTORY",
            label="Adequate similar-property inventory",
            points=Decimal("2.00"),
        )
    return _factor(
        negative,
        code="THIN_COMPARABLE_INVENTORY",
        label="Thin similar-property inventory",
        points=Decimal("-2.00"),
    )


def _liquidity_confidence(
    market_dataset: MarketDatasetResult,
    valuation: Valuation,
    *,
    unknown_important_factors: list[str],
) -> Decimal:
    known_signal_count = Decimal(9 - len(set(unknown_important_factors)))
    known_ratio = max(Decimal("0"), known_signal_count / Decimal("9"))
    valuation_confidence = valuation.confidence or Decimal("0")
    data_quality_score = market_dataset.data_quality.score or Decimal("0")
    comparable_depth = Decimal(min(_included_comparable_count(valuation), 8)) / Decimal("8")
    raw_score = (
        Decimal("10")
        + (valuation_confidence * Decimal("0.35"))
        + (data_quality_score * Decimal("0.25"))
        + (known_ratio * Decimal("25"))
        + (comparable_depth * Decimal("5"))
    )
    return _clamp_score(raw_score)


def _fast_sale_discounts(
    liquidity_level: str,
    *,
    valuation: Valuation,
    target_days: int,
) -> dict[str, Decimal]:
    if liquidity_level == "HIGH":
        discounts = dict(HIGH_LIQUIDITY_DISCOUNTS)
    elif liquidity_level == "MEDIUM":
        discounts = dict(MEDIUM_LIQUIDITY_DISCOUNTS)
    else:
        discounts = dict(LOW_LIQUIDITY_DISCOUNTS)

    valuation_confidence = valuation.confidence or Decimal("0")
    if valuation_confidence < Decimal("40"):
        _add_discount(discounts, Decimal("0.04"))
    elif valuation_confidence < Decimal("60"):
        _add_discount(discounts, Decimal("0.02"))

    dispersion = _valuation_dispersion(valuation)
    if dispersion > Decimal("0.15"):
        _add_discount(discounts, Decimal("0.02"))
    elif dispersion > Decimal("0.08"):
        _add_discount(discounts, Decimal("0.01"))

    if target_days <= 30:
        _add_discount(discounts, Decimal("0.02"))
    elif target_days >= 90:
        _add_discount(discounts, Decimal("-0.02"))

    return {
        "low": max(Decimal("0.01"), discounts["low"]),
        "base": max(Decimal("0.01"), discounts["base"]),
        "high": max(Decimal("0.01"), discounts["high"]),
    }


def _fast_sale_confidence(
    *,
    liquidity_confidence: Decimal,
    valuation_confidence: Decimal,
    target_days: int,
) -> Decimal:
    base = min(liquidity_confidence, valuation_confidence or Decimal("0"))
    if target_days <= 30:
        base -= Decimal("5.00")
    elif target_days >= 90:
        base += Decimal("2.00")
    return _clamp_score(base)


def _liquidity_input_summary(
    data: EffectivePropertyData,
    feature: PropertyFeature,
    valuation: Valuation,
) -> dict[str, object]:
    return {
        "property_type": data.property_type,
        "city": data.city,
        "municipality": data.municipality,
        "neighborhood": data.neighborhood,
        "micro_location": data.micro_location,
        "location_precision": data.location_precision,
        "size_m2": _decimal_to_string(data.size_m2),
        "rooms": _decimal_to_string(data.rooms),
        "floor": data.floor,
        "elevator": data.elevator,
        "condition_category": data.condition_category,
        "parking": data.parking,
        "building_type": data.building_type,
        "current_lowest_asking_price": _decimal_to_string(feature.current_lowest_asking_price),
        "active_listing_count": feature.active_listing_count,
        "known_listing_count": feature.known_listing_count,
        "valuation_id": str(valuation.id),
        "valuation_confidence": _decimal_to_string(valuation.confidence),
        "included_comparable_count": _included_comparable_count(valuation),
    }


def _included_comparable_count(valuation: Valuation) -> int:
    input_summary_value = valuation.input_summary_json.get("included_comparable_count")
    if isinstance(input_summary_value, int):
        return input_summary_value
    if isinstance(input_summary_value, str) and input_summary_value.isdigit():
        return int(input_summary_value)
    explanation_value = valuation.explanation_json.get("included_comparable_count")
    if isinstance(explanation_value, int):
        return explanation_value
    if isinstance(explanation_value, str) and explanation_value.isdigit():
        return int(explanation_value)
    return 0


def _valuation_dispersion(valuation: Valuation) -> Decimal:
    raw_value = valuation.explanation_json.get("price_dispersion")
    if raw_value is None:
        return Decimal("1.0000")
    try:
        return Decimal(str(raw_value))
    except (InvalidOperation, ValueError):
        return Decimal("1.0000")


def _discounted_value(value: Decimal, discount: Decimal) -> Decimal:
    return (value * (Decimal("1") - discount)).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def _add_discount(discounts: dict[str, Decimal], adjustment: Decimal) -> None:
    discounts["low"] += adjustment
    discounts["base"] += adjustment
    discounts["high"] += adjustment


def _target_day_context(target_days: int) -> str:
    if target_days <= 30:
        return "short_fast_sale_horizon"
    if target_days >= 90:
        return "extended_fast_sale_horizon"
    return "standard_fast_sale_horizon"


def _liquidity_level(score: Decimal) -> str:
    if score >= HIGH_LIQUIDITY_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_LIQUIDITY_THRESHOLD:
        return "MEDIUM"
    return "LOW"


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

    lowered = value.casefold()
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


def _factor(
    factors: list[dict[str, object]],
    *,
    code: str,
    label: str,
    points: Decimal,
) -> Decimal:
    factors.append(
        {
            "code": code,
            "label": label,
            "points": _decimal_to_string(points),
        }
    )
    return points


def _required_money(value: Decimal | None) -> Decimal:
    if value is None:
        raise ValueError("money value is required")
    return value


def _clamp_score(value: Decimal) -> Decimal:
    return min(Decimal("100"), max(Decimal("0"), value)).quantize(
        SCORE_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


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
