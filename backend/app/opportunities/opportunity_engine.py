from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    CostProfile,
    DealAnalysis,
    FastSaleEstimate,
    InvestmentProfile,
    LiquidityAssessment,
    Listing,
    ListingEvent,
    OpportunityAssessment,
    Property,
    RiskAssessment,
    SellerAssessment,
    Valuation,
)
from app.domain.enums import (
    AlertChannel,
    AlertStatus,
    AlertType,
    AnalysisLevel,
    DealAnalysisStatus,
    FastSaleStatus,
    LiquidityStatus,
    ListingEventType,
    ListingStatus,
    OpportunityAction,
    RiskGateStatus,
    ValuationStatus,
)
from app.opportunities.telegram import TelegramSender

OPPORTUNITY_RULES_VERSION = "opportunity_rules_v1"
NO_QUALIFYING_OPPORTUNITIES = "NO_QUALIFYING_OPPORTUNITIES"
QUALIFYING_OPPORTUNITIES = "QUALIFYING_OPPORTUNITIES"

ALERTABLE_ACTIONS = {OpportunityAction.CALL, OpportunityAction.URGENT_CALL}
MAX_ALERT_SEND_ATTEMPTS = 3

CALL_SCORE_THRESHOLD = Decimal("65.00")
URGENT_SCORE_THRESHOLD = Decimal("82.00")
URGENT_NEGOTIATION_PCT = Decimal("0.030000")
CALL_NEGOTIATION_PCT = Decimal("0.100000")
WATCH_NEGOTIATION_PCT = Decimal("0.200000")
RECENT_LISTING_DAYS = 3
RECENT_PRICE_CUT_DAYS = 14
LARGE_PRICE_CUT_PCT = Decimal("0.050000")

SCORE_QUANTIZER = Decimal("0.01")
RANKING_QUANTIZER = Decimal("0.0001")


@dataclass(frozen=True)
class ScoreResult:
    score: Decimal
    components: dict[str, str]


@dataclass(frozen=True)
class ListingContext:
    active_listing: Listing | None
    time_sensitive_signals: list[str]
    last_change: str | None


@dataclass(frozen=True)
class OpportunityDecision:
    recommended_action: OpportunityAction
    opportunity_score: Decimal | None
    ranking_value: Decimal | None
    reason_codes: list[str]
    explanation_json: dict[str, object]
    state_hash: str


@dataclass(frozen=True)
class AlertDeliveryAttempt:
    alert: Alert
    attempted: bool
    success: bool
    skipped_reason: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class OpportunityRunResult:
    assessment: OpportunityAssessment
    alert: Alert | None
    delivery: AlertDeliveryAttempt | None


@dataclass(frozen=True)
class OpportunityBatchResult:
    assessments: list[OpportunityAssessment]
    alerts: list[Alert]
    status: str


def assess_opportunity(
    session: Session,
    property_: Property,
    *,
    deal_analysis: DealAnalysis | None = None,
    seller_assessment: SellerAssessment | None = None,
    as_of: datetime | None = None,
    commit: bool = False,
) -> OpportunityAssessment:
    analysis_as_of = _analysis_as_of(as_of, deal_analysis)
    selected_deal = deal_analysis or _latest_deal_analysis(session, property_, analysis_as_of)
    selected_seller = seller_assessment or _latest_seller_assessment(
        session,
        property_,
        analysis_as_of,
    )
    decision = build_opportunity_decision(
        session,
        property_,
        deal_analysis=selected_deal,
        seller_assessment=selected_seller,
        as_of=analysis_as_of,
    )
    assessment = OpportunityAssessment(
        property=property_,
        deal_analysis=selected_deal,
        as_of=analysis_as_of,
        recommended_action=decision.recommended_action,
        opportunity_score=decision.opportunity_score,
        ranking_value=decision.ranking_value,
        reason_codes_json=decision.reason_codes,
        explanation_json=decision.explanation_json,
        rules_version=OPPORTUNITY_RULES_VERSION,
        state_hash=decision.state_hash,
    )
    session.add(assessment)
    session.flush()
    if commit:
        session.commit()
    return assessment


def assess_opportunity_and_alert(
    session: Session,
    property_: Property,
    *,
    deal_analysis: DealAnalysis | None = None,
    seller_assessment: SellerAssessment | None = None,
    sender: TelegramSender | None = None,
    app_base_url: str = "http://localhost:8000",
    as_of: datetime | None = None,
    commit: bool = False,
) -> OpportunityRunResult:
    assessment = assess_opportunity(
        session,
        property_,
        deal_analysis=deal_analysis,
        seller_assessment=seller_assessment,
        as_of=as_of,
    )
    alert = create_opportunity_alert(session, assessment, app_base_url=app_base_url)
    delivery = None
    if sender is not None and alert is not None:
        delivery = deliver_telegram_alert(session, alert, sender)

    if commit:
        session.commit()
    return OpportunityRunResult(assessment=assessment, alert=alert, delivery=delivery)


def assess_opportunity_batch(
    session: Session,
    properties: list[Property],
    *,
    sender: TelegramSender | None = None,
    app_base_url: str = "http://localhost:8000",
    as_of: datetime | None = None,
    commit: bool = False,
) -> OpportunityBatchResult:
    assessments: list[OpportunityAssessment] = []
    alerts: list[Alert] = []
    for property_ in properties:
        result = assess_opportunity_and_alert(
            session,
            property_,
            sender=sender,
            app_base_url=app_base_url,
            as_of=as_of,
        )
        assessments.append(result.assessment)
        if result.alert is not None:
            alerts.append(result.alert)

    if commit:
        session.commit()
    status = QUALIFYING_OPPORTUNITIES if alerts else NO_QUALIFYING_OPPORTUNITIES
    return OpportunityBatchResult(assessments=assessments, alerts=alerts, status=status)


def build_opportunity_decision(
    session: Session,
    property_: Property,
    *,
    deal_analysis: DealAnalysis | None,
    seller_assessment: SellerAssessment | None = None,
    as_of: datetime | None = None,
) -> OpportunityDecision:
    analysis_as_of = _analysis_as_of(as_of, deal_analysis)
    selected_risk = _risk_for_decision(session, property_, deal_analysis, analysis_as_of)
    selected_valuation = deal_analysis.valuation if deal_analysis is not None else None
    selected_liquidity = deal_analysis.liquidity_assessment if deal_analysis is not None else None
    selected_fast_sale = deal_analysis.fast_sale_estimate if deal_analysis is not None else None
    selected_investment_profile = (
        deal_analysis.investment_profile if deal_analysis is not None else None
    )
    selected_cost_profile = deal_analysis.cost_profile if deal_analysis is not None else None
    listing_context = _listing_context(session, property_, analysis_as_of)

    if selected_risk is not None and selected_risk.hard_gate_status == RiskGateStatus.BLOCK:
        return _decision(
            property_,
            deal_analysis=deal_analysis,
            valuation=selected_valuation,
            liquidity=selected_liquidity,
            fast_sale=selected_fast_sale,
            risk=selected_risk,
            seller=seller_assessment,
            listing_context=listing_context,
            action=OpportunityAction.IGNORE,
            score=None,
            ranking_value=None,
            reason_codes=["RISK_BLOCK"],
            gate_details={"hard_gate": "RISK_BLOCK"},
            score_components={},
        )

    minimum_data_issues = _minimum_data_issues(
        property_,
        deal_analysis=deal_analysis,
        valuation=selected_valuation,
        liquidity=selected_liquidity,
        fast_sale=selected_fast_sale,
        risk=selected_risk,
        cost_profile=selected_cost_profile,
        investment_profile=selected_investment_profile,
    )
    if minimum_data_issues:
        return _decision(
            property_,
            deal_analysis=deal_analysis,
            valuation=selected_valuation,
            liquidity=selected_liquidity,
            fast_sale=selected_fast_sale,
            risk=selected_risk,
            seller=seller_assessment,
            listing_context=listing_context,
            action=OpportunityAction.REVIEW,
            score=None,
            ranking_value=None,
            reason_codes=[*minimum_data_issues, "MINIMUM_DATA_INCOMPLETE"],
            gate_details={"minimum_data_issues": minimum_data_issues},
            score_components={},
        )

    assert deal_analysis is not None
    assert selected_valuation is not None
    assert selected_liquidity is not None
    assert selected_fast_sale is not None
    assert selected_risk is not None
    assert selected_investment_profile is not None

    confidence_issues = _confidence_issues(
        valuation=selected_valuation,
        liquidity=selected_liquidity,
        investment_profile=selected_investment_profile,
    )
    economic_issues = _economic_issues(
        deal_analysis=deal_analysis,
        investment_profile=selected_investment_profile,
    )
    score_result = _calculate_score(
        deal_analysis=deal_analysis,
        valuation=selected_valuation,
        liquidity=selected_liquidity,
        seller=seller_assessment,
        investment_profile=selected_investment_profile,
    )
    ranking_value = _calculate_ranking_value(deal_analysis)

    if confidence_issues:
        action = OpportunityAction.REVIEW
        reason_codes = [*confidence_issues, "CONFIDENCE_REVIEW_REQUIRED"]
    elif economic_issues:
        action = _action_for_failed_economics(deal_analysis, economic_issues)
        reason_codes = [*economic_issues, _reason_for_failed_economics(action)]
    elif selected_risk.hard_gate_status == RiskGateStatus.VERIFY:
        if _call_eligible(deal_analysis, score_result.score):
            action = OpportunityAction.CALL
            reason_codes = ["VERIFY_RISK_CALL_FOR_INFORMATION", "ECONOMICS_PASS"]
        else:
            action = OpportunityAction.REVIEW
            reason_codes = ["RISK_VERIFY_REVIEW_REQUIRED"]
    elif _urgent_eligible(
        deal_analysis,
        score_result.score,
        selected_investment_profile,
        listing_context.time_sensitive_signals,
    ):
        action = OpportunityAction.URGENT_CALL
        reason_codes = [
            "STRONG_ECONOMICS",
            _negotiation_reason(deal_analysis),
            *(listing_context.time_sensitive_signals or ["UNUSUALLY_STRONG_DEAL"]),
        ]
    elif _call_eligible(deal_analysis, score_result.score):
        action = OpportunityAction.CALL
        reason_codes = ["ECONOMICS_PASS", "NEGOTIATION_FEASIBLE"]
    elif _watch_eligible(deal_analysis, listing_context.time_sensitive_signals):
        action = OpportunityAction.WATCH
        reason_codes = ["WATCH_FOR_PRICE_IMPROVEMENT"]
    else:
        action = OpportunityAction.IGNORE
        reason_codes = ["LOW_OPPORTUNITY_SCORE"]

    return _decision(
        property_,
        deal_analysis=deal_analysis,
        valuation=selected_valuation,
        liquidity=selected_liquidity,
        fast_sale=selected_fast_sale,
        risk=selected_risk,
        seller=seller_assessment,
        listing_context=listing_context,
        action=action,
        score=score_result.score,
        ranking_value=ranking_value,
        reason_codes=reason_codes,
        gate_details={
            "hard_gate": selected_risk.hard_gate_status.value,
            "minimum_data_issues": [],
            "confidence_issues": confidence_issues,
            "economic_issues": economic_issues,
        },
        score_components=score_result.components,
    )


def create_opportunity_alert(
    session: Session,
    assessment: OpportunityAssessment,
    *,
    app_base_url: str,
) -> Alert | None:
    if assessment.recommended_action not in ALERTABLE_ACTIONS:
        return None

    dedupe_key = _opportunity_dedupe_key(assessment)
    existing = session.scalars(select(Alert).where(Alert.dedupe_key == dedupe_key)).first()
    if existing is not None:
        return existing

    reason_codes = assessment.reason_codes_json
    reason_code = reason_codes[0] if reason_codes else assessment.recommended_action.value
    payload = _opportunity_alert_payload(assessment, app_base_url=app_base_url)
    alert = Alert(
        property=assessment.property,
        opportunity_assessment=assessment,
        channel=AlertChannel.TELEGRAM,
        alert_type=AlertType.OPPORTUNITY,
        priority=_alert_priority(assessment.recommended_action),
        reason_code=reason_code,
        dedupe_key=dedupe_key,
        payload_json=payload,
        status=AlertStatus.PENDING,
    )
    session.add(alert)
    session.flush()
    return alert


def create_operational_telegram_alert(
    session: Session,
    *,
    reason_code: str,
    message_text: str,
    dedupe_key: str,
    priority: int = 50,
) -> Alert:
    existing = session.scalars(select(Alert).where(Alert.dedupe_key == dedupe_key)).first()
    if existing is not None:
        return existing

    alert = Alert(
        property_id=None,
        opportunity_assessment_id=None,
        channel=AlertChannel.TELEGRAM,
        alert_type=AlertType.OPERATIONAL,
        priority=priority,
        reason_code=reason_code,
        dedupe_key=dedupe_key,
        payload_json={"message_text": message_text},
        status=AlertStatus.PENDING,
    )
    session.add(alert)
    session.flush()
    return alert


def deliver_telegram_alert(
    session: Session,
    alert: Alert,
    sender: TelegramSender,
    *,
    max_attempts: int = MAX_ALERT_SEND_ATTEMPTS,
    now: datetime | None = None,
    commit: bool = False,
) -> AlertDeliveryAttempt:
    attempt_at = _aware_datetime(now or _utcnow())
    if alert.status == AlertStatus.SENT:
        return AlertDeliveryAttempt(
            alert=alert, attempted=False, success=True, skipped_reason="SENT"
        )
    if alert.status == AlertStatus.SUPPRESSED:
        return AlertDeliveryAttempt(
            alert=alert,
            attempted=False,
            success=False,
            skipped_reason="SUPPRESSED",
        )
    if alert.status == AlertStatus.FAILED and alert.send_attempt_count >= max_attempts:
        return AlertDeliveryAttempt(
            alert=alert,
            attempted=False,
            success=False,
            skipped_reason="MAX_ATTEMPTS_REACHED",
        )

    alert.send_attempt_count += 1
    alert.last_attempt_at = attempt_at
    try:
        provider_result = sender.send_alert(alert)
    except Exception as exc:
        alert.status = AlertStatus.FAILED
        alert.failed_at = attempt_at
        alert.error_message = str(exc)
        session.flush()
        if commit:
            session.commit()
        return AlertDeliveryAttempt(
            alert=alert,
            attempted=True,
            success=False,
            error_message=str(exc),
        )

    alert.status = AlertStatus.SENT
    alert.sent_at = attempt_at
    alert.failed_at = None
    alert.error_message = None
    alert.provider_message_id = provider_result.provider_message_id
    session.flush()
    if commit:
        session.commit()
    return AlertDeliveryAttempt(alert=alert, attempted=True, success=True)


def send_due_telegram_alerts(
    session: Session,
    sender: TelegramSender,
    *,
    max_attempts: int = MAX_ALERT_SEND_ATTEMPTS,
    limit: int = 50,
    commit: bool = False,
) -> list[AlertDeliveryAttempt]:
    due_alerts = session.scalars(
        select(Alert)
        .where(
            Alert.channel == AlertChannel.TELEGRAM,
            or_(
                Alert.status == AlertStatus.PENDING,
                ((Alert.status == AlertStatus.FAILED) & (Alert.send_attempt_count < max_attempts)),
            ),
        )
        .order_by(Alert.created_at.asc(), Alert.id.asc())
        .limit(limit)
    ).all()
    attempts = [
        deliver_telegram_alert(session, alert, sender, max_attempts=max_attempts)
        for alert in due_alerts
    ]
    if commit:
        session.commit()
    return attempts


def _decision(
    property_: Property,
    *,
    deal_analysis: DealAnalysis | None,
    valuation: Valuation | None,
    liquidity: LiquidityAssessment | None,
    fast_sale: FastSaleEstimate | None,
    risk: RiskAssessment | None,
    seller: SellerAssessment | None,
    listing_context: ListingContext,
    action: OpportunityAction,
    score: Decimal | None,
    ranking_value: Decimal | None,
    reason_codes: list[str],
    gate_details: dict[str, object],
    score_components: dict[str, str],
) -> OpportunityDecision:
    decision_summary = _decision_summary(
        property_,
        deal_analysis=deal_analysis,
        valuation=valuation,
        liquidity=liquidity,
        fast_sale=fast_sale,
        risk=risk,
        seller=seller,
        listing_context=listing_context,
    )
    explanation_json = {
        "rules_version": OPPORTUNITY_RULES_VERSION,
        "recommended_action": action.value,
        "reason_codes": reason_codes,
        "hard_gate_checked_before_score": True,
        "alert_eligible": action in ALERTABLE_ACTIONS,
        "gate_details": gate_details,
        "score_components": score_components,
        "decision_summary": decision_summary,
    }
    state_payload = {
        "rules_version": OPPORTUNITY_RULES_VERSION,
        "property_id": str(property_.id),
        "recommended_action": action.value,
        "reason_codes": reason_codes,
        "score": _decimal_to_string(score),
        "ranking_value": _decimal_to_string(ranking_value),
        "decision_summary": _stable_summary_for_hash(decision_summary),
    }
    return OpportunityDecision(
        recommended_action=action,
        opportunity_score=score,
        ranking_value=ranking_value,
        reason_codes=reason_codes,
        explanation_json=explanation_json,
        state_hash=_stable_hash(state_payload),
    )


def _minimum_data_issues(
    property_: Property,
    *,
    deal_analysis: DealAnalysis | None,
    valuation: Valuation | None,
    liquidity: LiquidityAssessment | None,
    fast_sale: FastSaleEstimate | None,
    risk: RiskAssessment | None,
    cost_profile: CostProfile | None,
    investment_profile: InvestmentProfile | None,
) -> list[str]:
    issues: list[str] = []
    if deal_analysis is None:
        issues.append("MISSING_DEAL_ANALYSIS")
    elif deal_analysis.status != DealAnalysisStatus.SUCCESS:
        issues.append("INSUFFICIENT_DEAL_DATA")
    if investment_profile is None:
        issues.append("MISSING_INVESTMENT_PROFILE")
    if cost_profile is None:
        issues.append("MISSING_COST_PROFILE")
    if not _successful_valuation(valuation):
        issues.append("MISSING_SUCCESSFUL_VALUATION")
    if not _successful_fast_sale(fast_sale):
        issues.append("MISSING_SUCCESSFUL_FAST_SALE")
    if not _successful_liquidity(liquidity):
        issues.append("MISSING_SUCCESSFUL_LIQUIDITY")
    if risk is None:
        issues.append("MISSING_RISK_ASSESSMENT")
    if property_.size_m2 is None or property_.size_m2 <= 0:
        issues.append("MISSING_USABLE_SIZE")
    if not _location_label(property_):
        issues.append("MISSING_USABLE_LOCATION")

    if deal_analysis is not None and deal_analysis.status == DealAnalysisStatus.SUCCESS:
        required_metrics = {
            "MISSING_ASKING_PRICE": deal_analysis.asking_price,
            "MISSING_MAX_BUY_PRICE": deal_analysis.max_buy_price,
            "MISSING_REQUIRED_NEGOTIATION": deal_analysis.required_negotiation_pct,
            "MISSING_EXPECTED_PROFIT": deal_analysis.expected_profit,
            "MISSING_DOWNSIDE_PROFIT": deal_analysis.downside_profit,
            "MISSING_ROI": deal_analysis.roi,
        }
        issues.extend(code for code, value in required_metrics.items() if value is None)
    return issues


def _confidence_issues(
    *,
    valuation: Valuation,
    liquidity: LiquidityAssessment,
    investment_profile: InvestmentProfile,
) -> list[str]:
    issues: list[str] = []
    if (
        investment_profile.min_valuation_confidence is not None
        and valuation.confidence < investment_profile.min_valuation_confidence
    ):
        issues.append("VALUATION_CONFIDENCE_BELOW_MIN")
    if liquidity.liquidity_score is None:
        issues.append("MISSING_LIQUIDITY_SCORE")
    elif (
        investment_profile.min_liquidity_score is not None
        and liquidity.liquidity_score < investment_profile.min_liquidity_score
    ):
        issues.append("LIQUIDITY_BELOW_MIN")
    return issues


def _economic_issues(
    *,
    deal_analysis: DealAnalysis,
    investment_profile: InvestmentProfile,
) -> list[str]:
    issues: list[str] = []
    assert deal_analysis.expected_profit is not None
    assert deal_analysis.downside_profit is not None
    assert deal_analysis.roi is not None

    if deal_analysis.expected_profit < 0:
        issues.append("NEGATIVE_EXPECTED_PROFIT")
    if (
        investment_profile.min_expected_profit is not None
        and deal_analysis.expected_profit < investment_profile.min_expected_profit
    ):
        issues.append("EXPECTED_PROFIT_BELOW_MIN")
    if (
        investment_profile.min_downside_profit is not None
        and deal_analysis.downside_profit < investment_profile.min_downside_profit
    ):
        issues.append("DOWNSIDE_PROFIT_BELOW_MIN")
    if investment_profile.min_roi is not None and deal_analysis.roi < investment_profile.min_roi:
        issues.append("ROI_BELOW_MIN")
    return issues


def _calculate_score(
    *,
    deal_analysis: DealAnalysis,
    valuation: Valuation,
    liquidity: LiquidityAssessment,
    seller: SellerAssessment | None,
    investment_profile: InvestmentProfile,
) -> ScoreResult:
    assert deal_analysis.expected_profit is not None
    assert deal_analysis.downside_profit is not None
    assert deal_analysis.roi is not None

    expected_reference = _positive_reference(
        investment_profile.desired_profit,
        investment_profile.min_expected_profit,
        Decimal("25000.00"),
    )
    downside_reference = _positive_reference(
        investment_profile.min_downside_profit,
        investment_profile.min_expected_profit,
        Decimal("10000.00"),
    )
    roi_reference = _positive_reference(
        investment_profile.min_roi,
        Decimal("0.150000"),
        Decimal("0.150000"),
    )
    components = {
        "expected_return_quality": _component_score(
            deal_analysis.expected_profit,
            expected_reference,
        ),
        "downside_safety": _component_score(deal_analysis.downside_profit, downside_reference),
        "roi_quality": _component_score(deal_analysis.roi, roi_reference),
        "negotiation_feasibility": _negotiation_component(
            deal_analysis.required_negotiation_pct,
        ),
        "liquidity": _clamp_score(liquidity.liquidity_score),
        "valuation_confidence": _clamp_score(valuation.confidence),
        "seller_opportunity": _seller_score(seller),
    }
    weighted = (
        components["expected_return_quality"] * Decimal("0.30")
        + components["downside_safety"] * Decimal("0.25")
        + components["roi_quality"] * Decimal("0.15")
        + components["negotiation_feasibility"] * Decimal("0.10")
        + components["liquidity"] * Decimal("0.10")
        + components["valuation_confidence"] * Decimal("0.05")
        + components["seller_opportunity"] * Decimal("0.05")
    )
    return ScoreResult(
        score=_score(weighted),
        components={name: _decimal_to_string(value) for name, value in components.items()},
    )


def _calculate_ranking_value(deal_analysis: DealAnalysis) -> Decimal:
    assert deal_analysis.expected_profit is not None
    assert deal_analysis.downside_profit is not None
    assert deal_analysis.roi is not None
    assert deal_analysis.required_negotiation_amount is not None

    direct_economics = max(deal_analysis.expected_profit, Decimal("0.00"))
    downside = max(deal_analysis.downside_profit, Decimal("0.00")) * Decimal("2")
    roi_bonus = max(deal_analysis.roi, Decimal("0")) * Decimal("100000")
    velocity = deal_analysis.profit_per_capital_day or Decimal("0")
    velocity_bonus = max(velocity, Decimal("0")) * Decimal("1000000")
    negotiation_penalty = deal_analysis.required_negotiation_amount * Decimal("0.50")
    return max(
        Decimal("0"),
        direct_economics + downside + roi_bonus + velocity_bonus - negotiation_penalty,
    ).quantize(RANKING_QUANTIZER, rounding=ROUND_HALF_UP)


def _action_for_failed_economics(
    deal_analysis: DealAnalysis,
    economic_issues: list[str],
) -> OpportunityAction:
    if "NEGATIVE_EXPECTED_PROFIT" in economic_issues:
        return OpportunityAction.IGNORE
    if "DOWNSIDE_PROFIT_BELOW_MIN" in economic_issues or "ROI_BELOW_MIN" in economic_issues:
        return OpportunityAction.REVIEW
    if (
        deal_analysis.required_negotiation_pct is not None
        and deal_analysis.required_negotiation_pct <= WATCH_NEGOTIATION_PCT
    ):
        return OpportunityAction.WATCH
    return OpportunityAction.IGNORE


def _reason_for_failed_economics(action: OpportunityAction) -> str:
    if action == OpportunityAction.WATCH:
        return "WATCH_FOR_PRICE_IMPROVEMENT"
    if action == OpportunityAction.REVIEW:
        return "MANUAL_REVIEW_REQUIRED"
    return "ECONOMICS_FAIL_HARD_GATE"


def _urgent_eligible(
    deal_analysis: DealAnalysis,
    score: Decimal,
    investment_profile: InvestmentProfile,
    time_sensitive_signals: list[str],
) -> bool:
    if deal_analysis.required_negotiation_pct is None:
        return False
    if deal_analysis.required_negotiation_pct > URGENT_NEGOTIATION_PCT:
        return False
    if score < URGENT_SCORE_THRESHOLD:
        return False
    return bool(time_sensitive_signals) or _unusually_strong_deal(deal_analysis, investment_profile)


def _call_eligible(deal_analysis: DealAnalysis, score: Decimal) -> bool:
    return (
        deal_analysis.required_negotiation_pct is not None
        and deal_analysis.required_negotiation_pct <= CALL_NEGOTIATION_PCT
        and score >= CALL_SCORE_THRESHOLD
    )


def _watch_eligible(
    deal_analysis: DealAnalysis,
    time_sensitive_signals: list[str],
) -> bool:
    return (
        deal_analysis.required_negotiation_pct is not None
        and deal_analysis.required_negotiation_pct <= WATCH_NEGOTIATION_PCT
    ) or bool(time_sensitive_signals)


def _unusually_strong_deal(
    deal_analysis: DealAnalysis,
    investment_profile: InvestmentProfile,
) -> bool:
    assert deal_analysis.expected_profit is not None
    reference = _positive_reference(
        investment_profile.desired_profit,
        investment_profile.min_expected_profit,
        Decimal("25000.00"),
    )
    return deal_analysis.expected_profit >= reference * Decimal("1.50")


def _negotiation_reason(deal_analysis: DealAnalysis) -> str:
    if deal_analysis.required_negotiation_amount == Decimal("0.00"):
        return "ASKING_WITHIN_MAX_BUY"
    return "ASKING_CLOSE_TO_MAX_BUY"


def _opportunity_alert_payload(
    assessment: OpportunityAssessment,
    *,
    app_base_url: str,
) -> dict[str, object]:
    route = f"/properties/{assessment.property_id}"
    deep_link = f"{app_base_url.rstrip('/')}{route}"
    summary = assessment.explanation_json["decision_summary"]
    assert isinstance(summary, dict)
    message_text = _opportunity_message(
        action=assessment.recommended_action,
        reason_codes=assessment.reason_codes_json,
        summary=summary,
        deep_link=deep_link,
    )
    return {
        "message_text": message_text,
        "property_route": route,
        "deep_link_url": deep_link,
        "decision_summary": summary,
    }


def _opportunity_message(
    *,
    action: OpportunityAction,
    reason_codes: list[str],
    summary: dict[str, object],
    deep_link: str,
) -> str:
    return "\n".join(
        [
            action.value.replace("_", " "),
            "",
            str(summary.get("location") or "UNKNOWN LOCATION"),
            str(summary.get("property") or "UNKNOWN PROPERTY"),
            "",
            f"ASKING {summary.get('asking_price') or 'UNKNOWN'}",
            f"FMV {summary.get('fmv_range') or 'UNKNOWN'}",
            f"FAST SALE {summary.get('fast_sale_base') or 'UNKNOWN'}",
            f"MAX BUY {summary.get('max_buy_price') or 'UNKNOWN'}",
            f"PROFIT {summary.get('expected_profit') or 'UNKNOWN'}",
            f"DOWNSIDE {summary.get('downside_profit') or 'UNKNOWN'}",
            (
                f"Liquidity {summary.get('liquidity_score') or 'UNKNOWN'} | "
                f"Confidence {summary.get('valuation_confidence') or 'UNKNOWN'}"
            ),
            f"Seller {summary.get('seller_motivation') or 'UNKNOWN'}",
            f"Risk {summary.get('risk_gate') or 'UNKNOWN'}",
            f"Reasons: {', '.join(reason_codes[:3])}",
            deep_link,
        ]
    )


def _decision_summary(
    property_: Property,
    *,
    deal_analysis: DealAnalysis | None,
    valuation: Valuation | None,
    liquidity: LiquidityAssessment | None,
    fast_sale: FastSaleEstimate | None,
    risk: RiskAssessment | None,
    seller: SellerAssessment | None,
    listing_context: ListingContext,
) -> dict[str, object]:
    return {
        "property_id": str(property_.id),
        "location": _location_label(property_) or "UNKNOWN",
        "property": _property_label(property_),
        "asking_price": _format_money(
            deal_analysis.asking_price if deal_analysis is not None else None,
        ),
        "fmv_range": _format_money_range(
            valuation.fair_value_low if valuation is not None else None,
            valuation.fair_value_high if valuation is not None else None,
        ),
        "fast_sale_base": _format_money(
            fast_sale.value_base if fast_sale is not None else None,
        ),
        "max_buy_price": _format_money(
            deal_analysis.max_buy_price if deal_analysis is not None else None,
        ),
        "expected_profit": _format_money(
            deal_analysis.expected_profit if deal_analysis is not None else None,
        ),
        "downside_profit": _format_money(
            deal_analysis.downside_profit if deal_analysis is not None else None,
        ),
        "roi": _decimal_to_string(deal_analysis.roi if deal_analysis is not None else None),
        "required_negotiation_pct": _decimal_to_string(
            deal_analysis.required_negotiation_pct if deal_analysis is not None else None,
        ),
        "liquidity_score": _decimal_to_string(
            liquidity.liquidity_score if liquidity is not None else None,
        ),
        "valuation_confidence": _decimal_to_string(
            valuation.confidence if valuation is not None else None,
        ),
        "seller_motivation": (
            seller.seller_motivation_level.value if seller is not None else "UNKNOWN"
        ),
        "risk_gate": risk.hard_gate_status.value if risk is not None else "UNKNOWN",
        "market_age_days": property_.estimated_market_age_days,
        "last_change": listing_context.last_change,
        "time_sensitive_signals": listing_context.time_sensitive_signals,
        "active_listing_id": (
            str(listing_context.active_listing.id)
            if listing_context.active_listing is not None
            else None
        ),
    }


def _listing_context(session: Session, property_: Property, as_of: datetime) -> ListingContext:
    active_listing = session.scalars(
        select(Listing)
        .where(
            Listing.property_id == property_.id,
            Listing.status == ListingStatus.ACTIVE,
        )
        .order_by(Listing.asking_price.asc().nulls_last(), Listing.first_seen_at.desc())
    ).first()
    signals: list[str] = []
    last_change = None
    if active_listing is not None and active_listing.first_seen_at is not None:
        first_seen = _aware_datetime(active_listing.first_seen_at)
        if first_seen >= as_of - timedelta(days=RECENT_LISTING_DAYS):
            signals.append("NEW_LISTING")
            last_change = "New listing"

    price_cut = _latest_recent_price_cut(session, property_, as_of)
    if price_cut is not None:
        old_price, new_price, detected_at = price_cut
        cut_pct = (old_price - new_price) / old_price
        if cut_pct >= LARGE_PRICE_CUT_PCT:
            signals.append("LARGE_RECENT_PRICE_CUT")
        last_change = f"Price cut {_percent(cut_pct)} on {detected_at.date().isoformat()}"

    return ListingContext(
        active_listing=active_listing,
        time_sensitive_signals=signals,
        last_change=last_change,
    )


def _latest_recent_price_cut(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> tuple[Decimal, Decimal, datetime] | None:
    event = session.scalars(
        select(ListingEvent)
        .join(Listing, Listing.id == ListingEvent.listing_id)
        .where(
            Listing.property_id == property_.id,
            ListingEvent.event_type == ListingEventType.PRICE_CHANGED,
            ListingEvent.old_price.is_not(None),
            ListingEvent.new_price.is_not(None),
            ListingEvent.old_price > 0,
            ListingEvent.new_price < ListingEvent.old_price,
            ListingEvent.detected_at >= as_of - timedelta(days=RECENT_PRICE_CUT_DAYS),
            ListingEvent.detected_at <= as_of,
        )
        .order_by(ListingEvent.detected_at.desc(), ListingEvent.id.desc())
    ).first()
    if event is None or event.old_price is None or event.new_price is None:
        return None
    return event.old_price, event.new_price, _aware_datetime(event.detected_at)


def _latest_deal_analysis(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> DealAnalysis | None:
    return session.scalars(
        select(DealAnalysis)
        .where(DealAnalysis.property_id == property_.id, DealAnalysis.as_of <= as_of)
        .order_by(DealAnalysis.as_of.desc(), DealAnalysis.created_at.desc(), DealAnalysis.id.desc())
    ).first()


def _latest_seller_assessment(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> SellerAssessment | None:
    return session.scalars(
        select(SellerAssessment)
        .where(SellerAssessment.property_id == property_.id, SellerAssessment.as_of <= as_of)
        .order_by(
            SellerAssessment.as_of.desc(),
            SellerAssessment.created_at.desc(),
            SellerAssessment.id.desc(),
        )
    ).first()


def _risk_for_decision(
    session: Session,
    property_: Property,
    deal_analysis: DealAnalysis | None,
    as_of: datetime,
) -> RiskAssessment | None:
    if deal_analysis is not None and deal_analysis.risk_assessment is not None:
        return deal_analysis.risk_assessment
    return session.scalars(
        select(RiskAssessment)
        .where(RiskAssessment.property_id == property_.id, RiskAssessment.as_of <= as_of)
        .order_by(
            RiskAssessment.as_of.desc(),
            RiskAssessment.created_at.desc(),
            RiskAssessment.id.desc(),
        )
    ).first()


def _successful_valuation(valuation: Valuation | None) -> bool:
    return (
        valuation is not None
        and valuation.status == ValuationStatus.SUCCESS
        and valuation.fair_value_base is not None
        and valuation.fair_value_base > 0
    )


def _successful_liquidity(liquidity: LiquidityAssessment | None) -> bool:
    return (
        liquidity is not None
        and liquidity.status == LiquidityStatus.SUCCESS
        and liquidity.liquidity_score is not None
    )


def _successful_fast_sale(fast_sale: FastSaleEstimate | None) -> bool:
    return (
        fast_sale is not None
        and fast_sale.status == FastSaleStatus.SUCCESS
        and fast_sale.value_low is not None
        and fast_sale.value_low > 0
        and fast_sale.value_base is not None
        and fast_sale.value_base > 0
        and fast_sale.value_high is not None
        and fast_sale.value_high > 0
    )


def _component_score(value: Decimal, reference: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0.00")
    if reference <= 0:
        return Decimal("100.00")
    return _clamp_score(value / reference * Decimal("100"))


def _negotiation_component(required_negotiation_pct: Decimal | None) -> Decimal:
    if required_negotiation_pct is None:
        return Decimal("0.00")
    if required_negotiation_pct <= 0:
        return Decimal("100.00")
    if required_negotiation_pct <= URGENT_NEGOTIATION_PCT:
        return Decimal("90.00")
    if required_negotiation_pct <= CALL_NEGOTIATION_PCT:
        return Decimal("75.00")
    if required_negotiation_pct <= WATCH_NEGOTIATION_PCT:
        return Decimal("45.00")
    return Decimal("10.00")


def _seller_score(seller: SellerAssessment | None) -> Decimal:
    if seller is None:
        return Decimal("0.00")
    if seller.seller_motivation_score is not None:
        return _clamp_score(seller.seller_motivation_score)
    return {
        AnalysisLevel.HIGH: Decimal("85.00"),
        AnalysisLevel.MEDIUM: Decimal("55.00"),
        AnalysisLevel.LOW: Decimal("20.00"),
        AnalysisLevel.UNKNOWN: Decimal("0.00"),
    }[seller.seller_motivation_level]


def _positive_reference(*values: Decimal | None) -> Decimal:
    positive_values = [value for value in values if value is not None and value > 0]
    if not positive_values:
        return Decimal("1.00")
    return max(positive_values)


def _clamp_score(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return min(Decimal("100.00"), max(Decimal("0.00"), _score(value)))


def _score(value: Decimal) -> Decimal:
    return value.quantize(SCORE_QUANTIZER, rounding=ROUND_HALF_UP)


def _opportunity_dedupe_key(assessment: OpportunityAssessment) -> str:
    return (
        f"opportunity:{assessment.property_id}:"
        f"{assessment.recommended_action.value}:{assessment.state_hash}"
    )


def _alert_priority(action: OpportunityAction) -> int:
    return {
        OpportunityAction.URGENT_CALL: 100,
        OpportunityAction.CALL: 80,
        OpportunityAction.REVIEW: 50,
        OpportunityAction.WATCH: 30,
        OpportunityAction.IGNORE: 0,
    }[action]


def _stable_summary_for_hash(summary: dict[str, object]) -> dict[str, object]:
    keys = {
        "property_id",
        "asking_price",
        "fmv_range",
        "fast_sale_base",
        "max_buy_price",
        "expected_profit",
        "downside_profit",
        "roi",
        "required_negotiation_pct",
        "liquidity_score",
        "valuation_confidence",
        "seller_motivation",
        "risk_gate",
        "time_sensitive_signals",
    }
    return {key: summary.get(key) for key in sorted(keys)}


def _stable_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _location_label(property_: Property) -> str | None:
    parts = [
        property_.city,
        property_.municipality,
        property_.micro_location or property_.neighborhood,
    ]
    cleaned = [part for part in parts if part]
    if not cleaned:
        return None
    return " - ".join(cleaned)


def _property_label(property_: Property) -> str:
    size = (
        f"{_format_decimal(property_.size_m2)} m2"
        if property_.size_m2 is not None
        else "UNKNOWN m2"
    )
    rooms = (
        f"{_format_decimal(property_.rooms)} rooms"
        if property_.rooms is not None
        else "UNKNOWN rooms"
    )
    floor = "UNKNOWN floor"
    if property_.floor is not None and property_.total_floors is not None:
        floor = f"{property_.floor}/{property_.total_floors}"
    elif property_.floor is not None:
        floor = str(property_.floor)
    elevator = "lift" if property_.elevator is True else None
    values = [size, rooms, floor]
    if elevator is not None:
        values.append(elevator)
    return " | ".join(values)


def _format_money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"EUR {value.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}"


def _format_money_range(low: Decimal | None, high: Decimal | None) -> str | None:
    if low is None or high is None:
        return None
    return f"{_format_money(low)}-{_format_money(high)}"


def _percent(value: Decimal) -> str:
    return f"{(value * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _decimal_to_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _analysis_as_of(as_of: datetime | None, deal_analysis: DealAnalysis | None) -> datetime:
    if as_of is not None:
        return _aware_datetime(as_of)
    if deal_analysis is not None:
        return _aware_datetime(deal_analysis.as_of)
    return _utcnow()


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _utcnow() -> datetime:
    return datetime.now(UTC)
