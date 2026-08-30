from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ComparableSet,
    DataQualityAssessment,
    DealAnalysis,
    FastSaleEstimate,
    HistoricalEvaluationItem,
    HistoricalEvaluationRun,
    Interaction,
    LiquidityAssessment,
    Listing,
    ListingEvent,
    LlmAnalysis,
    Offer,
    OpportunityAssessment,
    PipelineStatusEvent,
    Property,
    PropertyFeature,
    PropertyListingLink,
    PropertyOutcome,
    PropertyOverride,
    PropertyReview,
    RiskAssessment,
    SellerAssessment,
    ShadowDeal,
    ShadowDealOutcome,
    Valuation,
)
from app.domain.enums import (
    HistoricalEvaluationClassification,
    HistoricalEvaluationRunStatus,
    InteractionType,
    ListingEventType,
    ListingStatus,
    OpportunityAction,
    PropertyOutcomeType,
    ShadowDealStatus,
    ShadowOutcomeStatus,
)

HISTORICAL_SNAPSHOT_VERSION = "historical_property_snapshot_v1"
HISTORICAL_EVALUATION_VERSION = "historical_evaluation_v1"
SHADOW_OUTCOME_EVALUATION_VERSION = "shadow_outcome_v1"

ALERTABLE_ACTIONS = {OpportunityAction.CALL, OpportunityAction.URGENT_CALL}
POSITIVE_OUTCOMES = {PropertyOutcomeType.BOUGHT_BY_USER}
NEGATIVE_OUTCOMES = {
    PropertyOutcomeType.LOST_TO_OTHER_BUYER,
    PropertyOutcomeType.SALE_CANCELLED,
}
UNKNOWN_OUTCOMES = {
    PropertyOutcomeType.STILL_ACTIVE,
    PropertyOutcomeType.REMOVED_UNKNOWN,
    PropertyOutcomeType.RELISTED,
    PropertyOutcomeType.OTHER,
}

MONEY_QUANTIZER = Decimal("0.01")
RATIO_QUANTIZER = Decimal("0.000001")


def build_historical_property_snapshot(
    session: Session,
    property_: Property,
    *,
    as_of: datetime,
) -> dict[str, object]:
    snapshot_as_of = _aware_datetime(as_of)
    session.flush()

    listing_snapshots = _listing_snapshots_as_of(session, property_, snapshot_as_of)
    analysis = _analysis_snapshot_as_of(session, property_, snapshot_as_of)
    manual_inputs = _manual_inputs_as_of(session, property_, snapshot_as_of)
    outcomes_known = _outcome_snapshots_as_of(session, property_, snapshot_as_of)
    property_facts = _property_facts_from_listing_snapshots(listing_snapshots)
    model_versions = _model_versions_from_analysis(analysis)

    return {
        "snapshot_version": HISTORICAL_SNAPSHOT_VERSION,
        "property_id": str(property_.id),
        "as_of": snapshot_as_of.isoformat(),
        "known_as_of": bool(
            listing_snapshots or any(analysis.values()) or _manual_inputs_present(manual_inputs)
        ),
        "property_facts": property_facts,
        "listings": listing_snapshots,
        "analysis": analysis,
        "manual_inputs": manual_inputs,
        "outcomes_known_as_of": outcomes_known,
        "model_versions": model_versions,
        "no_lookahead_guarantee": {
            "listing_events_cutoff": snapshot_as_of.isoformat(),
            "analysis_cutoff": snapshot_as_of.isoformat(),
            "manual_input_cutoff": snapshot_as_of.isoformat(),
            "outcome_knowledge_cutoff": snapshot_as_of.isoformat(),
        },
    }


def create_shadow_deal(
    session: Session,
    property_: Property,
    *,
    opportunity_assessment: OpportunityAssessment,
    simulated_buy_date: datetime,
    simulated_buy_price: Decimal,
    assumed_total_cost_basis: Decimal | None = None,
    expected_exit_price: Decimal | None = None,
    expected_holding_days: int | None = None,
    expected_profit: Decimal | None = None,
    notes: str | None = None,
    commit: bool = False,
) -> ShadowDeal:
    buy_date = _aware_datetime(simulated_buy_date)
    _validate_positive_money(simulated_buy_price, "simulated_buy_price")
    if expected_holding_days is not None and expected_holding_days < 0:
        raise ValueError("expected_holding_days must be non-negative")
    if opportunity_assessment.property_id != property_.id:
        raise ValueError("opportunity_assessment must belong to property")
    if _aware_datetime(opportunity_assessment.as_of) > buy_date:
        raise ValueError("opportunity_assessment.as_of cannot be after simulated_buy_date")

    deal_analysis = opportunity_assessment.deal_analysis
    if deal_analysis is not None:
        if deal_analysis.property_id != property_.id:
            raise ValueError("linked deal_analysis must belong to property")
        if _aware_datetime(deal_analysis.as_of) > buy_date:
            raise ValueError("deal_analysis.as_of cannot be after simulated_buy_date")

    selected_total_cost_basis = assumed_total_cost_basis
    if selected_total_cost_basis is None and deal_analysis is not None:
        selected_total_cost_basis = deal_analysis.total_cost_basis
    if selected_total_cost_basis is None:
        selected_total_cost_basis = simulated_buy_price
    _validate_non_negative_money(selected_total_cost_basis, "assumed_total_cost_basis")

    selected_expected_exit = expected_exit_price
    if selected_expected_exit is None and deal_analysis is not None:
        selected_expected_exit = deal_analysis.expected_exit_price
    if selected_expected_exit is not None:
        _validate_non_negative_money(selected_expected_exit, "expected_exit_price")

    selected_expected_holding = expected_holding_days
    if selected_expected_holding is None and deal_analysis is not None:
        selected_expected_holding = deal_analysis.expected_holding_days

    selected_expected_profit = expected_profit
    if selected_expected_profit is None and selected_expected_exit is not None:
        selected_expected_profit = _money(selected_expected_exit - selected_total_cost_basis)
    if selected_expected_profit is None and deal_analysis is not None:
        selected_expected_profit = deal_analysis.expected_profit

    snapshot = build_historical_property_snapshot(session, property_, as_of=buy_date)
    shadow_deal = ShadowDeal(
        property=property_,
        opportunity_assessment=opportunity_assessment,
        deal_analysis=deal_analysis,
        simulated_buy_date=buy_date,
        simulated_buy_price=_money(simulated_buy_price),
        assumed_total_cost_basis=_money(selected_total_cost_basis),
        expected_exit_price=_money(selected_expected_exit)
        if selected_expected_exit is not None
        else None,
        expected_holding_days=selected_expected_holding,
        expected_profit=_money(selected_expected_profit)
        if selected_expected_profit is not None
        else None,
        decision_action=opportunity_assessment.recommended_action,
        status=ShadowDealStatus.OPEN,
        input_snapshot_json=snapshot,
        model_versions_json=dict(snapshot["model_versions"]),
        notes=notes,
    )
    session.add(shadow_deal)
    session.flush()
    if commit:
        session.commit()
    return shadow_deal


def evaluate_shadow_deal_outcome(
    session: Session,
    shadow_deal: ShadowDeal,
    *,
    evaluation_as_of: datetime,
    property_outcome: PropertyOutcome | None = None,
    evaluated_at: datetime | None = None,
    commit: bool = False,
) -> ShadowDealOutcome:
    outcome_cutoff = _aware_datetime(evaluation_as_of)
    timestamp = _aware_datetime(evaluated_at or _utcnow())
    selected_outcome = property_outcome or _latest_outcome_known_as_of(
        session,
        shadow_deal.property_id,
        outcome_cutoff,
    )
    if selected_outcome is not None:
        _validate_outcome_for_cutoff(selected_outcome, shadow_deal.property_id, outcome_cutoff)

    outcome_status = _shadow_outcome_status(selected_outcome)
    simulated_profit = _simulated_profit(shadow_deal, selected_outcome)
    simulated_roi = _simulated_roi(shadow_deal, simulated_profit)
    summary = {
        "evaluation_version": SHADOW_OUTCOME_EVALUATION_VERSION,
        "shadow_deal_id": str(shadow_deal.id),
        "property_id": str(shadow_deal.property_id),
        "evaluation_as_of": outcome_cutoff.isoformat(),
        "original_input_snapshot_hash": _stable_hash(shadow_deal.input_snapshot_json),
        "original_model_versions": shadow_deal.model_versions_json,
        "original_expected": {
            "simulated_buy_price": _decimal_to_string(shadow_deal.simulated_buy_price),
            "assumed_total_cost_basis": _decimal_to_string(shadow_deal.assumed_total_cost_basis),
            "expected_exit_price": _decimal_to_string(shadow_deal.expected_exit_price),
            "expected_holding_days": shadow_deal.expected_holding_days,
            "expected_profit": _decimal_to_string(shadow_deal.expected_profit),
            "decision_action": _enum_value(shadow_deal.decision_action),
        },
        "observed_outcome": _property_outcome_snapshot(selected_outcome),
        "simulated_profit": _decimal_to_string(simulated_profit),
        "simulated_roi": _decimal_to_string(simulated_roi),
    }
    outcome = ShadowDealOutcome(
        shadow_deal=shadow_deal,
        property_outcome=selected_outcome,
        evaluation_as_of=outcome_cutoff,
        evaluated_at=timestamp,
        outcome_status=outcome_status,
        actual_observed_outcome=(
            selected_outcome.outcome_type if selected_outcome is not None else None
        ),
        actual_observed_price=selected_outcome.sale_price if selected_outcome is not None else None,
        actual_observed_date=(
            selected_outcome.outcome_date if selected_outcome is not None else None
        ),
        simulated_profit=simulated_profit,
        simulated_roi=simulated_roi,
        evaluation_version=SHADOW_OUTCOME_EVALUATION_VERSION,
        outcome_summary_json=summary,
    )
    session.add(outcome)
    session.flush()
    if commit:
        session.commit()
    return outcome


def run_historical_evaluation(
    session: Session,
    *,
    prediction_as_of: datetime,
    evaluation_as_of: datetime | None = None,
    evaluation_version: str = HISTORICAL_EVALUATION_VERSION,
    commit: bool = False,
) -> HistoricalEvaluationRun:
    prediction_cutoff = _aware_datetime(prediction_as_of)
    outcome_cutoff = _aware_datetime(evaluation_as_of or _utcnow())
    if outcome_cutoff < prediction_cutoff:
        raise ValueError("evaluation_as_of cannot be before prediction_as_of")

    property_ids = _property_ids_for_evaluation(session, prediction_cutoff, outcome_cutoff)
    run = HistoricalEvaluationRun(
        prediction_as_of=prediction_cutoff,
        evaluation_as_of=outcome_cutoff,
        evaluation_version=evaluation_version,
        status=HistoricalEvaluationRunStatus.SUCCESS,
        input_scope_json={
            "prediction_inputs_cutoff": prediction_cutoff.isoformat(),
            "outcome_measurement_cutoff": outcome_cutoff.isoformat(),
            "no_lookahead_rule": (
                "listing, analysis, manual input, and outcome inputs <= prediction_as_of; "
                "outcome measurement <= evaluation_as_of"
            ),
        },
        metrics_json={},
        completed_at=_utcnow(),
    )
    session.add(run)
    session.flush()

    items: list[HistoricalEvaluationItem] = []
    for property_id in property_ids:
        property_ = session.get(Property, property_id)
        if property_ is None:
            continue
        snapshot = build_historical_property_snapshot(
            session,
            property_,
            as_of=prediction_cutoff,
        )
        opportunity = _latest_opportunity_as_of(session, property_, prediction_cutoff)
        deal = _deal_for_evaluation(session, property_, opportunity, prediction_cutoff)
        outcome = _latest_outcome_known_as_of(session, property_.id, outcome_cutoff)
        classification = _classify_evaluation_item(opportunity, deal, outcome)
        item = HistoricalEvaluationItem(
            run=run,
            property=property_,
            opportunity_assessment=opportunity,
            deal_analysis=deal,
            property_outcome=outcome,
            recommended_action=opportunity.recommended_action if opportunity is not None else None,
            classification=classification,
            opportunity_score=opportunity.opportunity_score if opportunity is not None else None,
            ranking_value=opportunity.ranking_value if opportunity is not None else None,
            expected_profit=deal.expected_profit if deal is not None else None,
            downside_profit=deal.downside_profit if deal is not None else None,
            roi=deal.roi if deal is not None else None,
            outcome_type=outcome.outcome_type if outcome is not None else None,
            snapshot_json=snapshot,
            explanation_json=_evaluation_item_explanation(
                evaluation_version=evaluation_version,
                prediction_cutoff=prediction_cutoff,
                outcome_cutoff=outcome_cutoff,
                opportunity=opportunity,
                deal=deal,
                outcome=outcome,
                classification=classification,
            ),
        )
        session.add(item)
        items.append(item)

    session.flush()
    run.metrics_json = _evaluation_metrics(items)
    session.flush()
    if commit:
        session.commit()
    return run


def _listing_snapshots_as_of(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> list[dict[str, object]]:
    links = session.scalars(
        select(PropertyListingLink)
        .where(
            PropertyListingLink.property_id == property_.id,
            PropertyListingLink.created_at <= as_of,
        )
        .order_by(PropertyListingLink.created_at.asc(), PropertyListingLink.id.asc())
    ).all()

    snapshots: list[dict[str, object]] = []
    seen_listing_ids: set[uuid.UUID] = set()
    for link in links:
        listing = link.listing or session.get(Listing, link.listing_id)
        if listing is None or listing.id in seen_listing_ids:
            continue
        if _aware_datetime(listing.first_seen_at) > as_of:
            continue
        seen_listing_ids.add(listing.id)
        snapshots.append(_listing_snapshot_as_of(session, listing, link, as_of))
    return snapshots


def _listing_snapshot_as_of(
    session: Session,
    listing: Listing,
    link: PropertyListingLink,
    as_of: datetime,
) -> dict[str, object]:
    events = session.scalars(
        select(ListingEvent)
        .where(ListingEvent.listing_id == listing.id)
        .order_by(ListingEvent.detected_at.asc(), ListingEvent.id.asc())
    ).all()
    price = _listing_price_as_of(listing, events, as_of)
    size = _listing_detail_field_as_of(listing, events, as_of, "size_m2")
    return {
        "listing_id": str(listing.id),
        "source_id": str(listing.source_id),
        "external_listing_id": listing.external_listing_id,
        "url": listing.url,
        "canonical_url": listing.canonical_url,
        "linked_at": _aware_datetime(link.created_at).isoformat(),
        "matching_decision": link.decision.value,
        "matching_version": link.matching_version,
        "status": _listing_status_as_of(listing, events, as_of).value,
        "asking_price": _decimal_to_string(price),
        "currency": _enum_value(listing.currency),
        "price_per_m2": _decimal_to_string(_price_per_m2(price, size)),
        "title": _listing_text_field_as_of(listing, events, as_of, "title"),
        "description": _listing_text_field_as_of(listing, events, as_of, "description"),
        "city_raw": listing.city_raw,
        "location_raw": listing.location_raw,
        "size_m2": _decimal_to_string(size),
        "rooms": _decimal_to_string(_listing_detail_field_as_of(listing, events, as_of, "rooms")),
        "floor": _listing_detail_field_as_of(listing, events, as_of, "floor"),
        "total_floors": _listing_detail_field_as_of(listing, events, as_of, "total_floors"),
        "elevator": _listing_detail_field_as_of(listing, events, as_of, "elevator"),
        "parking": _listing_detail_field_as_of(listing, events, as_of, "parking"),
        "condition_raw": _listing_detail_field_as_of(listing, events, as_of, "condition_raw"),
        "seller": _seller_snapshot_as_of(listing, events, as_of),
        "first_seen_at": _aware_datetime(listing.first_seen_at).isoformat(),
        "last_seen_at": _optional_datetime_as_of(listing.last_seen_at, as_of),
    }


def _listing_price_as_of(
    listing: Listing,
    events: list[ListingEvent],
    as_of: datetime,
) -> Decimal | None:
    future_price_event = _first_event_after(
        events,
        as_of,
        ListingEventType.PRICE_CHANGED,
        field_name="asking_price",
    )
    if future_price_event is not None:
        if future_price_event.old_price is not None:
            return future_price_event.old_price
        old_value = _json_field(future_price_event.old_value_json, "asking_price")
        return _optional_decimal(old_value)

    past_price_event = _last_event_at_or_before(
        events,
        as_of,
        ListingEventType.PRICE_CHANGED,
        field_name="asking_price",
    )
    if past_price_event is not None:
        if past_price_event.new_price is not None:
            return past_price_event.new_price
        new_value = _json_field(past_price_event.new_value_json, "asking_price")
        return _optional_decimal(new_value)

    return listing.asking_price


def _listing_status_as_of(
    listing: Listing,
    events: list[ListingEvent],
    as_of: datetime,
) -> ListingStatus:
    status_events = {
        ListingEventType.DISCOVERED,
        ListingEventType.STATUS_CHANGED,
        ListingEventType.REMOVED,
        ListingEventType.REAPPEARED,
    }
    future_status_events = [
        event
        for event in events
        if event.event_type in status_events
        and _aware_datetime(event.detected_at) > as_of
        and _json_field(event.old_value_json, "status") is not None
    ]
    if future_status_events:
        raw_status = _json_field(future_status_events[0].old_value_json, "status")
        return _safe_listing_status(raw_status, default=ListingStatus.UNKNOWN)

    past_status_events = [
        event
        for event in events
        if event.event_type in status_events and _aware_datetime(event.detected_at) <= as_of
    ]
    if past_status_events:
        latest = past_status_events[-1]
        raw_status = _json_field(latest.new_value_json, "status")
        if raw_status is not None:
            return _safe_listing_status(raw_status, default=ListingStatus.UNKNOWN)
        if latest.event_type == ListingEventType.DISCOVERED:
            return ListingStatus.ACTIVE
        if latest.event_type == ListingEventType.REMOVED:
            return ListingStatus.REMOVED
        if latest.event_type == ListingEventType.REAPPEARED:
            return ListingStatus.ACTIVE

    return ListingStatus.ACTIVE


def _listing_text_field_as_of(
    listing: Listing,
    events: list[ListingEvent],
    as_of: datetime,
    field_name: str,
) -> str | None:
    event_type = (
        ListingEventType.TITLE_CHANGED
        if field_name == "title"
        else ListingEventType.DESCRIPTION_CHANGED
    )
    return _event_field_as_of(getattr(listing, field_name), events, as_of, event_type, field_name)


def _listing_detail_field_as_of(
    listing: Listing,
    events: list[ListingEvent],
    as_of: datetime,
    field_name: str,
) -> Any:
    return _event_field_as_of(
        getattr(listing, field_name),
        events,
        as_of,
        ListingEventType.DETAIL_CHANGED,
        field_name,
    )


def _event_field_as_of(
    current_value: Any,
    events: list[ListingEvent],
    as_of: datetime,
    event_type: ListingEventType,
    field_name: str,
) -> Any:
    future_event = _first_event_after(events, as_of, event_type, field_name=field_name)
    if future_event is not None:
        return _json_field(future_event.old_value_json, field_name)

    past_event = _last_event_at_or_before(events, as_of, event_type, field_name=field_name)
    if past_event is not None:
        return _json_field(past_event.new_value_json, field_name)

    return current_value


def _seller_snapshot_as_of(
    listing: Listing,
    events: list[ListingEvent],
    as_of: datetime,
) -> dict[str, object]:
    default_seller = {
        "seller_type": _enum_value(listing.seller_type),
        "seller_name": listing.seller_name,
        "agency_name": listing.agency_name,
        "seller_phone": listing.seller_phone,
        "seller_contact_raw": listing.seller_contact_raw,
    }
    future_event = _first_event_after(events, as_of, ListingEventType.SELLER_CHANGED)
    if future_event is not None and isinstance(future_event.old_value_json, dict):
        return _jsonable_dict(future_event.old_value_json)
    past_event = _last_event_at_or_before(events, as_of, ListingEventType.SELLER_CHANGED)
    if past_event is not None and isinstance(past_event.new_value_json, dict):
        return _jsonable_dict(past_event.new_value_json)
    return default_seller


def _first_event_after(
    events: list[ListingEvent],
    as_of: datetime,
    event_type: ListingEventType,
    *,
    field_name: str | None = None,
) -> ListingEvent | None:
    for event in events:
        if event.event_type != event_type or _aware_datetime(event.detected_at) <= as_of:
            continue
        if field_name is None or _json_field(event.old_value_json, field_name) is not None:
            return event
    return None


def _last_event_at_or_before(
    events: list[ListingEvent],
    as_of: datetime,
    event_type: ListingEventType,
    *,
    field_name: str | None = None,
) -> ListingEvent | None:
    for event in reversed(events):
        if event.event_type != event_type or _aware_datetime(event.detected_at) > as_of:
            continue
        if field_name is None or _json_field(event.new_value_json, field_name) is not None:
            return event
    return None


def _analysis_snapshot_as_of(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> dict[str, object]:
    feature = _latest_feature_as_of(session, property_, as_of)
    data_quality = _latest_as_of(session, DataQualityAssessment, property_, as_of)
    comparable_set = _latest_as_of(session, ComparableSet, property_, as_of)
    valuation = _latest_as_of(session, Valuation, property_, as_of)
    liquidity = _latest_as_of(session, LiquidityAssessment, property_, as_of)
    fast_sale = _latest_as_of(session, FastSaleEstimate, property_, as_of)
    llm = _latest_llm_as_of(session, property_, as_of)
    seller = _latest_seller_as_of(session, property_, as_of)
    risk = _latest_risk_as_of(session, property_, as_of)
    deal = _latest_deal_as_of(session, property_, as_of)
    opportunity = _latest_opportunity_as_of(session, property_, as_of)
    return {
        "property_features": _feature_snapshot(feature),
        "data_quality": _data_quality_snapshot(data_quality),
        "comparable_set": _comparable_set_snapshot(comparable_set),
        "valuation": _valuation_snapshot(valuation),
        "liquidity": _liquidity_snapshot(liquidity),
        "fast_sale": _fast_sale_snapshot(fast_sale),
        "llm": _llm_snapshot(llm),
        "seller": _seller_assessment_snapshot(seller),
        "risk": _risk_snapshot(risk),
        "deal": _deal_snapshot(deal),
        "opportunity": _opportunity_snapshot(opportunity),
    }


def _manual_inputs_as_of(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> dict[str, object]:
    reviews = session.scalars(
        select(PropertyReview)
        .where(PropertyReview.property_id == property_.id, PropertyReview.reviewed_at <= as_of)
        .order_by(PropertyReview.reviewed_at.asc(), PropertyReview.id.asc())
    ).all()
    interactions = session.scalars(
        select(Interaction)
        .where(Interaction.property_id == property_.id, Interaction.occurred_at <= as_of)
        .order_by(Interaction.occurred_at.asc(), Interaction.id.asc())
    ).all()
    offers = session.scalars(
        select(Offer)
        .where(Offer.property_id == property_.id, Offer.offered_at <= as_of)
        .order_by(Offer.offered_at.asc(), Offer.id.asc())
    ).all()
    overrides = session.scalars(
        select(PropertyOverride)
        .where(PropertyOverride.property_id == property_.id, PropertyOverride.created_at <= as_of)
        .order_by(PropertyOverride.created_at.asc(), PropertyOverride.id.asc())
    ).all()
    pipeline_events = session.scalars(
        select(PipelineStatusEvent)
        .where(
            PipelineStatusEvent.property_id == property_.id,
            PipelineStatusEvent.occurred_at <= as_of,
        )
        .order_by(PipelineStatusEvent.occurred_at.asc(), PipelineStatusEvent.id.asc())
    ).all()
    return {
        "reviews": [_review_snapshot(row) for row in reviews],
        "interactions": [_interaction_snapshot(row) for row in interactions],
        "offers": [_offer_snapshot(row, as_of) for row in offers],
        "overrides": [_override_snapshot(row) for row in overrides],
        "pipeline_events": [_pipeline_event_snapshot(row) for row in pipeline_events],
    }


def _outcome_snapshots_as_of(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> list[dict[str, object]]:
    outcomes = session.scalars(
        select(PropertyOutcome)
        .where(
            PropertyOutcome.property_id == property_.id,
            PropertyOutcome.outcome_date <= as_of,
            PropertyOutcome.created_at <= as_of,
        )
        .order_by(PropertyOutcome.outcome_date.asc(), PropertyOutcome.created_at.asc())
    ).all()
    return [_property_outcome_snapshot(outcome) for outcome in outcomes]


def _latest_outcome_known_as_of(
    session: Session,
    property_id: uuid.UUID,
    as_of: datetime,
) -> PropertyOutcome | None:
    return session.scalars(
        select(PropertyOutcome)
        .where(
            PropertyOutcome.property_id == property_id,
            PropertyOutcome.outcome_date <= as_of,
            PropertyOutcome.created_at <= as_of,
        )
        .order_by(
            PropertyOutcome.outcome_date.desc(),
            PropertyOutcome.created_at.desc(),
            PropertyOutcome.id.desc(),
        )
    ).first()


def _latest_as_of(
    session: Session,
    model: type[Any],
    property_: Property,
    as_of: datetime,
) -> Any | None:
    return session.scalars(
        select(model)
        .where(model.property_id == property_.id, model.as_of <= as_of)
        .order_by(model.as_of.desc(), model.created_at.desc(), model.id.desc())
    ).first()


def _latest_feature_as_of(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> Any | None:
    return session.scalars(
        select(PropertyFeature)
        .where(PropertyFeature.property_id == property_.id, PropertyFeature.computed_at <= as_of)
        .order_by(
            PropertyFeature.computed_at.desc(),
            PropertyFeature.created_at.desc(),
            PropertyFeature.id.desc(),
        )
    ).first()


def _latest_llm_as_of(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> LlmAnalysis | None:
    return session.scalars(
        select(LlmAnalysis)
        .where(
            LlmAnalysis.property_id == property_.id,
            LlmAnalysis.completed_at.is_not(None),
            LlmAnalysis.completed_at <= as_of,
        )
        .order_by(
            LlmAnalysis.completed_at.desc(), LlmAnalysis.created_at.desc(), LlmAnalysis.id.desc()
        )
    ).first()


def _latest_seller_as_of(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> Any | None:
    return _latest_as_of(session, SellerAssessment, property_, as_of)


def _latest_risk_as_of(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> Any | None:
    return _latest_as_of(session, RiskAssessment, property_, as_of)


def _latest_deal_as_of(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> DealAnalysis | None:
    return _latest_as_of(session, DealAnalysis, property_, as_of)


def _latest_opportunity_as_of(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> OpportunityAssessment | None:
    return _latest_as_of(session, OpportunityAssessment, property_, as_of)


def _property_ids_for_evaluation(
    session: Session,
    prediction_as_of: datetime,
    evaluation_as_of: datetime,
) -> list[uuid.UUID]:
    opportunity_ids = set(
        session.scalars(
            select(OpportunityAssessment.property_id).where(
                OpportunityAssessment.as_of <= prediction_as_of
            )
        ).all()
    )
    outcome_ids = set(
        session.scalars(
            select(PropertyOutcome.property_id).where(
                PropertyOutcome.outcome_date <= evaluation_as_of,
                PropertyOutcome.created_at <= evaluation_as_of,
            )
        ).all()
    )
    return sorted(opportunity_ids | outcome_ids, key=str)


def _deal_for_evaluation(
    session: Session,
    property_: Property,
    opportunity: OpportunityAssessment | None,
    prediction_as_of: datetime,
) -> DealAnalysis | None:
    if opportunity is not None and opportunity.deal_analysis is not None:
        deal = opportunity.deal_analysis
        if deal.property_id == property_.id and _aware_datetime(deal.as_of) <= prediction_as_of:
            return deal
    return _latest_deal_as_of(session, property_, prediction_as_of)


def _classify_evaluation_item(
    opportunity: OpportunityAssessment | None,
    deal: DealAnalysis | None,
    outcome: PropertyOutcome | None,
) -> HistoricalEvaluationClassification:
    action = opportunity.recommended_action if opportunity is not None else None
    outcome_signal = _outcome_signal(outcome, deal)
    if outcome_signal == "UNKNOWN":
        return HistoricalEvaluationClassification.UNKNOWN

    alertable = action in ALERTABLE_ACTIONS
    if alertable and outcome_signal == "POSITIVE":
        return HistoricalEvaluationClassification.TRUE_POSITIVE
    if alertable and outcome_signal == "NEGATIVE":
        return HistoricalEvaluationClassification.FALSE_POSITIVE
    if not alertable and outcome_signal == "POSITIVE":
        return HistoricalEvaluationClassification.FALSE_NEGATIVE
    return HistoricalEvaluationClassification.TRUE_NEGATIVE


def _outcome_signal(outcome: PropertyOutcome | None, deal: DealAnalysis | None) -> str:
    if outcome is None or outcome.outcome_type in UNKNOWN_OUTCOMES:
        return "UNKNOWN"
    if outcome.outcome_type in POSITIVE_OUTCOMES:
        return "POSITIVE"
    if outcome.outcome_type in NEGATIVE_OUTCOMES:
        return "NEGATIVE"
    if outcome.outcome_type in {
        PropertyOutcomeType.CONFIRMED_SOLD,
        PropertyOutcomeType.LIKELY_SOLD,
    }:
        if outcome.sale_price is None or deal is None or deal.max_buy_price is None:
            return "UNKNOWN"
        return "POSITIVE" if outcome.sale_price <= deal.max_buy_price else "NEGATIVE"
    return "UNKNOWN"


def _evaluation_item_explanation(
    *,
    evaluation_version: str,
    prediction_cutoff: datetime,
    outcome_cutoff: datetime,
    opportunity: OpportunityAssessment | None,
    deal: DealAnalysis | None,
    outcome: PropertyOutcome | None,
    classification: HistoricalEvaluationClassification,
) -> dict[str, object]:
    return {
        "evaluation_version": evaluation_version,
        "prediction_as_of": prediction_cutoff.isoformat(),
        "evaluation_as_of": outcome_cutoff.isoformat(),
        "classification": classification.value,
        "recommendation": {
            "opportunity_assessment_id": str(opportunity.id) if opportunity is not None else None,
            "recommended_action": _enum_value(opportunity.recommended_action)
            if opportunity is not None
            else None,
            "rules_version": opportunity.rules_version if opportunity is not None else None,
            "deal_analysis_id": str(deal.id) if deal is not None else None,
            "deal_formula_version": deal.formula_version if deal is not None else None,
        },
        "outcome_measurement": _property_outcome_snapshot(outcome),
        "no_lookahead_rule": {
            "prediction_inputs_cutoff": prediction_cutoff.isoformat(),
            "outcome_measurement_cutoff": outcome_cutoff.isoformat(),
        },
    }


def _evaluation_metrics(items: list[HistoricalEvaluationItem]) -> dict[str, object]:
    counts = {
        "total_items": len(items),
        "alertable_recommendations": 0,
        "measured_outcomes": 0,
        "true_positive": 0,
        "false_positive": 0,
        "false_negative": 0,
        "true_negative": 0,
        "unknown": 0,
        "downside_failures": 0,
        "missed_opportunities": 0,
    }
    valuation_errors: list[Decimal] = []
    observed_profits: list[Decimal] = []
    for item in items:
        if item.recommended_action in ALERTABLE_ACTIONS:
            counts["alertable_recommendations"] += 1
        counts[item.classification.value.lower()] += 1
        if item.classification != HistoricalEvaluationClassification.UNKNOWN:
            counts["measured_outcomes"] += 1
        if item.classification == HistoricalEvaluationClassification.FALSE_NEGATIVE:
            counts["missed_opportunities"] += 1
        if (
            item.recommended_action in ALERTABLE_ACTIONS
            and item.downside_profit is not None
            and item.downside_profit < 0
        ):
            counts["downside_failures"] += 1

        valuation_error = _valuation_error_from_item(item)
        if valuation_error is not None:
            valuation_errors.append(valuation_error)
        observed_profit = _observed_profit_from_item(item)
        if observed_profit is not None:
            observed_profits.append(observed_profit)

    alert_denominator = counts["true_positive"] + counts["false_positive"]
    return {
        **counts,
        "alert_precision": _ratio_string(
            Decimal(counts["true_positive"]) / Decimal(alert_denominator)
            if alert_denominator
            else None
        ),
        "call_worthy_rate": _ratio_string(
            Decimal(counts["alertable_recommendations"]) / Decimal(len(items)) if items else None
        ),
        "valuation_mae": _decimal_to_string(_mean(valuation_errors)),
        "simulated_profitability_total": _decimal_to_string(sum(observed_profits, Decimal("0.00")))
        if observed_profits
        else None,
    }


def _valuation_error_from_item(item: HistoricalEvaluationItem) -> Decimal | None:
    outcome = item.property_outcome
    if outcome is None or outcome.sale_price is None:
        return None
    valuation = item.snapshot_json.get("analysis", {}).get("valuation")
    if not isinstance(valuation, dict):
        return None
    fair_value_base = _optional_decimal(valuation.get("fair_value_base"))
    if fair_value_base is None:
        return None
    return abs(fair_value_base - outcome.sale_price)


def _observed_profit_from_item(item: HistoricalEvaluationItem) -> Decimal | None:
    outcome = item.property_outcome
    if outcome is None or outcome.sale_price is None:
        return None
    deal = item.snapshot_json.get("analysis", {}).get("deal")
    if not isinstance(deal, dict):
        return None
    total_cost_basis = _optional_decimal(deal.get("total_cost_basis"))
    if total_cost_basis is None:
        return None
    return _money(outcome.sale_price - total_cost_basis)


def _property_facts_from_listing_snapshots(
    listing_snapshots: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "source": "linked_listing_snapshots_as_of",
        "city": _first_snapshot_value(listing_snapshots, "city_raw"),
        "location": _first_snapshot_value(listing_snapshots, "location_raw"),
        "size_m2": _first_snapshot_value(listing_snapshots, "size_m2"),
        "rooms": _first_snapshot_value(listing_snapshots, "rooms"),
        "floor": _first_snapshot_value(listing_snapshots, "floor"),
        "total_floors": _first_snapshot_value(listing_snapshots, "total_floors"),
        "elevator": _first_snapshot_value(listing_snapshots, "elevator"),
        "parking": _first_snapshot_value(listing_snapshots, "parking"),
        "condition": _first_snapshot_value(listing_snapshots, "condition_raw"),
    }


def _manual_inputs_present(manual_inputs: dict[str, object]) -> bool:
    return any(bool(value) for value in manual_inputs.values())


def _model_versions_from_analysis(analysis: dict[str, object]) -> dict[str, object]:
    return {
        "feature_version": _nested_value(analysis, "property_features", "feature_version"),
        "data_quality_rules": _nested_value(analysis, "data_quality", "rules_version"),
        "comparable_engine": _nested_value(analysis, "comparable_set", "comparable_engine_version"),
        "valuation": _nested_value(analysis, "valuation", "model_version"),
        "liquidity": _nested_value(analysis, "liquidity", "model_version"),
        "fast_sale": _nested_value(analysis, "fast_sale", "model_version"),
        "llm_prompt": _nested_value(analysis, "llm", "prompt_version"),
        "llm_model": _nested_value(analysis, "llm", "model"),
        "seller": _nested_value(analysis, "seller", "model_version"),
        "risk": _nested_value(analysis, "risk", "rules_version"),
        "deal_formula": _nested_value(analysis, "deal", "formula_version"),
        "opportunity_rules": _nested_value(analysis, "opportunity", "rules_version"),
    }


def _feature_snapshot(row: Any | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "computed_at": _aware_datetime(row.computed_at).isoformat(),
        "feature_version": row.feature_version,
        "price_per_m2": _decimal_to_string(row.price_per_m2),
        "property_market_age_days": row.property_market_age_days,
        "active_listing_count": row.active_listing_count,
        "known_listing_count": row.known_listing_count,
        "relist_count": row.relist_count,
        "current_lowest_asking_price": _decimal_to_string(row.current_lowest_asking_price),
        "total_price_drop_pct": _decimal_to_string(row.total_price_drop_pct),
    }


def _data_quality_snapshot(row: DataQualityAssessment | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "as_of": _aware_datetime(row.as_of).isoformat(),
        "score": _decimal_to_string(row.score),
        "rules_version": row.rules_version,
        "missing_critical_fields": row.missing_critical_fields_json,
    }


def _comparable_set_snapshot(row: ComparableSet | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "as_of": _aware_datetime(row.as_of).isoformat(),
        "comparable_engine_version": row.comparable_engine_version,
        "search_parameters": row.search_parameters_json,
    }


def _valuation_snapshot(row: Valuation | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "as_of": _aware_datetime(row.as_of).isoformat(),
        "status": row.status.value,
        "fair_value_low": _decimal_to_string(row.fair_value_low),
        "fair_value_base": _decimal_to_string(row.fair_value_base),
        "fair_value_high": _decimal_to_string(row.fair_value_high),
        "currency": row.currency.value,
        "confidence": _decimal_to_string(row.confidence),
        "model_type": row.model_type.value,
        "model_version": row.model_version,
        "input_summary": row.input_summary_json,
    }


def _liquidity_snapshot(row: LiquidityAssessment | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "valuation_id": str(row.valuation_id) if row.valuation_id is not None else None,
        "as_of": _aware_datetime(row.as_of).isoformat(),
        "status": row.status.value,
        "liquidity_score": _decimal_to_string(row.liquidity_score),
        "confidence": _decimal_to_string(row.confidence),
        "model_version": row.model_version,
    }


def _fast_sale_snapshot(row: FastSaleEstimate | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "valuation_id": str(row.valuation_id) if row.valuation_id is not None else None,
        "liquidity_assessment_id": str(row.liquidity_assessment_id)
        if row.liquidity_assessment_id is not None
        else None,
        "as_of": _aware_datetime(row.as_of).isoformat(),
        "status": row.status.value,
        "value_low": _decimal_to_string(row.value_low),
        "value_base": _decimal_to_string(row.value_base),
        "value_high": _decimal_to_string(row.value_high),
        "target_days": row.target_days,
        "confidence": _decimal_to_string(row.confidence),
        "model_version": row.model_version,
    }


def _llm_snapshot(row: LlmAnalysis | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "listing_id": str(row.listing_id),
        "completed_at": _optional_datetime(row.completed_at),
        "status": row.status.value,
        "input_hash": row.input_hash,
        "provider": row.provider,
        "model": row.model,
        "prompt_version": row.prompt_version,
    }


def _seller_assessment_snapshot(row: Any | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "primary_llm_analysis_id": str(row.primary_llm_analysis_id)
        if row.primary_llm_analysis_id is not None
        else None,
        "as_of": _aware_datetime(row.as_of).isoformat(),
        "seller_motivation_level": row.seller_motivation_level.value,
        "seller_motivation_score": _decimal_to_string(row.seller_motivation_score),
        "seller_motivation_confidence": _decimal_to_string(row.seller_motivation_confidence),
        "negotiability_level": row.negotiability_level.value,
        "negotiability_score": _decimal_to_string(row.negotiability_score),
        "model_version": row.model_version,
    }


def _risk_snapshot(row: Any | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "as_of": _aware_datetime(row.as_of).isoformat(),
        "hard_gate_status": row.hard_gate_status.value,
        "risk_score": _decimal_to_string(row.risk_score),
        "confidence": _decimal_to_string(row.confidence),
        "rules_version": row.rules_version,
    }


def _deal_snapshot(row: DealAnalysis | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "valuation_id": str(row.valuation_id) if row.valuation_id is not None else None,
        "liquidity_assessment_id": str(row.liquidity_assessment_id)
        if row.liquidity_assessment_id is not None
        else None,
        "fast_sale_estimate_id": str(row.fast_sale_estimate_id)
        if row.fast_sale_estimate_id is not None
        else None,
        "risk_assessment_id": str(row.risk_assessment_id)
        if row.risk_assessment_id is not None
        else None,
        "cost_profile_id": str(row.cost_profile_id) if row.cost_profile_id is not None else None,
        "investment_profile_id": str(row.investment_profile_id)
        if row.investment_profile_id is not None
        else None,
        "as_of": _aware_datetime(row.as_of).isoformat(),
        "status": row.status.value,
        "asking_price": _decimal_to_string(row.asking_price),
        "assumed_purchase_price": _decimal_to_string(row.assumed_purchase_price),
        "total_cost_basis": _decimal_to_string(row.total_cost_basis),
        "expected_exit_price": _decimal_to_string(row.expected_exit_price),
        "max_buy_price": _decimal_to_string(row.max_buy_price),
        "required_negotiation_amount": _decimal_to_string(row.required_negotiation_amount),
        "required_negotiation_pct": _decimal_to_string(row.required_negotiation_pct),
        "expected_profit": _decimal_to_string(row.expected_profit),
        "downside_profit": _decimal_to_string(row.downside_profit),
        "upside_profit": _decimal_to_string(row.upside_profit),
        "roi": _decimal_to_string(row.roi),
        "expected_holding_days": row.expected_holding_days,
        "formula_version": row.formula_version,
        "input_summary": row.input_summary_json,
    }


def _opportunity_snapshot(row: OpportunityAssessment | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "deal_analysis_id": str(row.deal_analysis_id) if row.deal_analysis_id is not None else None,
        "as_of": _aware_datetime(row.as_of).isoformat(),
        "recommended_action": row.recommended_action.value,
        "opportunity_score": _decimal_to_string(row.opportunity_score),
        "ranking_value": _decimal_to_string(row.ranking_value),
        "reason_codes": row.reason_codes_json,
        "rules_version": row.rules_version,
        "state_hash": row.state_hash,
        "explanation": row.explanation_json,
    }


def _review_snapshot(row: PropertyReview) -> dict[str, object]:
    return {
        "id": str(row.id),
        "reviewed_at": _aware_datetime(row.reviewed_at).isoformat(),
        "decision": row.decision.value,
        "manual_fmv": _decimal_to_string(row.manual_fmv),
        "manual_fast_sale_value": _decimal_to_string(row.manual_fast_sale_value),
        "manual_max_buy_price": _decimal_to_string(row.manual_max_buy_price),
        "notes": row.notes,
    }


def _interaction_snapshot(row: Interaction) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "id": str(row.id),
        "interaction_type": row.interaction_type.value,
        "occurred_at": _aware_datetime(row.occurred_at).isoformat(),
        "notes": row.notes,
    }
    if row.interaction_type == InteractionType.CALL and row.call_feedback is not None:
        feedback = row.call_feedback
        snapshot["call_feedback"] = {
            "seller_motivation": _enum_value(feedback.seller_motivation),
            "reason_for_sale": _enum_value(feedback.reason_for_sale),
            "lowest_indicated_price": _decimal_to_string(feedback.lowest_indicated_price),
            "cash_preferred": feedback.cash_preferred,
            "desired_closing_days": feedback.desired_closing_days,
            "viewing_available": feedback.viewing_available,
            "claimed_registered": feedback.claimed_registered,
            "claimed_owner_1_1": feedback.claimed_owner_1_1,
            "claimed_mortgage": feedback.claimed_mortgage,
            "tenant_present": feedback.tenant_present,
            "structured_notes": feedback.structured_notes_json,
        }
    if row.interaction_type == InteractionType.VISIT and row.visit_feedback is not None:
        feedback = row.visit_feedback
        snapshot["visit_feedback"] = {
            "condition_category": feedback.condition_category,
            "estimated_renovation_low": _decimal_to_string(feedback.estimated_renovation_low),
            "estimated_renovation_base": _decimal_to_string(feedback.estimated_renovation_base),
            "estimated_renovation_high": _decimal_to_string(feedback.estimated_renovation_high),
            "elevator_verified": feedback.elevator_verified,
            "visible_defects": feedback.visible_defects_json,
            "manual_fmv": _decimal_to_string(feedback.manual_fmv),
            "manual_fast_sale_value": _decimal_to_string(feedback.manual_fast_sale_value),
            "manual_max_buy_price": _decimal_to_string(feedback.manual_max_buy_price),
        }
    return snapshot


def _offer_snapshot(row: Offer, as_of: datetime) -> dict[str, object]:
    response_known = (
        row.seller_response_at is not None and _aware_datetime(row.seller_response_at) <= as_of
    )
    return {
        "id": str(row.id),
        "offered_at": _aware_datetime(row.offered_at).isoformat(),
        "amount": _decimal_to_string(row.amount),
        "currency": row.currency.value,
        "offer_type": row.offer_type,
        "conditions": row.conditions_json,
        "status": row.status.value if response_known else "OPEN",
        "seller_response_at": _optional_datetime(row.seller_response_at)
        if response_known
        else None,
        "counteroffer_amount": _decimal_to_string(row.counteroffer_amount)
        if response_known
        else None,
        "notes": row.notes,
    }


def _override_snapshot(row: PropertyOverride) -> dict[str, object]:
    return {
        "id": str(row.id),
        "field_name": row.field_name,
        "value": row.value_json,
        "source_kind": row.source_kind.value,
        "source_reference": row.source_reference,
        "reason": row.reason,
        "created_at": _aware_datetime(row.created_at).isoformat(),
    }


def _pipeline_event_snapshot(row: PipelineStatusEvent) -> dict[str, object]:
    return {
        "id": str(row.id),
        "old_status": _enum_value(row.old_status),
        "new_status": row.new_status.value,
        "source_kind": row.source_kind.value,
        "source_reference": row.source_reference,
        "reason": row.reason,
        "occurred_at": _aware_datetime(row.occurred_at).isoformat(),
    }


def _property_outcome_snapshot(row: PropertyOutcome | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "outcome_type": row.outcome_type.value,
        "outcome_date": _aware_datetime(row.outcome_date).isoformat(),
        "sale_price": _decimal_to_string(row.sale_price),
        "currency": _enum_value(row.currency),
        "confidence": _decimal_to_string(row.confidence),
        "source_kind": _enum_value(row.source_kind),
        "source_reference": row.source_reference,
        "notes": row.notes,
        "created_at": _aware_datetime(row.created_at).isoformat(),
    }


def _validate_outcome_for_cutoff(
    outcome: PropertyOutcome,
    property_id: uuid.UUID,
    cutoff: datetime,
) -> None:
    if outcome.property_id != property_id:
        raise ValueError("property_outcome must belong to shadow deal property")
    if (
        _aware_datetime(outcome.outcome_date) > cutoff
        or _aware_datetime(outcome.created_at) > cutoff
    ):
        raise ValueError("property_outcome was not known by evaluation_as_of")


def _shadow_outcome_status(outcome: PropertyOutcome | None) -> ShadowOutcomeStatus:
    if outcome is None or outcome.outcome_type == PropertyOutcomeType.STILL_ACTIVE:
        return ShadowOutcomeStatus.OPEN
    if outcome.outcome_type in UNKNOWN_OUTCOMES:
        return ShadowOutcomeStatus.UNKNOWN
    return ShadowOutcomeStatus.MEASURED


def _simulated_profit(
    shadow_deal: ShadowDeal,
    outcome: PropertyOutcome | None,
) -> Decimal | None:
    if (
        outcome is None
        or outcome.sale_price is None
        or shadow_deal.assumed_total_cost_basis is None
    ):
        return None
    return _money(outcome.sale_price - shadow_deal.assumed_total_cost_basis)


def _simulated_roi(
    shadow_deal: ShadowDeal,
    simulated_profit: Decimal | None,
) -> Decimal | None:
    if (
        simulated_profit is None
        or shadow_deal.assumed_total_cost_basis is None
        or shadow_deal.assumed_total_cost_basis <= 0
    ):
        return None
    return (simulated_profit / shadow_deal.assumed_total_cost_basis).quantize(
        RATIO_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


def _price_per_m2(price: Decimal | None, size_m2: Any) -> Decimal | None:
    size = _optional_decimal(size_m2)
    if price is None or size is None or size <= 0:
        return None
    return _money(price / size)


def _first_snapshot_value(
    snapshots: list[dict[str, object]],
    key: str,
) -> object:
    for snapshot in snapshots:
        value = snapshot.get(key)
        if value is not None:
            return value
    return None


def _nested_value(payload: dict[str, object], section: str, key: str) -> object:
    nested = payload.get(section)
    if isinstance(nested, dict):
        return nested.get(key)
    return None


def _json_field(payload: dict[str, object] | None, field_name: str) -> object:
    if not isinstance(payload, dict):
        return None
    return payload.get(field_name)


def _jsonable_dict(payload: dict[str, object]) -> dict[str, object]:
    return {key: _json_value(value) for key, value in payload.items()}


def _safe_listing_status(value: object, *, default: ListingStatus) -> ListingStatus:
    try:
        return ListingStatus(str(value))
    except ValueError:
        return default


def _optional_datetime(value: datetime | None) -> str | None:
    return _aware_datetime(value).isoformat() if value is not None else None


def _optional_datetime_as_of(value: datetime | None, as_of: datetime) -> str | None:
    if value is None:
        return None
    timestamp = _aware_datetime(value)
    if timestamp > as_of:
        return None
    return timestamp.isoformat()


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _validate_positive_money(value: Decimal, field_name: str) -> None:
    _validate_non_negative_money(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _validate_non_negative_money(value: Decimal, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return _money(sum(values, Decimal("0.00")) / Decimal(len(values)))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def _ratio_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return _decimal_to_string(value.quantize(RATIO_QUANTIZER, rounding=ROUND_HALF_UP))


def _decimal_to_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _enum_value(value: Enum | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return _decimal_to_string(value)
    if isinstance(value, datetime):
        return _aware_datetime(value).isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(nested_value) for key, nested_value in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _stable_hash(payload: object) -> str:
    encoded = json.dumps(_json_value(payload), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _utcnow() -> datetime:
    return datetime.now(UTC)
