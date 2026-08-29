from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import (
    Listing,
    ListingEvent,
    LlmAnalysis,
    Property,
    RiskAssessment,
    RiskFlag,
    SellerAssessment,
    Source,
)
from app.domain.enums import (
    AnalysisLevel,
    CurrencyCode,
    DataSourceKind,
    ListingEventType,
    ListingStatus,
    LlmAnalysisStatus,
    PropertyType,
    ReasonForSale,
    RiskGateEffect,
    RiskGateStatus,
    RiskSeverity,
    SellerType,
)
from app.intelligence.llm_analysis import LLMProviderError, analyze_listing_with_llm
from app.intelligence.seller_risk import (
    RISK_RULES_VERSION,
    SELLER_RULES_VERSION,
    ManualRiskInput,
    ManualSellerInput,
    assess_seller_intelligence_and_risk,
)

AS_OF = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


class FakeProvider:
    provider_name = "fake_provider"
    model_name = "fake-model-v1"

    def __init__(self, *outputs: dict[str, object] | Exception) -> None:
        self.outputs = list(outputs)
        self.call_count = 0

    def extract_structured_listing(
        self,
        input_payload: dict[str, object],
        *,
        prompt_version: str,
    ) -> dict[str, object]:
        _ = input_payload, prompt_version
        self.call_count += 1
        output = self.outputs[min(self.call_count - 1, len(self.outputs) - 1)]
        if isinstance(output, Exception):
            raise output
        return output


def structured_output(
    *,
    seller_motivation: str = "HIGH",
    negotiability: str = "MEDIUM",
    cash_preferred: bool | None = True,
    reason_for_sale: str = "MOVING_ABROAD",
    condition: str | None = "GOOD",
    legal_claims: list[dict[str, object]] | None = None,
    risk_signals: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "seller_motivation": {
            "level": seller_motivation,
            "confidence": "82.00",
            "evidence": [
                {"text": "Seller mentions a quick agreement.", "source_field": "description"}
            ],
        },
        "negotiability": {
            "level": negotiability,
            "confidence": "76.00",
            "evidence": [
                {"text": "Price is explicitly negotiable.", "source_field": "description"}
            ],
        },
        "cash_preference": {
            "value": cash_preferred,
            "confidence": "65.00",
            "evidence": [{"text": "Cash buyers are preferred.", "source_field": "description"}],
        },
        "reason_for_sale": {
            "value": reason_for_sale,
            "confidence": "70.00",
            "evidence": [{"text": "Owner is moving abroad.", "source_field": "description"}],
        },
        "condition": {
            "value": condition,
            "confidence": "68.00",
            "evidence": [
                {"text": "Apartment is described as maintained.", "source_field": "description"}
            ],
        },
        "legal_claims": legal_claims or [],
        "risk_signals": risk_signals or [],
    }


def create_source(session: Session, code: str = "phase8") -> Source:
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
    external_listing_id: str = "phase8-listing",
    description: str = "Owner is moving abroad and can quickly agree with a serious cash buyer.",
    legal_status_raw: str | None = "registered",
    first_seen_at: datetime | None = None,
    seller_type: SellerType = SellerType.OWNER,
    **overrides: object,
) -> Listing:
    values = {
        "source": source,
        "property": property_,
        "external_listing_id": external_listing_id,
        "url": f"https://example.test/{external_listing_id}",
        "canonical_url": f"https://example.test/{external_listing_id}",
        "title": "Apartment listing",
        "description": description,
        "asking_price": Decimal("210000.00"),
        "currency": CurrencyCode.EUR,
        "city_raw": "Beograd",
        "location_raw": "Blok 45, Novi Beograd, Beograd",
        "size_m2": property_.size_m2,
        "rooms": property_.rooms,
        "floor": property_.floor,
        "total_floors": property_.total_floors,
        "elevator": property_.elevator,
        "parking": property_.parking,
        "condition_raw": property_.condition_category,
        "legal_status_raw": legal_status_raw,
        "seller_type": seller_type,
        "status": ListingStatus.ACTIVE,
        "first_seen_at": first_seen_at or AS_OF - timedelta(days=30),
        "last_seen_at": AS_OF,
    }
    values.update(overrides)
    listing = Listing(**values)
    session.add(listing)
    session.flush()
    return listing


def add_price_cut(
    session: Session,
    listing: Listing,
    *,
    days_ago: int,
    old_price: str,
    new_price: str,
) -> ListingEvent:
    event = ListingEvent(
        listing=listing,
        event_type=ListingEventType.PRICE_CHANGED,
        detected_at=AS_OF - timedelta(days=days_ago),
        old_price=Decimal(old_price),
        new_price=Decimal(new_price),
        old_value_json={"asking_price": old_price},
        new_value_json={"asking_price": new_price},
    )
    session.add(event)
    session.flush()
    return event


def count_rows(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_phase8_tables_exist(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {
        "llm_analyses",
        "seller_assessments",
        "risk_assessments",
        "risk_flags",
    }.issubset(set(inspector.get_table_names()))


def test_llm_schema_success_preserves_unknown_and_evidence(db_session: Session) -> None:
    source = create_source(db_session, "phase8_llm_unknown")
    property_ = create_property(db_session)
    listing = create_listing(db_session, source, property_)
    provider = FakeProvider(
        structured_output(
            seller_motivation="UNKNOWN",
            negotiability="UNKNOWN",
            cash_preferred=None,
            reason_for_sale="UNKNOWN",
            condition=None,
        )
    )

    analysis = analyze_listing_with_llm(db_session, listing, provider=provider)

    assert analysis.status == LlmAnalysisStatus.SUCCESS
    assert analysis.seller_motivation_level == AnalysisLevel.UNKNOWN
    assert analysis.negotiability_level == AnalysisLevel.UNKNOWN
    assert analysis.cash_preferred is None
    assert analysis.reason_for_sale == ReasonForSale.UNKNOWN
    assert analysis.evidence_json["seller_motivation"][0]["text"]
    assert listing.llm_input_hash == analysis.input_hash
    assert property_.condition_category == "GOOD"


def test_invalid_llm_output_is_not_domain_truth(db_session: Session) -> None:
    source = create_source(db_session, "phase8_invalid")
    property_ = create_property(db_session, condition_category="GOOD")
    listing = create_listing(db_session, source, property_)
    provider = FakeProvider({"seller_motivation": {"level": "CERTAINLY_DESPERATE"}})

    analysis = analyze_listing_with_llm(db_session, listing, provider=provider)

    assert analysis.status == LlmAnalysisStatus.INVALID_OUTPUT
    assert analysis.seller_motivation_level is None
    assert analysis.condition_category is None
    assert analysis.error_message == "structured output failed schema validation"
    assert property_.condition_category == "GOOD"


def test_successful_llm_analysis_is_cached_by_semantic_input(db_session: Session) -> None:
    source = create_source(db_session, "phase8_cache")
    property_ = create_property(db_session)
    listing = create_listing(db_session, source, property_)
    provider = FakeProvider(structured_output(), structured_output(negotiability="HIGH"))

    first = analyze_listing_with_llm(db_session, listing, provider=provider)
    listing.last_seen_at = AS_OF + timedelta(days=1)
    second = analyze_listing_with_llm(db_session, listing, provider=provider)
    listing.description = "Updated description mentions urgent relocation and cash preference."
    third = analyze_listing_with_llm(db_session, listing, provider=provider)

    assert first.id == second.id
    assert third.id != first.id
    assert provider.call_count == 2
    assert count_rows(db_session, LlmAnalysis) == 2


def test_llm_provider_failure_is_non_fatal(db_session: Session) -> None:
    source = create_source(db_session, "phase8_outage")
    property_ = create_property(db_session)
    listing = create_listing(db_session, source, property_)
    provider = FakeProvider(LLMProviderError("provider unavailable"))

    failed = analyze_listing_with_llm(db_session, listing, provider=provider)
    result = assess_seller_intelligence_and_risk(db_session, property_, as_of=AS_OF)

    assert failed.status == LlmAnalysisStatus.FAILED
    assert failed.error_message == "provider unavailable"
    assert listing.property_id == property_.id
    assert result.seller_assessment.model_version == SELLER_RULES_VERSION
    assert result.risk_assessment.rules_version == RISK_RULES_VERSION


def test_deterministic_seller_signals_can_raise_motivation_without_llm(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase8_deterministic")
    property_ = create_property(db_session)
    listing = create_listing(
        db_session,
        source,
        property_,
        first_seen_at=AS_OF - timedelta(days=140),
        asking_price=Decimal("180000.00"),
    )
    add_price_cut(db_session, listing, days_ago=90, old_price="220000.00", new_price="200000.00")
    add_price_cut(db_session, listing, days_ago=20, old_price="200000.00", new_price="180000.00")

    result = assess_seller_intelligence_and_risk(db_session, property_, as_of=AS_OF)

    assert result.seller_assessment.seller_motivation_level == AnalysisLevel.HIGH
    assert result.seller_assessment.primary_llm_analysis_id is None
    assert any(
        component["name"] == "price_history"
        for component in result.seller_assessment.evidence_json["motivation_components"]
    )


def test_manual_seller_precedence_overrides_llm_high_motivation(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase8_manual_seller")
    property_ = create_property(db_session)
    listing = create_listing(db_session, source, property_)
    llm_analysis = analyze_listing_with_llm(
        db_session,
        listing,
        provider=FakeProvider(structured_output(seller_motivation="HIGH", negotiability="HIGH")),
    )
    manual = ManualSellerInput(
        seller_motivation_level=AnalysisLevel.LOW,
        seller_motivation_confidence=Decimal("95.00"),
        negotiability_level=AnalysisLevel.LOW,
        negotiability_confidence=Decimal("90.00"),
        source_kind=DataSourceKind.VERIFIED_MANUAL,
        source_reference="call:test",
        evidence=("Seller said the price is firm.",),
    )

    result = assess_seller_intelligence_and_risk(
        db_session,
        property_,
        llm_analyses=[llm_analysis],
        manual_seller_input=manual,
        as_of=AS_OF,
    )

    assert result.seller_assessment.seller_motivation_level == AnalysisLevel.LOW
    assert result.seller_assessment.negotiability_level == AnalysisLevel.LOW
    assert result.seller_assessment.seller_motivation_confidence == Decimal("95.00")
    assert result.seller_assessment.evidence_json["manual_precedence_applied"] == [
        "seller_motivation",
        "negotiability",
    ]


def test_risk_gate_pass_verify_block_soft_and_seller_separation(db_session: Session) -> None:
    source = create_source(db_session, "phase8_gates")
    pass_property = create_property(db_session)
    pass_listing = create_listing(db_session, source, pass_property)
    pass_llm = analyze_listing_with_llm(
        db_session,
        pass_listing,
        provider=FakeProvider(structured_output(seller_motivation="HIGH")),
    )
    pass_result = assess_seller_intelligence_and_risk(
        db_session,
        pass_property,
        llm_analyses=[pass_llm],
        manual_seller_input=ManualSellerInput(
            seller_motivation_level=AnalysisLevel.HIGH,
            seller_motivation_confidence=Decimal("90.00"),
        ),
        as_of=AS_OF,
    )

    verify_property = create_property(db_session)
    create_listing(
        db_session, source, verify_property, external_listing_id="verify", legal_status_raw=None
    )
    verify_result = assess_seller_intelligence_and_risk(db_session, verify_property, as_of=AS_OF)

    soft_property = create_property(db_session, floor=9, elevator=False)
    create_listing(db_session, source, soft_property, external_listing_id="soft")
    soft_result = assess_seller_intelligence_and_risk(db_session, soft_property, as_of=AS_OF)

    block_property = create_property(db_session)
    create_listing(db_session, source, block_property, external_listing_id="block")
    block_result = assess_seller_intelligence_and_risk(
        db_session,
        block_property,
        manual_seller_input=ManualSellerInput(
            seller_motivation_level=AnalysisLevel.HIGH,
            seller_motivation_confidence=Decimal("90.00"),
        ),
        manual_risk_inputs=[
            ManualRiskInput(
                code="PARTIAL_OWNERSHIP",
                severity=RiskSeverity.CRITICAL,
                gate_effect=RiskGateEffect.BLOCK,
                confidence=Decimal("95.00"),
                description="Verified partial ownership.",
                evidence=("Cadastre extract confirms partial ownership.",),
            )
        ],
        as_of=AS_OF,
    )

    assert pass_result.seller_assessment.seller_motivation_level == AnalysisLevel.HIGH
    assert pass_result.risk_assessment.hard_gate_status == RiskGateStatus.PASS
    assert verify_result.risk_assessment.hard_gate_status == RiskGateStatus.VERIFY
    assert any(flag.code == "CRITICAL_DOCUMENTATION_UNKNOWN" for flag in verify_result.risk_flags)
    assert soft_result.risk_assessment.hard_gate_status == RiskGateStatus.PASS
    assert any(
        flag.code == "HIGH_FLOOR_NO_ELEVATOR" and flag.gate_effect == RiskGateEffect.NONE
        for flag in soft_result.risk_flags
    )
    assert block_result.seller_assessment.seller_motivation_level == AnalysisLevel.HIGH
    assert block_result.risk_assessment.hard_gate_status == RiskGateStatus.BLOCK
    assert any(
        flag.code == "PARTIAL_OWNERSHIP"
        and flag.source_kind == DataSourceKind.VERIFIED_MANUAL
        and flag.evidence_json["evidence"]
        for flag in block_result.risk_flags
    )


def test_verified_manual_risk_precedence_suppresses_weaker_automatic_claim(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase8_risk_precedence")
    property_ = create_property(db_session)
    listing = create_listing(db_session, source, property_)
    llm_analysis = analyze_listing_with_llm(
        db_session,
        listing,
        provider=FakeProvider(
            structured_output(
                legal_claims=[
                    {
                        "code": "UNREGISTERED_OR_UNCLEAR",
                        "confidence": "78.00",
                        "evidence": [
                            {
                                "text": "LLM believes documentation is unclear.",
                                "source_field": "description",
                            }
                        ],
                    }
                ]
            )
        ),
    )

    result = assess_seller_intelligence_and_risk(
        db_session,
        property_,
        llm_analyses=[llm_analysis],
        manual_risk_inputs=[
            ManualRiskInput(
                code="REGISTERED_CLEAR",
                severity=RiskSeverity.INFO,
                gate_effect=RiskGateEffect.NONE,
                confidence=Decimal("95.00"),
                description="Verified documentation is clear.",
                evidence=("Verified manual legal review confirmed registration.",),
                source_kind=DataSourceKind.VERIFIED_MANUAL,
                source_reference="manual-review:test",
                suppresses_codes=("UNREGISTERED_OR_UNCLEAR",),
            )
        ],
        as_of=AS_OF,
    )

    assert result.risk_assessment.hard_gate_status == RiskGateStatus.PASS
    assert not any(flag.code == "UNREGISTERED_OR_UNCLEAR" for flag in result.risk_flags)
    assert any(
        flag.code == "REGISTERED_CLEAR" and flag.source_kind == DataSourceKind.VERIFIED_MANUAL
        for flag in result.risk_flags
    )
    assert count_rows(db_session, SellerAssessment) == 1
    assert count_rows(db_session, RiskAssessment) == 1
    assert count_rows(db_session, RiskFlag) == 1
