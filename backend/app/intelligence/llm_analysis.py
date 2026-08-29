from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Listing, ListingEvent, LlmAnalysis
from app.domain.enums import (
    AnalysisLevel,
    LlmAnalysisStatus,
    ReasonForSale,
    RiskSeverity,
)

LLM_PROMPT_VERSION = "seller_risk_prompt_v1"
DEFAULT_LLM_PROVIDER = "generic_http_json"


class LLMProviderError(RuntimeError):
    """Raised when the configured LLM provider cannot return a usable response."""


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def extract_structured_listing(
        self,
        input_payload: dict[str, object],
        *,
        prompt_version: str,
    ) -> dict[str, object]:
        """Return provider structured output for a listing input."""


@dataclass(frozen=True)
class HttpJsonLLMProvider:
    endpoint_url: str
    api_key: str
    model_name: str
    provider_name: str = DEFAULT_LLM_PROVIDER
    timeout_seconds: int = 30

    def extract_structured_listing(
        self,
        input_payload: dict[str, object],
        *,
        prompt_version: str,
    ) -> dict[str, object]:
        request_payload = {
            "model": self.model_name,
            "prompt_version": prompt_version,
            "input": input_payload,
            "output_schema": "dpr_seller_risk_v1",
        }
        request = urllib.request.Request(
            self.endpoint_url,
            data=json.dumps(request_payload, sort_keys=True).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise LLMProviderError(str(exc)) from exc

        if not isinstance(response_payload, dict):
            raise LLMProviderError("provider returned non-object JSON")
        structured_output = response_payload.get("structured_output", response_payload)
        if not isinstance(structured_output, dict):
            raise LLMProviderError("provider returned non-object structured output")
        return structured_output


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)
    source_field: str | None = Field(default=None, max_length=100)


class LevelSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: AnalysisLevel
    confidence: Decimal = Field(ge=0, le=100)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=8)


class CashPreferenceSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: bool | None
    confidence: Decimal = Field(ge=0, le=100)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=8)


class ReasonForSaleSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: ReasonForSale
    confidence: Decimal = Field(ge=0, le=100)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=8)


class ConditionSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None = Field(default=None, max_length=100)
    confidence: Decimal = Field(ge=0, le=100)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=8)


class LegalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100)
    confidence: Decimal = Field(ge=0, le=100)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=8)


class LlmRiskSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100)
    severity: RiskSeverity
    confidence: Decimal = Field(ge=0, le=100)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=8)


class StructuredListingAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seller_motivation: LevelSignal
    negotiability: LevelSignal
    cash_preference: CashPreferenceSignal
    reason_for_sale: ReasonForSaleSignal
    condition: ConditionSignal
    legal_claims: list[LegalClaim] = Field(default_factory=list, max_length=12)
    risk_signals: list[LlmRiskSignal] = Field(default_factory=list, max_length=12)


def analyze_listing_with_llm(
    session: Session,
    listing: Listing,
    *,
    provider: LLMProvider,
    prompt_version: str = LLM_PROMPT_VERSION,
    commit: bool = False,
) -> LlmAnalysis:
    input_payload = build_llm_listing_input(session, listing)
    input_hash = stable_input_hash(input_payload)
    listing.llm_input_hash = input_hash

    cached = _cached_successful_analysis(
        session,
        listing=listing,
        input_hash=input_hash,
        prompt_version=prompt_version,
        model=provider.model_name,
    )
    if cached is not None:
        if commit:
            session.commit()
        return cached

    completed_at = _utcnow()
    try:
        raw_output = provider.extract_structured_listing(
            input_payload,
            prompt_version=prompt_version,
        )
    except Exception as exc:
        analysis = _failed_analysis(
            listing,
            input_hash=input_hash,
            provider=provider,
            prompt_version=prompt_version,
            completed_at=completed_at,
            error_message=str(exc),
        )
        session.add(analysis)
        session.flush()
        if commit:
            session.commit()
        return analysis

    try:
        structured_output = StructuredListingAnalysis.model_validate(raw_output)
    except ValidationError as exc:
        analysis = _invalid_output_analysis(
            listing,
            input_hash=input_hash,
            provider=provider,
            prompt_version=prompt_version,
            completed_at=completed_at,
            raw_output=raw_output,
            validation_error=exc,
        )
        session.add(analysis)
        session.flush()
        if commit:
            session.commit()
        return analysis

    analysis = _successful_analysis(
        listing,
        input_hash=input_hash,
        provider=provider,
        prompt_version=prompt_version,
        completed_at=completed_at,
        structured_output=structured_output,
    )
    session.add(analysis)
    session.flush()
    if commit:
        session.commit()
    return analysis


def build_llm_listing_input(session: Session, listing: Listing) -> dict[str, object]:
    return {
        "title": listing.title,
        "description": listing.description,
        "seller_type": listing.seller_type.value if listing.seller_type is not None else None,
        "seller_name": listing.seller_name,
        "agency_name": listing.agency_name,
        "asking_price": _decimal_to_string(listing.asking_price),
        "currency": listing.currency.value if listing.currency is not None else None,
        "condition_raw": listing.condition_raw,
        "legal_status_raw": listing.legal_status_raw,
        "price_history_summary": _price_history_summary(session, listing),
    }


def stable_input_hash(input_payload: dict[str, object]) -> str:
    encoded = json.dumps(
        input_payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cached_successful_analysis(
    session: Session,
    *,
    listing: Listing,
    input_hash: str,
    prompt_version: str,
    model: str,
) -> LlmAnalysis | None:
    return session.scalars(
        select(LlmAnalysis)
        .where(
            LlmAnalysis.listing_id == listing.id,
            LlmAnalysis.input_hash == input_hash,
            LlmAnalysis.prompt_version == prompt_version,
            LlmAnalysis.model == model,
            LlmAnalysis.status == LlmAnalysisStatus.SUCCESS,
        )
        .order_by(LlmAnalysis.created_at.desc(), LlmAnalysis.id.desc())
    ).first()


def _successful_analysis(
    listing: Listing,
    *,
    input_hash: str,
    provider: LLMProvider,
    prompt_version: str,
    completed_at: datetime,
    structured_output: StructuredListingAnalysis,
) -> LlmAnalysis:
    output_json = _jsonable(structured_output.model_dump(mode="json"))
    return LlmAnalysis(
        listing=listing,
        property_id=listing.property_id,
        input_hash=input_hash,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_version=prompt_version,
        status=LlmAnalysisStatus.SUCCESS,
        seller_motivation_level=structured_output.seller_motivation.level,
        seller_motivation_confidence=structured_output.seller_motivation.confidence,
        cash_preferred=structured_output.cash_preference.value,
        cash_preference_confidence=structured_output.cash_preference.confidence,
        negotiability_level=structured_output.negotiability.level,
        negotiability_confidence=structured_output.negotiability.confidence,
        reason_for_sale=structured_output.reason_for_sale.value,
        reason_for_sale_confidence=structured_output.reason_for_sale.confidence,
        condition_category=structured_output.condition.value,
        condition_confidence=structured_output.condition.confidence,
        structured_output_json=output_json,
        evidence_json=_evidence_summary(structured_output),
        completed_at=completed_at,
    )


def _failed_analysis(
    listing: Listing,
    *,
    input_hash: str,
    provider: LLMProvider,
    prompt_version: str,
    completed_at: datetime,
    error_message: str,
) -> LlmAnalysis:
    return LlmAnalysis(
        listing=listing,
        property_id=listing.property_id,
        input_hash=input_hash,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_version=prompt_version,
        status=LlmAnalysisStatus.FAILED,
        structured_output_json={},
        evidence_json={},
        completed_at=completed_at,
        error_message=error_message[:4000],
    )


def _invalid_output_analysis(
    listing: Listing,
    *,
    input_hash: str,
    provider: LLMProvider,
    prompt_version: str,
    completed_at: datetime,
    raw_output: dict[str, object],
    validation_error: ValidationError,
) -> LlmAnalysis:
    return LlmAnalysis(
        listing=listing,
        property_id=listing.property_id,
        input_hash=input_hash,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_version=prompt_version,
        status=LlmAnalysisStatus.INVALID_OUTPUT,
        structured_output_json={
            "raw_output": _jsonable(raw_output),
            "validation_errors": _jsonable(validation_error.errors()),
        },
        evidence_json={},
        completed_at=completed_at,
        error_message="structured output failed schema validation",
    )


def _evidence_summary(structured_output: StructuredListingAnalysis) -> dict[str, object]:
    return {
        "seller_motivation": _evidence_items(structured_output.seller_motivation.evidence),
        "negotiability": _evidence_items(structured_output.negotiability.evidence),
        "cash_preference": _evidence_items(structured_output.cash_preference.evidence),
        "reason_for_sale": _evidence_items(structured_output.reason_for_sale.evidence),
        "condition": _evidence_items(structured_output.condition.evidence),
        "legal_claims": [
            {
                "code": claim.code,
                "confidence": _decimal_to_string(claim.confidence),
                "evidence": _evidence_items(claim.evidence),
            }
            for claim in structured_output.legal_claims
        ],
        "risk_signals": [
            {
                "code": signal.code,
                "severity": signal.severity.value,
                "confidence": _decimal_to_string(signal.confidence),
                "evidence": _evidence_items(signal.evidence),
            }
            for signal in structured_output.risk_signals
        ],
    }


def _evidence_items(items: list[EvidenceItem]) -> list[dict[str, object]]:
    return [{"text": item.text, "source_field": item.source_field} for item in items]


def _price_history_summary(session: Session, listing: Listing) -> dict[str, object]:
    events = session.scalars(
        select(ListingEvent).where(ListingEvent.listing_id == listing.id)
    ).all()
    price_cuts = [
        event
        for event in events
        if event.old_price is not None
        and event.new_price is not None
        and event.new_price < event.old_price
    ]
    if not price_cuts:
        return {
            "price_cut_count": 0,
            "total_price_drop_pct": "0.0000",
        }
    first_price = price_cuts[0].old_price
    lowest_price = min(event.new_price for event in price_cuts if event.new_price is not None)
    if first_price is None or first_price <= 0:
        drop_pct = Decimal("0.0000")
    else:
        drop_pct = ((first_price - lowest_price) / first_price * Decimal("100")).quantize(
            Decimal("0.0001")
        )
    return {
        "price_cut_count": len(price_cuts),
        "total_price_drop_pct": _decimal_to_string(drop_pct),
    }


def _jsonable(value: Any) -> dict[str, object] | list[object] | str | int | float | bool | None:
    return json.loads(json.dumps(value, sort_keys=True, default=_json_default))


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return _decimal_to_string(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _decimal_to_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _utcnow() -> datetime:
    return datetime.now(UTC)
