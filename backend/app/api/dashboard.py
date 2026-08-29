from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.api.dependencies import get_db_session, require_api_access
from app.core.config import get_settings
from app.db.models import (
    ComparableItem,
    ComparableSet,
    CostProfile,
    DealAnalysis,
    DealScenario,
    FastSaleEstimate,
    InvestmentProfile,
    JobRun,
    LiquidityAssessment,
    Listing,
    ListingEvent,
    LlmAnalysis,
    OpportunityAssessment,
    Property,
    PropertyAnalysisState,
    PropertyFeature,
    RiskAssessment,
    RiskFlag,
    SellerAssessment,
    Source,
    SourceRuntimeState,
    Valuation,
    WatchRule,
    WatchTriggerEvent,
)
from app.domain.enums import (
    ListingEventType,
    ListingStatus,
    OpportunityAction,
    SourceHealthStatus,
    WatchRuleType,
)
from app.watchlist.watchlist_service import (
    create_or_update_watch_rule,
    deactivate_watch_rules,
    queue_manual_reanalysis,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_access)])

DbSession = Annotated[Session, Depends(get_db_session)]

QUEUE_ACTIONS = (
    OpportunityAction.URGENT_CALL,
    OpportunityAction.CALL,
    OpportunityAction.REVIEW,
    OpportunityAction.WATCH,
)


class WatchRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_type: WatchRuleType | None = None
    threshold_numeric: Decimal | None = Field(default=None, gt=0)
    rule_config: dict[str, Any] = Field(default_factory=dict)


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _decimal(value: Decimal | int | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal(value)
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _action_priority_expression() -> Any:
    return case(
        (OpportunityAssessment.recommended_action == OpportunityAction.URGENT_CALL, 4),
        (OpportunityAssessment.recommended_action == OpportunityAction.CALL, 3),
        (OpportunityAssessment.recommended_action == OpportunityAction.REVIEW, 2),
        (OpportunityAssessment.recommended_action == OpportunityAction.WATCH, 1),
        else_=0,
    )


def _action_priority(action: OpportunityAction | None) -> int | None:
    if action is None:
        return None
    return {
        OpportunityAction.URGENT_CALL: 4,
        OpportunityAction.CALL: 3,
        OpportunityAction.REVIEW: 2,
        OpportunityAction.WATCH: 1,
        OpportunityAction.IGNORE: 0,
    }[action]


def _latest_analysis_subquery(model: Any, name: str) -> Any:
    return select(
        model.id.label("id"),
        model.property_id.label("property_id"),
        func.row_number()
        .over(
            partition_by=model.property_id,
            order_by=(model.as_of.desc(), model.created_at.desc(), model.id.desc()),
        )
        .label("rn"),
    ).subquery(name)


def _latest_feature_subquery() -> Any:
    return select(
        PropertyFeature.id.label("id"),
        PropertyFeature.property_id.label("property_id"),
        func.row_number()
        .over(
            partition_by=PropertyFeature.property_id,
            order_by=(
                PropertyFeature.computed_at.desc(),
                PropertyFeature.created_at.desc(),
                PropertyFeature.id.desc(),
            ),
        )
        .label("rn"),
    ).subquery("latest_property_features")


def _latest_listing_subquery() -> Any:
    status_rank = case(
        (Listing.status == ListingStatus.ACTIVE, 0),
        (Listing.status == ListingStatus.NOT_SEEN, 1),
        (Listing.status == ListingStatus.UNKNOWN, 2),
        else_=3,
    )
    return (
        select(
            Listing.id.label("id"),
            Listing.property_id.label("property_id"),
            func.row_number()
            .over(
                partition_by=Listing.property_id,
                order_by=(
                    status_rank.asc(),
                    Listing.last_seen_at.desc(),
                    Listing.created_at.desc(),
                    Listing.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(Listing.property_id.is_not(None))
        .subquery("current_listings")
    )


def _latest_listing_event_subquery() -> Any:
    event_listing = aliased(Listing)
    return (
        select(
            event_listing.property_id.label("property_id"),
            func.max(ListingEvent.detected_at).label("last_event_at"),
        )
        .join(event_listing, ListingEvent.listing_id == event_listing.id)
        .where(event_listing.property_id.is_not(None))
        .group_by(event_listing.property_id)
        .subquery("latest_listing_events")
    )


def _latest_source_job_subquery() -> Any:
    return (
        select(
            JobRun.id.label("id"),
            JobRun.source_id.label("source_id"),
            func.row_number()
            .over(
                partition_by=JobRun.source_id,
                order_by=(JobRun.started_at.desc(), JobRun.created_at.desc(), JobRun.id.desc()),
            )
            .label("rn"),
        )
        .where(JobRun.source_id.is_not(None))
        .subquery("latest_source_jobs")
    )


def _validate_sort(sort: str, allowed: Iterable[str]) -> None:
    if sort not in set(allowed):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported sort field: {sort}",
        )


def _validate_direction(direction: str) -> str:
    normalized = direction.lower()
    if normalized not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="direction must be 'asc' or 'desc'",
        )
    return normalized


def _apply_order(stmt: Any, expression: Any, direction: str) -> Any:
    if direction == "asc":
        return stmt.order_by(expression.asc().nullslast())
    return stmt.order_by(expression.desc().nullslast())


def _count_from_stmt(session: Session, stmt: Any) -> int:
    return int(
        session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    )


def _pagination(page: int, page_size: int, total: int) -> dict[str, int]:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


def _location(property_: Property) -> dict[str, str | None]:
    parts = [
        property_.micro_location,
        property_.neighborhood,
        property_.municipality,
        property_.city,
    ]
    seen: set[str] = set()
    label_parts = []
    for part in parts:
        if part and part not in seen:
            label_parts.append(part)
            seen.add(part)
    return {
        "label": ", ".join(label_parts) if label_parts else None,
        "city": property_.city,
        "municipality": property_.municipality,
        "neighborhood": property_.neighborhood,
        "micro_location": property_.micro_location,
        "street": property_.street,
    }


def _property_label(property_: Property, listing: Listing | None = None) -> str | None:
    if listing and listing.title:
        return listing.title
    location = _location(property_)["label"]
    property_type = _enum_value(property_.property_type)
    if location:
        return f"{property_type} in {location}"
    return property_type


def _max_datetime(*values: datetime | None) -> datetime | None:
    known = [value for value in values if value is not None]
    return max(known) if known else None


def _current_last_change(
    property_: Property,
    listing: Listing | None,
    latest_event_at: datetime | None,
    opportunity: OpportunityAssessment | None = None,
) -> datetime | None:
    return _max_datetime(
        latest_event_at,
        listing.last_seen_at if listing else None,
        property_.last_seen_at,
        opportunity.created_at if opportunity else None,
    )


def _row_status(row: Any | None, latest_input_at: datetime | None) -> str:
    if row is None:
        return "NOT_RUN"
    row_as_of = getattr(row, "as_of", None)
    if latest_input_at and row_as_of and latest_input_at > row_as_of:
        return "STALE"
    return str(_enum_value(getattr(row, "status", "SUCCESS")))


def _is_stale(row: Any | None, latest_input_at: datetime | None) -> bool:
    return _row_status(row, latest_input_at) == "STALE"


def _state_status(
    state: PropertyAnalysisState | None,
    module: str,
    row: Any | None,
    latest_input_at: datetime | None,
) -> str:
    if state is None:
        return _row_status(row, latest_input_at)
    return str(_enum_value(getattr(state, f"{module}_status")))


def _feature_status(
    state: PropertyAnalysisState | None,
    feature: PropertyFeature | None,
) -> str:
    if state is not None:
        return str(_enum_value(state.features_status))
    return "SUCCESS" if feature is not None else "NOT_RUN"


def _matching_status(
    state: PropertyAnalysisState | None,
    listings: list[tuple[Listing, Source]],
) -> str:
    if state is not None:
        return str(_enum_value(state.matching_status))
    return "SUCCESS" if listings else "NOT_RUN"


def _serialize_watch_rule(rule: WatchRule | None) -> dict[str, Any] | None:
    if rule is None:
        return None
    return {
        "watch_rule_id": str(rule.id),
        "property_id": str(rule.property_id),
        "is_active": rule.is_active,
        "rule_type": str(_enum_value(rule.rule_type)) if rule.rule_type else None,
        "threshold_numeric": _decimal(rule.threshold_numeric),
        "rule_config": _json_safe(rule.rule_config_json),
        "created_at": _iso(rule.created_at),
        "triggered_at": _iso(rule.triggered_at),
        "last_evaluated_at": _iso(rule.last_evaluated_at),
    }


def _serialize_watch_trigger(trigger: WatchTriggerEvent) -> dict[str, Any]:
    return {
        "watch_trigger_event_id": str(trigger.id),
        "watch_rule_id": str(trigger.watch_rule_id),
        "property_id": str(trigger.property_id),
        "listing_event_id": str(trigger.listing_event_id) if trigger.listing_event_id else None,
        "trigger_type": str(_enum_value(trigger.trigger_type)) if trigger.trigger_type else None,
        "triggered_at": _iso(trigger.triggered_at),
        "summary": _json_safe(trigger.summary_json),
        "invalidated_modules": _json_safe(trigger.invalidated_modules_json),
        "reanalyzed_modules": _json_safe(trigger.reanalyzed_modules_json),
        "previous_opportunity_assessment_id": (
            str(trigger.previous_opportunity_assessment_id)
            if trigger.previous_opportunity_assessment_id
            else None
        ),
        "new_opportunity_assessment_id": (
            str(trigger.new_opportunity_assessment_id)
            if trigger.new_opportunity_assessment_id
            else None
        ),
        "alert_id": str(trigger.alert_id) if trigger.alert_id else None,
    }


def _latest_watch_rule_subquery() -> Any:
    return (
        select(
            WatchRule.id.label("id"),
            WatchRule.property_id.label("property_id"),
            func.row_number()
            .over(
                partition_by=WatchRule.property_id,
                order_by=(WatchRule.created_at.desc(), WatchRule.id.desc()),
            )
            .label("rn"),
        )
        .where(WatchRule.is_active.is_(True))
        .subquery("latest_active_watch_rules")
    )


def _latest_watch_trigger_subquery() -> Any:
    return select(
        WatchTriggerEvent.id.label("id"),
        WatchTriggerEvent.property_id.label("property_id"),
        func.row_number()
        .over(
            partition_by=WatchTriggerEvent.property_id,
            order_by=(
                WatchTriggerEvent.triggered_at.desc(),
                WatchTriggerEvent.created_at.desc(),
                WatchTriggerEvent.id.desc(),
            ),
        )
        .label("rn"),
    ).subquery("latest_watch_trigger_events")


def _latest_price_cut_subquery() -> Any:
    price_cut_listing = aliased(Listing)
    return (
        select(
            price_cut_listing.property_id.label("property_id"),
            func.max(ListingEvent.detected_at).label("last_price_cut_at"),
        )
        .join(price_cut_listing, ListingEvent.listing_id == price_cut_listing.id)
        .where(
            price_cut_listing.property_id.is_not(None),
            ListingEvent.event_type == ListingEventType.PRICE_CHANGED,
            ListingEvent.old_price.is_not(None),
            ListingEvent.new_price.is_not(None),
            ListingEvent.new_price < ListingEvent.old_price,
        )
        .group_by(price_cut_listing.property_id)
        .subquery("latest_price_cuts")
    )


def _source_warnings(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Source, SourceRuntimeState)
        .outerjoin(SourceRuntimeState, SourceRuntimeState.source_id == Source.id)
        .where(
            (Source.is_enabled.is_(False))
            | SourceRuntimeState.health_status.in_(
                [SourceHealthStatus.DEGRADED, SourceHealthStatus.FAILED]
            )
        )
        .order_by(Source.code.asc())
    ).all()
    warnings: list[dict[str, Any]] = []
    for source, state in rows:
        warnings.append(
            {
                "source_id": str(source.id),
                "source_code": source.code,
                "source_name": source.name,
                "status": "DISABLED"
                if not source.is_enabled
                else str(_enum_value(state.health_status if state else "UNKNOWN")),
                "last_error_at": _iso(state.last_error_at) if state else None,
                "last_error_type": state.last_error_type if state else None,
                "last_error_message": state.last_error_message if state else None,
            }
        )
    return warnings


def _apply_property_filters(
    stmt: Any,
    *,
    city: str | None,
    municipality: str | None,
    source_code: str | None,
) -> Any:
    if city:
        stmt = stmt.where(Property.city == city)
    if municipality:
        stmt = stmt.where(Property.municipality == municipality)
    if source_code:
        source_filter = aliased(Source)
        listing_filter = aliased(Listing)
        source_exists = (
            select(1)
            .select_from(listing_filter)
            .join(source_filter, listing_filter.source_id == source_filter.id)
            .where(
                listing_filter.property_id == Property.id,
                source_filter.code == source_code,
            )
            .exists()
        )
        stmt = stmt.where(source_exists)
    return stmt


def _queue_summary(session: Session) -> dict[str, Any]:
    latest_opportunity_sq = _latest_analysis_subquery(
        OpportunityAssessment, "latest_queue_summary_opportunities"
    )
    rows = session.execute(
        select(OpportunityAssessment.recommended_action, func.count())
        .join(latest_opportunity_sq, latest_opportunity_sq.c.id == OpportunityAssessment.id)
        .where(
            latest_opportunity_sq.c.rn == 1,
            OpportunityAssessment.recommended_action.in_(QUEUE_ACTIONS),
        )
        .group_by(OpportunityAssessment.recommended_action)
    ).all()

    by_action = {action.value: 0 for action in QUEUE_ACTIONS}
    for action, count in rows:
        by_action[str(_enum_value(action))] = int(count)
    total = sum(by_action.values())
    return {
        "status": "HAS_OPPORTUNITIES" if total else "NO_QUALIFYING_OPPORTUNITIES",
        "total": total,
        "by_action": by_action,
    }


def _serialize_queue_item(
    property_: Property,
    opportunity: OpportunityAssessment,
    deal: DealAnalysis | None,
    valuation: Valuation | None,
    fast_sale: FastSaleEstimate | None,
    liquidity: LiquidityAssessment | None,
    risk: RiskAssessment | None,
    feature: PropertyFeature | None,
    listing: Listing | None,
    source: Source | None,
    latest_event_at: datetime | None,
) -> dict[str, Any]:
    last_change = _current_last_change(property_, listing, latest_event_at, opportunity)
    asking_price = deal.asking_price if deal else listing.asking_price if listing else None
    currency = valuation.currency if valuation else listing.currency if listing else None
    return {
        "property_id": str(property_.id),
        "property_label": _property_label(property_, listing),
        "recommended_action": str(_enum_value(opportunity.recommended_action)),
        "action_priority": _action_priority(opportunity.recommended_action),
        "reason_codes": _json_safe(opportunity.reason_codes_json),
        "location": _location(property_),
        "property_type": str(_enum_value(property_.property_type)),
        "size_m2": _decimal(property_.size_m2),
        "rooms": _decimal(property_.rooms),
        "asking_price": _decimal(asking_price),
        "currency": str(_enum_value(currency)) if currency else None,
        "fair_value_low": _decimal(valuation.fair_value_low if valuation else None),
        "fair_value_base": _decimal(valuation.fair_value_base if valuation else None),
        "fair_value_high": _decimal(valuation.fair_value_high if valuation else None),
        "fast_sale_base": _decimal(fast_sale.value_base if fast_sale else None),
        "max_buy_price": _decimal(deal.max_buy_price if deal else None),
        "expected_profit": _decimal(deal.expected_profit if deal else None),
        "downside_profit": _decimal(deal.downside_profit if deal else None),
        "liquidity_score": _decimal(liquidity.liquidity_score if liquidity else None),
        "valuation_confidence": _decimal(valuation.confidence if valuation else None),
        "risk_gate": str(_enum_value(risk.hard_gate_status)) if risk else None,
        "property_market_age_days": (
            feature.property_market_age_days if feature else property_.estimated_market_age_days
        ),
        "last_change": _iso(last_change),
        "analysis_status": _row_status(opportunity, latest_event_at),
        "is_stale": _is_stale(opportunity, latest_event_at),
        "current_listing": {
            "listing_id": str(listing.id) if listing else None,
            "source_code": source.code if source else None,
            "source_name": source.name if source else None,
            "status": str(_enum_value(listing.status)) if listing else None,
            "url": listing.url if listing else None,
            "canonical_url": listing.canonical_url if listing else None,
        },
    }


@router.get("/action-queue")
def get_action_queue(
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    action: OpportunityAction | None = None,
    city: str | None = None,
    municipality: str | None = None,
    source: str | None = None,
    sort: str = "priority",
    direction: str = "desc",
) -> dict[str, Any]:
    direction = _validate_direction(direction)
    allowed_sorts = {
        "priority": _action_priority_expression(),
        "ranking_value": OpportunityAssessment.ranking_value,
        "last_change": OpportunityAssessment.created_at,
        "market_age": PropertyFeature.property_market_age_days,
        "expected_profit": DealAnalysis.expected_profit,
        "downside_profit": DealAnalysis.downside_profit,
        "liquidity_score": LiquidityAssessment.liquidity_score,
        "valuation_confidence": Valuation.confidence,
        "max_buy_price": DealAnalysis.max_buy_price,
        "asking_price": DealAnalysis.asking_price,
    }
    _validate_sort(sort, allowed_sorts.keys())

    latest_opportunity_sq = _latest_analysis_subquery(
        OpportunityAssessment, "latest_queue_opportunities"
    )
    latest_feature_sq = _latest_feature_subquery()
    latest_listing_sq = _latest_listing_subquery()
    latest_event_sq = _latest_listing_event_subquery()
    current_listing = aliased(Listing)
    current_source = aliased(Source)

    stmt = (
        select(
            Property,
            OpportunityAssessment,
            DealAnalysis,
            Valuation,
            FastSaleEstimate,
            LiquidityAssessment,
            RiskAssessment,
            PropertyFeature,
            current_listing,
            current_source,
            latest_event_sq.c.last_event_at,
        )
        .join(latest_opportunity_sq, latest_opportunity_sq.c.property_id == Property.id)
        .join(OpportunityAssessment, OpportunityAssessment.id == latest_opportunity_sq.c.id)
        .outerjoin(DealAnalysis, OpportunityAssessment.deal_analysis_id == DealAnalysis.id)
        .outerjoin(Valuation, DealAnalysis.valuation_id == Valuation.id)
        .outerjoin(FastSaleEstimate, DealAnalysis.fast_sale_estimate_id == FastSaleEstimate.id)
        .outerjoin(
            LiquidityAssessment, DealAnalysis.liquidity_assessment_id == LiquidityAssessment.id
        )
        .outerjoin(RiskAssessment, DealAnalysis.risk_assessment_id == RiskAssessment.id)
        .outerjoin(
            latest_feature_sq,
            (latest_feature_sq.c.property_id == Property.id) & (latest_feature_sq.c.rn == 1),
        )
        .outerjoin(
            PropertyFeature,
            PropertyFeature.id == latest_feature_sq.c.id,
        )
        .outerjoin(
            latest_listing_sq,
            (latest_listing_sq.c.property_id == Property.id) & (latest_listing_sq.c.rn == 1),
        )
        .outerjoin(
            current_listing,
            current_listing.id == latest_listing_sq.c.id,
        )
        .outerjoin(current_source, current_listing.source_id == current_source.id)
        .outerjoin(latest_event_sq, latest_event_sq.c.property_id == Property.id)
        .where(
            latest_opportunity_sq.c.rn == 1,
            OpportunityAssessment.recommended_action.in_(QUEUE_ACTIONS),
        )
    )
    stmt = _apply_property_filters(
        stmt,
        city=city,
        municipality=municipality,
        source_code=source,
    )
    if action:
        stmt = stmt.where(OpportunityAssessment.recommended_action == action)

    total = _count_from_stmt(session, stmt)
    stmt = _apply_order(stmt, allowed_sorts[sort], direction)
    if sort == "priority":
        stmt = stmt.order_by(OpportunityAssessment.ranking_value.desc().nullslast())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    items = [
        _serialize_queue_item(
            property_,
            opportunity,
            deal,
            valuation,
            fast_sale,
            liquidity,
            risk,
            feature,
            listing,
            source_row,
            latest_event_at,
        )
        for (
            property_,
            opportunity,
            deal,
            valuation,
            fast_sale,
            liquidity,
            risk,
            feature,
            listing,
            source_row,
            latest_event_at,
        ) in session.execute(stmt).all()
    ]

    warnings = _source_warnings(session)
    return {
        "items": items,
        "pagination": _pagination(page, page_size, total),
        "summary": _queue_summary(session),
        "source_warnings": warnings,
    }


def _watch_gap(asking_price: Decimal | None, max_buy_price: Decimal | None) -> Decimal | None:
    if asking_price is None or max_buy_price is None:
        return None
    return asking_price - max_buy_price


def _serialize_watchlist_item(
    property_: Property,
    rule: WatchRule,
    opportunity: OpportunityAssessment | None,
    deal: DealAnalysis | None,
    feature: PropertyFeature | None,
    listing: Listing | None,
    source: Source | None,
    latest_event_at: datetime | None,
    last_price_cut_at: datetime | None,
    latest_trigger: WatchTriggerEvent | None,
) -> dict[str, Any]:
    asking_price = deal.asking_price if deal else listing.asking_price if listing else None
    currency = listing.currency if listing else None
    gap = _watch_gap(asking_price, deal.max_buy_price if deal else None)
    last_change = _max_datetime(
        latest_trigger.triggered_at if latest_trigger else None,
        latest_event_at,
        listing.last_seen_at if listing else None,
        opportunity.created_at if opportunity else None,
    )
    return {
        "property_id": str(property_.id),
        "property_label": _property_label(property_, listing),
        "location": _location(property_),
        "asking_price": _decimal(asking_price),
        "currency": str(_enum_value(currency)) if currency else None,
        "max_buy_price": _decimal(deal.max_buy_price if deal else None),
        "gap_to_max_buy": _decimal(gap),
        "last_price_cut": _iso(last_price_cut_at),
        "property_market_age_days": (
            feature.property_market_age_days if feature else property_.estimated_market_age_days
        ),
        "watch_rule": _serialize_watch_rule(rule),
        "last_change": _iso(last_change),
        "last_change_summary": (
            _json_safe(latest_trigger.summary_json) if latest_trigger is not None else None
        ),
        "recommended_action": (
            str(_enum_value(opportunity.recommended_action)) if opportunity else None
        ),
        "reason_codes": _json_safe(opportunity.reason_codes_json) if opportunity else [],
        "analysis_status": _row_status(opportunity, latest_event_at),
        "current_listing": {
            "listing_id": str(listing.id) if listing else None,
            "source_code": source.code if source else None,
            "source_name": source.name if source else None,
            "status": str(_enum_value(listing.status)) if listing else None,
            "url": listing.url if listing else None,
        },
    }


@router.get("/watchlist")
def get_watchlist(
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    latest_watch_rule_sq = _latest_watch_rule_subquery()
    latest_opportunity_sq = _latest_analysis_subquery(
        OpportunityAssessment, "latest_watchlist_opportunities"
    )
    latest_feature_sq = _latest_feature_subquery()
    latest_listing_sq = _latest_listing_subquery()
    latest_event_sq = _latest_listing_event_subquery()
    latest_price_cut_sq = _latest_price_cut_subquery()
    latest_trigger_sq = _latest_watch_trigger_subquery()
    current_listing = aliased(Listing)
    current_source = aliased(Source)

    gap_expression = DealAnalysis.asking_price - DealAnalysis.max_buy_price
    positive_gap_rank = case((gap_expression >= 0, 0), else_=1)

    stmt = (
        select(
            Property,
            WatchRule,
            OpportunityAssessment,
            DealAnalysis,
            PropertyFeature,
            current_listing,
            current_source,
            latest_event_sq.c.last_event_at,
            latest_price_cut_sq.c.last_price_cut_at,
            WatchTriggerEvent,
        )
        .join(latest_watch_rule_sq, latest_watch_rule_sq.c.property_id == Property.id)
        .join(
            WatchRule,
            (WatchRule.id == latest_watch_rule_sq.c.id) & (latest_watch_rule_sq.c.rn == 1),
        )
        .outerjoin(
            latest_opportunity_sq,
            (latest_opportunity_sq.c.property_id == Property.id)
            & (latest_opportunity_sq.c.rn == 1),
        )
        .outerjoin(
            OpportunityAssessment,
            OpportunityAssessment.id == latest_opportunity_sq.c.id,
        )
        .outerjoin(DealAnalysis, OpportunityAssessment.deal_analysis_id == DealAnalysis.id)
        .outerjoin(
            latest_feature_sq,
            (latest_feature_sq.c.property_id == Property.id) & (latest_feature_sq.c.rn == 1),
        )
        .outerjoin(PropertyFeature, PropertyFeature.id == latest_feature_sq.c.id)
        .outerjoin(
            latest_listing_sq,
            (latest_listing_sq.c.property_id == Property.id) & (latest_listing_sq.c.rn == 1),
        )
        .outerjoin(current_listing, current_listing.id == latest_listing_sq.c.id)
        .outerjoin(current_source, current_listing.source_id == current_source.id)
        .outerjoin(latest_event_sq, latest_event_sq.c.property_id == Property.id)
        .outerjoin(latest_price_cut_sq, latest_price_cut_sq.c.property_id == Property.id)
        .outerjoin(
            latest_trigger_sq,
            (latest_trigger_sq.c.property_id == Property.id) & (latest_trigger_sq.c.rn == 1),
        )
        .outerjoin(
            WatchTriggerEvent,
            WatchTriggerEvent.id == latest_trigger_sq.c.id,
        )
    )
    total = _count_from_stmt(session, stmt)
    stmt = (
        stmt.order_by(
            positive_gap_rank.asc().nullslast(),
            gap_expression.asc().nullslast(),
            latest_event_sq.c.last_event_at.desc().nullslast(),
            WatchRule.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return {
        "items": [
            _serialize_watchlist_item(
                property_,
                rule,
                opportunity,
                deal,
                feature,
                listing,
                source_row,
                latest_event_at,
                last_price_cut_at,
                latest_trigger,
            )
            for (
                property_,
                rule,
                opportunity,
                deal,
                feature,
                listing,
                source_row,
                latest_event_at,
                last_price_cut_at,
                latest_trigger,
            ) in session.execute(stmt).all()
        ],
        "pagination": _pagination(page, page_size, total),
    }


@router.post("/properties/{property_id}/watch", status_code=status.HTTP_201_CREATED)
def watch_property(
    session: DbSession,
    property_id: uuid.UUID,
    payload: WatchRuleRequest,
) -> dict[str, Any]:
    property_ = _load_property(session, property_id)
    try:
        rule = create_or_update_watch_rule(
            session,
            property_,
            rule_type=payload.rule_type,
            threshold_numeric=payload.threshold_numeric,
            rule_config=payload.rule_config,
            commit=True,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return {"status": "WATCHED", "watch_rule": _serialize_watch_rule(rule)}


@router.delete("/properties/{property_id}/watch")
def unwatch_property(session: DbSession, property_id: uuid.UUID) -> dict[str, Any]:
    property_ = _load_property(session, property_id)
    deactivated = deactivate_watch_rules(session, property_, commit=True)
    return {"status": "UNWATCHED", "deactivated_count": len(deactivated)}


@router.post("/properties/{property_id}/reanalyze")
def reanalyze_property(session: DbSession, property_id: uuid.UUID) -> dict[str, Any]:
    property_ = _load_property(session, property_id)
    return queue_manual_reanalysis(session, property_, commit=True)


def _serialize_property_list_item(
    property_: Property,
    opportunity: OpportunityAssessment | None,
    deal: DealAnalysis | None,
    risk: RiskAssessment | None,
    feature: PropertyFeature | None,
    listing: Listing | None,
    source: Source | None,
    latest_event_at: datetime | None,
) -> dict[str, Any]:
    return {
        "property_id": str(property_.id),
        "property_label": _property_label(property_, listing),
        "location": _location(property_),
        "property_type": str(_enum_value(property_.property_type)),
        "pipeline_status": str(_enum_value(property_.pipeline_status)),
        "size_m2": _decimal(property_.size_m2),
        "rooms": _decimal(property_.rooms),
        "active_listing_count": (
            feature.active_listing_count if feature else property_.active_listing_count
        ),
        "known_listing_count": feature.known_listing_count if feature else None,
        "property_market_age_days": (
            feature.property_market_age_days if feature else property_.estimated_market_age_days
        ),
        "recommended_action": (
            str(_enum_value(opportunity.recommended_action)) if opportunity else None
        ),
        "reason_codes": _json_safe(opportunity.reason_codes_json) if opportunity else [],
        "risk_gate": str(_enum_value(risk.hard_gate_status)) if risk else None,
        "asking_price": _decimal(
            deal.asking_price if deal else listing.asking_price if listing else None
        ),
        "max_buy_price": _decimal(deal.max_buy_price if deal else None),
        "expected_profit": _decimal(deal.expected_profit if deal else None),
        "downside_profit": _decimal(deal.downside_profit if deal else None),
        "last_change": _iso(_current_last_change(property_, listing, latest_event_at, opportunity)),
        "analysis_status": _row_status(opportunity, latest_event_at),
        "current_listing": {
            "listing_id": str(listing.id) if listing else None,
            "source_code": source.code if source else None,
            "source_name": source.name if source else None,
            "status": str(_enum_value(listing.status)) if listing else None,
            "url": listing.url if listing else None,
        },
    }


@router.get("/properties")
def get_properties(
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    action: OpportunityAction | None = None,
    city: str | None = None,
    municipality: str | None = None,
    source: str | None = None,
    active_only: bool = False,
    sort: str = "last_seen",
    direction: str = "desc",
) -> dict[str, Any]:
    direction = _validate_direction(direction)
    allowed_sorts = {
        "last_seen": Property.last_seen_at,
        "created_at": Property.created_at,
        "market_age": PropertyFeature.property_market_age_days,
        "action": _action_priority_expression(),
        "expected_profit": DealAnalysis.expected_profit,
        "asking_price": DealAnalysis.asking_price,
    }
    _validate_sort(sort, allowed_sorts.keys())

    latest_opportunity_sq = _latest_analysis_subquery(
        OpportunityAssessment, "latest_property_opportunities"
    )
    latest_feature_sq = _latest_feature_subquery()
    latest_listing_sq = _latest_listing_subquery()
    latest_event_sq = _latest_listing_event_subquery()
    current_listing = aliased(Listing)
    current_source = aliased(Source)

    stmt = (
        select(
            Property,
            OpportunityAssessment,
            DealAnalysis,
            RiskAssessment,
            PropertyFeature,
            current_listing,
            current_source,
            latest_event_sq.c.last_event_at,
        )
        .outerjoin(latest_opportunity_sq, latest_opportunity_sq.c.property_id == Property.id)
        .outerjoin(
            OpportunityAssessment,
            (OpportunityAssessment.id == latest_opportunity_sq.c.id)
            & (latest_opportunity_sq.c.rn == 1),
        )
        .outerjoin(DealAnalysis, OpportunityAssessment.deal_analysis_id == DealAnalysis.id)
        .outerjoin(RiskAssessment, DealAnalysis.risk_assessment_id == RiskAssessment.id)
        .outerjoin(
            latest_feature_sq,
            (latest_feature_sq.c.property_id == Property.id) & (latest_feature_sq.c.rn == 1),
        )
        .outerjoin(
            PropertyFeature,
            PropertyFeature.id == latest_feature_sq.c.id,
        )
        .outerjoin(
            latest_listing_sq,
            (latest_listing_sq.c.property_id == Property.id) & (latest_listing_sq.c.rn == 1),
        )
        .outerjoin(
            current_listing,
            current_listing.id == latest_listing_sq.c.id,
        )
        .outerjoin(current_source, current_listing.source_id == current_source.id)
        .outerjoin(latest_event_sq, latest_event_sq.c.property_id == Property.id)
    )
    stmt = _apply_property_filters(
        stmt,
        city=city,
        municipality=municipality,
        source_code=source,
    )
    if action:
        stmt = stmt.where(OpportunityAssessment.recommended_action == action)
    if active_only:
        stmt = stmt.where(Property.active_listing_count > 0)

    total = _count_from_stmt(session, stmt)
    stmt = _apply_order(stmt, allowed_sorts[sort], direction)
    if sort == "action":
        stmt = stmt.order_by(OpportunityAssessment.ranking_value.desc().nullslast())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    return {
        "items": [
            _serialize_property_list_item(
                property_,
                opportunity,
                deal,
                risk,
                feature,
                listing,
                source_row,
                latest_event_at,
            )
            for (
                property_,
                opportunity,
                deal,
                risk,
                feature,
                listing,
                source_row,
                latest_event_at,
            ) in session.execute(stmt).all()
        ],
        "pagination": _pagination(page, page_size, total),
    }


def _latest_for_property(session: Session, model: Any, property_id: uuid.UUID) -> Any | None:
    return session.scalars(
        select(model)
        .where(model.property_id == property_id)
        .order_by(model.as_of.desc(), model.created_at.desc(), model.id.desc())
    ).first()


def _latest_feature_for_property(
    session: Session, property_id: uuid.UUID
) -> PropertyFeature | None:
    return session.scalars(
        select(PropertyFeature)
        .where(PropertyFeature.property_id == property_id)
        .order_by(
            PropertyFeature.computed_at.desc(),
            PropertyFeature.created_at.desc(),
            PropertyFeature.id.desc(),
        )
    ).first()


def _latest_llm_for_property(session: Session, property_id: uuid.UUID) -> LlmAnalysis | None:
    return session.scalars(
        select(LlmAnalysis)
        .where(LlmAnalysis.property_id == property_id)
        .order_by(
            LlmAnalysis.completed_at.desc().nullslast(),
            LlmAnalysis.created_at.desc(),
            LlmAnalysis.id.desc(),
        )
    ).first()


def _latest_listing_input_at(session: Session, property_id: uuid.UUID) -> datetime | None:
    last_seen_at = session.scalar(
        select(func.max(Listing.last_seen_at)).where(Listing.property_id == property_id)
    )
    last_event_at = session.scalar(
        select(func.max(ListingEvent.detected_at))
        .join(Listing, ListingEvent.listing_id == Listing.id)
        .where(Listing.property_id == property_id)
    )
    return _max_datetime(last_seen_at, last_event_at)


def _latest_analysis_at(*rows: Any | None) -> datetime | None:
    return _max_datetime(
        *[getattr(row, "as_of", None) for row in rows if row is not None],
        *[getattr(row, "created_at", None) for row in rows if row is not None],
    )


def _load_property(session: Session, property_id: uuid.UUID) -> Property:
    property_ = session.get(Property, property_id)
    if property_ is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found.",
        )
    return property_


def _listing_rows(session: Session, property_id: uuid.UUID) -> list[tuple[Listing, Source]]:
    status_rank = case(
        (Listing.status == ListingStatus.ACTIVE, 0),
        (Listing.status == ListingStatus.NOT_SEEN, 1),
        (Listing.status == ListingStatus.UNKNOWN, 2),
        else_=3,
    )
    return list(
        session.execute(
            select(Listing, Source)
            .join(Source, Listing.source_id == Source.id)
            .where(Listing.property_id == property_id)
            .order_by(status_rank.asc(), Listing.last_seen_at.desc(), Listing.created_at.desc())
        ).all()
    )


def _serialize_property(property_: Property, feature: PropertyFeature | None) -> dict[str, Any]:
    return {
        "property_id": str(property_.id),
        "property_label": _property_label(property_),
        "property_type": str(_enum_value(property_.property_type)),
        "location": _location(property_),
        "country_code": property_.country_code,
        "latitude": _decimal(property_.latitude),
        "longitude": _decimal(property_.longitude),
        "location_precision": property_.location_precision,
        "location_confidence": _decimal(property_.location_confidence),
        "size_m2": _decimal(property_.size_m2),
        "rooms": _decimal(property_.rooms),
        "bedrooms": property_.bedrooms,
        "floor": property_.floor,
        "total_floors": property_.total_floors,
        "elevator": property_.elevator,
        "construction_year": property_.construction_year,
        "building_type": property_.building_type,
        "heating_type": property_.heating_type,
        "parking": property_.parking,
        "garage": property_.garage,
        "terrace": property_.terrace,
        "condition_category": property_.condition_category,
        "pipeline_status": str(_enum_value(property_.pipeline_status)),
        "first_seen_at": _iso(property_.first_seen_at),
        "last_seen_at": _iso(property_.last_seen_at),
        "active_listing_count": (
            feature.active_listing_count if feature else property_.active_listing_count
        ),
        "known_listing_count": feature.known_listing_count if feature else None,
        "estimated_market_age_days": property_.estimated_market_age_days,
        "property_market_age_days": (
            feature.property_market_age_days if feature else property_.estimated_market_age_days
        ),
        "relist_count": feature.relist_count if feature else property_.relist_count,
        "price_cut_count": feature.price_cut_count if feature else None,
        "total_price_drop_pct": _decimal(feature.total_price_drop_pct if feature else None),
        "price_drop_30d_pct": _decimal(feature.price_drop_30d_pct if feature else None),
    }


def _serialize_listing(listing: Listing, source: Source) -> dict[str, Any]:
    return {
        "listing_id": str(listing.id),
        "source_id": str(source.id),
        "source_code": source.code,
        "source_name": source.name,
        "external_listing_id": listing.external_listing_id,
        "url": listing.url,
        "canonical_url": listing.canonical_url,
        "title": listing.title,
        "asking_price": _decimal(listing.asking_price),
        "currency": str(_enum_value(listing.currency)) if listing.currency else None,
        "status": str(_enum_value(listing.status)),
        "seller_type": str(_enum_value(listing.seller_type)),
        "seller_name": listing.seller_name,
        "agency_name": listing.agency_name,
        "first_seen_at": _iso(listing.first_seen_at),
        "last_seen_at": _iso(listing.last_seen_at),
        "removed_at": _iso(listing.removed_at),
    }


def _history_items(session: Session, property_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = session.execute(
        select(ListingEvent, Listing, Source)
        .join(Listing, ListingEvent.listing_id == Listing.id)
        .join(Source, Listing.source_id == Source.id)
        .where(Listing.property_id == property_id)
        .order_by(ListingEvent.detected_at.desc(), ListingEvent.created_at.desc())
    ).all()
    history = [
        {
            "event_type": str(_enum_value(event.event_type)),
            "detected_at": _iso(event.detected_at),
            "listing_id": str(listing.id),
            "source_code": source.code,
            "source_name": source.name,
            "title": listing.title,
            "old_value": _json_safe(event.old_value_json),
            "new_value": _json_safe(event.new_value_json),
            "old_price": _decimal(event.old_price),
            "new_price": _decimal(event.new_price),
        }
        for event, listing, source in rows
    ]

    discovered_listing_ids = {
        item["listing_id"]
        for item in history
        if item["event_type"] == ListingEventType.DISCOVERED.value
    }
    for listing, source in _listing_rows(session, property_id):
        if str(listing.id) in discovered_listing_ids:
            continue
        history.append(
            {
                "event_type": ListingEventType.DISCOVERED.value,
                "detected_at": _iso(listing.first_seen_at),
                "listing_id": str(listing.id),
                "source_code": source.code,
                "source_name": source.name,
                "title": listing.title,
                "old_value": None,
                "new_value": {
                    "asking_price": _decimal(listing.asking_price),
                    "status": str(_enum_value(listing.status)),
                },
                "old_price": None,
                "new_price": _decimal(listing.asking_price),
            }
        )

    return sorted(
        history,
        key=lambda item: item["detected_at"] or "",
        reverse=True,
    )


def _watch_detail(session: Session, property_: Property) -> dict[str, Any]:
    active_rule = session.scalars(
        select(WatchRule)
        .where(
            WatchRule.property_id == property_.id,
            WatchRule.is_active.is_(True),
        )
        .order_by(WatchRule.created_at.desc(), WatchRule.id.desc())
    ).first()
    recent_triggers = session.scalars(
        select(WatchTriggerEvent)
        .where(WatchTriggerEvent.property_id == property_.id)
        .order_by(
            WatchTriggerEvent.triggered_at.desc(),
            WatchTriggerEvent.created_at.desc(),
            WatchTriggerEvent.id.desc(),
        )
        .limit(5)
    ).all()
    return {
        "is_watched": active_rule is not None,
        "active_rule": _serialize_watch_rule(active_rule),
        "latest_changes": [_serialize_watch_trigger(trigger) for trigger in recent_triggers],
    }


def _serialize_valuation(valuation: Valuation | None, status_value: str) -> dict[str, Any]:
    if valuation is None:
        return {"status": status_value}
    return {
        "valuation_id": str(valuation.id),
        "status": status_value,
        "raw_status": str(_enum_value(valuation.status)),
        "as_of": _iso(valuation.as_of),
        "fair_value_low": _decimal(valuation.fair_value_low),
        "fair_value_base": _decimal(valuation.fair_value_base),
        "fair_value_high": _decimal(valuation.fair_value_high),
        "currency": str(_enum_value(valuation.currency)),
        "confidence": _decimal(valuation.confidence),
        "data_quality_at_analysis": _decimal(valuation.data_quality_at_analysis),
        "model_type": str(_enum_value(valuation.model_type)),
        "model_version": valuation.model_version,
        "input_summary": _json_safe(valuation.input_summary_json),
        "explanation": _json_safe(valuation.explanation_json),
    }


def _serialize_liquidity(
    liquidity: LiquidityAssessment | None,
    fast_sale: FastSaleEstimate | None,
    liquidity_status: str,
    fast_sale_status: str,
) -> dict[str, Any]:
    return {
        "assessment": None
        if liquidity is None
        else {
            "liquidity_id": str(liquidity.id),
            "status": liquidity_status,
            "raw_status": str(_enum_value(liquidity.status)),
            "as_of": _iso(liquidity.as_of),
            "liquidity_score": _decimal(liquidity.liquidity_score),
            "confidence": _decimal(liquidity.confidence),
            "probability_sale_30d": _decimal(liquidity.probability_sale_30d),
            "probability_sale_60d": _decimal(liquidity.probability_sale_60d),
            "probability_sale_90d": _decimal(liquidity.probability_sale_90d),
            "positive_factors": _json_safe(liquidity.positive_factors_json),
            "negative_factors": _json_safe(liquidity.negative_factors_json),
            "model_version": liquidity.model_version,
        },
        "fast_sale": None
        if fast_sale is None
        else {
            "fast_sale_id": str(fast_sale.id),
            "status": fast_sale_status,
            "raw_status": str(_enum_value(fast_sale.status)),
            "as_of": _iso(fast_sale.as_of),
            "value_low": _decimal(fast_sale.value_low),
            "value_base": _decimal(fast_sale.value_base),
            "value_high": _decimal(fast_sale.value_high),
            "target_days": fast_sale.target_days,
            "target_probability": _decimal(fast_sale.target_probability),
            "confidence": _decimal(fast_sale.confidence),
            "model_version": fast_sale.model_version,
            "explanation": _json_safe(fast_sale.explanation_json),
        },
    }


def _serialize_seller(seller: SellerAssessment | None, status_value: str) -> dict[str, Any]:
    if seller is None:
        return {"status": status_value}
    return {
        "seller_assessment_id": str(seller.id),
        "status": status_value,
        "as_of": _iso(seller.as_of),
        "seller_motivation_level": str(_enum_value(seller.seller_motivation_level)),
        "seller_motivation_score": _decimal(seller.seller_motivation_score),
        "seller_motivation_confidence": _decimal(seller.seller_motivation_confidence),
        "negotiability_level": str(_enum_value(seller.negotiability_level)),
        "negotiability_score": _decimal(seller.negotiability_score),
        "negotiability_confidence": _decimal(seller.negotiability_confidence),
        "cash_preferred": seller.cash_preferred,
        "cash_preference_confidence": _decimal(seller.cash_preference_confidence),
        "reason_for_sale": str(_enum_value(seller.reason_for_sale)),
        "evidence": _json_safe(seller.evidence_json),
        "model_version": seller.model_version,
    }


def _serialize_risk(
    session: Session,
    risk: RiskAssessment | None,
    status_value: str,
) -> dict[str, Any]:
    if risk is None:
        return {"status": status_value, "gate": None, "flags": []}
    flags = session.scalars(
        select(RiskFlag).where(RiskFlag.risk_assessment_id == risk.id).order_by(RiskFlag.code.asc())
    ).all()
    return {
        "risk_assessment_id": str(risk.id),
        "status": status_value,
        "as_of": _iso(risk.as_of),
        "gate": str(_enum_value(risk.hard_gate_status)),
        "risk_score": _decimal(risk.risk_score),
        "confidence": _decimal(risk.confidence),
        "rules_version": risk.rules_version,
        "flags": [
            {
                "code": flag.code,
                "severity": str(_enum_value(flag.severity)),
                "gate_effect": str(_enum_value(flag.gate_effect)),
                "source_kind": str(_enum_value(flag.source_kind)),
                "source_reference": flag.source_reference,
                "confidence": _decimal(flag.confidence),
                "description": flag.description,
                "evidence": _json_safe(flag.evidence_json),
            }
            for flag in flags
        ],
    }


def _serialize_deal(
    session: Session,
    deal: DealAnalysis | None,
    status_value: str,
) -> dict[str, Any]:
    if deal is None:
        return {"status": status_value, "scenarios": []}
    scenarios = session.scalars(
        select(DealScenario)
        .where(DealScenario.deal_analysis_id == deal.id)
        .order_by(DealScenario.scenario_type.asc())
    ).all()
    return {
        "deal_analysis_id": str(deal.id),
        "status": status_value,
        "raw_status": str(_enum_value(deal.status)),
        "as_of": _iso(deal.as_of),
        "assumed_purchase_price": _decimal(deal.assumed_purchase_price),
        "asking_price": _decimal(deal.asking_price),
        "max_buy_price": _decimal(deal.max_buy_price),
        "required_negotiation_amount": _decimal(deal.required_negotiation_amount),
        "required_negotiation_pct": _decimal(deal.required_negotiation_pct),
        "total_cost_basis": _decimal(deal.total_cost_basis),
        "expected_exit_price": _decimal(deal.expected_exit_price),
        "expected_profit": _decimal(deal.expected_profit),
        "downside_profit": _decimal(deal.downside_profit),
        "upside_profit": _decimal(deal.upside_profit),
        "roi": _decimal(deal.roi),
        "annualized_roi": _decimal(deal.annualized_roi),
        "expected_holding_days": deal.expected_holding_days,
        "capital_days": _decimal(deal.capital_days),
        "profit_per_capital_day": _decimal(deal.profit_per_capital_day),
        "formula_version": deal.formula_version,
        "costs": {
            "purchase_costs": _decimal(deal.purchase_costs),
            "renovation_cost": _decimal(deal.renovation_cost),
            "sale_costs": _decimal(deal.sale_costs),
            "taxes": _decimal(deal.taxes),
            "financing_costs": _decimal(deal.financing_costs),
            "holding_costs": _decimal(deal.holding_costs),
            "risk_reserve": _decimal(deal.risk_reserve),
            "other_costs": _decimal(deal.other_costs),
        },
        "input_summary": _json_safe(deal.input_summary_json),
        "explanation": _json_safe(deal.explanation_json),
        "scenarios": [
            {
                "scenario_type": str(_enum_value(scenario.scenario_type)),
                "purchase_price": _decimal(scenario.purchase_price),
                "exit_price": _decimal(scenario.exit_price),
                "cost_basis": _decimal(scenario.cost_basis),
                "profit": _decimal(scenario.profit),
                "roi": _decimal(scenario.roi),
                "holding_days": scenario.holding_days,
                "assumptions": _json_safe(scenario.assumptions_json),
            }
            for scenario in scenarios
        ],
    }


def _serialize_comparables(
    session: Session,
    comparable_set: ComparableSet | None,
    status_value: str,
) -> dict[str, Any]:
    if comparable_set is None:
        return {"status": status_value, "items": []}
    rows = session.execute(
        select(ComparableItem, Listing)
        .outerjoin(Listing, ComparableItem.listing_id == Listing.id)
        .where(ComparableItem.comparable_set_id == comparable_set.id)
        .order_by(
            ComparableItem.included_in_valuation.desc(),
            ComparableItem.weight.desc().nullslast(),
            ComparableItem.similarity_score.desc().nullslast(),
        )
    ).all()
    return {
        "comparable_set_id": str(comparable_set.id),
        "status": status_value,
        "as_of": _iso(comparable_set.as_of),
        "engine_version": comparable_set.comparable_engine_version,
        "search_parameters": _json_safe(comparable_set.search_parameters_json),
        "items": [
            {
                "comparable_item_id": str(item.id),
                "comparable_type": str(_enum_value(item.comparable_type)),
                "listing_id": str(item.listing_id) if item.listing_id else None,
                "property_id": str(item.property_id) if item.property_id else None,
                "transaction_record_id": (
                    str(item.transaction_record_id) if item.transaction_record_id else None
                ),
                "listing_title": listing.title if listing else None,
                "similarity_score": _decimal(item.similarity_score),
                "distance_m": _decimal(item.distance_m),
                "age_days_at_analysis": item.age_days_at_analysis,
                "price": _decimal(item.price),
                "price_per_m2": _decimal(item.price_per_m2),
                "weight": _decimal(item.weight),
                "included_in_valuation": item.included_in_valuation,
                "exclusion_reason": item.exclusion_reason,
            }
            for item, listing in rows
        ],
    }


def _serialize_decision_header(
    property_: Property,
    opportunity: OpportunityAssessment | None,
    deal: DealAnalysis | None,
    valuation: Valuation | None,
    fast_sale: FastSaleEstimate | None,
    liquidity: LiquidityAssessment | None,
    risk: RiskAssessment | None,
    listing: Listing | None,
    latest_input_at: datetime | None,
) -> dict[str, Any]:
    asking_price = deal.asking_price if deal else listing.asking_price if listing else None
    currency = valuation.currency if valuation else listing.currency if listing else None
    return {
        "property_id": str(property_.id),
        "property_label": _property_label(property_, listing),
        "recommended_action": (
            str(_enum_value(opportunity.recommended_action)) if opportunity else None
        ),
        "action_priority": _action_priority(
            opportunity.recommended_action if opportunity else None
        ),
        "reason_codes": _json_safe(opportunity.reason_codes_json) if opportunity else [],
        "opportunity_score": _decimal(opportunity.opportunity_score if opportunity else None),
        "ranking_value": _decimal(opportunity.ranking_value if opportunity else None),
        "opportunity_status": _row_status(opportunity, latest_input_at),
        "asking_price": _decimal(asking_price),
        "currency": str(_enum_value(currency)) if currency else None,
        "fair_value_low": _decimal(valuation.fair_value_low if valuation else None),
        "fair_value_base": _decimal(valuation.fair_value_base if valuation else None),
        "fair_value_high": _decimal(valuation.fair_value_high if valuation else None),
        "fast_sale_base": _decimal(fast_sale.value_base if fast_sale else None),
        "max_buy_price": _decimal(deal.max_buy_price if deal else None),
        "expected_profit": _decimal(deal.expected_profit if deal else None),
        "downside_profit": _decimal(deal.downside_profit if deal else None),
        "roi": _decimal(deal.roi if deal else None),
        "liquidity_score": _decimal(liquidity.liquidity_score if liquidity else None),
        "valuation_confidence": _decimal(valuation.confidence if valuation else None),
        "risk_gate": str(_enum_value(risk.hard_gate_status)) if risk else None,
    }


@router.get("/properties/{property_id}")
def get_property_detail(session: DbSession, property_id: uuid.UUID) -> dict[str, Any]:
    property_ = _load_property(session, property_id)
    feature = _latest_feature_for_property(session, property_id)
    listing_rows = _listing_rows(session, property_id)
    current_listing = listing_rows[0][0] if listing_rows else None

    comparable_set = _latest_for_property(session, ComparableSet, property_id)
    llm_analysis = _latest_llm_for_property(session, property_id)
    valuation = _latest_for_property(session, Valuation, property_id)
    liquidity = _latest_for_property(session, LiquidityAssessment, property_id)
    fast_sale = _latest_for_property(session, FastSaleEstimate, property_id)
    seller = _latest_for_property(session, SellerAssessment, property_id)
    risk = _latest_for_property(session, RiskAssessment, property_id)
    deal = _latest_for_property(session, DealAnalysis, property_id)
    opportunity = _latest_for_property(session, OpportunityAssessment, property_id)
    analysis_state = session.get(PropertyAnalysisState, property_id)
    latest_input_at = _latest_listing_input_at(session, property_id)
    last_analysis_at = _latest_analysis_at(
        comparable_set,
        llm_analysis,
        valuation,
        liquidity,
        fast_sale,
        seller,
        risk,
        deal,
        opportunity,
    )
    if analysis_state is not None:
        last_analysis_at = _max_datetime(
            last_analysis_at,
            analysis_state.last_analysis_completed_at,
            analysis_state.last_analysis_started_at,
        )

    statuses = {
        "features": _feature_status(analysis_state, feature),
        "matching": _matching_status(analysis_state, listing_rows),
        "comparables": _state_status(analysis_state, "comparable", comparable_set, latest_input_at),
        "valuation": _state_status(analysis_state, "valuation", valuation, latest_input_at),
        "liquidity": _state_status(analysis_state, "liquidity", liquidity, latest_input_at),
        "fast_sale": _state_status(analysis_state, "fast_sale", fast_sale, latest_input_at),
        "llm": _state_status(analysis_state, "llm", llm_analysis, latest_input_at),
        "seller": _state_status(analysis_state, "seller", seller, latest_input_at),
        "risk": _state_status(analysis_state, "risk", risk, latest_input_at),
        "deal": _state_status(analysis_state, "deal", deal, latest_input_at),
        "opportunity": _state_status(analysis_state, "opportunity", opportunity, latest_input_at),
    }

    return {
        "property": _serialize_property(property_, feature),
        "decision": _serialize_decision_header(
            property_,
            opportunity,
            deal,
            valuation,
            fast_sale,
            liquidity,
            risk,
            current_listing,
            latest_input_at,
        ),
        "freshness": {
            "last_listing_update": _iso(latest_input_at),
            "last_analysis": _iso(last_analysis_at),
            "is_stale": any(status_value == "STALE" for status_value in statuses.values()),
            "statuses": statuses,
        },
        "listings": [_serialize_listing(listing, source) for listing, source in listing_rows],
        "history": _history_items(session, property_id),
        "watch": _watch_detail(session, property_),
        "comparables": _serialize_comparables(session, comparable_set, statuses["comparables"]),
        "valuation": _serialize_valuation(valuation, statuses["valuation"]),
        "liquidity": _serialize_liquidity(
            liquidity,
            fast_sale,
            statuses["liquidity"],
            statuses["fast_sale"],
        ),
        "seller": _serialize_seller(seller, statuses["seller"]),
        "risk": _serialize_risk(session, risk, statuses["risk"]),
        "deal": _serialize_deal(session, deal, statuses["deal"]),
    }


@router.get("/properties/{property_id}/history")
def get_property_history(session: DbSession, property_id: uuid.UUID) -> dict[str, Any]:
    _load_property(session, property_id)
    return {"property_id": str(property_id), "items": _history_items(session, property_id)}


@router.get("/sources")
def get_sources(session: DbSession) -> dict[str, Any]:
    latest_job_sq = _latest_source_job_subquery()
    latest_job = aliased(JobRun)

    rows = session.execute(
        select(Source, SourceRuntimeState, latest_job)
        .outerjoin(SourceRuntimeState, SourceRuntimeState.source_id == Source.id)
        .outerjoin(
            latest_job_sq,
            (latest_job_sq.c.source_id == Source.id) & (latest_job_sq.c.rn == 1),
        )
        .outerjoin(latest_job, latest_job.id == latest_job_sq.c.id)
        .order_by(Source.code.asc())
    ).all()

    items: list[dict[str, Any]] = []
    summary = {
        "HEALTHY": 0,
        "DEGRADED": 0,
        "FAILED": 0,
        "DISABLED": 0,
        "UNKNOWN": 0,
    }
    for source, state, job in rows:
        source_status = (
            "DISABLED"
            if not source.is_enabled
            else str(_enum_value(state.health_status if state else "UNKNOWN"))
        )
        summary[source_status] = summary.get(source_status, 0) + 1
        items.append(
            {
                "source_id": str(source.id),
                "name": source.name,
                "code": source.code,
                "source_type": str(_enum_value(source.source_type)),
                "base_url": source.base_url,
                "enabled": source.is_enabled,
                "capabilities": {
                    "discovery": source.supports_discovery,
                    "market_scan": source.supports_market_scan,
                    "detail_fetch": source.supports_detail_fetch,
                    "transaction_data": source.supports_transaction_data,
                },
                "health_status": source_status,
                "last_attempt_at": _iso(state.last_attempt_at) if state else None,
                "last_success_at": _iso(state.last_success_at) if state else None,
                "last_discovery_success_at": (
                    _iso(state.last_discovery_success_at) if state else None
                ),
                "last_market_scan_success_at": (
                    _iso(state.last_market_scan_success_at) if state else None
                ),
                "last_error_at": _iso(state.last_error_at) if state else None,
                "last_error_type": state.last_error_type if state else None,
                "last_error_message": state.last_error_message if state else None,
                "recent_http_error_count": state.recent_http_error_count if state else 0,
                "recent_parse_error_count": state.recent_parse_error_count if state else 0,
                "consecutive_zero_result_count": (
                    state.consecutive_zero_result_count if state else 0
                ),
                "last_discovered_count": state.last_discovered_count if state else None,
                "latest_job": None
                if job is None
                else {
                    "job_id": str(job.id),
                    "job_type": job.job_type,
                    "status": job.status,
                    "started_at": _iso(job.started_at),
                    "finished_at": _iso(job.finished_at),
                    "items_discovered": job.items_discovered,
                    "items_processed": job.items_processed,
                    "items_changed": job.items_changed,
                    "items_failed": job.items_failed,
                    "parse_errors": job.parse_errors,
                    "http_errors": job.http_errors,
                    "error_summary": job.error_summary,
                },
            }
        )

    return {"items": items, "summary": summary, "source_warnings": _source_warnings(session)}


@router.get("/settings")
def get_dashboard_settings(session: DbSession) -> dict[str, Any]:
    settings = get_settings()
    investment_profiles = session.scalars(
        select(InvestmentProfile).order_by(
            InvestmentProfile.is_default.desc(),
            InvestmentProfile.updated_at.desc(),
            InvestmentProfile.name.asc(),
        )
    ).all()
    cost_profiles = session.scalars(
        select(CostProfile).order_by(
            CostProfile.is_active.desc(),
            CostProfile.updated_at.desc(),
            CostProfile.name.asc(),
        )
    ).all()
    source_counts = session.execute(
        select(Source.is_enabled, func.count()).group_by(Source.is_enabled)
    ).all()

    return {
        "app": {
            "environment": settings.app_env,
            "base_url": settings.app_base_url,
            "auth_mode": "bearer_token" if settings.api_access_token else "local_unprotected",
            "production_access_configured": bool(settings.api_access_token),
        },
        "api": {
            "cors_allowed_origins": [
                origin.strip()
                for origin in settings.cors_allowed_origins.split(",")
                if origin.strip()
            ],
        },
        "notifications": {
            "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
            "telegram_channel": "TELEGRAM",
        },
        "investment_profiles": [
            {
                "profile_id": str(profile.id),
                "name": profile.name,
                "is_default": profile.is_default,
                "min_expected_profit": _decimal(profile.min_expected_profit),
                "min_downside_profit": _decimal(profile.min_downside_profit),
                "min_roi": _decimal(profile.min_roi),
                "max_expected_holding_days": profile.max_expected_holding_days,
                "min_liquidity_score": _decimal(profile.min_liquidity_score),
                "min_valuation_confidence": _decimal(profile.min_valuation_confidence),
                "default_risk_reserve": _decimal(profile.default_risk_reserve),
                "desired_profit": _decimal(profile.desired_profit),
                "version": profile.version,
            }
            for profile in investment_profiles
        ],
        "cost_profiles": [
            {
                "profile_id": str(profile.id),
                "name": profile.name,
                "code": profile.code,
                "currency": str(_enum_value(profile.currency)),
                "is_active": profile.is_active,
                "version": profile.version,
            }
            for profile in cost_profiles
        ],
        "sources": {
            "enabled": sum(int(count) for is_enabled, count in source_counts if is_enabled),
            "disabled": sum(int(count) for is_enabled, count in source_counts if not is_enabled),
        },
    }
