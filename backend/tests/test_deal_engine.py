from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import (
    ComparableSet,
    CostProfile,
    DealAnalysis,
    DealScenario,
    FastSaleEstimate,
    InvestmentProfile,
    LiquidityAssessment,
    Listing,
    Property,
    RiskAssessment,
    Source,
    Valuation,
)
from app.deals.deal_engine import (
    DEAL_FORMULA_VERSION,
    analyze_deal,
    calculate_deal_scenario,
    calculate_required_negotiation,
    solve_max_buy_price,
)
from app.domain.enums import (
    CurrencyCode,
    DataSourceKind,
    DealAnalysisStatus,
    DealScenarioType,
    FastSaleStatus,
    LiquidityStatus,
    ListingStatus,
    PropertyType,
    RiskGateStatus,
    SellerType,
    ValuationModelType,
    ValuationStatus,
)

AS_OF = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def create_source(session: Session, code: str = "phase9") -> Source:
    source = Source(
        name=f"Source {code}",
        code=code,
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
    external_listing_id: str = "phase9-listing",
) -> Listing:
    listing = Listing(
        source=source,
        property=property_,
        external_listing_id=external_listing_id,
        url=f"https://example.test/{external_listing_id}",
        canonical_url=f"https://example.test/{external_listing_id}",
        title="Deal target listing",
        description="Listing for deal analysis.",
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
        first_seen_at=AS_OF - timedelta(days=10),
        last_seen_at=AS_OF,
    )
    session.add(listing)
    session.flush()
    return listing


def create_cost_profile(
    session: Session,
    code: str = "phase9_costs",
    **rules: dict[str, object],
) -> CostProfile:
    profile = CostProfile(
        name=f"Cost profile {code}",
        code=code,
        currency=CurrencyCode.EUR,
        is_active=True,
        purchase_tax_rule_json=rules.get("purchase_tax_rule_json", {}),
        notary_rule_json=rules.get("notary_rule_json", {}),
        lawyer_rule_json=rules.get("lawyer_rule_json", {}),
        agency_rule_json=rules.get("agency_rule_json", {}),
        sale_cost_rule_json=rules.get("sale_cost_rule_json", {}),
        holding_cost_rule_json=rules.get("holding_cost_rule_json", {}),
        financing_rule_json=rules.get("financing_rule_json", {}),
        other_cost_rule_json=rules.get("other_cost_rule_json", {}),
        version="cost_profile_v1",
    )
    session.add(profile)
    session.flush()
    return profile


def create_investment_profile(
    session: Session,
    *,
    min_expected_profit: Decimal | None = Decimal("0.00"),
    min_downside_profit: Decimal | None = None,
    min_roi: Decimal | None = None,
    max_expected_holding_days: int | None = 180,
    default_risk_reserve: Decimal = Decimal("0.00"),
) -> InvestmentProfile:
    profile = InvestmentProfile(
        name="Default investment profile",
        is_default=True,
        min_expected_profit=min_expected_profit,
        min_downside_profit=min_downside_profit,
        min_roi=min_roi,
        max_expected_holding_days=max_expected_holding_days,
        min_liquidity_score=Decimal("50.00"),
        min_valuation_confidence=Decimal("60.00"),
        default_risk_reserve=default_risk_reserve,
        desired_profit=Decimal("25000.00"),
        version="investment_profile_v1",
    )
    session.add(profile)
    session.flush()
    return profile


def create_valuation(session: Session, property_: Property) -> Valuation:
    comparable_set = ComparableSet(
        property=property_,
        as_of=AS_OF,
        comparable_engine_version="test_comparable_engine",
        search_parameters_json={"source": "test"},
    )
    session.add(comparable_set)
    session.flush()
    valuation = Valuation(
        property=property_,
        comparable_set=comparable_set,
        as_of=AS_OF,
        status=ValuationStatus.SUCCESS,
        fair_value_low=Decimal("150000.00"),
        fair_value_base=Decimal("170000.00"),
        fair_value_high=Decimal("190000.00"),
        currency=CurrencyCode.EUR,
        confidence=Decimal("75.00"),
        data_quality_at_analysis=Decimal("80.00"),
        model_type=ValuationModelType.LISTING_COMPS,
        model_version="valuation_v1",
        input_summary_json={"source": "test"},
        explanation_json={"source": "test"},
    )
    session.add(valuation)
    session.flush()
    return valuation


def create_fast_sale(
    session: Session,
    property_: Property,
    valuation: Valuation,
    *,
    low: Decimal = Decimal("160000.00"),
    base: Decimal = Decimal("165000.00"),
    high: Decimal = Decimal("170000.00"),
) -> tuple[LiquidityAssessment, FastSaleEstimate]:
    liquidity = LiquidityAssessment(
        property=property_,
        valuation=valuation,
        as_of=AS_OF,
        status=LiquidityStatus.SUCCESS,
        liquidity_score=Decimal("72.00"),
        confidence=Decimal("70.00"),
        probability_sale_30d=None,
        probability_sale_60d=None,
        probability_sale_90d=None,
        positive_factors_json={"source": "test"},
        negative_factors_json={"source": "test"},
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
        value_low=low,
        value_base=base,
        value_high=high,
        target_days=60,
        target_probability=None,
        confidence=Decimal("68.00"),
        model_version="fast_sale_v1",
        explanation_json={"source": "test"},
    )
    session.add(fast_sale)
    session.flush()
    return liquidity, fast_sale


def create_risk_assessment(session: Session, property_: Property) -> RiskAssessment:
    risk = RiskAssessment(
        property=property_,
        as_of=AS_OF,
        hard_gate_status=RiskGateStatus.PASS,
        risk_score=Decimal("15.00"),
        confidence=Decimal("70.00"),
        rules_version="risk_rules_v1",
    )
    session.add(risk)
    session.flush()
    return risk


def count_rows(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_phase9_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {
        "cost_profiles",
        "investment_profiles",
        "deal_analyses",
        "deal_scenarios",
    }.issubset(set(inspector.get_table_names()))


def test_fixed_cost_deal_uses_manual_fixture_metrics(db_session: Session) -> None:
    source = create_source(db_session, "phase9_fixed")
    property_ = create_property(db_session)
    create_listing(db_session, source, property_, asking_price=Decimal("130000.00"))
    cost_profile = create_cost_profile(
        db_session,
        "phase9_fixed_costs",
        notary_rule_json={"fixed_amount": "5000.00"},
        holding_cost_rule_json={"fixed_amount": "1000.00"},
    )
    investment_profile = create_investment_profile(
        db_session,
        min_expected_profit=Decimal("15000.00"),
        max_expected_holding_days=365,
    )
    valuation = create_valuation(db_session, property_)
    liquidity, fast_sale = create_fast_sale(
        db_session,
        property_,
        valuation,
        low=Decimal("160000.00"),
        base=Decimal("165000.00"),
        high=Decimal("170000.00"),
    )
    risk = create_risk_assessment(db_session, property_)

    result = analyze_deal(
        db_session,
        property_,
        valuation=valuation,
        liquidity_assessment=liquidity,
        fast_sale_estimate=fast_sale,
        risk_assessment=risk,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        assumed_purchase_price=Decimal("130000.00"),
        renovation_cost=Decimal("5000.00"),
        expected_holding_days=365,
        as_of=AS_OF,
    )
    deal = result.deal_analysis

    assert deal.status == DealAnalysisStatus.SUCCESS
    assert deal.purchase_costs == Decimal("5000.00")
    assert deal.renovation_cost == Decimal("5000.00")
    assert deal.holding_costs == Decimal("1000.00")
    assert deal.total_cost_basis == Decimal("141000.00")
    assert deal.expected_exit_price == Decimal("165000.00")
    assert deal.expected_profit == Decimal("24000.00")
    assert deal.roi == Decimal("0.170213")
    assert deal.annualized_roi == Decimal("0.170213")
    assert deal.max_buy_price == Decimal("133000.00")
    assert deal.required_negotiation_amount == Decimal("0.00")
    assert deal.formula_version == DEAL_FORMULA_VERSION
    assert len(result.scenarios) == 3


def test_percentage_purchase_and_sale_costs_are_applied_once(db_session: Session) -> None:
    cost_profile = create_cost_profile(
        db_session,
        "phase9_percentage",
        purchase_tax_rule_json={"purchase_price_pct": "2.5"},
        sale_cost_rule_json={"exit_price_pct": "3.0"},
    )
    investment_profile = create_investment_profile(db_session)

    scenario = calculate_deal_scenario(
        scenario_type=DealScenarioType.BASE,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        purchase_price=Decimal("100000.00"),
        exit_price=Decimal("120000.00"),
        renovation_cost=Decimal("0.00"),
        holding_days=180,
    )

    assert scenario.costs.taxes == Decimal("2500.00")
    assert scenario.costs.sale_costs == Decimal("3600.00")
    assert scenario.costs.total_cost_basis == Decimal("102500.00")
    assert scenario.costs.net_sale_proceeds == Decimal("116400.00")
    assert scenario.profit == Decimal("13900.00")
    assert scenario.roi == Decimal("0.135610")


def test_max_buy_solver_profit_roi_percentage_costs_and_monotonicity(
    db_session: Session,
) -> None:
    fixed_cost_profile = create_cost_profile(
        db_session,
        "phase9_maxbuy_fixed",
        notary_rule_json={"fixed_amount": "10000.00"},
    )
    percentage_cost_profile = create_cost_profile(
        db_session,
        "phase9_maxbuy_pct",
        notary_rule_json={"fixed_amount": "10000.00"},
        purchase_tax_rule_json={"purchase_price_pct": "2.5"},
    )
    fixed_profit_profile = create_investment_profile(
        db_session,
        min_expected_profit=Decimal("15000.00"),
        min_roi=None,
        max_expected_holding_days=0,
    )
    roi_profile = create_investment_profile(
        db_session,
        min_expected_profit=Decimal("15000.00"),
        min_roi=Decimal("0.200000"),
        max_expected_holding_days=0,
    )

    only_fixed = solve_max_buy_price(
        cost_profile=fixed_cost_profile,
        investment_profile=fixed_profit_profile,
        conservative_exit_price=Decimal("165000.00"),
        renovation_cost=Decimal("0.00"),
        holding_days=0,
    )
    with_percentage = solve_max_buy_price(
        cost_profile=percentage_cost_profile,
        investment_profile=fixed_profit_profile,
        conservative_exit_price=Decimal("165000.00"),
        renovation_cost=Decimal("0.00"),
        holding_days=0,
    )
    roi_limited = solve_max_buy_price(
        cost_profile=fixed_cost_profile,
        investment_profile=roi_profile,
        conservative_exit_price=Decimal("165000.00"),
        renovation_cost=Decimal("0.00"),
        holding_days=0,
    )
    higher_profit_profile = create_investment_profile(
        db_session,
        min_expected_profit=Decimal("25000.00"),
        min_roi=None,
        max_expected_holding_days=0,
    )
    higher_profit = solve_max_buy_price(
        cost_profile=fixed_cost_profile,
        investment_profile=higher_profit_profile,
        conservative_exit_price=Decimal("165000.00"),
        renovation_cost=Decimal("0.00"),
        holding_days=0,
    )
    higher_exit = solve_max_buy_price(
        cost_profile=fixed_cost_profile,
        investment_profile=fixed_profit_profile,
        conservative_exit_price=Decimal("175000.00"),
        renovation_cost=Decimal("0.00"),
        holding_days=0,
    )

    assert only_fixed == Decimal("140000.00")
    assert with_percentage == Decimal("136585.37")
    assert roi_limited == Decimal("127500.00")
    assert higher_profit <= only_fixed
    assert higher_exit >= only_fixed


def test_required_negotiation_never_negative() -> None:
    required = calculate_required_negotiation(
        Decimal("150000.00"),
        Decimal("140000.00"),
    )
    already_within_max_buy = calculate_required_negotiation(
        Decimal("135000.00"),
        Decimal("140000.00"),
    )

    assert required.amount == Decimal("10000.00")
    assert required.pct == Decimal("0.066667")
    assert already_within_max_buy.amount == Decimal("0.00")
    assert already_within_max_buy.pct == Decimal("0.000000")


def test_scenarios_persist_order_and_versioned_history(db_session: Session) -> None:
    source = create_source(db_session, "phase9_scenarios")
    property_ = create_property(db_session)
    create_listing(db_session, source, property_, asking_price=Decimal("140000.00"))
    cost_profile = create_cost_profile(
        db_session,
        "phase9_scenario_costs",
        sale_cost_rule_json={"exit_price_pct": "2.0"},
        holding_cost_rule_json={"per_day_amount": "10.00"},
    )
    investment_profile = create_investment_profile(
        db_session,
        min_expected_profit=Decimal("0.00"),
        min_roi=Decimal("0.100000"),
        max_expected_holding_days=180,
        default_risk_reserve=Decimal("3000.00"),
    )
    valuation = create_valuation(db_session, property_)
    liquidity, fast_sale = create_fast_sale(
        db_session,
        property_,
        valuation,
        low=Decimal("160000.00"),
        base=Decimal("170000.00"),
        high=Decimal("185000.00"),
    )

    first = analyze_deal(
        db_session,
        property_,
        valuation=valuation,
        liquidity_assessment=liquidity,
        fast_sale_estimate=fast_sale,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        assumed_purchase_price=Decimal("140000.00"),
        renovation_cost=Decimal("10000.00"),
        expected_holding_days=180,
        as_of=AS_OF,
    )
    second = analyze_deal(
        db_session,
        property_,
        valuation=valuation,
        liquidity_assessment=liquidity,
        fast_sale_estimate=fast_sale,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        assumed_purchase_price=Decimal("140000.00"),
        renovation_cost=Decimal("10000.00"),
        expected_holding_days=180,
        as_of=AS_OF,
    )

    scenarios = {scenario.scenario_type: scenario for scenario in first.scenarios}
    assert first.deal_analysis.id != second.deal_analysis.id
    assert count_rows(db_session, DealAnalysis) == 2
    assert count_rows(db_session, DealScenario) == 6
    assert scenarios[DealScenarioType.DOWNSIDE].profit <= scenarios[DealScenarioType.BASE].profit
    assert scenarios[DealScenarioType.BASE].profit <= scenarios[DealScenarioType.UPSIDE].profit
    assert scenarios[DealScenarioType.DOWNSIDE].holding_days == 225
    assert scenarios[DealScenarioType.BASE].holding_days == 180
    assert scenarios[DealScenarioType.UPSIDE].holding_days == 135
    assert (
        scenarios[DealScenarioType.DOWNSIDE].assumptions_json["cost_breakdown"]["renovation_cost"]
        == "12000.00"
    )
    assert first.deal_analysis.formula_version == DEAL_FORMULA_VERSION
    assert first.deal_analysis.input_summary_json["fast_sale_estimate_id"] == str(fast_sale.id)


def test_zero_and_negative_margin_are_successful_calculations(db_session: Session) -> None:
    source = create_source(db_session, "phase9_margin")
    property_ = create_property(db_session)
    create_listing(db_session, source, property_, asking_price=Decimal("150000.00"))
    cost_profile = create_cost_profile(db_session, "phase9_margin_costs")
    investment_profile = create_investment_profile(
        db_session,
        min_expected_profit=Decimal("0.00"),
        min_roi=None,
        max_expected_holding_days=180,
    )
    valuation = create_valuation(db_session, property_)
    liquidity, fast_sale = create_fast_sale(
        db_session,
        property_,
        valuation,
        low=Decimal("140000.00"),
        base=Decimal("140000.00"),
        high=Decimal("140000.00"),
    )

    result = analyze_deal(
        db_session,
        property_,
        valuation=valuation,
        liquidity_assessment=liquidity,
        fast_sale_estimate=fast_sale,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        assumed_purchase_price=Decimal("150000.00"),
        renovation_cost=Decimal("0.00"),
        expected_holding_days=180,
        as_of=AS_OF,
    )
    zero_margin = calculate_deal_scenario(
        scenario_type=DealScenarioType.BASE,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        purchase_price=Decimal("100000.00"),
        exit_price=Decimal("100000.00"),
        renovation_cost=Decimal("0.00"),
        holding_days=180,
    )

    assert result.deal_analysis.status == DealAnalysisStatus.SUCCESS
    assert result.deal_analysis.expected_profit == Decimal("-10000.00")
    assert result.deal_analysis.roi == Decimal("-0.066667")
    assert zero_margin.profit == Decimal("0.00")
    assert zero_margin.roi == Decimal("0.000000")


def test_invalid_inputs_and_zero_holding_behavior(db_session: Session) -> None:
    cost_profile = create_cost_profile(db_session, "phase9_invalid")
    investment_profile = create_investment_profile(
        db_session,
        min_expected_profit=Decimal("0.00"),
        min_roi=None,
        max_expected_holding_days=0,
    )

    with pytest.raises(ValueError, match="holding_days must be non-negative"):
        calculate_deal_scenario(
            scenario_type=DealScenarioType.BASE,
            cost_profile=cost_profile,
            investment_profile=investment_profile,
            purchase_price=Decimal("100000.00"),
            exit_price=Decimal("120000.00"),
            renovation_cost=Decimal("0.00"),
            holding_days=-1,
        )
    with pytest.raises(ValueError, match="purchase_price must be non-negative"):
        calculate_deal_scenario(
            scenario_type=DealScenarioType.BASE,
            cost_profile=cost_profile,
            investment_profile=investment_profile,
            purchase_price=Decimal("-1.00"),
            exit_price=Decimal("120000.00"),
            renovation_cost=Decimal("0.00"),
            holding_days=0,
        )
    with pytest.raises(ValueError, match="capital invested must be greater than zero"):
        calculate_deal_scenario(
            scenario_type=DealScenarioType.BASE,
            cost_profile=cost_profile,
            investment_profile=investment_profile,
            purchase_price=Decimal("0.00"),
            exit_price=Decimal("120000.00"),
            renovation_cost=Decimal("0.00"),
            holding_days=0,
        )
    with pytest.raises(ValueError, match="purchase_price must be a finite decimal"):
        calculate_deal_scenario(
            scenario_type=DealScenarioType.BASE,
            cost_profile=cost_profile,
            investment_profile=investment_profile,
            purchase_price=Decimal("NaN"),
            exit_price=Decimal("120000.00"),
            renovation_cost=Decimal("0.00"),
            holding_days=0,
        )

    zero_days = calculate_deal_scenario(
        scenario_type=DealScenarioType.BASE,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        purchase_price=Decimal("100000.00"),
        exit_price=Decimal("110000.00"),
        renovation_cost=Decimal("0.00"),
        holding_days=0,
    )

    assert zero_days.roi == Decimal("0.100000")
    assert zero_days.annualized_roi is None
    assert zero_days.capital_days == Decimal("0.00")
    assert zero_days.profit_per_capital_day is None


def test_missing_renovation_creates_insufficient_deal_without_zero_cost(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase9_insufficient")
    property_ = create_property(db_session)
    create_listing(db_session, source, property_, asking_price=Decimal("130000.00"))
    cost_profile = create_cost_profile(db_session, "phase9_insufficient_costs")
    investment_profile = create_investment_profile(db_session)
    valuation = create_valuation(db_session, property_)
    liquidity, fast_sale = create_fast_sale(db_session, property_, valuation)

    result = analyze_deal(
        db_session,
        property_,
        valuation=valuation,
        liquidity_assessment=liquidity,
        fast_sale_estimate=fast_sale,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        assumed_purchase_price=Decimal("130000.00"),
        renovation_cost=None,
        expected_holding_days=180,
        as_of=AS_OF,
    )

    assert result.deal_analysis.status == DealAnalysisStatus.INSUFFICIENT_DATA
    assert result.deal_analysis.renovation_cost is None
    assert result.deal_analysis.expected_profit is None
    assert result.deal_analysis.explanation_json["reason"] == "MISSING_RENOVATION_COST"
    assert result.scenarios == []
