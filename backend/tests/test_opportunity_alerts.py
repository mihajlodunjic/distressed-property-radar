from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    ComparableSet,
    CostProfile,
    DealAnalysis,
    FastSaleEstimate,
    InvestmentProfile,
    LiquidityAssessment,
    Listing,
    OpportunityAssessment,
    Property,
    RiskAssessment,
    SellerAssessment,
    Source,
    Valuation,
)
from app.deals.deal_engine import analyze_deal
from app.domain.enums import (
    AlertStatus,
    AlertType,
    AnalysisLevel,
    CurrencyCode,
    DataSourceKind,
    DealAnalysisStatus,
    FastSaleStatus,
    LiquidityStatus,
    ListingStatus,
    OpportunityAction,
    PropertyType,
    ReasonForSale,
    RiskGateStatus,
    SellerType,
    ValuationModelType,
    ValuationStatus,
)
from app.opportunities.opportunity_engine import (
    NO_QUALIFYING_OPPORTUNITIES,
    OPPORTUNITY_RULES_VERSION,
    assess_opportunity_and_alert,
    assess_opportunity_batch,
    create_operational_telegram_alert,
    create_opportunity_alert,
    deliver_telegram_alert,
    send_due_telegram_alerts,
)
from app.opportunities.telegram import TelegramDeliveryResult

AS_OF = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class OpportunityFixture:
    property: Property
    listing: Listing
    valuation: Valuation
    liquidity: LiquidityAssessment
    fast_sale: FastSaleEstimate
    risk: RiskAssessment
    seller: SellerAssessment
    cost_profile: CostProfile
    investment_profile: InvestmentProfile
    deal: DealAnalysis


class FakeTelegramSender:
    def __init__(self, *results: TelegramDeliveryResult | Exception) -> None:
        self.results = list(results)
        self.call_count = 0
        self.statuses_at_send: list[AlertStatus] = []
        self.messages: list[str] = []

    def send_alert(self, alert: Alert) -> TelegramDeliveryResult:
        self.call_count += 1
        self.statuses_at_send.append(alert.status)
        message_text = alert.payload_json.get("message_text")
        if isinstance(message_text, str):
            self.messages.append(message_text)
        result = (
            self.results[min(self.call_count - 1, len(self.results) - 1)]
            if self.results
            else TelegramDeliveryResult(provider_message_id=f"fake-{self.call_count}")
        )
        if isinstance(result, Exception):
            raise result
        return result


def create_source(session: Session, code: str | None = None) -> Source:
    suffix = code or uuid.uuid4().hex[:10]
    source = Source(
        name=f"Source {suffix}",
        code=f"phase10_{suffix}",
        source_type=DataSourceKind.SCRAPED,
        base_url="https://example.test",
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
        "condition_category": "GOOD",
        "estimated_market_age_days": 12,
    }
    values.update(overrides)
    property_ = Property(**values)
    session.add(property_)
    session.flush()
    return property_


def create_listing(
    session: Session,
    source: Source,
    property_: Property,
    *,
    asking_price: Decimal = Decimal("130000.00"),
    first_seen_at: datetime = AS_OF - timedelta(days=20),
) -> Listing:
    external_id = f"listing-{uuid.uuid4().hex[:10]}"
    listing = Listing(
        source=source,
        property=property_,
        external_listing_id=external_id,
        url=f"https://example.test/{external_id}",
        canonical_url=f"https://example.test/{external_id}",
        title="Opportunity target listing",
        description="Owner can agree quickly with a serious cash buyer.",
        asking_price=asking_price,
        currency=CurrencyCode.EUR,
        city_raw="Beograd",
        location_raw="Blok 45, Novi Beograd, Beograd",
        size_m2=property_.size_m2,
        rooms=property_.rooms,
        floor=property_.floor,
        total_floors=property_.total_floors,
        elevator=property_.elevator,
        parking=property_.parking,
        condition_raw=property_.condition_category,
        seller_type=SellerType.OWNER,
        status=ListingStatus.ACTIVE,
        first_seen_at=first_seen_at,
        last_seen_at=AS_OF,
    )
    session.add(listing)
    session.flush()
    return listing


def create_cost_profile(session: Session) -> CostProfile:
    suffix = uuid.uuid4().hex[:10]
    profile = CostProfile(
        name=f"Cost profile {suffix}",
        code=f"phase10_costs_{suffix}",
        currency=CurrencyCode.EUR,
        is_active=True,
        purchase_tax_rule_json={},
        notary_rule_json={},
        lawyer_rule_json={},
        agency_rule_json={},
        sale_cost_rule_json={},
        holding_cost_rule_json={},
        financing_rule_json={},
        other_cost_rule_json={},
        version="cost_profile_v1",
    )
    session.add(profile)
    session.flush()
    return profile


def create_investment_profile(
    session: Session,
    *,
    min_expected_profit: Decimal = Decimal("10000.00"),
    min_downside_profit: Decimal = Decimal("5000.00"),
    min_roi: Decimal = Decimal("0.080000"),
    min_liquidity_score: Decimal = Decimal("60.00"),
    min_valuation_confidence: Decimal = Decimal("60.00"),
) -> InvestmentProfile:
    profile = InvestmentProfile(
        name="Phase 10 investment profile",
        is_default=True,
        min_expected_profit=min_expected_profit,
        min_downside_profit=min_downside_profit,
        min_roi=min_roi,
        max_expected_holding_days=120,
        min_liquidity_score=min_liquidity_score,
        min_valuation_confidence=min_valuation_confidence,
        default_risk_reserve=Decimal("0.00"),
        desired_profit=Decimal("25000.00"),
        version="investment_profile_v1",
    )
    session.add(profile)
    session.flush()
    return profile


def create_valuation(
    session: Session,
    property_: Property,
    *,
    confidence: Decimal = Decimal("75.00"),
) -> Valuation:
    comparable_set = ComparableSet(
        property=property_,
        as_of=AS_OF,
        comparable_engine_version="test_comparable_engine",
        search_parameters_json={"source": "phase10"},
    )
    session.add(comparable_set)
    session.flush()
    valuation = Valuation(
        property=property_,
        comparable_set=comparable_set,
        as_of=AS_OF,
        status=ValuationStatus.SUCCESS,
        fair_value_low=Decimal("170000.00"),
        fair_value_base=Decimal("180000.00"),
        fair_value_high=Decimal("190000.00"),
        currency=CurrencyCode.EUR,
        confidence=confidence,
        data_quality_at_analysis=Decimal("82.00"),
        model_type=ValuationModelType.LISTING_COMPS,
        model_version="valuation_v1",
        input_summary_json={"source": "phase10"},
        explanation_json={"source": "phase10"},
    )
    session.add(valuation)
    session.flush()
    return valuation


def create_liquidity_and_fast_sale(
    session: Session,
    property_: Property,
    valuation: Valuation,
    *,
    liquidity_score: Decimal = Decimal("75.00"),
) -> tuple[LiquidityAssessment, FastSaleEstimate]:
    liquidity = LiquidityAssessment(
        property=property_,
        valuation=valuation,
        as_of=AS_OF,
        status=LiquidityStatus.SUCCESS,
        liquidity_score=liquidity_score,
        confidence=Decimal("72.00"),
        probability_sale_30d=None,
        probability_sale_60d=None,
        probability_sale_90d=None,
        positive_factors_json={"source": "phase10"},
        negative_factors_json={"source": "phase10"},
        model_version="liquidity_rules_v1",
    )
    session.add(liquidity)
    session.flush()
    fast_sale = FastSaleEstimate(
        property=property_,
        valuation=valuation,
        liquidity_assessment=liquidity,
        as_of=AS_OF,
        status=FastSaleStatus.SUCCESS,
        value_low=Decimal("165000.00"),
        value_base=Decimal("175000.00"),
        value_high=Decimal("185000.00"),
        target_days=60,
        target_probability=None,
        confidence=Decimal("70.00"),
        model_version="fast_sale_v1",
        explanation_json={"source": "phase10"},
    )
    session.add(fast_sale)
    session.flush()
    return liquidity, fast_sale


def create_risk(
    session: Session,
    property_: Property,
    *,
    gate: RiskGateStatus = RiskGateStatus.PASS,
) -> RiskAssessment:
    risk = RiskAssessment(
        property=property_,
        as_of=AS_OF,
        hard_gate_status=gate,
        risk_score=Decimal("12.00") if gate == RiskGateStatus.PASS else Decimal("95.00"),
        confidence=Decimal("78.00"),
        rules_version="risk_rules_v1",
    )
    session.add(risk)
    session.flush()
    return risk


def create_seller(
    session: Session,
    property_: Property,
    *,
    level: AnalysisLevel = AnalysisLevel.MEDIUM,
) -> SellerAssessment:
    score = {
        AnalysisLevel.HIGH: Decimal("85.00"),
        AnalysisLevel.MEDIUM: Decimal("55.00"),
        AnalysisLevel.LOW: Decimal("20.00"),
        AnalysisLevel.UNKNOWN: None,
    }[level]
    seller = SellerAssessment(
        property=property_,
        as_of=AS_OF,
        seller_motivation_level=level,
        seller_motivation_score=score,
        seller_motivation_confidence=Decimal("76.00"),
        negotiability_level=AnalysisLevel.MEDIUM,
        negotiability_score=Decimal("55.00"),
        negotiability_confidence=Decimal("70.00"),
        cash_preferred=True,
        cash_preference_confidence=Decimal("65.00"),
        reason_for_sale=ReasonForSale.MOVING_ABROAD,
        evidence_json={"source": "phase10"},
        model_version="seller_intelligence_v1",
    )
    session.add(seller)
    session.flush()
    return seller


def create_manual_deal_fixture(
    session: Session,
    *,
    risk_gate: RiskGateStatus = RiskGateStatus.PASS,
    seller_level: AnalysisLevel = AnalysisLevel.MEDIUM,
    valuation_confidence: Decimal = Decimal("75.00"),
    liquidity_score: Decimal = Decimal("75.00"),
    asking_price: Decimal = Decimal("100000.00"),
    required_negotiation_pct: Decimal = Decimal("0.050000"),
    expected_profit: Decimal = Decimal("24000.00"),
    downside_profit: Decimal = Decimal("7000.00"),
    roi: Decimal = Decimal("0.120000"),
    first_seen_at: datetime = AS_OF - timedelta(days=20),
) -> OpportunityFixture:
    source = create_source(session)
    property_ = create_property(session)
    listing = create_listing(
        session,
        source,
        property_,
        asking_price=asking_price,
        first_seen_at=first_seen_at,
    )
    cost_profile = create_cost_profile(session)
    investment_profile = create_investment_profile(session)
    valuation = create_valuation(session, property_, confidence=valuation_confidence)
    liquidity, fast_sale = create_liquidity_and_fast_sale(
        session,
        property_,
        valuation,
        liquidity_score=liquidity_score,
    )
    risk = create_risk(session, property_, gate=risk_gate)
    seller = create_seller(session, property_, level=seller_level)
    max_buy_price = asking_price * (Decimal("1.000000") - required_negotiation_pct)
    required_negotiation_amount = asking_price - max_buy_price
    deal = DealAnalysis(
        property=property_,
        valuation=valuation,
        liquidity_assessment=liquidity,
        fast_sale_estimate=fast_sale,
        risk_assessment=risk,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        as_of=AS_OF,
        status=DealAnalysisStatus.SUCCESS,
        assumed_purchase_price=asking_price,
        asking_price=asking_price,
        purchase_costs=Decimal("0.00"),
        renovation_cost=Decimal("0.00"),
        sale_costs=Decimal("0.00"),
        taxes=Decimal("0.00"),
        financing_costs=Decimal("0.00"),
        holding_costs=Decimal("0.00"),
        risk_reserve=Decimal("0.00"),
        other_costs=Decimal("0.00"),
        total_cost_basis=asking_price,
        expected_exit_price=asking_price + expected_profit,
        max_buy_price=max_buy_price,
        required_negotiation_amount=required_negotiation_amount,
        required_negotiation_pct=required_negotiation_pct,
        expected_profit=expected_profit,
        downside_profit=downside_profit,
        upside_profit=expected_profit + Decimal("10000.00"),
        roi=roi,
        annualized_roi=roi,
        expected_holding_days=120,
        capital_days=asking_price * Decimal("120"),
        profit_per_capital_day=expected_profit / (asking_price * Decimal("120")),
        formula_version="deal_formula_v1",
        input_summary_json={"source": "phase10"},
        explanation_json={"source": "phase10"},
    )
    session.add(deal)
    session.flush()
    return OpportunityFixture(
        property=property_,
        listing=listing,
        valuation=valuation,
        liquidity=liquidity,
        fast_sale=fast_sale,
        risk=risk,
        seller=seller,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        deal=deal,
    )


def create_deal_for_fixture(
    session: Session,
    fixture: OpportunityFixture,
    *,
    asking_price: Decimal = Decimal("100000.00"),
    required_negotiation_pct: Decimal = Decimal("0.050000"),
    expected_profit: Decimal = Decimal("24000.00"),
    downside_profit: Decimal = Decimal("7000.00"),
    roi: Decimal = Decimal("0.120000"),
) -> DealAnalysis:
    max_buy_price = asking_price * (Decimal("1.000000") - required_negotiation_pct)
    required_negotiation_amount = asking_price - max_buy_price
    deal = DealAnalysis(
        property=fixture.property,
        valuation=fixture.valuation,
        liquidity_assessment=fixture.liquidity,
        fast_sale_estimate=fixture.fast_sale,
        risk_assessment=fixture.risk,
        cost_profile=fixture.cost_profile,
        investment_profile=fixture.investment_profile,
        as_of=AS_OF,
        status=DealAnalysisStatus.SUCCESS,
        assumed_purchase_price=asking_price,
        asking_price=asking_price,
        purchase_costs=Decimal("0.00"),
        renovation_cost=Decimal("0.00"),
        sale_costs=Decimal("0.00"),
        taxes=Decimal("0.00"),
        financing_costs=Decimal("0.00"),
        holding_costs=Decimal("0.00"),
        risk_reserve=Decimal("0.00"),
        other_costs=Decimal("0.00"),
        total_cost_basis=asking_price,
        expected_exit_price=asking_price + expected_profit,
        max_buy_price=max_buy_price,
        required_negotiation_amount=required_negotiation_amount,
        required_negotiation_pct=required_negotiation_pct,
        expected_profit=expected_profit,
        downside_profit=downside_profit,
        upside_profit=expected_profit + Decimal("10000.00"),
        roi=roi,
        annualized_roi=roi,
        expected_holding_days=120,
        capital_days=asking_price * Decimal("120"),
        profit_per_capital_day=expected_profit / (asking_price * Decimal("120")),
        formula_version="deal_formula_v1",
        input_summary_json={"source": "phase10"},
        explanation_json={"source": "phase10"},
    )
    session.add(deal)
    session.flush()
    return deal


def count_rows(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_phase10_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {"opportunity_assessments", "alerts"}.issubset(set(inspector.get_table_names()))


@pytest.mark.parametrize(
    (
        "case",
        "inputs",
        "expected_action",
        "expected_reason",
    ),
    [
        (
            "ignore_negative_profit_even_with_high_seller_motivation",
            {
                "seller_level": AnalysisLevel.HIGH,
                "expected_profit": Decimal("-1000.00"),
                "downside_profit": Decimal("-5000.00"),
                "roi": Decimal("-0.010000"),
            },
            OpportunityAction.IGNORE,
            "NEGATIVE_EXPECTED_PROFIT",
        ),
        (
            "watch_when_price_improvement_can_make_economics_work",
            {
                "expected_profit": Decimal("8000.00"),
                "downside_profit": Decimal("6000.00"),
                "roi": Decimal("0.090000"),
                "required_negotiation_pct": Decimal("0.120000"),
            },
            OpportunityAction.WATCH,
            "WATCH_FOR_PRICE_IMPROVEMENT",
        ),
        (
            "review_large_discount_with_low_confidence",
            {
                "expected_profit": Decimal("50000.00"),
                "downside_profit": Decimal("20000.00"),
                "roi": Decimal("0.250000"),
                "required_negotiation_pct": Decimal("0.000000"),
                "valuation_confidence": Decimal("59.99"),
            },
            OpportunityAction.REVIEW,
            "VALUATION_CONFIDENCE_BELOW_MIN",
        ),
        (
            "call_when_economics_pass_after_modest_negotiation",
            {
                "expected_profit": Decimal("24000.00"),
                "downside_profit": Decimal("7000.00"),
                "roi": Decimal("0.120000"),
                "required_negotiation_pct": Decimal("0.050000"),
            },
            OpportunityAction.CALL,
            "ECONOMICS_PASS",
        ),
        (
            "urgent_call_for_new_strong_deal_within_max_buy",
            {
                "seller_level": AnalysisLevel.HIGH,
                "expected_profit": Decimal("50000.00"),
                "downside_profit": Decimal("20000.00"),
                "roi": Decimal("0.250000"),
                "required_negotiation_pct": Decimal("0.000000"),
                "first_seen_at": AS_OF - timedelta(days=1),
            },
            OpportunityAction.URGENT_CALL,
            "NEW_LISTING",
        ),
    ],
)
def test_rules_based_actions_are_table_driven(
    db_session: Session,
    case: str,
    inputs: dict[str, object],
    expected_action: OpportunityAction,
    expected_reason: str,
) -> None:
    _ = case
    fixture = create_manual_deal_fixture(db_session, **inputs)

    result = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert result.assessment.recommended_action == expected_action
    assert expected_reason in result.assessment.reason_codes_json
    assert result.assessment.rules_version == OPPORTUNITY_RULES_VERSION
    assert result.assessment.explanation_json["hard_gate_checked_before_score"] is True
    assert (
        result.alert is None
        if expected_action
        not in {
            OpportunityAction.CALL,
            OpportunityAction.URGENT_CALL,
        }
        else result.alert is not None
    )


@pytest.mark.parametrize(
    ("valuation_confidence", "expected_action"),
    [
        (Decimal("59.99"), OpportunityAction.REVIEW),
        (Decimal("60.00"), OpportunityAction.CALL),
    ],
)
def test_confidence_threshold_boundary_caps_aggressive_actions(
    db_session: Session,
    valuation_confidence: Decimal,
    expected_action: OpportunityAction,
) -> None:
    fixture = create_manual_deal_fixture(
        db_session,
        valuation_confidence=valuation_confidence,
        expected_profit=Decimal("24000.00"),
        downside_profit=Decimal("7000.00"),
        roi=Decimal("0.120000"),
        required_negotiation_pct=Decimal("0.050000"),
    )

    result = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert result.assessment.recommended_action == expected_action
    if valuation_confidence < Decimal("60.00"):
        assert result.assessment.recommended_action not in {
            OpportunityAction.CALL,
            OpportunityAction.URGENT_CALL,
        }
        assert result.alert is None


def test_downside_threshold_degrades_high_base_profit_to_review(db_session: Session) -> None:
    fixture = create_manual_deal_fixture(
        db_session,
        expected_profit=Decimal("50000.00"),
        downside_profit=Decimal("1000.00"),
        roi=Decimal("0.250000"),
        required_negotiation_pct=Decimal("0.000000"),
    )

    result = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert result.assessment.recommended_action == OpportunityAction.REVIEW
    assert "DOWNSIDE_PROFIT_BELOW_MIN" in result.assessment.reason_codes_json
    assert result.alert is None


def test_ranking_value_prioritizes_direct_economics_and_downside(
    db_session: Session,
) -> None:
    weaker = create_manual_deal_fixture(
        db_session,
        expected_profit=Decimal("22000.00"),
        downside_profit=Decimal("6000.00"),
        roi=Decimal("0.120000"),
        required_negotiation_pct=Decimal("0.050000"),
    )
    stronger = create_manual_deal_fixture(
        db_session,
        expected_profit=Decimal("22000.00"),
        downside_profit=Decimal("14000.00"),
        roi=Decimal("0.120000"),
        required_negotiation_pct=Decimal("0.050000"),
    )

    weaker_result = assess_opportunity_and_alert(
        db_session,
        weaker.property,
        deal_analysis=weaker.deal,
        seller_assessment=weaker.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )
    stronger_result = assess_opportunity_and_alert(
        db_session,
        stronger.property,
        deal_analysis=stronger.deal,
        seller_assessment=stronger.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert weaker_result.assessment.ranking_value is not None
    assert stronger_result.assessment.ranking_value is not None
    assert stronger_result.assessment.ranking_value > weaker_result.assessment.ranking_value


def test_block_overrides_excellent_score_and_high_seller_motivation(db_session: Session) -> None:
    fixture = create_manual_deal_fixture(
        db_session,
        risk_gate=RiskGateStatus.BLOCK,
        seller_level=AnalysisLevel.HIGH,
        expected_profit=Decimal("90000.00"),
        downside_profit=Decimal("50000.00"),
        roi=Decimal("0.600000"),
        required_negotiation_pct=Decimal("0.000000"),
        first_seen_at=AS_OF - timedelta(days=1),
    )
    sender = FakeTelegramSender()

    result = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        sender=sender,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert result.assessment.recommended_action == OpportunityAction.IGNORE
    assert result.assessment.opportunity_score is None
    assert "RISK_BLOCK" in result.assessment.reason_codes_json
    assert result.alert is None
    assert sender.call_count == 0
    assert count_rows(db_session, Alert) == 0


def test_new_property_can_flow_from_listing_analysis_deal_to_sent_alert(
    db_session: Session,
) -> None:
    source = create_source(db_session, "full_flow")
    property_ = create_property(db_session)
    create_listing(
        db_session,
        source,
        property_,
        asking_price=Decimal("120000.00"),
        first_seen_at=AS_OF - timedelta(days=1),
    )
    cost_profile = create_cost_profile(db_session)
    investment_profile = create_investment_profile(db_session)
    valuation = create_valuation(db_session, property_, confidence=Decimal("82.00"))
    liquidity, fast_sale = create_liquidity_and_fast_sale(
        db_session,
        property_,
        valuation,
        liquidity_score=Decimal("82.00"),
    )
    risk = create_risk(db_session, property_, gate=RiskGateStatus.PASS)
    seller = create_seller(db_session, property_, level=AnalysisLevel.HIGH)
    deal_result = analyze_deal(
        db_session,
        property_,
        valuation=valuation,
        liquidity_assessment=liquidity,
        fast_sale_estimate=fast_sale,
        risk_assessment=risk,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        assumed_purchase_price=Decimal("120000.00"),
        renovation_cost=Decimal("0.00"),
        expected_holding_days=120,
        as_of=AS_OF,
    )
    sender = FakeTelegramSender(TelegramDeliveryResult(provider_message_id="tg-1"))

    result = assess_opportunity_and_alert(
        db_session,
        property_,
        deal_analysis=deal_result.deal_analysis,
        seller_assessment=seller,
        sender=sender,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert result.assessment.recommended_action == OpportunityAction.URGENT_CALL
    assert result.alert is not None
    assert result.alert.status == AlertStatus.SENT
    assert result.alert.provider_message_id == "tg-1"
    assert result.alert.send_attempt_count == 1
    assert sender.statuses_at_send == [AlertStatus.PENDING]
    assert "http://radar.test/properties/" in result.alert.payload_json["deep_link_url"]
    assert "URGENT CALL" in sender.messages[0]


def test_alert_creation_persists_pending_before_delivery(db_session: Session) -> None:
    fixture = create_manual_deal_fixture(
        db_session,
        expected_profit=Decimal("24000.00"),
        downside_profit=Decimal("7000.00"),
        roi=Decimal("0.120000"),
        required_negotiation_pct=Decimal("0.050000"),
    )
    assessment_result = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    alert = create_opportunity_alert(
        db_session,
        assessment_result.assessment,
        app_base_url="http://radar.test",
    )

    assert alert is not None
    assert alert.status == AlertStatus.PENDING
    assert alert.alert_type == AlertType.OPPORTUNITY
    assert count_rows(db_session, Alert) == 1

    sender = FakeTelegramSender(TelegramDeliveryResult(provider_message_id="tg-pending"))
    delivery = deliver_telegram_alert(db_session, alert, sender)

    assert delivery.success is True
    assert alert.status == AlertStatus.SENT
    assert alert.sent_at is not None
    assert alert.provider_message_id == "tg-pending"


def test_unchanged_opportunity_state_does_not_send_duplicate_alert(
    db_session: Session,
) -> None:
    fixture = create_manual_deal_fixture(
        db_session,
        expected_profit=Decimal("24000.00"),
        downside_profit=Decimal("7000.00"),
        roi=Decimal("0.120000"),
        required_negotiation_pct=Decimal("0.050000"),
    )
    sender = FakeTelegramSender()

    first = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        sender=sender,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )
    second = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        sender=sender,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert first.alert is second.alert
    assert second.delivery is not None
    assert second.delivery.attempted is False
    assert second.delivery.skipped_reason == "SENT"
    assert sender.call_count == 1
    assert count_rows(db_session, OpportunityAssessment) == 2
    assert count_rows(db_session, Alert) == 1


def test_failed_telegram_delivery_preserves_assessment_and_retries_same_alert(
    db_session: Session,
) -> None:
    fixture = create_manual_deal_fixture(
        db_session,
        expected_profit=Decimal("24000.00"),
        downside_profit=Decimal("7000.00"),
        roi=Decimal("0.120000"),
        required_negotiation_pct=Decimal("0.050000"),
    )
    failing_sender = FakeTelegramSender(RuntimeError("telegram unavailable"))

    result = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        sender=failing_sender,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert result.alert is not None
    assert result.alert.status == AlertStatus.FAILED
    assert result.alert.send_attempt_count == 1
    assert result.alert.failed_at is not None
    assert result.delivery is not None
    assert result.delivery.success is False
    assert count_rows(db_session, OpportunityAssessment) == 1
    assert count_rows(db_session, Alert) == 1

    retry_sender = FakeTelegramSender(TelegramDeliveryResult(provider_message_id="tg-retry"))
    retry_attempts = send_due_telegram_alerts(db_session, retry_sender)

    assert len(retry_attempts) == 1
    assert retry_attempts[0].alert.id == result.alert.id
    assert retry_attempts[0].success is True
    assert result.alert.status == AlertStatus.SENT
    assert result.alert.send_attempt_count == 2
    assert result.alert.provider_message_id == "tg-retry"
    assert count_rows(db_session, Alert) == 1


def test_no_qualifying_opportunities_is_valid_result(db_session: Session) -> None:
    fixture = create_manual_deal_fixture(
        db_session,
        expected_profit=Decimal("-1000.00"),
        downside_profit=Decimal("-5000.00"),
        roi=Decimal("-0.010000"),
    )
    sender = FakeTelegramSender()

    result = assess_opportunity_batch(
        db_session,
        [fixture.property],
        sender=sender,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert result.status == NO_QUALIFYING_OPPORTUNITIES
    assert result.alerts == []
    assert sender.call_count == 0
    assert count_rows(db_session, Alert) == 0
    assert result.assessments[0].recommended_action == OpportunityAction.IGNORE


def test_watch_to_call_upgrade_creates_one_action_alert(db_session: Session) -> None:
    fixture = create_manual_deal_fixture(
        db_session,
        expected_profit=Decimal("8000.00"),
        downside_profit=Decimal("6000.00"),
        roi=Decimal("0.090000"),
        required_negotiation_pct=Decimal("0.120000"),
    )
    sender = FakeTelegramSender()

    first = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        sender=sender,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )
    upgraded_deal = create_deal_for_fixture(
        db_session,
        fixture,
        expected_profit=Decimal("24000.00"),
        downside_profit=Decimal("7000.00"),
        roi=Decimal("0.120000"),
        required_negotiation_pct=Decimal("0.050000"),
    )

    second = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=upgraded_deal,
        seller_assessment=fixture.seller,
        sender=sender,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert first.assessment.recommended_action == OpportunityAction.WATCH
    assert first.alert is None
    assert second.assessment.recommended_action == OpportunityAction.CALL
    assert second.alert is not None
    assert second.alert.status == AlertStatus.SENT
    assert sender.call_count == 1
    assert count_rows(db_session, Alert) == 1


def test_operational_alert_is_separate_from_property_opportunity_alert(
    db_session: Session,
) -> None:
    alert = create_operational_telegram_alert(
        db_session,
        reason_code="SOURCE_FAILED",
        message_text="Source four_zida failed.",
        dedupe_key="operational:source_failed:four_zida",
        priority=70,
    )
    duplicate = create_operational_telegram_alert(
        db_session,
        reason_code="SOURCE_FAILED",
        message_text="Source four_zida failed.",
        dedupe_key="operational:source_failed:four_zida",
        priority=70,
    )

    assert duplicate.id == alert.id
    assert alert.alert_type == AlertType.OPERATIONAL
    assert alert.property_id is None
    assert alert.opportunity_assessment_id is None
    assert alert.status == AlertStatus.PENDING
    assert count_rows(db_session, Alert) == 1
