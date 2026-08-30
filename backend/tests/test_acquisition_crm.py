from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
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

from app.acquisition.acquisition_service import skip_property
from app.api.dependencies import get_db_session
from app.db.models import (
    CallFeedback,
    DealAnalysis,
    Interaction,
    LlmAnalysis,
    Offer,
    OpportunityAssessment,
    PipelineStatusEvent,
    PropertyAnalysisState,
    PropertyOutcome,
    PropertyOverride,
    PropertyReview,
    RiskFlag,
    SellerAssessment,
    SkipRecord,
    Valuation,
    VisitFeedback,
)
from app.domain.enums import (
    AnalysisLevel,
    AnalysisStatus,
    DataSourceKind,
    LlmAnalysisStatus,
    OpportunityAction,
    PropertyPipelineStatus,
    ReasonForSale,
    SkipReasonCode,
)
from app.intelligence.seller_risk import assess_seller_intelligence_and_risk
from app.main import create_app
from app.opportunities.opportunity_engine import assess_opportunity_and_alert


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


def test_phase13_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {
        "property_reviews",
        "interactions",
        "call_feedback",
        "visit_feedback",
        "offers",
        "skip_records",
        "property_outcomes",
        "property_overrides",
        "pipeline_status_events",
    }.issubset(set(inspector.get_table_names()))


def test_candidate_can_move_from_alert_to_review_call_visit_offer_and_outcome(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    fixture = create_manual_deal_fixture(db_session)
    sender = FakeTelegramSender()
    alert_result = assess_opportunity_and_alert(
        db_session,
        fixture.property,
        deal_analysis=fixture.deal,
        seller_assessment=fixture.seller,
        sender=sender,
        app_base_url="http://radar.test",
        as_of=AS_OF,
    )

    assert alert_result.assessment.recommended_action in {
        OpportunityAction.CALL,
        OpportunityAction.URGENT_CALL,
    }
    assert sender.call_count == 1

    review_response = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/review",
        json={
            "reviewed_at": (AS_OF + timedelta(minutes=1)).isoformat(),
            "decision": "INTERESTING",
            "manual_max_buy_price": "98000.00",
            "notes": "Worth calling.",
        },
    )
    assert review_response.status_code == 201
    assert review_response.json()["pipeline_status"] == "REVIEWED"
    assert review_response.json()["invalidated_modules"] == [
        "valuation",
        "fast_sale",
        "deal",
        "opportunity",
    ]

    call_response = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/interactions/call",
        json={
            "occurred_at": (AS_OF + timedelta(minutes=2)).isoformat(),
            "seller_motivation": "LOW",
            "reason_for_sale": "OTHER",
            "lowest_indicated_price": "118000.00",
            "cash_preferred": False,
            "desired_closing_days": 45,
            "viewing_available": True,
            "claimed_registered": False,
            "tenant_present": None,
            "follow_up_at": (AS_OF + timedelta(days=1)).isoformat(),
            "follow_up_notes": "Send financing proof.",
            "notes": "Seller was firm on price.",
        },
    )
    assert call_response.status_code == 201
    assert call_response.json()["pipeline_status"] == "CALLED"
    assert call_response.json()["reanalyzed_modules"] == [
        "seller",
        "risk",
        "deal",
        "opportunity",
    ]

    visit_response = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/interactions/visit",
        json={
            "occurred_at": (AS_OF + timedelta(minutes=3)).isoformat(),
            "condition_category": "FULL",
            "estimated_renovation_low": "18000.00",
            "estimated_renovation_base": "25000.00",
            "estimated_renovation_high": "32000.00",
            "layout_score": 3,
            "light_score": 4,
            "noise_score": 2,
            "building_score": 3,
            "entrance_score": 2,
            "parking_score": 3,
            "elevator_verified": False,
            "visible_defects": ["moisture near bathroom"],
            "manual_fmv": "168000.00",
            "manual_fast_sale_value": "152000.00",
            "notes": "Needs full renovation.",
        },
    )
    assert visit_response.status_code == 201
    assert visit_response.json()["pipeline_status"] == "VISITED"
    assert visit_response.json()["record"]["visit_feedback"]["elevator_verified"] is False
    assert {"valuation", "seller", "risk", "deal", "opportunity"}.issubset(
        set(visit_response.json()["invalidated_modules"])
    )

    offer_response = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/offers",
        json={
            "offered_at": (AS_OF + timedelta(minutes=4)).isoformat(),
            "amount": "112000.00",
            "currency": "EUR",
            "conditions": {"cash": True, "closing_days": 14},
            "status": "OPEN",
            "notes": "Initial cash offer.",
        },
    )
    assert offer_response.status_code == 201
    offer_id = offer_response.json()["record"]["offer_id"]
    assert offer_response.json()["pipeline_status"] == "OFFERED"

    counter_response = dashboard_client.patch(
        f"/api/v1/offers/{offer_id}",
        json={
            "status": "COUNTERED",
            "seller_response_at": (AS_OF + timedelta(minutes=5)).isoformat(),
            "counteroffer_amount": "125000.00",
            "notes": "Seller countered.",
        },
    )
    assert counter_response.status_code == 200
    assert counter_response.json()["pipeline_status"] == "NEGOTIATING"

    outcome_response = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/outcomes",
        json={
            "outcome_date": (AS_OF + timedelta(minutes=6)).isoformat(),
            "outcome_type": "BOUGHT_BY_USER",
            "sale_price": "120000.00",
            "currency": "EUR",
            "confidence": "100.00",
            "notes": "Accepted after negotiation.",
        },
    )
    assert outcome_response.status_code == 201
    assert outcome_response.json()["pipeline_status"] == "WON"

    detail_response = dashboard_client.get(f"/api/v1/properties/{fixture.property.id}")
    assert detail_response.status_code == 200
    acquisition = detail_response.json()["acquisition"]
    assert acquisition["pipeline_status"] == "WON"
    assert acquisition["reviews"][0]["decision"] == "INTERESTING"
    assert acquisition["interactions"][0]["interaction_type"] == "VISIT"
    assert acquisition["offers"][0]["status"] == "COUNTERED"
    assert acquisition["outcomes"][0]["outcome_type"] == "BOUGHT_BY_USER"
    assert any(item["type"] == "PIPELINE_STATUS" for item in acquisition["timeline"])

    pipeline_response = dashboard_client.get("/api/v1/pipeline?pipeline_status=WON")
    assert pipeline_response.status_code == 200
    pipeline_payload = pipeline_response.json()
    assert pipeline_payload["pagination"]["total"] == 1
    assert pipeline_payload["items"][0]["property_id"] == str(fixture.property.id)


def test_manual_call_feedback_takes_precedence_and_survives_automatic_reanalysis(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    fixture = create_manual_deal_fixture(db_session, seller_level=AnalysisLevel.HIGH)
    db_session.add(
        LlmAnalysis(
            listing=fixture.listing,
            property=fixture.property,
            input_hash="phase13-manual-precedence",
            provider="fake",
            model="fake-model",
            prompt_version="seller_risk_prompt_v1",
            status=LlmAnalysisStatus.SUCCESS,
            seller_motivation_level=AnalysisLevel.HIGH,
            seller_motivation_confidence=Decimal("92.00"),
            cash_preferred=True,
            cash_preference_confidence=Decimal("85.00"),
            negotiability_level=AnalysisLevel.HIGH,
            negotiability_confidence=Decimal("88.00"),
            reason_for_sale=ReasonForSale.MOVING_ABROAD,
            reason_for_sale_confidence=Decimal("82.00"),
            condition_category="GOOD",
            condition_confidence=Decimal("70.00"),
            structured_output_json={"seller_motivation": {"level": "HIGH"}},
            evidence_json={"seller_motivation": [{"text": "urgent sale"}]},
            completed_at=AS_OF,
        )
    )
    db_session.flush()
    original_seller_count = count_rows(db_session, SellerAssessment)

    response = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/interactions/call",
        json={
            "occurred_at": (AS_OF + timedelta(minutes=7)).isoformat(),
            "seller_motivation": "LOW",
            "reason_for_sale": "OTHER",
            "lowest_indicated_price": "129000.00",
            "cash_preferred": False,
            "claimed_owner_1_1": False,
            "notes": "Seller said no urgency and ownership needs verification.",
        },
    )

    assert response.status_code == 201
    latest_seller = db_session.scalars(
        select(SellerAssessment)
        .where(SellerAssessment.property_id == fixture.property.id)
        .order_by(SellerAssessment.as_of.desc(), SellerAssessment.created_at.desc())
    ).first()
    assert latest_seller is not None
    assert latest_seller.seller_motivation_level == AnalysisLevel.LOW
    assert "seller_motivation" in latest_seller.evidence_json["manual_precedence_applied"]
    assert count_rows(db_session, SellerAssessment) == original_seller_count + 1

    risk_flags = db_session.scalars(
        select(RiskFlag)
        .join(RiskFlag.risk_assessment)
        .where(
            RiskFlag.source_kind == DataSourceKind.MANUAL,
            RiskFlag.source_reference == response.json()["record"]["interaction_id"],
        )
    ).all()
    assert any(flag.code == "PARTIAL_OWNERSHIP" for flag in risk_flags)

    assess_seller_intelligence_and_risk(
        db_session,
        fixture.property,
        as_of=AS_OF + timedelta(minutes=8),
    )
    latest_after_automatic = db_session.scalars(
        select(SellerAssessment)
        .where(SellerAssessment.property_id == fixture.property.id)
        .order_by(SellerAssessment.as_of.desc(), SellerAssessment.created_at.desc())
    ).first()
    assert latest_after_automatic is not None
    assert latest_after_automatic.seller_motivation_level == AnalysisLevel.LOW
    assert "seller_motivation" in latest_after_automatic.evidence_json["manual_precedence_applied"]


def test_visit_feedback_preserves_scraped_listing_and_records_verified_overrides(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    fixture = create_manual_deal_fixture(db_session)
    valuation_count = count_rows(db_session, Valuation)
    deal_count = count_rows(db_session, DealAnalysis)
    opportunity_count = count_rows(db_session, OpportunityAssessment)

    response = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/interactions/visit",
        json={
            "occurred_at": (AS_OF + timedelta(minutes=10)).isoformat(),
            "condition_category": "FULL",
            "estimated_renovation_base": "26000.00",
            "elevator_verified": False,
            "visible_defects": ["old electrical panel"],
            "manual_max_buy_price": "90000.00",
            "notes": "Verified on visit.",
        },
    )

    assert response.status_code == 201
    assert fixture.property.condition_category == "FULL"
    assert fixture.property.elevator is False
    assert fixture.listing.condition_raw == "GOOD"
    assert fixture.listing.elevator is True
    overrides = db_session.scalars(
        select(PropertyOverride).where(PropertyOverride.property_id == fixture.property.id)
    ).all()
    assert {override.field_name for override in overrides} >= {
        "condition_category",
        "elevator",
        "manual_max_buy_price",
    }
    assert {override.source_kind for override in overrides} == {DataSourceKind.VERIFIED_MANUAL}
    assert count_rows(db_session, Valuation) == valuation_count + 1
    assert count_rows(db_session, DealAnalysis) == deal_count + 1
    assert count_rows(db_session, OpportunityAssessment) == opportunity_count + 1
    state = db_session.get(PropertyAnalysisState, fixture.property.id)
    assert state is not None
    assert state.seller_status == AnalysisStatus.SUCCESS
    assert state.risk_status == AnalysisStatus.SUCCESS
    assert state.deal_status in {AnalysisStatus.SUCCESS, AnalysisStatus.INSUFFICIENT_DATA}
    assert state.opportunity_status == AnalysisStatus.SUCCESS


def test_skip_command_is_atomic_and_auditable(db_session: Session) -> None:
    fixture = create_manual_deal_fixture(db_session)

    result = skip_property(
        db_session,
        fixture.property,
        reason_code=SkipReasonCode.NO_MARGIN,
        notes="No downside margin after review.",
        skipped_at=AS_OF + timedelta(minutes=12),
        commit=False,
    )

    assert result.record.reason_code == SkipReasonCode.NO_MARGIN
    assert fixture.property.pipeline_status == PropertyPipelineStatus.SKIPPED
    assert result.pipeline_event is not None
    assert result.pipeline_event.source_reference == str(result.record.id)
    assert count_rows(db_session, SkipRecord) == 1
    assert count_rows(db_session, PipelineStatusEvent) == 1


def test_phase13_write_endpoint_validation_and_not_found(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    fixture = create_manual_deal_fixture(db_session)

    invalid_call = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/interactions/call",
        json={"seller_motivation": "VERY_HIGH"},
    )
    invalid_offer = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/offers",
        json={"amount": "-1.00", "currency": "EUR"},
    )
    invalid_visit = dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/interactions/visit",
        json={"occurred_at": "not-a-date"},
    )
    missing_property = dashboard_client.post(
        f"/api/v1/properties/{uuid.uuid4()}/review",
        json={"decision": "UNSURE"},
    )
    missing_offer = dashboard_client.patch(
        f"/api/v1/offers/{uuid.uuid4()}",
        json={"status": "REJECTED"},
    )

    assert invalid_call.status_code == 422
    assert invalid_offer.status_code == 422
    assert invalid_visit.status_code == 422
    assert missing_property.status_code == 404
    assert missing_offer.status_code == 404
    assert count_rows(db_session, CallFeedback) == 0
    assert count_rows(db_session, Offer) == 0
    assert count_rows(db_session, VisitFeedback) == 0
    assert fixture.property.pipeline_status == PropertyPipelineStatus.NEW


def test_phase13_persistence_counts_are_separate_history_tables(
    db_session: Session,
    dashboard_client: TestClient,
) -> None:
    fixture = create_manual_deal_fixture(db_session)

    dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/review",
        json={"decision": "UNSURE", "notes": "Need more data."},
    )
    dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/interactions/call",
        json={"notes": "No answer."},
    )
    dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/offers",
        json={"amount": "100000.00", "currency": "EUR"},
    )
    dashboard_client.post(
        f"/api/v1/properties/{fixture.property.id}/outcomes",
        json={"outcome_type": "LOST_TO_OTHER_BUYER"},
    )

    assert count_rows(db_session, PropertyReview) == 1
    assert count_rows(db_session, Interaction) == 1
    assert count_rows(db_session, Offer) == 1
    assert count_rows(db_session, PropertyOutcome) == 1
    assert count_rows(db_session, PipelineStatusEvent) >= 3
    assert count_rows(db_session, SellerAssessment) == 1
    assert count_rows(db_session, DealAnalysis) == 1
