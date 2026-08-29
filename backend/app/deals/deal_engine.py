from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CostProfile,
    DealAnalysis,
    DealScenario,
    FastSaleEstimate,
    InvestmentProfile,
    LiquidityAssessment,
    Listing,
    Property,
    RiskAssessment,
    Valuation,
)
from app.domain.enums import (
    CurrencyCode,
    DealAnalysisStatus,
    DealScenarioType,
    FastSaleStatus,
    ListingStatus,
    ValuationStatus,
)

DEAL_FORMULA_VERSION = "deal_formula_v1"
DEAL_SCENARIO_RULES_VERSION = "deal_scenario_rules_v1"

MONEY_QUANTIZER = Decimal("0.01")
RATIO_QUANTIZER = Decimal("0.000001")
CAPITAL_DAY_QUANTIZER = Decimal("0.01")
PROFIT_PER_CAPITAL_DAY_QUANTIZER = Decimal("0.0000000001")

SCENARIO_RULES: dict[DealScenarioType, dict[str, Decimal]] = {
    DealScenarioType.DOWNSIDE: {
        "renovation_multiplier": Decimal("1.20"),
        "holding_days_multiplier": Decimal("1.25"),
    },
    DealScenarioType.BASE: {
        "renovation_multiplier": Decimal("1.00"),
        "holding_days_multiplier": Decimal("1.00"),
    },
    DealScenarioType.UPSIDE: {
        "renovation_multiplier": Decimal("0.90"),
        "holding_days_multiplier": Decimal("0.75"),
    },
}


@dataclass(frozen=True)
class CostBreakdown:
    purchase_costs: Decimal
    renovation_cost: Decimal
    sale_costs: Decimal
    taxes: Decimal
    financing_costs: Decimal
    holding_costs: Decimal
    risk_reserve: Decimal
    other_costs: Decimal
    total_cost_basis: Decimal
    net_sale_proceeds: Decimal


@dataclass(frozen=True)
class ScenarioCalculation:
    scenario_type: DealScenarioType
    purchase_price: Decimal
    exit_price: Decimal
    holding_days: int
    costs: CostBreakdown
    profit: Decimal
    roi: Decimal | None
    annualized_roi: Decimal | None
    capital_days: Decimal
    profit_per_capital_day: Decimal | None
    assumptions_json: dict[str, object]


@dataclass(frozen=True)
class RequiredNegotiation:
    amount: Decimal | None
    pct: Decimal | None


@dataclass(frozen=True)
class DealRunResult:
    deal_analysis: DealAnalysis
    scenarios: list[DealScenario]


def analyze_deal(
    session: Session,
    property_: Property,
    *,
    valuation: Valuation | None = None,
    liquidity_assessment: LiquidityAssessment | None = None,
    fast_sale_estimate: FastSaleEstimate | None = None,
    risk_assessment: RiskAssessment | None = None,
    cost_profile: CostProfile | None = None,
    investment_profile: InvestmentProfile | None = None,
    assumed_purchase_price: Decimal | None = None,
    renovation_cost: Decimal | None = None,
    expected_holding_days: int | None = None,
    as_of: datetime | None = None,
    commit: bool = False,
) -> DealRunResult:
    analysis_as_of = _analysis_as_of(as_of, fast_sale_estimate, valuation)
    selected_cost_profile = cost_profile or _active_cost_profile(session)
    selected_investment_profile = investment_profile or _default_investment_profile(session)
    selected_valuation = valuation or _latest_successful_valuation(
        session,
        property_,
        analysis_as_of,
    )
    selected_fast_sale = fast_sale_estimate or _latest_successful_fast_sale(
        session,
        property_,
        analysis_as_of,
    )
    selected_liquidity = liquidity_assessment or (
        selected_fast_sale.liquidity_assessment if selected_fast_sale is not None else None
    )
    selected_risk = risk_assessment or _latest_risk_assessment(session, property_, analysis_as_of)
    asking_price = _current_asking_price(session, property_, analysis_as_of)
    purchase_price = assumed_purchase_price if assumed_purchase_price is not None else asking_price
    holding_days = (
        expected_holding_days
        if expected_holding_days is not None
        else (
            selected_investment_profile.max_expected_holding_days
            if selected_investment_profile is not None
            else None
        )
    )

    missing_reason = _missing_input_reason(
        cost_profile=selected_cost_profile,
        investment_profile=selected_investment_profile,
        valuation=selected_valuation,
        fast_sale_estimate=selected_fast_sale,
        purchase_price=purchase_price,
        renovation_cost=renovation_cost,
        holding_days=holding_days,
    )
    if missing_reason is not None:
        deal_analysis = _persist_insufficient_deal(
            session,
            property_,
            valuation=selected_valuation,
            liquidity_assessment=selected_liquidity,
            fast_sale_estimate=selected_fast_sale,
            risk_assessment=selected_risk,
            cost_profile=selected_cost_profile,
            investment_profile=selected_investment_profile,
            as_of=analysis_as_of,
            reason=missing_reason,
            asking_price=asking_price,
            assumed_purchase_price=purchase_price,
        )
        if commit:
            session.commit()
        return DealRunResult(deal_analysis=deal_analysis, scenarios=[])

    assert selected_cost_profile is not None
    assert selected_investment_profile is not None
    assert selected_fast_sale is not None
    assert purchase_price is not None
    assert renovation_cost is not None
    assert holding_days is not None

    scenario_calculations = build_deal_scenarios(
        cost_profile=selected_cost_profile,
        investment_profile=selected_investment_profile,
        fast_sale_estimate=selected_fast_sale,
        assumed_purchase_price=purchase_price,
        renovation_cost=renovation_cost,
        expected_holding_days=holding_days,
    )
    base_scenario = _scenario_by_type(scenario_calculations, DealScenarioType.BASE)
    downside_scenario = _scenario_by_type(scenario_calculations, DealScenarioType.DOWNSIDE)
    upside_scenario = _scenario_by_type(scenario_calculations, DealScenarioType.UPSIDE)
    max_buy_price = solve_max_buy_price(
        cost_profile=selected_cost_profile,
        investment_profile=selected_investment_profile,
        conservative_exit_price=downside_scenario.exit_price,
        renovation_cost=downside_scenario.costs.renovation_cost,
        holding_days=downside_scenario.holding_days,
    )
    required_negotiation = calculate_required_negotiation(asking_price, max_buy_price)

    deal_analysis = DealAnalysis(
        property=property_,
        valuation=selected_valuation,
        liquidity_assessment=selected_liquidity,
        fast_sale_estimate=selected_fast_sale,
        risk_assessment=selected_risk,
        cost_profile=selected_cost_profile,
        investment_profile=selected_investment_profile,
        as_of=analysis_as_of,
        status=DealAnalysisStatus.SUCCESS,
        assumed_purchase_price=_money(purchase_price),
        asking_price=_money(asking_price) if asking_price is not None else None,
        purchase_costs=base_scenario.costs.purchase_costs,
        renovation_cost=base_scenario.costs.renovation_cost,
        sale_costs=base_scenario.costs.sale_costs,
        taxes=base_scenario.costs.taxes,
        financing_costs=base_scenario.costs.financing_costs,
        holding_costs=base_scenario.costs.holding_costs,
        risk_reserve=base_scenario.costs.risk_reserve,
        other_costs=base_scenario.costs.other_costs,
        total_cost_basis=base_scenario.costs.total_cost_basis,
        expected_exit_price=base_scenario.exit_price,
        max_buy_price=max_buy_price,
        required_negotiation_amount=required_negotiation.amount,
        required_negotiation_pct=required_negotiation.pct,
        expected_profit=base_scenario.profit,
        downside_profit=downside_scenario.profit,
        upside_profit=upside_scenario.profit,
        roi=base_scenario.roi,
        annualized_roi=base_scenario.annualized_roi,
        expected_holding_days=base_scenario.holding_days,
        capital_days=base_scenario.capital_days,
        profit_per_capital_day=base_scenario.profit_per_capital_day,
        formula_version=DEAL_FORMULA_VERSION,
        input_summary_json=_input_summary(
            valuation=selected_valuation,
            liquidity_assessment=selected_liquidity,
            fast_sale_estimate=selected_fast_sale,
            risk_assessment=selected_risk,
            cost_profile=selected_cost_profile,
            investment_profile=selected_investment_profile,
            asking_price=asking_price,
        ),
        explanation_json={
            "status": DealAnalysisStatus.SUCCESS.value,
            "formula_version": DEAL_FORMULA_VERSION,
            "scenario_rules_version": DEAL_SCENARIO_RULES_VERSION,
            "capital_invested_definition": "total_cost_basis",
            "annualized_roi_definition": "linear_roi_times_365_over_holding_days",
            "max_buy_basis": "downside_fast_sale_exit",
            "max_buy_constraints": _max_buy_constraints_json(selected_investment_profile),
            "required_negotiation": {
                "amount": _decimal_to_string(required_negotiation.amount),
                "pct": _decimal_to_string(required_negotiation.pct),
            },
        },
    )
    session.add(deal_analysis)
    session.flush()
    scenarios = [
        _persist_scenario(session, deal_analysis, scenario) for scenario in scenario_calculations
    ]

    if commit:
        session.commit()
    return DealRunResult(deal_analysis=deal_analysis, scenarios=scenarios)


def build_deal_scenarios(
    *,
    cost_profile: CostProfile,
    investment_profile: InvestmentProfile,
    fast_sale_estimate: FastSaleEstimate,
    assumed_purchase_price: Decimal,
    renovation_cost: Decimal,
    expected_holding_days: int,
) -> list[ScenarioCalculation]:
    _validate_successful_fast_sale(fast_sale_estimate)
    exit_by_type = {
        DealScenarioType.DOWNSIDE: fast_sale_estimate.value_low,
        DealScenarioType.BASE: fast_sale_estimate.value_base,
        DealScenarioType.UPSIDE: fast_sale_estimate.value_high,
    }
    scenarios: list[ScenarioCalculation] = []
    for scenario_type in (
        DealScenarioType.DOWNSIDE,
        DealScenarioType.BASE,
        DealScenarioType.UPSIDE,
    ):
        rules = SCENARIO_RULES[scenario_type]
        scenario_renovation = _money(renovation_cost * rules["renovation_multiplier"])
        scenario_holding_days = _scaled_holding_days(
            expected_holding_days,
            rules["holding_days_multiplier"],
        )
        scenarios.append(
            calculate_deal_scenario(
                scenario_type=scenario_type,
                cost_profile=cost_profile,
                investment_profile=investment_profile,
                purchase_price=assumed_purchase_price,
                exit_price=_required_money(exit_by_type[scenario_type], "fast_sale_exit_price"),
                renovation_cost=scenario_renovation,
                holding_days=scenario_holding_days,
                assumptions_extra={
                    "scenario_rules_version": DEAL_SCENARIO_RULES_VERSION,
                    "renovation_multiplier": _decimal_to_string(
                        rules["renovation_multiplier"],
                    ),
                    "holding_days_multiplier": _decimal_to_string(
                        rules["holding_days_multiplier"],
                    ),
                    "fast_sale_estimate_id": str(fast_sale_estimate.id),
                },
            )
        )
    return scenarios


def calculate_deal_scenario(
    *,
    scenario_type: DealScenarioType,
    cost_profile: CostProfile,
    investment_profile: InvestmentProfile,
    purchase_price: Decimal,
    exit_price: Decimal,
    renovation_cost: Decimal,
    holding_days: int,
    assumptions_extra: dict[str, object] | None = None,
) -> ScenarioCalculation:
    purchase_price = _validate_money(purchase_price, "purchase_price")
    exit_price = _validate_money(exit_price, "exit_price")
    renovation_cost = _validate_money(renovation_cost, "renovation_cost")
    risk_reserve = _validate_money(investment_profile.default_risk_reserve, "risk_reserve")
    if holding_days < 0:
        raise ValueError("holding_days must be non-negative")

    taxes = _rule_amount(
        cost_profile.purchase_tax_rule_json,
        purchase_price=purchase_price,
        exit_price=exit_price,
        holding_days=holding_days,
        field_name="purchase_tax_rule_json",
    )
    notary = _rule_amount(
        cost_profile.notary_rule_json,
        purchase_price=purchase_price,
        exit_price=exit_price,
        holding_days=holding_days,
        field_name="notary_rule_json",
    )
    lawyer = _rule_amount(
        cost_profile.lawyer_rule_json,
        purchase_price=purchase_price,
        exit_price=exit_price,
        holding_days=holding_days,
        field_name="lawyer_rule_json",
    )
    agency = _rule_amount(
        cost_profile.agency_rule_json,
        purchase_price=purchase_price,
        exit_price=exit_price,
        holding_days=holding_days,
        field_name="agency_rule_json",
    )
    sale_costs = _rule_amount(
        cost_profile.sale_cost_rule_json,
        purchase_price=purchase_price,
        exit_price=exit_price,
        holding_days=holding_days,
        field_name="sale_cost_rule_json",
    )
    holding_costs = _rule_amount(
        cost_profile.holding_cost_rule_json,
        purchase_price=purchase_price,
        exit_price=exit_price,
        holding_days=holding_days,
        field_name="holding_cost_rule_json",
    )
    financing_costs = _rule_amount(
        cost_profile.financing_rule_json,
        purchase_price=purchase_price,
        exit_price=exit_price,
        holding_days=holding_days,
        field_name="financing_rule_json",
    )
    other_costs = _rule_amount(
        cost_profile.other_cost_rule_json,
        purchase_price=purchase_price,
        exit_price=exit_price,
        holding_days=holding_days,
        field_name="other_cost_rule_json",
    )
    purchase_costs = _money(notary + lawyer + agency)
    total_cost_basis = _money(
        purchase_price
        + purchase_costs
        + renovation_cost
        + taxes
        + financing_costs
        + holding_costs
        + risk_reserve
        + other_costs
    )
    if total_cost_basis <= 0:
        raise ValueError("capital invested must be greater than zero")

    net_sale_proceeds = _money(exit_price - sale_costs)
    profit = _money(net_sale_proceeds - total_cost_basis)
    roi = _ratio(profit / total_cost_basis)
    annualized_roi = None
    if holding_days > 0:
        annualized_roi = _ratio(roi * Decimal("365") / Decimal(holding_days))
    capital_days = _capital_days(total_cost_basis * Decimal(holding_days))
    profit_per_capital_day = None
    if capital_days > 0:
        profit_per_capital_day = _profit_per_capital_day(profit / capital_days)

    costs = CostBreakdown(
        purchase_costs=purchase_costs,
        renovation_cost=renovation_cost,
        sale_costs=sale_costs,
        taxes=taxes,
        financing_costs=financing_costs,
        holding_costs=holding_costs,
        risk_reserve=risk_reserve,
        other_costs=other_costs,
        total_cost_basis=total_cost_basis,
        net_sale_proceeds=net_sale_proceeds,
    )
    return ScenarioCalculation(
        scenario_type=scenario_type,
        purchase_price=purchase_price,
        exit_price=exit_price,
        holding_days=holding_days,
        costs=costs,
        profit=profit,
        roi=roi,
        annualized_roi=annualized_roi,
        capital_days=capital_days,
        profit_per_capital_day=profit_per_capital_day,
        assumptions_json={
            "formula_version": DEAL_FORMULA_VERSION,
            "scenario_type": scenario_type.value,
            "capital_invested_definition": "total_cost_basis",
            "annualized_roi_definition": (
                "null_when_holding_days_is_zero_else_linear_roi_times_365_over_holding_days"
            ),
            "cost_breakdown": _cost_breakdown_json(costs),
            "cost_profile_id": str(cost_profile.id),
            "cost_profile_code": cost_profile.code,
            "cost_profile_version": cost_profile.version,
            "investment_profile_id": str(investment_profile.id),
            "investment_profile_version": investment_profile.version,
            **(assumptions_extra or {}),
        },
    )


def solve_max_buy_price(
    *,
    cost_profile: CostProfile,
    investment_profile: InvestmentProfile,
    conservative_exit_price: Decimal,
    renovation_cost: Decimal,
    holding_days: int,
) -> Decimal:
    conservative_exit_price = _validate_money(conservative_exit_price, "conservative_exit_price")
    renovation_cost = _validate_money(renovation_cost, "renovation_cost")
    if holding_days < 0:
        raise ValueError("holding_days must be non-negative")
    if conservative_exit_price <= 0:
        return Decimal("0.00")

    low = Decimal("0.00")
    high = conservative_exit_price
    probe = Decimal("0.01")
    if not _purchase_price_satisfies_constraints(
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        purchase_price=probe,
        conservative_exit_price=conservative_exit_price,
        renovation_cost=renovation_cost,
        holding_days=holding_days,
    ):
        return Decimal("0.00")

    for _ in range(96):
        midpoint = (low + high) / Decimal("2")
        if _purchase_price_satisfies_constraints(
            cost_profile=cost_profile,
            investment_profile=investment_profile,
            purchase_price=midpoint,
            conservative_exit_price=conservative_exit_price,
            renovation_cost=renovation_cost,
            holding_days=holding_days,
        ):
            low = midpoint
        else:
            high = midpoint
    return low.quantize(MONEY_QUANTIZER, rounding=ROUND_DOWN)


def calculate_required_negotiation(
    asking_price: Decimal | None,
    max_buy_price: Decimal | None,
) -> RequiredNegotiation:
    if asking_price is None or max_buy_price is None:
        return RequiredNegotiation(amount=None, pct=None)
    asking = _validate_money(asking_price, "asking_price")
    max_buy = _validate_money(max_buy_price, "max_buy_price")
    amount = max(Decimal("0.00"), _money(asking - max_buy))
    pct = None if asking == 0 else _ratio(amount / asking)
    return RequiredNegotiation(amount=amount, pct=pct)


def _purchase_price_satisfies_constraints(
    *,
    cost_profile: CostProfile,
    investment_profile: InvestmentProfile,
    purchase_price: Decimal,
    conservative_exit_price: Decimal,
    renovation_cost: Decimal,
    holding_days: int,
) -> bool:
    try:
        scenario = calculate_deal_scenario(
            scenario_type=DealScenarioType.DOWNSIDE,
            cost_profile=cost_profile,
            investment_profile=investment_profile,
            purchase_price=purchase_price,
            exit_price=conservative_exit_price,
            renovation_cost=renovation_cost,
            holding_days=holding_days,
        )
    except ValueError:
        return False

    required_profit = _required_profit(investment_profile)
    if scenario.profit < required_profit:
        return False
    if investment_profile.min_roi is not None:
        min_roi = _validate_ratio(investment_profile.min_roi, "min_roi")
        exact_roi = scenario.profit / scenario.costs.total_cost_basis
        if exact_roi < min_roi:
            return False
    return True


def _persist_scenario(
    session: Session,
    deal_analysis: DealAnalysis,
    scenario: ScenarioCalculation,
) -> DealScenario:
    row = DealScenario(
        deal_analysis=deal_analysis,
        scenario_type=scenario.scenario_type,
        purchase_price=scenario.purchase_price,
        exit_price=scenario.exit_price,
        cost_basis=scenario.costs.total_cost_basis,
        profit=scenario.profit,
        roi=scenario.roi,
        holding_days=scenario.holding_days,
        assumptions_json={
            **scenario.assumptions_json,
            "annualized_roi": _decimal_to_string(scenario.annualized_roi),
            "capital_days": _decimal_to_string(scenario.capital_days),
            "profit_per_capital_day": _decimal_to_string(scenario.profit_per_capital_day),
            "net_sale_proceeds": _decimal_to_string(scenario.costs.net_sale_proceeds),
        },
    )
    session.add(row)
    session.flush()
    return row


def _persist_insufficient_deal(
    session: Session,
    property_: Property,
    *,
    valuation: Valuation | None,
    liquidity_assessment: LiquidityAssessment | None,
    fast_sale_estimate: FastSaleEstimate | None,
    risk_assessment: RiskAssessment | None,
    cost_profile: CostProfile | None,
    investment_profile: InvestmentProfile | None,
    as_of: datetime,
    reason: str,
    asking_price: Decimal | None,
    assumed_purchase_price: Decimal | None,
) -> DealAnalysis:
    deal_analysis = DealAnalysis(
        property=property_,
        valuation=valuation,
        liquidity_assessment=liquidity_assessment,
        fast_sale_estimate=fast_sale_estimate,
        risk_assessment=risk_assessment,
        cost_profile=cost_profile,
        investment_profile=investment_profile,
        as_of=as_of,
        status=DealAnalysisStatus.INSUFFICIENT_DATA,
        assumed_purchase_price=_money(assumed_purchase_price)
        if assumed_purchase_price is not None
        else None,
        asking_price=_money(asking_price) if asking_price is not None else None,
        formula_version=DEAL_FORMULA_VERSION,
        input_summary_json=_input_summary(
            valuation=valuation,
            liquidity_assessment=liquidity_assessment,
            fast_sale_estimate=fast_sale_estimate,
            risk_assessment=risk_assessment,
            cost_profile=cost_profile,
            investment_profile=investment_profile,
            asking_price=asking_price,
        ),
        explanation_json={
            "status": DealAnalysisStatus.INSUFFICIENT_DATA.value,
            "formula_version": DEAL_FORMULA_VERSION,
            "reason": reason,
        },
    )
    session.add(deal_analysis)
    session.flush()
    return deal_analysis


def _missing_input_reason(
    *,
    cost_profile: CostProfile | None,
    investment_profile: InvestmentProfile | None,
    valuation: Valuation | None,
    fast_sale_estimate: FastSaleEstimate | None,
    purchase_price: Decimal | None,
    renovation_cost: Decimal | None,
    holding_days: int | None,
) -> str | None:
    if cost_profile is None:
        return "MISSING_COST_PROFILE"
    if investment_profile is None:
        return "MISSING_INVESTMENT_PROFILE"
    if not _has_successful_valuation(valuation):
        return "MISSING_SUCCESSFUL_VALUATION"
    if not _has_successful_fast_sale(fast_sale_estimate):
        return "MISSING_SUCCESSFUL_FAST_SALE"
    if valuation is not None and valuation.currency != cost_profile.currency:
        return "CURRENCY_MISMATCH"
    if purchase_price is None:
        return "MISSING_PURCHASE_PRICE"
    if renovation_cost is None:
        return "MISSING_RENOVATION_COST"
    if holding_days is None:
        return "MISSING_HOLDING_DAYS"
    return None


def _input_summary(
    *,
    valuation: Valuation | None,
    liquidity_assessment: LiquidityAssessment | None,
    fast_sale_estimate: FastSaleEstimate | None,
    risk_assessment: RiskAssessment | None,
    cost_profile: CostProfile | None,
    investment_profile: InvestmentProfile | None,
    asking_price: Decimal | None,
) -> dict[str, object]:
    return {
        "valuation_id": str(valuation.id) if valuation is not None else None,
        "valuation_status": valuation.status.value if valuation is not None else None,
        "valuation_model_version": valuation.model_version if valuation is not None else None,
        "liquidity_assessment_id": (
            str(liquidity_assessment.id) if liquidity_assessment is not None else None
        ),
        "fast_sale_estimate_id": (
            str(fast_sale_estimate.id) if fast_sale_estimate is not None else None
        ),
        "fast_sale_status": (
            fast_sale_estimate.status.value if fast_sale_estimate is not None else None
        ),
        "risk_assessment_id": str(risk_assessment.id) if risk_assessment is not None else None,
        "risk_gate": (
            risk_assessment.hard_gate_status.value if risk_assessment is not None else None
        ),
        "cost_profile_id": str(cost_profile.id) if cost_profile is not None else None,
        "cost_profile_code": cost_profile.code if cost_profile is not None else None,
        "cost_profile_version": cost_profile.version if cost_profile is not None else None,
        "investment_profile_id": (
            str(investment_profile.id) if investment_profile is not None else None
        ),
        "investment_profile_version": (
            investment_profile.version if investment_profile is not None else None
        ),
        "asking_price": _decimal_to_string(asking_price),
        "formula_version": DEAL_FORMULA_VERSION,
    }


def _max_buy_constraints_json(investment_profile: InvestmentProfile) -> dict[str, object]:
    return {
        "required_profit": _decimal_to_string(_required_profit(investment_profile)),
        "min_expected_profit": _decimal_to_string(investment_profile.min_expected_profit),
        "min_downside_profit": _decimal_to_string(investment_profile.min_downside_profit),
        "min_roi": _decimal_to_string(investment_profile.min_roi),
    }


def _cost_breakdown_json(costs: CostBreakdown) -> dict[str, object]:
    return {
        "purchase_costs": _decimal_to_string(costs.purchase_costs),
        "renovation_cost": _decimal_to_string(costs.renovation_cost),
        "sale_costs": _decimal_to_string(costs.sale_costs),
        "taxes": _decimal_to_string(costs.taxes),
        "financing_costs": _decimal_to_string(costs.financing_costs),
        "holding_costs": _decimal_to_string(costs.holding_costs),
        "risk_reserve": _decimal_to_string(costs.risk_reserve),
        "other_costs": _decimal_to_string(costs.other_costs),
        "total_cost_basis": _decimal_to_string(costs.total_cost_basis),
        "net_sale_proceeds": _decimal_to_string(costs.net_sale_proceeds),
    }


def _rule_amount(
    rule: dict[str, object],
    *,
    purchase_price: Decimal,
    exit_price: Decimal,
    holding_days: int,
    field_name: str,
) -> Decimal:
    if not isinstance(rule, dict):
        raise ValueError(f"{field_name} must be an object")
    allowed_keys = {"fixed_amount", "purchase_price_pct", "exit_price_pct", "per_day_amount"}
    unknown_keys = set(rule) - allowed_keys
    if unknown_keys:
        unknown = ", ".join(sorted(unknown_keys))
        raise ValueError(f"{field_name} has unsupported keys: {unknown}")

    fixed_amount = _rule_decimal(rule.get("fixed_amount"), field_name, "fixed_amount")
    purchase_price_pct = _rule_decimal(
        rule.get("purchase_price_pct"),
        field_name,
        "purchase_price_pct",
    )
    exit_price_pct = _rule_decimal(rule.get("exit_price_pct"), field_name, "exit_price_pct")
    per_day_amount = _rule_decimal(rule.get("per_day_amount"), field_name, "per_day_amount")

    amount = (
        fixed_amount
        + (purchase_price * purchase_price_pct / Decimal("100"))
        + (exit_price * exit_price_pct / Decimal("100"))
        + (per_day_amount * Decimal(holding_days))
    )
    return _money(amount)


def _rule_decimal(value: object, field_name: str, key: str) -> Decimal:
    if value is None:
        return Decimal("0")
    parsed = _parse_decimal(value, f"{field_name}.{key}")
    if parsed < 0:
        raise ValueError(f"{field_name}.{key} must be non-negative")
    return parsed


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


def _latest_successful_fast_sale(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> FastSaleEstimate | None:
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


def _latest_risk_assessment(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> RiskAssessment | None:
    return session.scalars(
        select(RiskAssessment)
        .where(
            RiskAssessment.property_id == property_.id,
            RiskAssessment.as_of <= as_of,
        )
        .order_by(RiskAssessment.as_of.desc(), RiskAssessment.created_at.desc())
    ).first()


def _active_cost_profile(session: Session) -> CostProfile | None:
    return session.scalars(
        select(CostProfile)
        .where(CostProfile.is_active.is_(True))
        .order_by(CostProfile.created_at.desc(), CostProfile.id.desc())
    ).first()


def _default_investment_profile(session: Session) -> InvestmentProfile | None:
    return session.scalars(
        select(InvestmentProfile)
        .where(InvestmentProfile.is_default.is_(True))
        .order_by(InvestmentProfile.created_at.desc(), InvestmentProfile.id.desc())
    ).first()


def _current_asking_price(session: Session, property_: Property, as_of: datetime) -> Decimal | None:
    return session.scalars(
        select(Listing.asking_price)
        .where(
            Listing.property_id == property_.id,
            Listing.status == ListingStatus.ACTIVE,
            Listing.currency == CurrencyCode.EUR,
            Listing.asking_price.is_not(None),
            Listing.asking_price > 0,
            Listing.first_seen_at <= as_of,
            Listing.last_seen_at <= as_of,
        )
        .order_by(Listing.asking_price.asc())
    ).first()


def _has_successful_valuation(valuation: Valuation | None) -> bool:
    return (
        valuation is not None
        and valuation.status == ValuationStatus.SUCCESS
        and valuation.fair_value_base is not None
        and valuation.fair_value_base > 0
    )


def _has_successful_fast_sale(fast_sale_estimate: FastSaleEstimate | None) -> bool:
    return (
        fast_sale_estimate is not None
        and fast_sale_estimate.status == FastSaleStatus.SUCCESS
        and fast_sale_estimate.value_low is not None
        and fast_sale_estimate.value_low > 0
        and fast_sale_estimate.value_base is not None
        and fast_sale_estimate.value_base > 0
        and fast_sale_estimate.value_high is not None
        and fast_sale_estimate.value_high > 0
    )


def _validate_successful_fast_sale(fast_sale_estimate: FastSaleEstimate) -> None:
    if not _has_successful_fast_sale(fast_sale_estimate):
        raise ValueError("fast_sale_estimate must have successful low/base/high values")


def _scenario_by_type(
    scenarios: list[ScenarioCalculation],
    scenario_type: DealScenarioType,
) -> ScenarioCalculation:
    return next(scenario for scenario in scenarios if scenario.scenario_type == scenario_type)


def _required_profit(investment_profile: InvestmentProfile) -> Decimal:
    values = [
        value
        for value in (
            investment_profile.min_expected_profit,
            investment_profile.min_downside_profit,
        )
        if value is not None
    ]
    if not values:
        return Decimal("0.00")
    return _money(max(values))


def _scaled_holding_days(base_days: int, multiplier: Decimal) -> int:
    if base_days < 0:
        raise ValueError("expected_holding_days must be non-negative")
    return int((Decimal(base_days) * multiplier).to_integral_value(rounding=ROUND_HALF_UP))


def _analysis_as_of(
    as_of: datetime | None,
    fast_sale_estimate: FastSaleEstimate | None,
    valuation: Valuation | None,
) -> datetime:
    if as_of is not None:
        return _aware_datetime(as_of)
    if fast_sale_estimate is not None:
        return _aware_datetime(fast_sale_estimate.as_of)
    if valuation is not None:
        return _aware_datetime(valuation.as_of)
    return _utcnow()


def _validate_money(value: Decimal, field_name: str) -> Decimal:
    parsed = _parse_decimal(value, field_name)
    if parsed < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return _money(parsed)


def _required_money(value: Decimal | None, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{field_name} is required")
    return _validate_money(value, field_name)


def _validate_ratio(value: Decimal, field_name: str) -> Decimal:
    parsed = _parse_decimal(value, field_name)
    if parsed < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return _ratio(parsed)


def _parse_decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return parsed


def _money(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return value.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def _ratio(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.000000")
    return value.quantize(RATIO_QUANTIZER, rounding=ROUND_HALF_UP)


def _capital_days(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return value.quantize(CAPITAL_DAY_QUANTIZER, rounding=ROUND_HALF_UP)


def _profit_per_capital_day(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.0000000000")
    return value.quantize(PROFIT_PER_CAPITAL_DAY_QUANTIZER, rounding=ROUND_HALF_UP)


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
