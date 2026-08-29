from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.state import (
    mark_modules_pending,
    mark_modules_stale,
    mark_modules_success,
    status_from_analysis_row,
)
from app.db.models import (
    Alert,
    DealAnalysis,
    FastSaleEstimate,
    LiquidityAssessment,
    Listing,
    ListingEvent,
    OpportunityAssessment,
    Property,
    RiskAssessment,
    SellerAssessment,
    Valuation,
    WatchRule,
    WatchTriggerEvent,
)
from app.deals.deal_engine import analyze_deal
from app.domain.enums import (
    AnalysisStatus,
    FastSaleStatus,
    LiquidityStatus,
    ListingEventType,
    OpportunityAction,
    ValuationStatus,
    WatchRuleType,
)
from app.intelligence.seller_risk import assess_seller_intelligence_and_risk
from app.opportunities.opportunity_engine import OpportunityRunResult, assess_opportunity_and_alert
from app.opportunities.telegram import TelegramSender

WATCH_REANALYSIS_VERSION = "watch_reanalysis_v1"

DEFAULT_MANUAL_REANALYSIS_MODULES = (
    "features",
    "comparable",
    "valuation",
    "liquidity",
    "fast_sale",
    "llm",
    "seller",
    "risk",
    "deal",
    "opportunity",
)

EVENT_INVALIDATION_MODULES: dict[ListingEventType, tuple[str, ...]] = {
    ListingEventType.PRICE_CHANGED: ("deal", "opportunity"),
    ListingEventType.DESCRIPTION_CHANGED: ("llm", "seller", "risk", "deal", "opportunity"),
    ListingEventType.SELLER_CHANGED: ("seller", "risk", "deal", "opportunity"),
}

EVENT_REANALYSIS_MODULES: dict[ListingEventType, tuple[str, ...]] = {
    ListingEventType.PRICE_CHANGED: ("deal", "opportunity"),
    ListingEventType.DESCRIPTION_CHANGED: ("seller", "risk", "deal", "opportunity"),
    ListingEventType.SELLER_CHANGED: ("seller", "risk", "deal", "opportunity"),
}

DEFAULT_RELEVANT_CHANGE_EVENTS = frozenset(EVENT_INVALIDATION_MODULES.keys())


@dataclass(frozen=True)
class ReanalysisRunResult:
    deal_analysis: DealAnalysis | None
    opportunity_result: OpportunityRunResult | None
    seller_assessment: SellerAssessment | None
    risk_assessment: RiskAssessment | None
    modules: tuple[str, ...]


@dataclass(frozen=True)
class WatchTriggerEvaluation:
    watch_rule: WatchRule
    trigger_event: WatchTriggerEvent | None
    invalidated_modules: tuple[str, ...]
    reanalysis: ReanalysisRunResult | None


def create_or_update_watch_rule(
    session: Session,
    property_: Property,
    *,
    rule_type: WatchRuleType | str | None = None,
    threshold_numeric: Decimal | None = None,
    rule_config: dict[str, object] | None = None,
    commit: bool = False,
) -> WatchRule:
    normalized_rule_type = WatchRuleType(rule_type) if rule_type is not None else None
    _validate_rule_input(normalized_rule_type, threshold_numeric)

    active_rules = session.scalars(
        select(WatchRule).where(
            WatchRule.property_id == property_.id,
            WatchRule.is_active.is_(True),
        )
    ).all()
    for active_rule in active_rules:
        active_rule.is_active = False

    rule = WatchRule(
        property=property_,
        is_active=True,
        rule_type=normalized_rule_type,
        threshold_numeric=threshold_numeric,
        rule_config_json=rule_config or {},
    )
    session.add(rule)
    session.flush()
    if commit:
        session.commit()
    return rule


def deactivate_watch_rules(
    session: Session,
    property_: Property,
    *,
    commit: bool = False,
) -> list[WatchRule]:
    rules = session.scalars(
        select(WatchRule).where(
            WatchRule.property_id == property_.id,
            WatchRule.is_active.is_(True),
        )
    ).all()
    for rule in rules:
        rule.is_active = False
    session.flush()
    if commit:
        session.commit()
    return list(rules)


def queue_manual_reanalysis(
    session: Session,
    property_: Property,
    *,
    modules: tuple[str, ...] = DEFAULT_MANUAL_REANALYSIS_MODULES,
    as_of: datetime | None = None,
    commit: bool = False,
) -> dict[str, object]:
    queued_at = _aware_datetime(as_of or _utcnow())
    mark_modules_pending(session, property_, modules, as_of=queued_at)
    if commit:
        session.commit()
    return {
        "status": "QUEUED",
        "property_id": str(property_.id),
        "queued_modules": list(modules),
        "queued_at": queued_at.isoformat(),
    }


def evaluate_watch_rules_for_listing_event(
    session: Session,
    listing_event: ListingEvent,
    *,
    sender: TelegramSender | None = None,
    app_base_url: str = "http://localhost:8000",
    commit: bool = False,
) -> list[WatchTriggerEvaluation]:
    session.flush()
    listing = listing_event.listing or session.get(Listing, listing_event.listing_id)
    if listing is None or listing.property_id is None:
        return []
    property_ = listing.property or session.get(Property, listing.property_id)
    if property_ is None:
        return []

    active_rules = session.scalars(
        select(WatchRule)
        .where(
            WatchRule.property_id == property_.id,
            WatchRule.is_active.is_(True),
        )
        .order_by(WatchRule.created_at.asc(), WatchRule.id.asc())
    ).all()
    if not active_rules:
        return []

    detected_at = _aware_datetime(listing_event.detected_at)
    invalidated_modules = modules_invalidated_by_event(listing_event)

    results: list[WatchTriggerEvaluation] = []
    stale_marked = False
    for rule in active_rules:
        rule.last_evaluated_at = detected_at
        if not _rule_matches_event(rule, listing_event):
            if invalidated_modules and not stale_marked:
                mark_modules_stale(session, property_, invalidated_modules, as_of=detected_at)
                stale_marked = True
            results.append(
                WatchTriggerEvaluation(
                    watch_rule=rule,
                    trigger_event=None,
                    invalidated_modules=invalidated_modules,
                    reanalysis=None,
                )
            )
            continue

        change_key = _change_key(rule, listing_event)
        if _trigger_already_recorded(session, rule, change_key):
            results.append(
                WatchTriggerEvaluation(
                    watch_rule=rule,
                    trigger_event=None,
                    invalidated_modules=invalidated_modules,
                    reanalysis=None,
                )
            )
            continue

        if invalidated_modules and not stale_marked:
            mark_modules_stale(session, property_, invalidated_modules, as_of=detected_at)
            stale_marked = True

        previous_opportunity = _latest_for_property(
            session,
            OpportunityAssessment,
            property_,
            as_of=detected_at,
        )
        reanalysis = reanalyze_property_after_listing_change(
            session,
            property_,
            listing_event,
            sender=sender,
            app_base_url=app_base_url,
        )
        trigger_event = WatchTriggerEvent(
            watch_rule=rule,
            property=property_,
            listing_event_id=listing_event.id,
            trigger_type=rule.rule_type,
            change_key=change_key,
            summary_json=_what_changed_summary(
                listing_event,
                rule=rule,
                previous_opportunity=previous_opportunity,
                new_opportunity=(
                    reanalysis.opportunity_result.assessment
                    if reanalysis.opportunity_result is not None
                    else None
                ),
            ),
            invalidated_modules_json=list(invalidated_modules),
            reanalyzed_modules_json=list(reanalysis.modules),
            previous_opportunity_assessment_id=(
                previous_opportunity.id if previous_opportunity is not None else None
            ),
            new_opportunity_assessment_id=(
                reanalysis.opportunity_result.assessment.id
                if reanalysis.opportunity_result is not None
                else None
            ),
            alert_id=(
                reanalysis.opportunity_result.alert.id
                if reanalysis.opportunity_result is not None
                and reanalysis.opportunity_result.alert is not None
                else None
            ),
            triggered_at=detected_at,
        )
        session.add(trigger_event)
        session.flush()
        rule.triggered_at = detected_at
        rule.last_triggered_change_key = change_key
        results.append(
            WatchTriggerEvaluation(
                watch_rule=rule,
                trigger_event=trigger_event,
                invalidated_modules=invalidated_modules,
                reanalysis=reanalysis,
            )
        )

    session.flush()
    if commit:
        session.commit()
    return results


def reanalyze_property_after_listing_change(
    session: Session,
    property_: Property,
    listing_event: ListingEvent,
    *,
    sender: TelegramSender | None = None,
    app_base_url: str = "http://localhost:8000",
) -> ReanalysisRunResult:
    as_of = _aware_datetime(listing_event.detected_at)
    modules = EVENT_REANALYSIS_MODULES.get(listing_event.event_type, ())
    if not modules:
        return ReanalysisRunResult(
            deal_analysis=None,
            opportunity_result=None,
            seller_assessment=None,
            risk_assessment=None,
            modules=(),
        )

    previous_deal = _latest_for_property(session, DealAnalysis, property_, as_of=as_of)
    seller = _latest_for_property(session, SellerAssessment, property_, as_of=as_of)
    risk = _risk_for_reanalysis(session, property_, previous_deal, as_of)

    if listing_event.event_type in {
        ListingEventType.DESCRIPTION_CHANGED,
        ListingEventType.SELLER_CHANGED,
    }:
        seller_risk = assess_seller_intelligence_and_risk(session, property_, as_of=as_of)
        seller = seller_risk.seller_assessment
        risk = seller_risk.risk_assessment

    deal_result = analyze_deal(
        session,
        property_,
        valuation=_latest_successful_valuation(session, property_, previous_deal, as_of),
        liquidity_assessment=_latest_successful_liquidity(session, property_, previous_deal, as_of),
        fast_sale_estimate=_latest_successful_fast_sale(session, property_, previous_deal, as_of),
        risk_assessment=risk,
        cost_profile=previous_deal.cost_profile if previous_deal is not None else None,
        investment_profile=(
            previous_deal.investment_profile if previous_deal is not None else None
        ),
        renovation_cost=previous_deal.renovation_cost if previous_deal is not None else None,
        expected_holding_days=(
            previous_deal.expected_holding_days if previous_deal is not None else None
        ),
        as_of=as_of,
    )
    opportunity_result = assess_opportunity_and_alert(
        session,
        property_,
        deal_analysis=deal_result.deal_analysis,
        seller_assessment=seller,
        sender=sender,
        app_base_url=app_base_url,
        as_of=as_of,
    )
    _mark_reanalysis_success(
        session,
        property_,
        listing_event,
        deal_analysis=deal_result.deal_analysis,
        opportunity_result=opportunity_result,
        seller=seller,
        risk=risk,
        as_of=as_of,
    )
    return ReanalysisRunResult(
        deal_analysis=deal_result.deal_analysis,
        opportunity_result=opportunity_result,
        seller_assessment=seller,
        risk_assessment=risk,
        modules=modules,
    )


def modules_invalidated_by_event(listing_event: ListingEvent) -> tuple[str, ...]:
    return EVENT_INVALIDATION_MODULES.get(listing_event.event_type, ())


def active_watch_rule_for_property(session: Session, property_: Property) -> WatchRule | None:
    return session.scalars(
        select(WatchRule)
        .where(
            WatchRule.property_id == property_.id,
            WatchRule.is_active.is_(True),
        )
        .order_by(WatchRule.created_at.desc(), WatchRule.id.desc())
    ).first()


def latest_watch_trigger_for_property(
    session: Session,
    property_: Property,
) -> WatchTriggerEvent | None:
    return session.scalars(
        select(WatchTriggerEvent)
        .where(WatchTriggerEvent.property_id == property_.id)
        .order_by(
            WatchTriggerEvent.triggered_at.desc(),
            WatchTriggerEvent.created_at.desc(),
            WatchTriggerEvent.id.desc(),
        )
    ).first()


def latest_alert_for_assessment(
    session: Session,
    opportunity_assessment: OpportunityAssessment,
) -> Alert | None:
    return session.scalars(
        select(Alert)
        .where(Alert.opportunity_assessment_id == opportunity_assessment.id)
        .order_by(Alert.created_at.desc(), Alert.id.desc())
    ).first()


def _validate_rule_input(
    rule_type: WatchRuleType | None,
    threshold_numeric: Decimal | None,
) -> None:
    if rule_type in {WatchRuleType.PRICE_BELOW, WatchRuleType.PRICE_DROP_PERCENT}:
        if threshold_numeric is None:
            raise ValueError(f"{rule_type.value} requires threshold_numeric")
        if threshold_numeric <= 0:
            raise ValueError("threshold_numeric must be positive")


def _rule_matches_event(rule: WatchRule, listing_event: ListingEvent) -> bool:
    if rule.rule_type is None:
        return listing_event.event_type in DEFAULT_RELEVANT_CHANGE_EVENTS
    if rule.rule_type == WatchRuleType.ANY_PRICE_CHANGE:
        return listing_event.event_type == ListingEventType.PRICE_CHANGED
    if rule.rule_type == WatchRuleType.PRICE_BELOW:
        return _price_below_matches(rule, listing_event)
    if rule.rule_type == WatchRuleType.PRICE_DROP_PERCENT:
        return _price_drop_percent_matches(rule, listing_event)
    if rule.rule_type == WatchRuleType.DESCRIPTION_CHANGE:
        return listing_event.event_type == ListingEventType.DESCRIPTION_CHANGED
    if rule.rule_type == WatchRuleType.SELLER_CHANGE:
        return listing_event.event_type == ListingEventType.SELLER_CHANGED
    return False


def _price_below_matches(rule: WatchRule, listing_event: ListingEvent) -> bool:
    if (
        listing_event.event_type != ListingEventType.PRICE_CHANGED
        or rule.threshold_numeric is None
        or listing_event.new_price is None
    ):
        return False
    if listing_event.old_price is None:
        return listing_event.new_price <= rule.threshold_numeric
    return listing_event.old_price > rule.threshold_numeric >= listing_event.new_price


def _price_drop_percent_matches(rule: WatchRule, listing_event: ListingEvent) -> bool:
    if (
        listing_event.event_type != ListingEventType.PRICE_CHANGED
        or rule.threshold_numeric is None
        or listing_event.old_price is None
        or listing_event.new_price is None
        or listing_event.old_price <= 0
        or listing_event.new_price >= listing_event.old_price
    ):
        return False
    drop_pct = (listing_event.old_price - listing_event.new_price) / listing_event.old_price
    return drop_pct >= _threshold_as_ratio(rule.threshold_numeric)


def _threshold_as_ratio(value: Decimal) -> Decimal:
    if value >= 1:
        return value / Decimal("100")
    return value


def _trigger_already_recorded(session: Session, rule: WatchRule, change_key: str) -> bool:
    if rule.last_triggered_change_key == change_key:
        return True
    return (
        session.scalar(
            select(WatchTriggerEvent.id).where(
                WatchTriggerEvent.watch_rule_id == rule.id,
                WatchTriggerEvent.change_key == change_key,
            )
        )
        is not None
    )


def _change_key(rule: WatchRule, listing_event: ListingEvent) -> str:
    threshold = str(rule.threshold_numeric) if rule.threshold_numeric is not None else "default"
    event_id = str(listing_event.id) if listing_event.id is not None else "pending"
    rule_type = rule.rule_type.value if rule.rule_type is not None else "DEFAULT"
    return f"{event_id}:{rule_type}:{threshold}"


def _what_changed_summary(
    listing_event: ListingEvent,
    *,
    rule: WatchRule,
    previous_opportunity: OpportunityAssessment | None,
    new_opportunity: OpportunityAssessment | None,
) -> dict[str, object]:
    previous_action = (
        previous_opportunity.recommended_action.value if previous_opportunity is not None else None
    )
    new_action = new_opportunity.recommended_action.value if new_opportunity is not None else None
    summary: dict[str, object] = {
        "version": WATCH_REANALYSIS_VERSION,
        "event_type": listing_event.event_type.value,
        "trigger_type": rule.rule_type.value if rule.rule_type is not None else "DEFAULT",
        "threshold_numeric": _decimal_to_string(rule.threshold_numeric),
        "listing_event_id": str(listing_event.id) if listing_event.id is not None else None,
        "detected_at": _aware_datetime(listing_event.detected_at).isoformat(),
        "previous_action": previous_action,
        "new_action": new_action,
        "action_upgraded": _action_rank(new_action) > _action_rank(previous_action),
    }
    if listing_event.event_type == ListingEventType.PRICE_CHANGED:
        summary.update(
            {
                "summary_text": (
                    "Price changed from "
                    f"{_decimal_to_string(listing_event.old_price)} to "
                    f"{_decimal_to_string(listing_event.new_price)}"
                ),
                "old_price": _decimal_to_string(listing_event.old_price),
                "new_price": _decimal_to_string(listing_event.new_price),
                "price_drop_pct": _decimal_to_string(_price_drop_pct(listing_event)),
            }
        )
    elif listing_event.event_type == ListingEventType.DESCRIPTION_CHANGED:
        summary.update(
            {
                "summary_text": "Description changed",
                "old_description": _old_new_value(listing_event.old_value_json, "description"),
                "new_description": _old_new_value(listing_event.new_value_json, "description"),
            }
        )
    elif listing_event.event_type == ListingEventType.SELLER_CHANGED:
        summary.update(
            {
                "summary_text": "Seller changed",
                "old_seller": listing_event.old_value_json or {},
                "new_seller": listing_event.new_value_json or {},
            }
        )
    else:
        summary["summary_text"] = listing_event.event_type.value
    return summary


def _mark_reanalysis_success(
    session: Session,
    property_: Property,
    listing_event: ListingEvent,
    *,
    deal_analysis: DealAnalysis,
    opportunity_result: OpportunityRunResult,
    seller: SellerAssessment | None,
    risk: RiskAssessment | None,
    as_of: datetime,
) -> None:
    statuses: dict[str, AnalysisStatus] = {
        "deal": AnalysisStatus(status_from_analysis_row(deal_analysis)),
        "opportunity": AnalysisStatus.SUCCESS,
    }
    if listing_event.event_type in {
        ListingEventType.DESCRIPTION_CHANGED,
        ListingEventType.SELLER_CHANGED,
    }:
        statuses["seller"] = (
            AnalysisStatus.SUCCESS if seller is not None else AnalysisStatus.NOT_RUN
        )
        statuses["risk"] = AnalysisStatus.SUCCESS if risk is not None else AnalysisStatus.NOT_RUN
    mark_modules_success(session, property_, statuses, as_of=as_of)
    _ = opportunity_result


def _latest_for_property(
    session: Session,
    model: type[Any],
    property_: Property,
    *,
    as_of: datetime,
) -> Any | None:
    return session.scalars(
        select(model)
        .where(model.property_id == property_.id, model.as_of <= as_of)
        .order_by(model.as_of.desc(), model.created_at.desc(), model.id.desc())
    ).first()


def _latest_successful_valuation(
    session: Session,
    property_: Property,
    previous_deal: DealAnalysis | None,
    as_of: datetime,
) -> Valuation | None:
    if (
        previous_deal is not None
        and previous_deal.valuation is not None
        and previous_deal.valuation.as_of <= as_of
        and previous_deal.valuation.status == ValuationStatus.SUCCESS
    ):
        return previous_deal.valuation
    return session.scalars(
        select(Valuation)
        .where(
            Valuation.property_id == property_.id,
            Valuation.as_of <= as_of,
            Valuation.status == ValuationStatus.SUCCESS,
        )
        .order_by(Valuation.as_of.desc(), Valuation.created_at.desc(), Valuation.id.desc())
    ).first()


def _latest_successful_liquidity(
    session: Session,
    property_: Property,
    previous_deal: DealAnalysis | None,
    as_of: datetime,
) -> LiquidityAssessment | None:
    if (
        previous_deal is not None
        and previous_deal.liquidity_assessment is not None
        and previous_deal.liquidity_assessment.as_of <= as_of
        and previous_deal.liquidity_assessment.status == LiquidityStatus.SUCCESS
    ):
        return previous_deal.liquidity_assessment
    return session.scalars(
        select(LiquidityAssessment)
        .where(
            LiquidityAssessment.property_id == property_.id,
            LiquidityAssessment.as_of <= as_of,
            LiquidityAssessment.status == LiquidityStatus.SUCCESS,
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
    previous_deal: DealAnalysis | None,
    as_of: datetime,
) -> FastSaleEstimate | None:
    if (
        previous_deal is not None
        and previous_deal.fast_sale_estimate is not None
        and previous_deal.fast_sale_estimate.as_of <= as_of
        and previous_deal.fast_sale_estimate.status == FastSaleStatus.SUCCESS
    ):
        return previous_deal.fast_sale_estimate
    return session.scalars(
        select(FastSaleEstimate)
        .where(
            FastSaleEstimate.property_id == property_.id,
            FastSaleEstimate.as_of <= as_of,
            FastSaleEstimate.status == FastSaleStatus.SUCCESS,
        )
        .order_by(
            FastSaleEstimate.as_of.desc(),
            FastSaleEstimate.created_at.desc(),
            FastSaleEstimate.id.desc(),
        )
    ).first()


def _risk_for_reanalysis(
    session: Session,
    property_: Property,
    previous_deal: DealAnalysis | None,
    as_of: datetime,
) -> RiskAssessment | None:
    if (
        previous_deal is not None
        and previous_deal.risk_assessment is not None
        and previous_deal.risk_assessment.as_of <= as_of
    ):
        return previous_deal.risk_assessment
    return _latest_for_property(session, RiskAssessment, property_, as_of=as_of)


def _price_drop_pct(listing_event: ListingEvent) -> Decimal | None:
    if (
        listing_event.old_price is None
        or listing_event.new_price is None
        or listing_event.old_price <= 0
        or listing_event.new_price >= listing_event.old_price
    ):
        return None
    return (listing_event.old_price - listing_event.new_price) / listing_event.old_price


def _old_new_value(values: dict[str, object] | None, key: str) -> object | None:
    if not values:
        return None
    return values.get(key)


def _decimal_to_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _action_rank(action: str | None) -> int:
    if action is None:
        return -1
    ranks = {
        OpportunityAction.IGNORE.value: 0,
        OpportunityAction.WATCH.value: 1,
        OpportunityAction.REVIEW.value: 2,
        OpportunityAction.CALL.value: 3,
        OpportunityAction.URGENT_CALL.value: 4,
    }
    return ranks.get(action, -1)


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _utcnow() -> datetime:
    return datetime.now(UTC)
