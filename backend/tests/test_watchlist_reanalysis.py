from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session
from test_opportunity_alerts import (
    AS_OF,
    FakeTelegramSender,
    create_manual_deal_fixture,
)

from app.api.dependencies import get_db_session
from app.db.models import (
    Alert,
    DealAnalysis,
    LiquidityAssessment,
    Listing,
    ListingEvent,
    OpportunityAssessment,
    PropertyAnalysisState,
    RiskAssessment,
    SellerAssessment,
    Valuation,
    WatchRule,
    WatchTriggerEvent,
)
from app.domain.enums import (
    AnalysisStatus,
    ListingEventType,
    OpportunityAction,
    SellerType,
    WatchRuleType,
)
from app.main import create_app
from app.opportunities.opportunity_engine import assess_opportunity_and_alert
from app.watchlist.watchlist_service import (
    create_or_update_watch_rule,
    evaluate_watch_rules_for_listing_event,
)


@pytest.fixture
def dashboard_client(db_session: Session) -> Iterator[TestClient]:
    app = create_app()

    def override_db_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as client:
        yield client


def count_rows(session: Session, model: type[Any]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_phase12_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {
        "property_analysis_state",
        "watch_rules",
        "watch_trigger_events",
    }.issubset(set(inspector.get_table_names()))


def add_price_event(
    session: Session,
    listing: Listing,
    *,
    old_price: Decimal,
    new_price: Decimal,
    detected_at: datetime,
) -> ListingEvent:
    listing.asking_price = new_price
    listing.last_seen_at = detected_at
    event = ListingEvent(
        listing=listing,
        event_type=ListingEventType.PRICE_CHANGED,
        detected_at=detected_at,
        old_value_json={"asking_price": str(old_price)},
        new_value_json={"asking_price": str(new_price)},
        old_price=old_price,
        new_price=new_price,
    )
    session.add(event)
    session.flush()
    return event


def add_description_event(
    session: Session,
    listing: Listing,
    *,
    old_description: str,
    new_description: str,
) -> ListingEvent:
    detected_at = AS_OF + timedelta(minutes=5)
    listing.description = new_description
    listing.last_seen_at = detected_at
    event = ListingEvent(
        listing=listing,
        event_type=ListingEventType.DESCRIPTION_CHANGED,
        detected_at=detected_at,
        old_value_json={"description": old_description},
        new_value_json={"description": new_description},
    )
    session.add(event)
    session.flush()
    return event


def test_price_below_watch_triggers_once_and_reanalyzes_before_alert(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    fixture = create_manual_deal_fixture(
        db_session,
        asking_price=Decimal("155000.00"),
        required_negotiation_pct=Decimal("0.120000"),
        expected_profit=Decimal("8000.00"),
        downside_profit=Decimal("6000.00"),
        roi=Decimal("0.090000"),
    )
    initial_opportunity = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    ).assessment
    assert initial_opportunity.recommended_action == OpportunityAction.WATCH

    rule = create_or_update_watch_rule(
        db_session,
        fixture.property,
        rule_type=WatchRuleType.PRICE_BELOW,
        threshold_numeric=Decimal("142000.00"),
    )
    assert rule.is_active is True

    no_cross_event = add_price_event(
        db_session,
        fixture.listing,
        old_price=Decimal("155000.00"),
        new_price=Decimal("145000.00"),
        detected_at=AS_OF + timedelta(minutes=1),
    )
    no_cross_result = evaluate_watch_rules_for_listing_event(db_session, no_cross_event)

    assert [item.trigger_event for item in no_cross_result] == [None]
    state = db_session.get(PropertyAnalysisState, fixture.property.id)
    assert state is not None
    assert state.deal_status == AnalysisStatus.STALE
    assert state.opportunity_status == AnalysisStatus.STALE
    assert state.valuation_status == AnalysisStatus.SUCCESS
    assert state.liquidity_status == AnalysisStatus.SUCCESS
    assert count_rows(db_session, DealAnalysis) == 1
    assert count_rows(db_session, OpportunityAssessment) == 1

    sender = FakeTelegramSender()
    cross_event = add_price_event(
        db_session,
        fixture.listing,
        old_price=Decimal("145000.00"),
        new_price=Decimal("141000.00"),
        detected_at=AS_OF + timedelta(minutes=2),
    )
    cross_result = evaluate_watch_rules_for_listing_event(
        db_session,
        cross_event,
        sender=sender,
        app_base_url="http://radar.test",
    )

    triggered = [item.trigger_event for item in cross_result if item.trigger_event is not None]
    assert len(triggered) == 1
    trigger = triggered[0]
    assert trigger.summary_json["old_price"] == "145000.00"
    assert trigger.summary_json["new_price"] == "141000.00"
    assert trigger.summary_json["previous_action"] == "WATCH"
    assert trigger.summary_json["new_action"] == "CALL"
    assert trigger.invalidated_modules_json == ["deal", "opportunity"]
    assert trigger.reanalyzed_modules_json == ["deal", "opportunity"]

    latest_deal = db_session.scalars(
        select(DealAnalysis)
        .where(DealAnalysis.property_id == fixture.property.id)
        .order_by(DealAnalysis.as_of.desc(), DealAnalysis.created_at.desc())
    ).first()
    latest_opportunity = db_session.scalars(
        select(OpportunityAssessment)
        .where(OpportunityAssessment.property_id == fixture.property.id)
        .order_by(OpportunityAssessment.as_of.desc(), OpportunityAssessment.created_at.desc())
    ).first()
    assert latest_deal is not None
    assert latest_deal.id != fixture.deal.id
    assert latest_deal.asking_price == Decimal("141000.00")
    assert latest_opportunity is not None
    assert latest_opportunity.deal_analysis_id == latest_deal.id
    assert latest_opportunity.recommended_action == OpportunityAction.CALL
    assert sender.call_count == 1
    assert count_rows(db_session, Alert) == 1
    assert count_rows(db_session, DealAnalysis) == 2
    assert count_rows(db_session, OpportunityAssessment) == 2

    state = db_session.get(PropertyAnalysisState, fixture.property.id)
    assert state is not None
    assert state.deal_status == AnalysisStatus.SUCCESS
    assert state.opportunity_status == AnalysisStatus.SUCCESS
    assert state.valuation_status == AnalysisStatus.SUCCESS

    duplicate_sender = FakeTelegramSender()
    duplicate_result = evaluate_watch_rules_for_listing_event(
        db_session,
        cross_event,
        sender=duplicate_sender,
        app_base_url="http://radar.test",
    )

    assert [item.trigger_event for item in duplicate_result] == [None]
    assert duplicate_sender.call_count == 0
    assert count_rows(db_session, WatchTriggerEvent) == 1
    assert count_rows(db_session, Alert) == 1
    assert count_rows(db_session, DealAnalysis) == 2
    state = db_session.get(PropertyAnalysisState, fixture.property.id)
    assert state is not None
    assert state.deal_status == AnalysisStatus.SUCCESS
    assert state.opportunity_status == AnalysisStatus.SUCCESS

    detail_response = dashboard_client.get(f"/api/v1/properties/{fixture.property.id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["freshness"]["statuses"]["valuation"] == "SUCCESS"
    assert detail["freshness"]["statuses"]["deal"] == "SUCCESS"
    assert detail["watch"]["latest_changes"][0]["summary"]["new_action"] == "CALL"
    assert "Price changed" in detail["watch"]["latest_changes"][0]["summary"]["summary_text"]


def test_description_watch_reanalysis_preserves_valuation_and_stales_llm(
    db_session: Session,
) -> None:
    fixture = create_manual_deal_fixture(db_session)
    assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )
    create_or_update_watch_rule(
        db_session,
        fixture.property,
        rule_type=WatchRuleType.DESCRIPTION_CHANGE,
    )
    valuation_count = count_rows(db_session, Valuation)
    liquidity_count = count_rows(db_session, LiquidityAssessment)
    seller_count = count_rows(db_session, SellerAssessment)
    risk_count = count_rows(db_session, RiskAssessment)
    deal_count = count_rows(db_session, DealAnalysis)

    event = add_description_event(
        db_session,
        fixture.listing,
        old_description=fixture.listing.description or "",
        new_description="Owner needs a quick cash sale after moving abroad.",
    )
    result = evaluate_watch_rules_for_listing_event(db_session, event)

    assert any(item.trigger_event is not None for item in result)
    assert count_rows(db_session, Valuation) == valuation_count
    assert count_rows(db_session, LiquidityAssessment) == liquidity_count
    assert count_rows(db_session, SellerAssessment) == seller_count + 1
    assert count_rows(db_session, RiskAssessment) == risk_count + 1
    assert count_rows(db_session, DealAnalysis) == deal_count + 1
    state = db_session.get(PropertyAnalysisState, fixture.property.id)
    assert state is not None
    assert state.llm_status == AnalysisStatus.STALE
    assert state.seller_status == AnalysisStatus.SUCCESS
    assert state.risk_status == AnalysisStatus.SUCCESS
    assert state.deal_status == AnalysisStatus.SUCCESS
    assert state.opportunity_status == AnalysisStatus.SUCCESS
    assert state.valuation_status == AnalysisStatus.SUCCESS


def test_watch_api_watchlist_and_reanalysis_endpoint_contract(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    fixture = create_manual_deal_fixture(db_session)
    assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    watch_response = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/watch",
        json={"rule_type": "PRICE_BELOW", "threshold_numeric": "142000.00"},
    )

    assert watch_response.status_code == 201
    assert watch_response.json()["status"] == "WATCHED"
    assert watch_response.json()["watch_rule"]["rule_type"] == "PRICE_BELOW"
    assert count_rows(db_session, WatchRule) == 1

    watchlist_response = dashboard_client.get("/api/v1/watchlist")
    assert watchlist_response.status_code == 200
    watchlist_payload = watchlist_response.json()
    assert watchlist_payload["pagination"]["total"] == 1
    item = watchlist_payload["items"][0]
    assert item["property_id"] == str(fixture.property.id)
    assert item["watch_rule"]["threshold_numeric"] == "142000.0000"
    assert item["gap_to_max_buy"] is not None

    reanalysis_response = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/reanalyze"
    )

    assert reanalysis_response.status_code == 200
    assert reanalysis_response.json()["status"] == "QUEUED"
    state = db_session.get(PropertyAnalysisState, fixture.property.id)
    assert state is not None
    assert state.valuation_status == AnalysisStatus.PENDING
    assert state.deal_status == AnalysisStatus.PENDING
    assert count_rows(db_session, DealAnalysis) == 1
    assert count_rows(db_session, OpportunityAssessment) == 1

    unwatch_response = dashboard_client.delete(f"/api/v1/properties/{fixture.property.id}/watch")
    assert unwatch_response.status_code == 200
    assert unwatch_response.json()["status"] == "UNWATCHED"

    empty_watchlist = dashboard_client.get("/api/v1/watchlist")
    assert empty_watchlist.status_code == 200
    assert empty_watchlist.json()["pagination"]["total"] == 0


def test_seller_change_trigger_reanalyzes_downstream_modules(db_session: Session) -> None:
    fixture = create_manual_deal_fixture(db_session)
    assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )
    create_or_update_watch_rule(
        db_session,
        fixture.property,
        rule_type=WatchRuleType.SELLER_CHANGE,
    )
    detected_at = AS_OF + timedelta(minutes=6)
    fixture.listing.seller_type = SellerType.AGENCY
    fixture.listing.agency_name = "New Agency"
    fixture.listing.last_seen_at = detected_at
    event = ListingEvent(
        listing=fixture.listing,
        event_type=ListingEventType.SELLER_CHANGED,
        detected_at=detected_at,
        old_value_json={"seller_type": "OWNER", "seller_name": None, "agency_name": None},
        new_value_json={"seller_type": "AGENCY", "seller_name": None, "agency_name": "New Agency"},
    )
    db_session.add(event)
    db_session.flush()

    result = evaluate_watch_rules_for_listing_event(db_session, event)

    assert any(item.trigger_event is not None for item in result)
    trigger = db_session.scalars(select(WatchTriggerEvent)).one()
    assert trigger.summary_json["summary_text"] == "Seller changed"
    assert trigger.invalidated_modules_json == ["seller", "risk", "deal", "opportunity"]
    assert trigger.reanalyzed_modules_json == ["seller", "risk", "deal", "opportunity"]


@pytest.mark.parametrize(
    ("rule_type", "threshold", "old_price", "new_price", "expected_trigger"),
    [
        (
            WatchRuleType.ANY_PRICE_CHANGE,
            None,
            Decimal("155000.00"),
            Decimal("154000.00"),
            True,
        ),
        (
            WatchRuleType.PRICE_DROP_PERCENT,
            Decimal("0.050000"),
            Decimal("155000.00"),
            Decimal("149000.00"),
            False,
        ),
        (
            WatchRuleType.PRICE_DROP_PERCENT,
            Decimal("0.050000"),
            Decimal("155000.00"),
            Decimal("145000.00"),
            True,
        ),
    ],
)
def test_initial_price_watch_trigger_types(
    db_session: Session,
    rule_type: WatchRuleType,
    threshold: Decimal | None,
    old_price: Decimal,
    new_price: Decimal,
    expected_trigger: bool,
) -> None:
    fixture = create_manual_deal_fixture(db_session, asking_price=old_price)
    assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )
    create_or_update_watch_rule(
        db_session,
        fixture.property,
        rule_type=rule_type,
        threshold_numeric=threshold,
    )
    event = add_price_event(
        db_session,
        fixture.listing,
        old_price=old_price,
        new_price=new_price,
        detected_at=AS_OF + timedelta(minutes=10),
    )

    result = evaluate_watch_rules_for_listing_event(db_session, event)

    assert any(item.trigger_event is not None for item in result) is expected_trigger
