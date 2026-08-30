from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.state import mark_modules_stale, mark_modules_success, status_from_analysis_row
from app.db.models import (
    CallFeedback,
    FastSaleEstimate,
    Interaction,
    LiquidityAssessment,
    Offer,
    PipelineStatusEvent,
    Property,
    PropertyOutcome,
    PropertyOverride,
    PropertyReview,
    SkipRecord,
    Valuation,
    VisitFeedback,
)
from app.deals.deal_engine import analyze_deal
from app.domain.enums import (
    AnalysisStatus,
    CurrencyCode,
    DataSourceKind,
    FastSaleStatus,
    InteractionType,
    LiquidityStatus,
    OfferStatus,
    PropertyOutcomeType,
    PropertyPipelineStatus,
    PropertyReviewDecision,
    SkipReasonCode,
    ValuationStatus,
)
from app.intelligence.seller_risk import assess_seller_intelligence_and_risk
from app.liquidity.liquidity_engine import assess_liquidity_and_fast_sale
from app.opportunities.opportunity_engine import assess_opportunity
from app.valuation.comparable_engine import value_property

ACQUISITION_REANALYSIS_VERSION = "acquisition_feedback_reanalysis_v1"

PIPELINE_RANK = {
    PropertyPipelineStatus.NEW: 0,
    PropertyPipelineStatus.REVIEWED: 10,
    PropertyPipelineStatus.CALLED: 20,
    PropertyPipelineStatus.VISIT_SCHEDULED: 30,
    PropertyPipelineStatus.VISITED: 40,
    PropertyPipelineStatus.DUE_DILIGENCE: 50,
    PropertyPipelineStatus.OFFERED: 60,
    PropertyPipelineStatus.NEGOTIATING: 70,
    PropertyPipelineStatus.WON: 80,
    PropertyPipelineStatus.LOST: 80,
    PropertyPipelineStatus.SKIPPED: 80,
    PropertyPipelineStatus.SOLD: 80,
}
TERMINAL_PIPELINE_STATUSES = {
    PropertyPipelineStatus.WON,
    PropertyPipelineStatus.LOST,
    PropertyPipelineStatus.SKIPPED,
    PropertyPipelineStatus.SOLD,
}


@dataclass(frozen=True)
class AcquisitionCommandResult:
    record: Any
    pipeline_event: PipelineStatusEvent | None
    reanalyzed_modules: tuple[str, ...] = ()
    invalidated_modules: tuple[str, ...] = ()


def set_pipeline_status(
    session: Session,
    property_: Property,
    status: PropertyPipelineStatus,
    *,
    occurred_at: datetime | None = None,
    source_kind: DataSourceKind = DataSourceKind.MANUAL,
    source_reference: str | None = None,
    reason: str | None = None,
    commit: bool = False,
) -> PipelineStatusEvent | None:
    timestamp = _aware_datetime(occurred_at or _utcnow())
    old_status = property_.pipeline_status
    if old_status == status:
        property_.pipeline_status_updated_at = property_.pipeline_status_updated_at or timestamp
        if commit:
            session.commit()
        return None

    property_.pipeline_status = status
    property_.pipeline_status_updated_at = timestamp
    event = PipelineStatusEvent(
        property=property_,
        old_status=old_status,
        new_status=status,
        source_kind=source_kind,
        source_reference=source_reference,
        reason=reason,
        occurred_at=timestamp,
    )
    session.add(event)
    session.flush()
    if commit:
        session.commit()
    return event


def record_property_review(
    session: Session,
    property_: Property,
    *,
    decision: PropertyReviewDecision,
    reviewed_at: datetime | None = None,
    manual_fmv: Decimal | None = None,
    manual_fast_sale_value: Decimal | None = None,
    manual_max_buy_price: Decimal | None = None,
    notes: str | None = None,
    commit: bool = False,
) -> AcquisitionCommandResult:
    timestamp = _aware_datetime(reviewed_at or _utcnow())
    review = PropertyReview(
        property=property_,
        reviewed_at=timestamp,
        decision=decision,
        manual_fmv=manual_fmv,
        manual_fast_sale_value=manual_fast_sale_value,
        manual_max_buy_price=manual_max_buy_price,
        notes=notes,
    )
    session.add(review)
    session.flush()

    _record_manual_estimate_overrides(
        session,
        property_,
        source_reference=str(review.id),
        source_kind=DataSourceKind.MANUAL,
        manual_fmv=manual_fmv,
        manual_fast_sale_value=manual_fast_sale_value,
        manual_max_buy_price=manual_max_buy_price,
        reason="property_review",
    )
    invalidated = _manual_estimate_invalidations(
        manual_fmv=manual_fmv,
        manual_fast_sale_value=manual_fast_sale_value,
        manual_max_buy_price=manual_max_buy_price,
    )
    if invalidated:
        mark_modules_stale(session, property_, invalidated, as_of=timestamp)
    pipeline_event = _advance_pipeline_status(
        session,
        property_,
        PropertyPipelineStatus.REVIEWED,
        occurred_at=timestamp,
        source_reference=str(review.id),
        reason="property_review",
    )
    if commit:
        session.commit()
    return AcquisitionCommandResult(
        record=review,
        pipeline_event=pipeline_event,
        invalidated_modules=invalidated,
    )


def log_call_feedback(
    session: Session,
    property_: Property,
    *,
    occurred_at: datetime | None = None,
    seller_motivation: Any | None = None,
    reason_for_sale: Any | None = None,
    lowest_indicated_price: Decimal | None = None,
    cash_preferred: bool | None = None,
    desired_closing_days: int | None = None,
    viewing_available: bool | None = None,
    claimed_registered: bool | None = None,
    claimed_owner_1_1: bool | None = None,
    claimed_mortgage: bool | None = None,
    tenant_present: bool | None = None,
    structured_notes: dict[str, object] | None = None,
    notes: str | None = None,
    follow_up_at: datetime | None = None,
    follow_up_notes: str | None = None,
    commit: bool = False,
) -> AcquisitionCommandResult:
    timestamp = _aware_datetime(occurred_at or _utcnow())
    interaction = Interaction(
        property=property_,
        interaction_type=InteractionType.CALL,
        occurred_at=timestamp,
        follow_up_at=_optional_aware_datetime(follow_up_at),
        follow_up_notes=follow_up_notes,
        notes=notes,
    )
    session.add(interaction)
    session.flush()
    feedback = CallFeedback(
        interaction=interaction,
        seller_motivation=seller_motivation,
        reason_for_sale=reason_for_sale,
        lowest_indicated_price=lowest_indicated_price,
        cash_preferred=cash_preferred,
        desired_closing_days=desired_closing_days,
        viewing_available=viewing_available,
        claimed_registered=claimed_registered,
        claimed_owner_1_1=claimed_owner_1_1,
        claimed_mortgage=claimed_mortgage,
        tenant_present=tenant_present,
        structured_notes_json=structured_notes or {},
    )
    session.add(feedback)
    session.flush()

    pipeline_event = _advance_pipeline_status(
        session,
        property_,
        PropertyPipelineStatus.CALLED,
        occurred_at=timestamp,
        source_reference=str(interaction.id),
        reason="call_feedback",
    )
    invalidated: tuple[str, ...] = ()
    reanalyzed: tuple[str, ...] = ()
    if _call_feedback_is_analysis_relevant(feedback):
        invalidated = ("seller", "risk", "deal", "opportunity")
        reanalyzed = _run_feedback_reanalysis(
            session,
            property_,
            as_of=timestamp,
            invalidated_modules=invalidated,
        )
    if commit:
        session.commit()
    return AcquisitionCommandResult(
        record=interaction,
        pipeline_event=pipeline_event,
        invalidated_modules=invalidated,
        reanalyzed_modules=reanalyzed,
    )


def log_visit_feedback(
    session: Session,
    property_: Property,
    *,
    occurred_at: datetime | None = None,
    condition_category: str | None = None,
    estimated_renovation_low: Decimal | None = None,
    estimated_renovation_base: Decimal | None = None,
    estimated_renovation_high: Decimal | None = None,
    layout_score: int | None = None,
    light_score: int | None = None,
    noise_score: int | None = None,
    building_score: int | None = None,
    entrance_score: int | None = None,
    parking_score: int | None = None,
    elevator_verified: bool | None = None,
    visible_defects: list[object] | None = None,
    manual_fmv: Decimal | None = None,
    manual_fast_sale_value: Decimal | None = None,
    manual_max_buy_price: Decimal | None = None,
    notes: str | None = None,
    follow_up_at: datetime | None = None,
    follow_up_notes: str | None = None,
    commit: bool = False,
) -> AcquisitionCommandResult:
    _validate_renovation_range(
        estimated_renovation_low,
        estimated_renovation_base,
        estimated_renovation_high,
    )
    timestamp = _aware_datetime(occurred_at or _utcnow())
    interaction = Interaction(
        property=property_,
        interaction_type=InteractionType.VISIT,
        occurred_at=timestamp,
        follow_up_at=_optional_aware_datetime(follow_up_at),
        follow_up_notes=follow_up_notes,
        notes=notes,
    )
    session.add(interaction)
    session.flush()
    feedback = VisitFeedback(
        interaction=interaction,
        condition_category=_clean_optional_text(condition_category),
        estimated_renovation_low=estimated_renovation_low,
        estimated_renovation_base=estimated_renovation_base,
        estimated_renovation_high=estimated_renovation_high,
        layout_score=layout_score,
        light_score=light_score,
        noise_score=noise_score,
        building_score=building_score,
        entrance_score=entrance_score,
        parking_score=parking_score,
        elevator_verified=elevator_verified,
        visible_defects_json=visible_defects or [],
        manual_fmv=manual_fmv,
        manual_fast_sale_value=manual_fast_sale_value,
        manual_max_buy_price=manual_max_buy_price,
        notes=notes,
    )
    session.add(feedback)
    session.flush()

    property_fact_changed = _apply_visit_property_overrides(
        session,
        property_,
        feedback,
        source_reference=str(interaction.id),
    )
    _record_manual_estimate_overrides(
        session,
        property_,
        source_reference=str(interaction.id),
        source_kind=DataSourceKind.VERIFIED_MANUAL,
        manual_fmv=manual_fmv,
        manual_fast_sale_value=manual_fast_sale_value,
        manual_max_buy_price=manual_max_buy_price,
        reason="visit_feedback",
    )

    pipeline_event = _advance_pipeline_status(
        session,
        property_,
        PropertyPipelineStatus.VISITED,
        occurred_at=timestamp,
        source_reference=str(interaction.id),
        reason="visit_feedback",
    )
    invalidated: tuple[str, ...] = ()
    reanalyzed: tuple[str, ...] = ()
    if _visit_feedback_is_analysis_relevant(feedback):
        invalidated = _visit_invalidation_modules(
            property_fact_changed=property_fact_changed,
            manual_estimates_present=bool(
                _manual_estimate_invalidations(
                    manual_fmv=manual_fmv,
                    manual_fast_sale_value=manual_fast_sale_value,
                    manual_max_buy_price=manual_max_buy_price,
                )
            ),
        )
        reanalyzed = _run_feedback_reanalysis(
            session,
            property_,
            as_of=timestamp,
            invalidated_modules=invalidated,
            property_fact_changed=property_fact_changed,
            renovation_cost=estimated_renovation_base,
        )
    if commit:
        session.commit()
    return AcquisitionCommandResult(
        record=interaction,
        pipeline_event=pipeline_event,
        invalidated_modules=invalidated,
        reanalyzed_modules=reanalyzed,
    )


def create_offer(
    session: Session,
    property_: Property,
    *,
    amount: Decimal,
    currency: CurrencyCode = CurrencyCode.EUR,
    offered_at: datetime | None = None,
    offer_type: str | None = "INITIAL",
    conditions: dict[str, object] | None = None,
    status: OfferStatus = OfferStatus.OPEN,
    seller_response_at: datetime | None = None,
    counteroffer_amount: Decimal | None = None,
    notes: str | None = None,
    commit: bool = False,
) -> AcquisitionCommandResult:
    timestamp = _aware_datetime(offered_at or _utcnow())
    _validate_offer_amounts(amount=amount, counteroffer_amount=counteroffer_amount)
    offer = Offer(
        property=property_,
        offered_at=timestamp,
        amount=amount,
        currency=currency,
        offer_type=_clean_optional_text(offer_type),
        conditions_json=conditions or {},
        status=status,
        seller_response_at=_optional_aware_datetime(seller_response_at),
        counteroffer_amount=counteroffer_amount,
        notes=notes,
    )
    session.add(offer)
    session.flush()
    pipeline_event = _set_pipeline_from_offer(
        session,
        property_,
        offer,
        occurred_at=timestamp,
        reason="offer_created",
    )
    if commit:
        session.commit()
    return AcquisitionCommandResult(record=offer, pipeline_event=pipeline_event)


def update_offer(
    session: Session,
    offer: Offer,
    *,
    status: OfferStatus | None = None,
    seller_response_at: datetime | None = None,
    counteroffer_amount: Decimal | None = None,
    notes: str | None = None,
    commit: bool = False,
) -> AcquisitionCommandResult:
    if counteroffer_amount is not None and counteroffer_amount < 0:
        raise ValueError("counteroffer_amount must be non-negative")
    if status is not None:
        offer.status = status
    if seller_response_at is not None:
        offer.seller_response_at = _aware_datetime(seller_response_at)
    if counteroffer_amount is not None:
        offer.counteroffer_amount = counteroffer_amount
    if notes is not None:
        offer.notes = notes
    session.flush()
    pipeline_event = _set_pipeline_from_offer(
        session,
        offer.property,
        offer,
        occurred_at=offer.seller_response_at or _utcnow(),
        reason="offer_updated",
    )
    if commit:
        session.commit()
    return AcquisitionCommandResult(record=offer, pipeline_event=pipeline_event)


def skip_property(
    session: Session,
    property_: Property,
    *,
    reason_code: SkipReasonCode,
    notes: str | None = None,
    skipped_at: datetime | None = None,
    commit: bool = False,
) -> AcquisitionCommandResult:
    timestamp = _aware_datetime(skipped_at or _utcnow())
    skip_record = SkipRecord(
        property=property_,
        reason_code=reason_code,
        notes=notes,
        skipped_at=timestamp,
    )
    session.add(skip_record)
    session.flush()
    pipeline_event = set_pipeline_status(
        session,
        property_,
        PropertyPipelineStatus.SKIPPED,
        occurred_at=timestamp,
        source_reference=str(skip_record.id),
        reason="skip",
    )
    if commit:
        session.commit()
    return AcquisitionCommandResult(record=skip_record, pipeline_event=pipeline_event)


def record_property_outcome(
    session: Session,
    property_: Property,
    *,
    outcome_type: PropertyOutcomeType,
    outcome_date: datetime | None = None,
    sale_price: Decimal | None = None,
    currency: CurrencyCode | None = None,
    confidence: Decimal | None = None,
    source_kind: DataSourceKind | None = DataSourceKind.MANUAL,
    source_reference: str | None = None,
    notes: str | None = None,
    commit: bool = False,
) -> AcquisitionCommandResult:
    timestamp = _aware_datetime(outcome_date or _utcnow())
    outcome = PropertyOutcome(
        property=property_,
        outcome_type=outcome_type,
        outcome_date=timestamp,
        sale_price=sale_price,
        currency=currency,
        confidence=confidence,
        source_kind=source_kind,
        source_reference=source_reference,
        notes=notes,
    )
    session.add(outcome)
    session.flush()
    pipeline_event = _set_pipeline_from_outcome(
        session,
        property_,
        outcome,
        occurred_at=timestamp,
    )
    if commit:
        session.commit()
    return AcquisitionCommandResult(record=outcome, pipeline_event=pipeline_event)


def _run_feedback_reanalysis(
    session: Session,
    property_: Property,
    *,
    as_of: datetime,
    invalidated_modules: tuple[str, ...],
    property_fact_changed: bool = False,
    renovation_cost: Decimal | None = None,
) -> tuple[str, ...]:
    mark_modules_stale(session, property_, invalidated_modules, as_of=as_of)

    statuses: dict[str, AnalysisStatus] = {}
    valuation = _latest_successful_valuation(session, property_, as_of=as_of)
    liquidity = _latest_successful_liquidity(session, property_, as_of=as_of)
    fast_sale = _latest_successful_fast_sale(session, property_, as_of=as_of)
    reanalyzed: list[str] = []

    if property_fact_changed:
        valuation_result = value_property(session, property_, as_of=as_of)
        valuation = valuation_result.valuation
        liquidity_result = assess_liquidity_and_fast_sale(
            session,
            property_,
            valuation=valuation,
            as_of=as_of,
        )
        liquidity = liquidity_result.liquidity_assessment
        fast_sale = liquidity_result.fast_sale_estimate
        statuses.update(
            {
                "features": AnalysisStatus.SUCCESS,
                "comparable": AnalysisStatus.SUCCESS,
                "valuation": AnalysisStatus(status_from_analysis_row(valuation)),
                "liquidity": AnalysisStatus(status_from_analysis_row(liquidity)),
                "fast_sale": AnalysisStatus(status_from_analysis_row(fast_sale)),
            }
        )
        reanalyzed.extend(["features", "comparable", "valuation", "liquidity", "fast_sale"])

    seller_risk = assess_seller_intelligence_and_risk(
        session,
        property_,
        as_of=as_of,
    )
    deal_result = analyze_deal(
        session,
        property_,
        valuation=valuation,
        liquidity_assessment=liquidity,
        fast_sale_estimate=fast_sale,
        risk_assessment=seller_risk.risk_assessment,
        renovation_cost=renovation_cost,
        as_of=as_of,
    )
    opportunity = assess_opportunity(
        session,
        property_,
        deal_analysis=deal_result.deal_analysis,
        seller_assessment=seller_risk.seller_assessment,
        as_of=as_of,
    )
    _ = opportunity
    statuses.update(
        {
            "seller": AnalysisStatus.SUCCESS,
            "risk": AnalysisStatus.SUCCESS,
            "deal": AnalysisStatus(status_from_analysis_row(deal_result.deal_analysis)),
            "opportunity": AnalysisStatus.SUCCESS,
        }
    )
    reanalyzed.extend(["seller", "risk", "deal", "opportunity"])
    mark_modules_success(session, property_, statuses, as_of=as_of)
    return tuple(reanalyzed)


def _advance_pipeline_status(
    session: Session,
    property_: Property,
    status: PropertyPipelineStatus,
    *,
    occurred_at: datetime,
    source_reference: str | None,
    reason: str,
) -> PipelineStatusEvent | None:
    current = property_.pipeline_status
    if current in TERMINAL_PIPELINE_STATUSES:
        return None
    if PIPELINE_RANK[status] <= PIPELINE_RANK[current]:
        return None
    return set_pipeline_status(
        session,
        property_,
        status,
        occurred_at=occurred_at,
        source_reference=source_reference,
        reason=reason,
    )


def _set_pipeline_from_offer(
    session: Session,
    property_: Property,
    offer: Offer,
    *,
    occurred_at: datetime,
    reason: str,
) -> PipelineStatusEvent | None:
    if offer.status == OfferStatus.ACCEPTED:
        target = PropertyPipelineStatus.WON
    elif offer.status in {OfferStatus.REJECTED, OfferStatus.WITHDRAWN, OfferStatus.EXPIRED}:
        target = PropertyPipelineStatus.LOST
    elif offer.status == OfferStatus.COUNTERED or offer.counteroffer_amount is not None:
        target = PropertyPipelineStatus.NEGOTIATING
    else:
        target = PropertyPipelineStatus.OFFERED
    return _advance_pipeline_status(
        session,
        property_,
        target,
        occurred_at=occurred_at,
        source_reference=str(offer.id),
        reason=reason,
    )


def _set_pipeline_from_outcome(
    session: Session,
    property_: Property,
    outcome: PropertyOutcome,
    *,
    occurred_at: datetime,
) -> PipelineStatusEvent | None:
    if outcome.outcome_type == PropertyOutcomeType.BOUGHT_BY_USER:
        target = PropertyPipelineStatus.WON
    elif outcome.outcome_type == PropertyOutcomeType.LOST_TO_OTHER_BUYER:
        target = PropertyPipelineStatus.LOST
    elif outcome.outcome_type in {
        PropertyOutcomeType.CONFIRMED_SOLD,
        PropertyOutcomeType.LIKELY_SOLD,
    }:
        target = PropertyPipelineStatus.SOLD
    else:
        return None
    return _advance_pipeline_status(
        session,
        property_,
        target,
        occurred_at=occurred_at,
        source_reference=str(outcome.id),
        reason="property_outcome",
    )


def _apply_visit_property_overrides(
    session: Session,
    property_: Property,
    feedback: VisitFeedback,
    *,
    source_reference: str,
) -> bool:
    changed = False
    if feedback.condition_category:
        _add_property_override(
            session,
            property_,
            field_name="condition_category",
            value=feedback.condition_category,
            source_kind=DataSourceKind.VERIFIED_MANUAL,
            source_reference=source_reference,
            reason="visit_feedback",
        )
        if property_.condition_category != feedback.condition_category:
            property_.condition_category = feedback.condition_category
            changed = True
    if feedback.elevator_verified is not None:
        _add_property_override(
            session,
            property_,
            field_name="elevator",
            value=feedback.elevator_verified,
            source_kind=DataSourceKind.VERIFIED_MANUAL,
            source_reference=source_reference,
            reason="visit_feedback",
        )
        if property_.elevator != feedback.elevator_verified:
            property_.elevator = feedback.elevator_verified
            changed = True
    return changed


def _record_manual_estimate_overrides(
    session: Session,
    property_: Property,
    *,
    source_reference: str,
    source_kind: DataSourceKind,
    manual_fmv: Decimal | None,
    manual_fast_sale_value: Decimal | None,
    manual_max_buy_price: Decimal | None,
    reason: str,
) -> None:
    estimates = {
        "manual_fmv": manual_fmv,
        "manual_fast_sale_value": manual_fast_sale_value,
        "manual_max_buy_price": manual_max_buy_price,
    }
    for field_name, value in estimates.items():
        if value is not None:
            _add_property_override(
                session,
                property_,
                field_name=field_name,
                value=value,
                source_kind=source_kind,
                source_reference=source_reference,
                reason=reason,
            )


def _add_property_override(
    session: Session,
    property_: Property,
    *,
    field_name: str,
    value: object,
    source_kind: DataSourceKind,
    source_reference: str,
    reason: str,
) -> PropertyOverride:
    override = PropertyOverride(
        property=property_,
        field_name=field_name,
        value_json={"value": _json_value(value)},
        source_kind=source_kind,
        source_reference=source_reference,
        reason=reason,
    )
    session.add(override)
    session.flush()
    return override


def _manual_estimate_invalidations(
    *,
    manual_fmv: Decimal | None,
    manual_fast_sale_value: Decimal | None,
    manual_max_buy_price: Decimal | None,
) -> tuple[str, ...]:
    if manual_fmv is None and manual_fast_sale_value is None and manual_max_buy_price is None:
        return ()
    return ("valuation", "fast_sale", "deal", "opportunity")


def _visit_invalidation_modules(
    *,
    property_fact_changed: bool,
    manual_estimates_present: bool,
) -> tuple[str, ...]:
    modules = ["seller", "risk", "deal", "opportunity"]
    if property_fact_changed:
        modules = ["features", "comparable", "valuation", "liquidity", "fast_sale", *modules]
    elif manual_estimates_present:
        modules = ["valuation", "fast_sale", *modules]
    return tuple(dict.fromkeys(modules))


def _call_feedback_is_analysis_relevant(feedback: CallFeedback) -> bool:
    return any(
        value is not None
        for value in (
            feedback.seller_motivation,
            feedback.reason_for_sale,
            feedback.lowest_indicated_price,
            feedback.cash_preferred,
            feedback.claimed_registered,
            feedback.claimed_owner_1_1,
            feedback.claimed_mortgage,
            feedback.tenant_present,
        )
    )


def _visit_feedback_is_analysis_relevant(feedback: VisitFeedback) -> bool:
    return any(
        value is not None
        for value in (
            feedback.condition_category,
            feedback.estimated_renovation_low,
            feedback.estimated_renovation_base,
            feedback.estimated_renovation_high,
            feedback.elevator_verified,
            feedback.manual_fmv,
            feedback.manual_fast_sale_value,
            feedback.manual_max_buy_price,
        )
    ) or bool(feedback.visible_defects_json)


def _latest_successful_valuation(
    session: Session,
    property_: Property,
    *,
    as_of: datetime,
) -> Valuation | None:
    return session.scalars(
        select(Valuation)
        .where(
            Valuation.property_id == property_.id,
            Valuation.status == ValuationStatus.SUCCESS,
            Valuation.as_of <= as_of,
        )
        .order_by(Valuation.as_of.desc(), Valuation.created_at.desc(), Valuation.id.desc())
    ).first()


def _latest_successful_liquidity(
    session: Session,
    property_: Property,
    *,
    as_of: datetime,
) -> LiquidityAssessment | None:
    return session.scalars(
        select(LiquidityAssessment)
        .where(
            LiquidityAssessment.property_id == property_.id,
            LiquidityAssessment.status == LiquidityStatus.SUCCESS,
            LiquidityAssessment.as_of <= as_of,
        )
        .order_by(
            LiquidityAssessment.as_of.desc(),
            LiquidityAssessment.created_at.desc(),
            LiquidityAssessment.id.desc(),
        )
    ).first()


def _latest_successful_fast_sale(
    session: Session,
    property_: Property,
    *,
    as_of: datetime,
) -> FastSaleEstimate | None:
    return session.scalars(
        select(FastSaleEstimate)
        .where(
            FastSaleEstimate.property_id == property_.id,
            FastSaleEstimate.status == FastSaleStatus.SUCCESS,
            FastSaleEstimate.as_of <= as_of,
        )
        .order_by(
            FastSaleEstimate.as_of.desc(),
            FastSaleEstimate.created_at.desc(),
            FastSaleEstimate.id.desc(),
        )
    ).first()


def _validate_renovation_range(
    low: Decimal | None,
    base: Decimal | None,
    high: Decimal | None,
) -> None:
    values = [value for value in (low, base, high) if value is not None]
    if any(value < 0 for value in values):
        raise ValueError("renovation estimates must be non-negative")
    if low is not None and base is not None and low > base:
        raise ValueError("estimated_renovation_low cannot exceed base")
    if base is not None and high is not None and base > high:
        raise ValueError("estimated_renovation_base cannot exceed high")


def _validate_offer_amounts(*, amount: Decimal, counteroffer_amount: Decimal | None) -> None:
    if amount <= 0:
        raise ValueError("amount must be positive")
    if counteroffer_amount is not None and counteroffer_amount < 0:
        raise ValueError("counteroffer_amount must be non-negative")


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _aware_datetime(value).isoformat()
    return value


def _optional_aware_datetime(value: datetime | None) -> datetime | None:
    return _aware_datetime(value) if value is not None else None


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)
