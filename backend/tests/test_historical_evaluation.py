from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session
from test_opportunity_alerts import AS_OF, create_manual_deal_fixture

from app.db.models import (
    CallFeedback,
    DealAnalysis,
    HistoricalEvaluationItem,
    HistoricalEvaluationRun,
    Interaction,
    ListingEvent,
    OpportunityAssessment,
    PropertyListingLink,
    PropertyOutcome,
    PropertyOverride,
    ShadowDeal,
    ShadowDealOutcome,
)
from app.domain.enums import (
    AnalysisLevel,
    CurrencyCode,
    DataSourceKind,
    HistoricalEvaluationClassification,
    InteractionType,
    ListingEventType,
    MatchDecision,
    OpportunityAction,
    PropertyOutcomeType,
    ShadowOutcomeStatus,
)
from app.evaluation.historical import (
    HISTORICAL_EVALUATION_VERSION,
    build_historical_property_snapshot,
    create_shadow_deal,
    evaluate_shadow_deal_outcome,
    run_historical_evaluation,
)


def count_rows(session: Session, model: type[Any]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_phase16_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {
        "shadow_deals",
        "shadow_deal_outcomes",
        "historical_evaluation_runs",
        "historical_evaluation_items",
    }.issubset(set(inspector.get_table_names()))


def test_as_of_snapshot_excludes_future_price_text_manual_outcome_and_recommendation(
    db_session: Session,
) -> None:
    fixture = create_manual_deal_fixture(db_session)
    link_listing(db_session, fixture, linked_at=AS_OF - timedelta(days=10))
    old_opportunity = create_opportunity(
        db_session,
        fixture,
        action=OpportunityAction.CALL,
        as_of=AS_OF,
        state_hash="old-call",
    )
    future_opportunity = create_opportunity(
        db_session,
        fixture,
        action=OpportunityAction.URGENT_CALL,
        as_of=AS_OF + timedelta(days=1),
        score=Decimal("99.00"),
        state_hash="future-urgent",
    )

    fixture.listing.asking_price = Decimal("90000.00")
    fixture.listing.description = "Future seller text with stronger urgency."
    db_session.add_all(
        [
            ListingEvent(
                listing=fixture.listing,
                event_type=ListingEventType.PRICE_CHANGED,
                detected_at=AS_OF + timedelta(days=1),
                old_value_json={"asking_price": "100000.00"},
                new_value_json={"asking_price": "90000.00"},
                old_price=Decimal("100000.00"),
                new_price=Decimal("90000.00"),
            ),
            ListingEvent(
                listing=fixture.listing,
                event_type=ListingEventType.DESCRIPTION_CHANGED,
                detected_at=AS_OF + timedelta(days=1),
                old_value_json={
                    "description": "Owner can agree quickly with a serious cash buyer."
                },
                new_value_json={"description": "Future seller text with stronger urgency."},
            ),
            Interaction(
                property=fixture.property,
                interaction_type=InteractionType.CALL,
                occurred_at=AS_OF + timedelta(days=1),
                notes="Future manual call.",
            ),
            PropertyOverride(
                property=fixture.property,
                field_name="manual_max_buy_price",
                value_json={"value": "88000.00"},
                source_kind=DataSourceKind.MANUAL,
                reason="future_override",
                created_at=AS_OF + timedelta(days=1),
            ),
            PropertyOutcome(
                property=fixture.property,
                outcome_type=PropertyOutcomeType.BOUGHT_BY_USER,
                outcome_date=AS_OF + timedelta(days=7),
                sale_price=Decimal("97000.00"),
                currency=CurrencyCode.EUR,
                confidence=Decimal("100.00"),
                source_kind=DataSourceKind.MANUAL,
                created_at=AS_OF + timedelta(days=8),
            ),
        ]
    )
    db_session.flush()
    future_call = db_session.scalars(
        select(Interaction).where(Interaction.property_id == fixture.property.id)
    ).one()
    db_session.add(
        CallFeedback(
            interaction=future_call,
            seller_motivation=AnalysisLevel.HIGH,
            lowest_indicated_price=Decimal("90000.00"),
        )
    )
    db_session.flush()

    snapshot = build_historical_property_snapshot(db_session, fixture.property, as_of=AS_OF)

    listing_snapshot = snapshot["listings"][0]
    assert listing_snapshot["asking_price"] == "100000.00"
    assert listing_snapshot["description"] == "Owner can agree quickly with a serious cash buyer."
    assert snapshot["analysis"]["opportunity"]["id"] == str(old_opportunity.id)
    assert snapshot["analysis"]["opportunity"]["id"] != str(future_opportunity.id)
    assert snapshot["manual_inputs"]["interactions"] == []
    assert snapshot["manual_inputs"]["overrides"] == []
    assert snapshot["outcomes_known_as_of"] == []


def test_create_shadow_deal_persists_immutable_assumptions_snapshot_and_versions(
    db_session: Session,
) -> None:
    fixture = create_manual_deal_fixture(db_session)
    link_listing(db_session, fixture, linked_at=AS_OF - timedelta(days=10))
    opportunity = create_opportunity(
        db_session,
        fixture,
        action=OpportunityAction.CALL,
        as_of=AS_OF,
        state_hash="shadow-call",
    )

    shadow_deal = create_shadow_deal(
        db_session,
        fixture.property,
        opportunity_assessment=opportunity,
        simulated_buy_date=AS_OF + timedelta(minutes=5),
        simulated_buy_price=Decimal("95000.00"),
        assumed_total_cost_basis=Decimal("99000.00"),
        expected_exit_price=Decimal("125000.00"),
        expected_holding_days=90,
        notes="Paper trade.",
    )
    original_snapshot = shadow_deal.input_snapshot_json
    original_versions = shadow_deal.model_versions_json

    fixture.listing.asking_price = Decimal("88000.00")
    fixture.investment_profile.desired_profit = Decimal("50000.00")
    fixture.deal.expected_profit = Decimal("1.00")
    create_opportunity(
        db_session,
        fixture,
        action=OpportunityAction.URGENT_CALL,
        as_of=AS_OF + timedelta(days=1),
        score=Decimal("99.00"),
        state_hash="future-shadow",
    )
    db_session.flush()
    db_session.expire_all()

    saved_shadow = db_session.get(ShadowDeal, shadow_deal.id)
    assert saved_shadow is not None
    assert saved_shadow.simulated_buy_price == Decimal("95000.00")
    assert saved_shadow.assumed_total_cost_basis == Decimal("99000.00")
    assert saved_shadow.expected_profit == Decimal("26000.00")
    assert saved_shadow.input_snapshot_json == original_snapshot
    assert saved_shadow.model_versions_json == original_versions
    assert saved_shadow.model_versions_json["deal_formula"] == "deal_formula_v1"
    assert saved_shadow.model_versions_json["opportunity_rules"] == "opportunity_rules_v1"


def test_create_shadow_deal_rejects_future_opportunity_input(db_session: Session) -> None:
    fixture = create_manual_deal_fixture(db_session)
    future_opportunity = create_opportunity(
        db_session,
        fixture,
        action=OpportunityAction.CALL,
        as_of=AS_OF + timedelta(days=1),
        state_hash="future-input",
    )

    with pytest.raises(ValueError, match="opportunity_assessment.as_of"):
        create_shadow_deal(
            db_session,
            fixture.property,
            opportunity_assessment=future_opportunity,
            simulated_buy_date=AS_OF,
            simulated_buy_price=Decimal("95000.00"),
        )


def test_shadow_outcome_measurement_uses_frozen_inputs(db_session: Session) -> None:
    fixture = create_manual_deal_fixture(db_session)
    link_listing(db_session, fixture, linked_at=AS_OF - timedelta(days=10))
    opportunity = create_opportunity(
        db_session,
        fixture,
        action=OpportunityAction.CALL,
        as_of=AS_OF,
        state_hash="shadow-outcome",
    )
    shadow_deal = create_shadow_deal(
        db_session,
        fixture.property,
        opportunity_assessment=opportunity,
        simulated_buy_date=AS_OF,
        simulated_buy_price=Decimal("95000.00"),
        assumed_total_cost_basis=Decimal("99000.00"),
        expected_exit_price=Decimal("125000.00"),
    )
    outcome = PropertyOutcome(
        property=fixture.property,
        outcome_type=PropertyOutcomeType.BOUGHT_BY_USER,
        outcome_date=AS_OF + timedelta(days=10),
        sale_price=Decimal("125000.00"),
        currency=CurrencyCode.EUR,
        confidence=Decimal("100.00"),
        source_kind=DataSourceKind.MANUAL,
        created_at=AS_OF + timedelta(days=11),
    )
    db_session.add(outcome)
    db_session.flush()

    measurement = evaluate_shadow_deal_outcome(
        db_session,
        shadow_deal,
        evaluation_as_of=AS_OF + timedelta(days=12),
    )

    assert measurement.outcome_status == ShadowOutcomeStatus.MEASURED
    assert measurement.property_outcome_id == outcome.id
    assert measurement.simulated_profit == Decimal("26000.00")
    assert measurement.simulated_roi == Decimal("0.262626")
    assert (
        measurement.outcome_summary_json["original_expected"]["expected_exit_price"] == "125000.00"
    )
    assert count_rows(db_session, ShadowDealOutcome) == 1


def test_shadow_outcome_rejects_outcome_not_known_by_cutoff(db_session: Session) -> None:
    fixture = create_manual_deal_fixture(db_session)
    opportunity = create_opportunity(
        db_session,
        fixture,
        action=OpportunityAction.CALL,
        as_of=AS_OF,
        state_hash="shadow-reject",
    )
    shadow_deal = create_shadow_deal(
        db_session,
        fixture.property,
        opportunity_assessment=opportunity,
        simulated_buy_date=AS_OF,
        simulated_buy_price=Decimal("95000.00"),
    )
    future_outcome = PropertyOutcome(
        property=fixture.property,
        outcome_type=PropertyOutcomeType.BOUGHT_BY_USER,
        outcome_date=AS_OF + timedelta(days=10),
        sale_price=Decimal("125000.00"),
        currency=CurrencyCode.EUR,
        confidence=Decimal("100.00"),
        source_kind=DataSourceKind.MANUAL,
        created_at=AS_OF + timedelta(days=11),
    )
    db_session.add(future_outcome)
    db_session.flush()

    with pytest.raises(ValueError, match="not known"):
        evaluate_shadow_deal_outcome(
            db_session,
            shadow_deal,
            evaluation_as_of=AS_OF + timedelta(days=5),
            property_outcome=future_outcome,
        )


def test_historical_evaluation_uses_prediction_as_of_and_later_outcomes_for_measurement(
    db_session: Session,
) -> None:
    fixture = create_manual_deal_fixture(db_session)
    link_listing(db_session, fixture, linked_at=AS_OF - timedelta(days=10))
    old_opportunity = create_opportunity(
        db_session,
        fixture,
        action=OpportunityAction.CALL,
        as_of=AS_OF,
        state_hash="old-backtest-call",
    )
    future_opportunity = create_opportunity(
        db_session,
        fixture,
        action=OpportunityAction.URGENT_CALL,
        as_of=AS_OF + timedelta(days=1),
        score=Decimal("99.00"),
        state_hash="future-backtest-urgent",
    )
    outcome = PropertyOutcome(
        property=fixture.property,
        outcome_type=PropertyOutcomeType.BOUGHT_BY_USER,
        outcome_date=AS_OF + timedelta(days=7),
        sale_price=Decimal("97000.00"),
        currency=CurrencyCode.EUR,
        confidence=Decimal("100.00"),
        source_kind=DataSourceKind.MANUAL,
        created_at=AS_OF + timedelta(days=8),
    )
    db_session.add(outcome)
    db_session.flush()

    run = run_historical_evaluation(
        db_session,
        prediction_as_of=AS_OF,
        evaluation_as_of=AS_OF + timedelta(days=10),
    )

    assert run.evaluation_version == HISTORICAL_EVALUATION_VERSION
    assert count_rows(db_session, OpportunityAssessment) == 2
    assert count_rows(db_session, DealAnalysis) == 1
    assert len(run.items) == 1
    item = run.items[0]
    assert item.opportunity_assessment_id == old_opportunity.id
    assert item.opportunity_assessment_id != future_opportunity.id
    assert item.property_outcome_id == outcome.id
    assert item.classification == HistoricalEvaluationClassification.TRUE_POSITIVE
    assert item.snapshot_json["analysis"]["opportunity"]["id"] == str(old_opportunity.id)
    assert item.snapshot_json["outcomes_known_as_of"] == []
    assert item.explanation_json["outcome_measurement"]["id"] == str(outcome.id)
    assert run.metrics_json["true_positive"] == 1
    assert run.metrics_json["alert_precision"] == "1.000000"


def test_historical_evaluation_does_not_use_outcomes_after_evaluation_cutoff(
    db_session: Session,
) -> None:
    fixture = create_manual_deal_fixture(db_session)
    create_opportunity(
        db_session,
        fixture,
        action=OpportunityAction.CALL,
        as_of=AS_OF,
        state_hash="outcome-after-cutoff",
    )
    db_session.add(
        PropertyOutcome(
            property=fixture.property,
            outcome_type=PropertyOutcomeType.BOUGHT_BY_USER,
            outcome_date=AS_OF + timedelta(days=12),
            sale_price=Decimal("97000.00"),
            currency=CurrencyCode.EUR,
            confidence=Decimal("100.00"),
            source_kind=DataSourceKind.MANUAL,
            created_at=AS_OF + timedelta(days=13),
        )
    )
    db_session.flush()

    run = run_historical_evaluation(
        db_session,
        prediction_as_of=AS_OF,
        evaluation_as_of=AS_OF + timedelta(days=10),
    )

    assert count_rows(db_session, HistoricalEvaluationRun) == 1
    assert count_rows(db_session, HistoricalEvaluationItem) == 1
    item = run.items[0]
    assert item.property_outcome_id is None
    assert item.classification == HistoricalEvaluationClassification.UNKNOWN
    assert run.metrics_json["unknown"] == 1


def link_listing(db_session: Session, fixture: Any, *, linked_at: datetime) -> PropertyListingLink:
    link = PropertyListingLink(
        property=fixture.property,
        listing=fixture.listing,
        decision=MatchDecision.AUTO_MATCH,
        match_confidence=Decimal("0.9900"),
        matching_method="test",
        matching_version="deterministic_v1",
        created_at=linked_at,
    )
    db_session.add(link)
    db_session.flush()
    return link


def create_opportunity(
    db_session: Session,
    fixture: Any,
    *,
    action: OpportunityAction,
    as_of: datetime,
    score: Decimal = Decimal("70.00"),
    ranking_value: Decimal = Decimal("1000.0000"),
    state_hash: str,
) -> OpportunityAssessment:
    opportunity = OpportunityAssessment(
        property=fixture.property,
        deal_analysis=fixture.deal,
        as_of=as_of,
        recommended_action=action,
        opportunity_score=score,
        ranking_value=ranking_value,
        reason_codes_json=["TEST"],
        explanation_json={"source": "phase16-test", "state_hash": state_hash},
        rules_version="opportunity_rules_v1",
        state_hash=state_hash,
    )
    db_session.add(opportunity)
    db_session.flush()
    return opportunity
