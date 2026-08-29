from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session
from test_opportunity_alerts import (
    AS_OF,
    create_listing,
    create_manual_deal_fixture,
    create_property,
    create_source,
)

from app.api.dependencies import get_db_session
from app.core.config import get_settings
from app.db.models import (
    ComparableItem,
    DealScenario,
    JobRun,
    ListingEvent,
    OpportunityAssessment,
    Property,
    PropertyFeature,
    RiskFlag,
    SourceRuntimeState,
)
from app.domain.enums import (
    ComparableType,
    DataSourceKind,
    DealScenarioType,
    ListingEventType,
    OpportunityAction,
    PropertyType,
    RiskGateEffect,
    RiskGateStatus,
    RiskSeverity,
    SourceHealthStatus,
)
from app.main import create_app


@pytest.fixture
def dashboard_client(db_session: Session) -> Iterator[TestClient]:
    app = create_app()

    def override_db_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as client:
        yield client


def create_feature(session: Session, property_: Property) -> PropertyFeature:
    feature = PropertyFeature(
        property=property_,
        price_per_m2=Decimal("1857.14"),
        listing_age_days=12,
        property_market_age_days=20,
        active_listing_count=1,
        known_listing_count=1,
        relist_count=0,
        current_lowest_asking_price=Decimal("130000.00"),
        current_highest_asking_price=Decimal("130000.00"),
        total_price_drop_pct=Decimal("0.0500"),
        price_drop_7d_pct=None,
        price_drop_30d_pct=Decimal("0.0500"),
        price_cut_count=1,
        days_since_last_price_cut=1,
        largest_price_cut_pct=Decimal("0.0500"),
        owner_listing_present=True,
        agency_listing_count=0,
        computed_at=AS_OF,
        feature_version=f"dashboard_test_{uuid.uuid4().hex[:8]}",
    )
    session.add(feature)
    session.flush()
    return feature


def create_opportunity(
    session: Session,
    fixture_property: Property,
    deal_id: uuid.UUID | None,
    *,
    action: OpportunityAction,
    ranking_value: Decimal | None = Decimal("24000.0000"),
) -> OpportunityAssessment:
    opportunity = OpportunityAssessment(
        property=fixture_property,
        deal_analysis_id=deal_id,
        as_of=AS_OF,
        recommended_action=action,
        opportunity_score=None if action == OpportunityAction.IGNORE else Decimal("82.00"),
        ranking_value=ranking_value,
        reason_codes_json=["ECONOMICS_PASS"] if action != OpportunityAction.IGNORE else ["NO_DEAL"],
        explanation_json={
            "summary": "Backend opportunity explanation for dashboard tests.",
            "frontend_must_not_calculate": True,
        },
        rules_version="dashboard_test_rules_v1",
        state_hash=f"dashboard-{uuid.uuid4().hex}",
    )
    session.add(opportunity)
    session.flush()
    return opportunity


def add_source_failure(session: Session, fixture_source_id: uuid.UUID) -> None:
    state = SourceRuntimeState(
        source_id=fixture_source_id,
        last_attempt_at=AS_OF,
        last_success_at=AS_OF - timedelta(days=1),
        last_discovery_success_at=AS_OF - timedelta(days=1),
        last_market_scan_success_at=None,
        last_error_at=AS_OF,
        last_error_type="HTTP_500",
        last_error_message="Source returned a server error.",
        recent_http_error_count=3,
        recent_parse_error_count=1,
        consecutive_zero_result_count=0,
        health_status=SourceHealthStatus.FAILED,
        last_discovered_count=0,
    )
    session.add(state)
    session.flush()


def test_action_queue_contract_excludes_ignore_and_reports_source_warnings(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    fixture = create_manual_deal_fixture(db_session)
    create_feature(db_session, fixture.property)
    create_feature(db_session, fixture.property)
    create_listing(
        db_session,
        fixture.listing.source,
        fixture.property,
        asking_price=Decimal("99000.00"),
        first_seen_at=AS_OF - timedelta(days=2),
    )
    create_opportunity(
        db_session,
        fixture.property,
        fixture.deal.id,
        action=OpportunityAction.CALL,
    )
    add_source_failure(db_session, fixture.listing.source_id)

    ignored = create_manual_deal_fixture(db_session)
    create_opportunity(
        db_session,
        ignored.property,
        ignored.deal.id,
        action=OpportunityAction.IGNORE,
        ranking_value=None,
    )

    response = dashboard_client.get("/api/v1/action-queue")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "HAS_OPPORTUNITIES"
    assert payload["summary"]["by_action"]["CALL"] == 1
    assert payload["pagination"]["total"] == 1
    assert len(payload["items"]) == 1

    item = payload["items"][0]
    assert item["property_id"] == str(fixture.property.id)
    assert item["recommended_action"] == "CALL"
    assert item["reason_codes"] == ["ECONOMICS_PASS"]
    assert item["asking_price"] == "100000.00"
    assert item["fair_value_base"] == "180000.00"
    assert item["fast_sale_base"] == "175000.00"
    assert item["max_buy_price"] == "95000.00000000"
    assert item["expected_profit"] == "24000.00"
    assert item["downside_profit"] == "7000.00"
    assert item["liquidity_score"] == "75.00"
    assert item["valuation_confidence"] == "75.00"
    assert item["risk_gate"] == "PASS"
    assert item["property_market_age_days"] == 20
    assert item["current_listing"]["url"].startswith("https://example.test/")
    assert payload["source_warnings"][0]["status"] == "FAILED"


def test_empty_action_queue_is_valid_not_error(dashboard_client: TestClient) -> None:
    response = dashboard_client.get("/api/v1/action-queue")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "NO_QUALIFYING_OPPORTUNITIES"
    assert payload["items"] == []
    assert payload["pagination"]["total"] == 0


def test_action_queue_request_does_not_query_once_per_row(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    for _ in range(3):
        fixture = create_manual_deal_fixture(db_session)
        create_opportunity(
            db_session,
            fixture.property,
            fixture.deal.id,
            action=OpportunityAction.REVIEW,
        )

    statements: list[str] = []

    def before_cursor_execute(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        _ = conn, cursor, parameters, context, executemany
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", before_cursor_execute)
    try:
        response = dashboard_client.get("/api/v1/action-queue")
    finally:
        event.remove(db_session.bind, "before_cursor_execute", before_cursor_execute)

    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 3
    assert len(statements) <= 4


def test_properties_list_preserves_unknown_nulls(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    create_property(
        db_session,
        property_type=PropertyType.APARTMENT,
        size_m2=None,
        rooms=None,
        elevator=None,
        city=None,
        municipality=None,
        neighborhood=None,
        micro_location=None,
    )

    response = dashboard_client.get("/api/v1/properties")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["size_m2"] is None
    assert item["rooms"] is None
    assert item["location"]["label"] is None
    assert item["recommended_action"] is None
    assert item["analysis_status"] == "NOT_RUN"


def test_property_detail_exposes_history_stale_block_and_analysis_sections(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    fixture = create_manual_deal_fixture(db_session, risk_gate=RiskGateStatus.BLOCK)
    create_feature(db_session, fixture.property)
    create_opportunity(
        db_session,
        fixture.property,
        fixture.deal.id,
        action=OpportunityAction.IGNORE,
        ranking_value=None,
    )
    db_session.add(
        RiskFlag(
            risk_assessment=fixture.risk,
            code="CRITICAL_DOCUMENTATION_UNKNOWN",
            severity=RiskSeverity.CRITICAL,
            gate_effect=RiskGateEffect.BLOCK,
            source_kind=DataSourceKind.SCRAPED,
            source_reference=fixture.listing.external_listing_id,
            confidence=Decimal("92.00"),
            description="Critical documentation status is unknown.",
            evidence_json={"listing_text": "documentation not stated"},
        )
    )
    db_session.add(
        ComparableItem(
            comparable_set=fixture.valuation.comparable_set,
            comparable_type=ComparableType.LISTING,
            listing=fixture.listing,
            property_id=fixture.property.id,
            similarity_score=Decimal("0.9100"),
            distance_m=Decimal("220.00"),
            age_days_at_analysis=8,
            price=Decimal("178000.00"),
            price_per_m2=Decimal("2542.86"),
            weight=Decimal("0.7000"),
            included_in_valuation=True,
        )
    )
    db_session.add_all(
        [
            DealScenario(
                deal_analysis=fixture.deal,
                scenario_type=DealScenarioType.BASE,
                purchase_price=Decimal("100000.00"),
                exit_price=Decimal("124000.00"),
                cost_basis=Decimal("100000.00"),
                profit=Decimal("24000.00"),
                roi=Decimal("0.120000"),
                holding_days=120,
                assumptions_json={"case": "base"},
            ),
            ListingEvent(
                listing=fixture.listing,
                event_type=ListingEventType.PRICE_CHANGED,
                detected_at=AS_OF + timedelta(hours=1),
                old_value_json={"asking_price": "130000.00"},
                new_value_json={"asking_price": "100000.00"},
                old_price=Decimal("130000.00"),
                new_price=Decimal("100000.00"),
            ),
        ]
    )
    db_session.flush()

    response = dashboard_client.get(f"/api/v1/properties/{fixture.property.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"]["risk_gate"] == "BLOCK"
    assert payload["decision"]["recommended_action"] == "IGNORE"
    assert payload["freshness"]["is_stale"] is True
    assert payload["freshness"]["statuses"]["valuation"] == "STALE"
    assert payload["deal"]["expected_profit"] == "24000.00"
    assert payload["deal"]["scenarios"][0]["scenario_type"] == "BASE"
    assert payload["valuation"]["confidence"] == "75.00"
    assert payload["liquidity"]["fast_sale"]["value_base"] == "175000.00"
    assert payload["seller"]["cash_preferred"] is True
    assert payload["risk"]["flags"][0]["gate_effect"] == "BLOCK"
    assert payload["comparables"]["items"][0]["comparable_type"] == "LISTING"
    assert payload["listings"][0]["url"] == fixture.listing.url
    assert {item["event_type"] for item in payload["history"]} >= {
        "DISCOVERED",
        "PRICE_CHANGED",
    }


def test_property_history_endpoint_returns_unified_timeline(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    fixture = create_manual_deal_fixture(db_session)
    db_session.add(
        ListingEvent(
            listing=fixture.listing,
            event_type=ListingEventType.SELLER_CHANGED,
            detected_at=AS_OF + timedelta(minutes=5),
            old_value_json={"seller_type": "AGENCY"},
            new_value_json={"seller_type": "OWNER"},
        )
    )
    db_session.flush()

    response = dashboard_client.get(f"/api/v1/properties/{fixture.property.id}/history")

    assert response.status_code == 200
    events = response.json()["items"]
    assert events[0]["event_type"] == "SELLER_CHANGED"
    assert events[0]["source_code"].startswith("phase10_")
    assert any(item["event_type"] == "DISCOVERED" for item in events)


def test_sources_endpoint_reports_health_without_blocking_dashboard(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    source = create_source(db_session, "source_health")
    add_source_failure(db_session, source.id)
    db_session.add(
        JobRun(
            source=source,
            job_type="crawl_source",
            started_at=AS_OF - timedelta(minutes=10),
            finished_at=AS_OF - timedelta(minutes=9),
            status="FAILED",
            items_discovered=0,
            items_processed=0,
            items_changed=0,
            items_failed=1,
            pages_requested=2,
            cards_seen=0,
            cards_parsed=0,
            new_listings=0,
            changed_listings=0,
            not_seen_count=0,
            details_fetched=0,
            parse_errors=1,
            http_errors=3,
            error_summary="HTTP failures",
        )
    )
    db_session.add(
        JobRun(
            source=source,
            job_type="crawl_source",
            started_at=AS_OF - timedelta(hours=1),
            finished_at=AS_OF - timedelta(minutes=59),
            status="SUCCESS",
            items_discovered=5,
            items_processed=5,
            items_changed=0,
            items_failed=0,
            pages_requested=1,
            cards_seen=5,
            cards_parsed=5,
            new_listings=0,
            changed_listings=0,
            not_seen_count=0,
            details_fetched=0,
            parse_errors=0,
            http_errors=0,
        )
    )
    db_session.flush()

    response = dashboard_client.get("/api/v1/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["FAILED"] == 1
    source_item = next(item for item in payload["items"] if item["code"] == source.code)
    assert [item["code"] for item in payload["items"]].count(source.code) == 1
    assert source_item["health_status"] == "FAILED"
    assert source_item["latest_job"]["status"] == "FAILED"
    assert payload["source_warnings"][0]["last_error_type"] == "HTTP_500"


def test_settings_endpoint_hides_secret_values(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    _ = db_session

    response = dashboard_client.get("/api/v1/settings")

    assert response.status_code == 200
    payload = response.json()
    encoded = json.dumps(payload)
    assert "TELEGRAM_BOT_TOKEN" not in encoded
    assert "TELEGRAM_CHAT_ID" not in encoded
    assert "API_ACCESS_TOKEN" not in encoded
    assert "api_access_token" not in encoded
    assert payload["app"]["environment"] == "test"
    assert "telegram_configured" in payload["notifications"]


def test_private_api_rejects_unauthenticated_when_token_is_configured(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_ACCESS_TOKEN", "phase11-secret")
    get_settings.cache_clear()
    app = create_app()

    def override_db_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as client:
        unauthenticated = client.get("/api/v1/action-queue")
        authenticated = client.get(
            "/api/v1/action-queue",
            headers={"Authorization": "Bearer phase11-secret"},
        )

    get_settings.cache_clear()
    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200


def test_production_private_api_fails_closed_without_token(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_ACCESS_TOKEN", "")
    get_settings.cache_clear()
    app = create_app()

    def override_db_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as client:
        response = client.get("/api/v1/action-queue")

    get_settings.cache_clear()
    assert response.status_code == 503
