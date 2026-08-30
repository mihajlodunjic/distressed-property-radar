from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CallFeedback,
    Interaction,
    Listing,
    ListingEvent,
    LlmAnalysis,
    Property,
    PropertyFeature,
    RiskAssessment,
    RiskFlag,
    SellerAssessment,
    VisitFeedback,
)
from app.domain.enums import (
    AnalysisLevel,
    DataSourceKind,
    ListingEventType,
    LlmAnalysisStatus,
    ReasonForSale,
    RiskGateEffect,
    RiskGateStatus,
    RiskSeverity,
)
from app.features.property_dataset import (
    EffectivePropertyData,
    MarketDatasetResult,
    recalculate_property_market_dataset,
)

SELLER_RULES_VERSION = "seller_intelligence_v1"
RISK_RULES_VERSION = "risk_rules_v1"

SCORE_QUANTIZER = Decimal("0.01")
MANUAL_PRECEDENCE_MIN_CONFIDENCE = Decimal("70.00")

HARD_BLOCK_CODES = {
    "ACTIVE_DISPUTE",
    "AUCTION_SPECIAL_CONDITIONS",
    "OCCUPIED_PROPERTY",
    "PARTIAL_OWNERSHIP",
    "SUSPICIOUS_LISTING",
}
HARD_VERIFY_CODES = {
    "CRITICAL_DOCUMENTATION_UNKNOWN",
    "LEGALIZATION_UNCLEAR",
    "OWNERSHIP_UNKNOWN",
    "PROPERTY_TYPE_MISMATCH",
    "UNREGISTERED_OR_UNCLEAR",
}
SOFT_RISK_CODES = {
    "BASEMENT_OR_SEMI_BASEMENT",
    "GROUND_FLOOR",
    "HIGH_FLOOR_NO_ELEVATOR",
    "MAJOR_RENOVATION",
    "POOR_BUILDING",
    "POOR_PARKING",
    "TOP_FLOOR_RISK",
}


@dataclass(frozen=True)
class ManualSellerInput:
    seller_motivation_level: AnalysisLevel | None = None
    seller_motivation_confidence: Decimal | None = None
    negotiability_level: AnalysisLevel | None = None
    negotiability_confidence: Decimal | None = None
    lowest_indicated_price: Decimal | None = None
    cash_preferred: bool | None = None
    cash_preference_confidence: Decimal | None = None
    reason_for_sale: ReasonForSale | None = None
    reason_for_sale_confidence: Decimal | None = None
    source_kind: DataSourceKind = DataSourceKind.MANUAL
    source_reference: str | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ManualRiskInput:
    code: str
    severity: RiskSeverity
    gate_effect: RiskGateEffect
    confidence: Decimal
    description: str
    evidence: tuple[str, ...] = ()
    source_kind: DataSourceKind = DataSourceKind.VERIFIED_MANUAL
    source_reference: str | None = None
    suppresses_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SellerRiskRunResult:
    seller_assessment: SellerAssessment
    risk_assessment: RiskAssessment
    risk_flags: list[RiskFlag]


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    score: Decimal
    confidence: Decimal
    weight: Decimal
    source_kind: DataSourceKind
    evidence: list[str]


@dataclass(frozen=True)
class SellerIntelligenceData:
    seller_motivation_level: AnalysisLevel
    seller_motivation_score: Decimal | None
    seller_motivation_confidence: Decimal
    negotiability_level: AnalysisLevel
    negotiability_score: Decimal | None
    negotiability_confidence: Decimal
    cash_preferred: bool | None
    cash_preference_confidence: Decimal | None
    reason_for_sale: ReasonForSale
    evidence_json: dict[str, object]
    primary_llm_analysis: LlmAnalysis | None


@dataclass(frozen=True)
class RiskFlagInput:
    code: str
    severity: RiskSeverity
    gate_effect: RiskGateEffect
    source_kind: DataSourceKind
    source_reference: str | None
    confidence: Decimal
    description: str
    evidence: list[str]


def assess_seller_intelligence_and_risk(
    session: Session,
    property_: Property,
    *,
    llm_analyses: list[LlmAnalysis] | None = None,
    manual_seller_input: ManualSellerInput | None = None,
    manual_risk_inputs: list[ManualRiskInput] | None = None,
    as_of: datetime | None = None,
    commit: bool = False,
) -> SellerRiskRunResult:
    analysis_as_of = _aware_datetime(as_of or _utcnow())
    effective_manual_seller_input = (
        manual_seller_input
        if manual_seller_input is not None
        else _latest_manual_seller_input(session, property_, analysis_as_of)
    )
    effective_manual_risk_inputs = (
        manual_risk_inputs
        if manual_risk_inputs is not None
        else _manual_risk_inputs_from_feedback(session, property_, analysis_as_of)
    )
    market_dataset = recalculate_property_market_dataset(
        session,
        property_,
        as_of=analysis_as_of,
    )
    successful_llm_analyses = (
        _successful_analyses(llm_analyses)
        if llm_analyses is not None
        else _latest_successful_llm_analyses(session, property_)
    )
    seller_data = build_seller_intelligence(
        session,
        property_,
        market_dataset=market_dataset,
        llm_analyses=successful_llm_analyses,
        manual_seller_input=effective_manual_seller_input,
        as_of=analysis_as_of,
    )
    seller_assessment = _persist_seller_assessment(
        session,
        property_,
        as_of=analysis_as_of,
        seller_data=seller_data,
    )
    flag_inputs = build_risk_flags(
        session,
        property_,
        market_dataset=market_dataset,
        llm_analyses=successful_llm_analyses,
        manual_risk_inputs=effective_manual_risk_inputs,
        as_of=analysis_as_of,
    )
    risk_assessment = _persist_risk_assessment(
        session,
        property_,
        as_of=analysis_as_of,
        flags=flag_inputs,
    )
    risk_flags = _persist_risk_flags(session, risk_assessment, flag_inputs)

    if commit:
        session.commit()
    return SellerRiskRunResult(
        seller_assessment=seller_assessment,
        risk_assessment=risk_assessment,
        risk_flags=risk_flags,
    )


def build_seller_intelligence(
    session: Session,
    property_: Property,
    *,
    market_dataset: MarketDatasetResult,
    llm_analyses: list[LlmAnalysis],
    manual_seller_input: ManualSellerInput | None = None,
    as_of: datetime,
) -> SellerIntelligenceData:
    feature = market_dataset.feature
    motivation_components = _seller_motivation_components(llm_analyses, feature)
    motivation_components.extend(
        [
            _price_history_component(feature, weight=Decimal("30"), name="price_history"),
            _market_age_component(feature, weight=Decimal("15")),
            _relisting_component(
                feature,
                _seller_change_count(session, property_, as_of=as_of),
                weight=Decimal("10"),
            ),
        ]
    )
    if manual_seller_input is not None:
        manual_component = _manual_level_component(
            "manual_seller_motivation",
            manual_seller_input.seller_motivation_level,
            manual_seller_input.seller_motivation_confidence,
            source_kind=manual_seller_input.source_kind,
            evidence=list(manual_seller_input.evidence),
            weight=Decimal("10"),
        )
        if manual_component is not None:
            motivation_components.append(manual_component)

    motivation_score = _weighted_score(motivation_components)
    motivation_level = _level_from_score(motivation_score)
    motivation_confidence = _component_confidence(motivation_components)
    manual_precedence_applied: list[str] = []
    if _manual_level_has_precedence(
        manual_seller_input.seller_motivation_level if manual_seller_input else None,
        manual_seller_input.seller_motivation_confidence if manual_seller_input else None,
    ):
        motivation_level = manual_seller_input.seller_motivation_level
        motivation_score = _score_from_level(motivation_level)
        motivation_confidence = _clamp_score(manual_seller_input.seller_motivation_confidence)
        manual_precedence_applied.append("seller_motivation")

    negotiability_components = _negotiability_components(llm_analyses)
    negotiability_components.extend(
        [
            _price_history_component(feature, weight=Decimal("35"), name="price_history"),
            _market_age_component(feature, weight=Decimal("15")),
            _seller_type_component(feature, weight=Decimal("15")),
        ]
    )
    if manual_seller_input is not None:
        floor_component = _lowest_indicated_price_component(manual_seller_input, feature)
        if floor_component is not None:
            negotiability_components.append(floor_component)
        manual_component = _manual_level_component(
            "manual_negotiability",
            manual_seller_input.negotiability_level,
            manual_seller_input.negotiability_confidence,
            source_kind=manual_seller_input.source_kind,
            evidence=list(manual_seller_input.evidence),
            weight=Decimal("10"),
        )
        if manual_component is not None:
            negotiability_components.append(manual_component)

    negotiability_score = _weighted_score(negotiability_components)
    negotiability_level = _level_from_score(negotiability_score)
    negotiability_confidence = _component_confidence(negotiability_components)
    if _manual_level_has_precedence(
        manual_seller_input.negotiability_level if manual_seller_input else None,
        manual_seller_input.negotiability_confidence if manual_seller_input else None,
    ):
        negotiability_level = manual_seller_input.negotiability_level
        negotiability_score = _score_from_level(negotiability_level)
        negotiability_confidence = _clamp_score(manual_seller_input.negotiability_confidence)
        manual_precedence_applied.append("negotiability")

    cash_preferred, cash_confidence = _effective_cash_preference(
        llm_analyses,
        manual_seller_input,
        manual_precedence_applied,
    )
    reason_for_sale = _effective_reason_for_sale(
        llm_analyses,
        manual_seller_input,
        manual_precedence_applied,
    )
    primary_llm_analysis = _primary_llm_analysis(llm_analyses)
    evidence_json = {
        "model_version": SELLER_RULES_VERSION,
        "llm_analysis_ids": [str(analysis.id) for analysis in llm_analyses],
        "primary_llm_analysis_id": str(primary_llm_analysis.id) if primary_llm_analysis else None,
        "motivation_components": _component_json(motivation_components),
        "negotiability_components": _component_json(negotiability_components),
        "cash_preference_source": _cash_preference_source(llm_analyses, manual_seller_input),
        "reason_for_sale_source": _reason_for_sale_source(llm_analyses, manual_seller_input),
        "manual_precedence_applied": manual_precedence_applied,
    }
    return SellerIntelligenceData(
        seller_motivation_level=motivation_level,
        seller_motivation_score=motivation_score,
        seller_motivation_confidence=motivation_confidence,
        negotiability_level=negotiability_level,
        negotiability_score=negotiability_score,
        negotiability_confidence=negotiability_confidence,
        cash_preferred=cash_preferred,
        cash_preference_confidence=cash_confidence,
        reason_for_sale=reason_for_sale,
        evidence_json=evidence_json,
        primary_llm_analysis=primary_llm_analysis,
    )


def build_risk_flags(
    session: Session,
    property_: Property,
    *,
    market_dataset: MarketDatasetResult,
    llm_analyses: list[LlmAnalysis],
    manual_risk_inputs: list[ManualRiskInput],
    as_of: datetime,
) -> list[RiskFlagInput]:
    data = market_dataset.effective_data
    flags: list[RiskFlagInput] = []
    flags.extend(_source_legal_risk_flags(data))
    flags.extend(_llm_risk_flags(llm_analyses))
    flags.extend(_soft_property_risk_flags(data))

    manual_flags = [_manual_risk_flag(manual_input) for manual_input in manual_risk_inputs]
    for manual_input in manual_risk_inputs:
        if _manual_risk_has_precedence(manual_input):
            suppressed = {code.upper() for code in manual_input.suppresses_codes}
            if suppressed:
                flags = [
                    flag
                    for flag in flags
                    if not (
                        flag.code.upper() in suppressed
                        and flag.source_kind
                        in {DataSourceKind.SCRAPED, DataSourceKind.DERIVED, DataSourceKind.LLM}
                    )
                ]
    flags.extend(manual_flags)
    return _deduplicate_flags(flags, as_of=as_of, property_id=str(property_.id), session=session)


def _persist_seller_assessment(
    session: Session,
    property_: Property,
    *,
    as_of: datetime,
    seller_data: SellerIntelligenceData,
) -> SellerAssessment:
    assessment = SellerAssessment(
        property=property_,
        primary_llm_analysis=seller_data.primary_llm_analysis,
        as_of=as_of,
        seller_motivation_level=seller_data.seller_motivation_level,
        seller_motivation_score=seller_data.seller_motivation_score,
        seller_motivation_confidence=seller_data.seller_motivation_confidence,
        negotiability_level=seller_data.negotiability_level,
        negotiability_score=seller_data.negotiability_score,
        negotiability_confidence=seller_data.negotiability_confidence,
        cash_preferred=seller_data.cash_preferred,
        cash_preference_confidence=seller_data.cash_preference_confidence,
        reason_for_sale=seller_data.reason_for_sale,
        evidence_json=seller_data.evidence_json,
        model_version=SELLER_RULES_VERSION,
    )
    session.add(assessment)
    session.flush()
    return assessment


def _persist_risk_assessment(
    session: Session,
    property_: Property,
    *,
    as_of: datetime,
    flags: list[RiskFlagInput],
) -> RiskAssessment:
    assessment = RiskAssessment(
        property=property_,
        as_of=as_of,
        hard_gate_status=_gate_status(flags),
        risk_score=_risk_score(flags),
        confidence=_risk_confidence(flags),
        rules_version=RISK_RULES_VERSION,
    )
    session.add(assessment)
    session.flush()
    return assessment


def _persist_risk_flags(
    session: Session,
    risk_assessment: RiskAssessment,
    flags: list[RiskFlagInput],
) -> list[RiskFlag]:
    persisted_flags = [
        RiskFlag(
            risk_assessment=risk_assessment,
            code=flag.code,
            severity=flag.severity,
            gate_effect=flag.gate_effect,
            source_kind=flag.source_kind,
            source_reference=flag.source_reference,
            confidence=flag.confidence,
            description=flag.description,
            evidence_json={"evidence": flag.evidence},
        )
        for flag in flags
    ]
    session.add_all(persisted_flags)
    session.flush()
    return persisted_flags


def _latest_successful_llm_analyses(session: Session, property_: Property) -> list[LlmAnalysis]:
    return session.scalars(
        select(LlmAnalysis)
        .where(
            LlmAnalysis.property_id == property_.id,
            LlmAnalysis.status == LlmAnalysisStatus.SUCCESS,
        )
        .order_by(LlmAnalysis.completed_at.desc(), LlmAnalysis.created_at.desc())
    ).all()


def _latest_manual_seller_input(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> ManualSellerInput | None:
    rows = session.execute(
        select(CallFeedback, Interaction)
        .join(Interaction, CallFeedback.interaction_id == Interaction.id)
        .where(
            Interaction.property_id == property_.id,
            Interaction.occurred_at <= as_of,
        )
        .order_by(Interaction.occurred_at.desc(), Interaction.created_at.desc())
    ).all()
    for feedback, interaction in rows:
        if _call_feedback_has_seller_signal(feedback):
            return ManualSellerInput(
                seller_motivation_level=feedback.seller_motivation,
                seller_motivation_confidence=_manual_confidence(feedback.seller_motivation),
                lowest_indicated_price=feedback.lowest_indicated_price,
                cash_preferred=feedback.cash_preferred,
                cash_preference_confidence=_manual_confidence(feedback.cash_preferred),
                reason_for_sale=feedback.reason_for_sale,
                reason_for_sale_confidence=_manual_confidence(feedback.reason_for_sale),
                source_kind=DataSourceKind.MANUAL,
                source_reference=str(interaction.id),
                evidence=tuple(_manual_evidence("call_feedback", interaction)),
            )
    return None


def _manual_risk_inputs_from_feedback(
    session: Session,
    property_: Property,
    as_of: datetime,
) -> list[ManualRiskInput]:
    inputs: list[ManualRiskInput] = []
    call_rows = session.execute(
        select(CallFeedback, Interaction)
        .join(Interaction, CallFeedback.interaction_id == Interaction.id)
        .where(
            Interaction.property_id == property_.id,
            Interaction.occurred_at <= as_of,
        )
        .order_by(Interaction.occurred_at, Interaction.created_at)
    ).all()
    for feedback, interaction in call_rows:
        inputs.extend(_manual_call_risk_inputs(feedback, interaction))

    visit_rows = session.execute(
        select(VisitFeedback, Interaction)
        .join(Interaction, VisitFeedback.interaction_id == Interaction.id)
        .where(
            Interaction.property_id == property_.id,
            Interaction.occurred_at <= as_of,
        )
        .order_by(Interaction.occurred_at, Interaction.created_at)
    ).all()
    for feedback, interaction in visit_rows:
        inputs.extend(_manual_visit_risk_inputs(feedback, interaction, property_))
    return inputs


def _manual_call_risk_inputs(
    feedback: CallFeedback,
    interaction: Interaction,
) -> list[ManualRiskInput]:
    evidence = tuple(_manual_evidence("call_feedback", interaction))
    inputs: list[ManualRiskInput] = []
    if feedback.claimed_registered is False:
        inputs.append(
            ManualRiskInput(
                code="UNREGISTERED_OR_UNCLEAR",
                severity=RiskSeverity.HIGH,
                gate_effect=RiskGateEffect.VERIFY,
                confidence=Decimal("75.00"),
                description="Seller call indicated registration or legal status is not confirmed.",
                evidence=evidence,
                source_kind=DataSourceKind.MANUAL,
                source_reference=str(interaction.id),
            )
        )
    if feedback.claimed_owner_1_1 is False:
        inputs.append(
            ManualRiskInput(
                code="PARTIAL_OWNERSHIP",
                severity=RiskSeverity.CRITICAL,
                gate_effect=RiskGateEffect.VERIFY,
                confidence=Decimal("75.00"),
                description="Seller call indicated ownership may not be 1/1.",
                evidence=evidence,
                source_kind=DataSourceKind.MANUAL,
                source_reference=str(interaction.id),
            )
        )
    if feedback.claimed_mortgage is True:
        inputs.append(
            ManualRiskInput(
                code="MORTGAGE_CLAIMED",
                severity=RiskSeverity.MEDIUM,
                gate_effect=RiskGateEffect.VERIFY,
                confidence=Decimal("70.00"),
                description="Seller call indicated an active mortgage or lien may exist.",
                evidence=evidence,
                source_kind=DataSourceKind.MANUAL,
                source_reference=str(interaction.id),
            )
        )
    if feedback.tenant_present is True:
        inputs.append(
            ManualRiskInput(
                code="OCCUPIED_PROPERTY",
                severity=RiskSeverity.HIGH,
                gate_effect=RiskGateEffect.VERIFY,
                confidence=Decimal("75.00"),
                description="Seller call indicated the property may be tenant-occupied.",
                evidence=evidence,
                source_kind=DataSourceKind.MANUAL,
                source_reference=str(interaction.id),
            )
        )
    return inputs


def _manual_visit_risk_inputs(
    feedback: VisitFeedback,
    interaction: Interaction,
    property_: Property,
) -> list[ManualRiskInput]:
    evidence = tuple(_manual_evidence("visit_feedback", interaction))
    inputs: list[ManualRiskInput] = []
    condition = (feedback.condition_category or "").strip().upper()
    heavy_condition = condition in {"FULL", "RENOVATION", "FOR_RENOVATION", "NEEDS_RENOVATION"}
    heavy_renovation = (
        feedback.estimated_renovation_base is not None
        and feedback.estimated_renovation_base >= Decimal("20000.00")
    )
    if heavy_condition or heavy_renovation:
        inputs.append(
            ManualRiskInput(
                code="MAJOR_RENOVATION",
                severity=RiskSeverity.HIGH,
                gate_effect=RiskGateEffect.VERIFY,
                confidence=Decimal("90.00"),
                description="Visit feedback indicates major renovation risk.",
                evidence=evidence,
                source_kind=DataSourceKind.VERIFIED_MANUAL,
                source_reference=str(interaction.id),
            )
        )
    if feedback.elevator_verified is False and property_.floor is not None and property_.floor >= 3:
        inputs.append(
            ManualRiskInput(
                code="HIGH_FLOOR_NO_ELEVATOR",
                severity=RiskSeverity.MEDIUM,
                gate_effect=RiskGateEffect.VERIFY,
                confidence=Decimal("90.00"),
                description="Visit verified no elevator on a higher-floor apartment.",
                evidence=evidence,
                source_kind=DataSourceKind.VERIFIED_MANUAL,
                source_reference=str(interaction.id),
            )
        )
    if feedback.visible_defects_json:
        inputs.append(
            ManualRiskInput(
                code="VISIBLE_DEFECTS",
                severity=RiskSeverity.MEDIUM,
                gate_effect=RiskGateEffect.VERIFY,
                confidence=Decimal("85.00"),
                description="Visit feedback recorded visible defects.",
                evidence=[*evidence, f"visible_defects={feedback.visible_defects_json!r}"],
                source_kind=DataSourceKind.VERIFIED_MANUAL,
                source_reference=str(interaction.id),
            )
        )
    return inputs


def _call_feedback_has_seller_signal(feedback: CallFeedback) -> bool:
    return any(
        value is not None
        for value in (
            feedback.seller_motivation,
            feedback.reason_for_sale,
            feedback.lowest_indicated_price,
            feedback.cash_preferred,
        )
    )


def _manual_confidence(value: object | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal("90.00")


def _manual_evidence(prefix: str, interaction: Interaction) -> list[str]:
    evidence = [f"{prefix}:{interaction.id}", f"occurred_at:{interaction.occurred_at.isoformat()}"]
    if _has_text(interaction.notes):
        evidence.append(f"notes:{interaction.notes}")
    return evidence


def _successful_analyses(analyses: list[LlmAnalysis]) -> list[LlmAnalysis]:
    return [analysis for analysis in analyses if analysis.status == LlmAnalysisStatus.SUCCESS]


def _seller_motivation_components(
    llm_analyses: list[LlmAnalysis],
    feature: PropertyFeature,
) -> list[ScoreComponent]:
    components: list[ScoreComponent] = []
    llm_component = _llm_level_component(
        llm_analyses,
        name="llm_seller_motivation",
        level_attr="seller_motivation_level",
        confidence_attr="seller_motivation_confidence",
        evidence_key="seller_motivation",
        weight=Decimal("35"),
    )
    if llm_component is not None:
        components.append(llm_component)
    return components


def _negotiability_components(
    llm_analyses: list[LlmAnalysis],
) -> list[ScoreComponent]:
    components: list[ScoreComponent] = []
    llm_component = _llm_level_component(
        llm_analyses,
        name="llm_negotiability",
        level_attr="negotiability_level",
        confidence_attr="negotiability_confidence",
        evidence_key="negotiability",
        weight=Decimal("35"),
    )
    if llm_component is not None:
        components.append(llm_component)
    return components


def _llm_level_component(
    llm_analyses: list[LlmAnalysis],
    *,
    name: str,
    level_attr: str,
    confidence_attr: str,
    evidence_key: str,
    weight: Decimal,
) -> ScoreComponent | None:
    values: list[tuple[Decimal, Decimal]] = []
    evidence: list[str] = []
    for analysis in llm_analyses:
        level = getattr(analysis, level_attr)
        confidence = getattr(analysis, confidence_attr)
        if level is None or level == AnalysisLevel.UNKNOWN or confidence is None:
            continue
        values.append((_score_from_level(level), confidence))
        evidence.extend(_analysis_evidence(analysis, evidence_key))
    if not values:
        return None
    total_confidence = sum(confidence for _score, confidence in values)
    if total_confidence <= 0:
        score = sum(score for score, _confidence in values) / Decimal(len(values))
    else:
        score = sum(score * confidence for score, confidence in values) / total_confidence
    confidence = sum(confidence for _score, confidence in values) / Decimal(len(values))
    return ScoreComponent(
        name=name,
        score=_clamp_score(score),
        confidence=_clamp_score(confidence),
        weight=weight,
        source_kind=DataSourceKind.LLM,
        evidence=evidence,
    )


def _price_history_component(
    feature: PropertyFeature, *, weight: Decimal, name: str
) -> ScoreComponent:
    total_drop = feature.total_price_drop_pct or Decimal("0")
    if feature.price_cut_count >= 2 and total_drop >= Decimal("10"):
        score = Decimal("85")
        evidence = [f"{feature.price_cut_count} price cuts totaling {total_drop}%."]
    elif feature.price_cut_count >= 1 and total_drop >= Decimal("5"):
        score = Decimal("70")
        evidence = [f"Price cut history totals {total_drop}%."]
    elif feature.price_cut_count >= 1:
        score = Decimal("55")
        evidence = ["At least one price cut is recorded."]
    else:
        score = Decimal("30")
        evidence = ["No price cuts recorded."]
    return ScoreComponent(
        name=name,
        score=score,
        confidence=Decimal("70"),
        weight=weight,
        source_kind=DataSourceKind.DERIVED,
        evidence=evidence,
    )


def _market_age_component(feature: PropertyFeature, *, weight: Decimal) -> ScoreComponent:
    age_days = feature.property_market_age_days
    if age_days is None:
        return ScoreComponent(
            name="market_age",
            score=Decimal("50"),
            confidence=Decimal("25"),
            weight=weight,
            source_kind=DataSourceKind.DERIVED,
            evidence=["Property market age is unknown."],
        )
    if age_days >= 120:
        score = Decimal("75")
    elif age_days >= 60:
        score = Decimal("60")
    elif age_days >= 30:
        score = Decimal("45")
    else:
        score = Decimal("25")
    return ScoreComponent(
        name="market_age",
        score=score,
        confidence=Decimal("70"),
        weight=weight,
        source_kind=DataSourceKind.DERIVED,
        evidence=[f"Property market age is {age_days} days."],
    )


def _relisting_component(
    feature: PropertyFeature,
    seller_change_count: int,
    *,
    weight: Decimal,
) -> ScoreComponent:
    if feature.relist_count > 0 or seller_change_count > 0:
        score = Decimal("65")
        evidence = [
            f"Relist count {feature.relist_count}; seller-change events {seller_change_count}."
        ]
    else:
        score = Decimal("30")
        evidence = ["No relisting or seller-change signal recorded."]
    return ScoreComponent(
        name="relisting_seller_changes",
        score=score,
        confidence=Decimal("60"),
        weight=weight,
        source_kind=DataSourceKind.DERIVED,
        evidence=evidence,
    )


def _seller_type_component(feature: PropertyFeature, *, weight: Decimal) -> ScoreComponent:
    if feature.owner_listing_present:
        score = Decimal("65")
        evidence = ["At least one active owner listing is present."]
    elif feature.agency_listing_count > 0:
        score = Decimal("45")
        evidence = ["Only agency listings are currently visible."]
    else:
        score = Decimal("50")
        evidence = ["Seller type is unknown."]
    return ScoreComponent(
        name="seller_type",
        score=score,
        confidence=Decimal("55"),
        weight=weight,
        source_kind=DataSourceKind.DERIVED,
        evidence=evidence,
    )


def _manual_level_component(
    name: str,
    level: AnalysisLevel | None,
    confidence: Decimal | None,
    *,
    source_kind: DataSourceKind,
    evidence: list[str],
    weight: Decimal,
) -> ScoreComponent | None:
    if level is None or level == AnalysisLevel.UNKNOWN or confidence is None:
        return None
    return ScoreComponent(
        name=name,
        score=_score_from_level(level),
        confidence=_clamp_score(confidence),
        weight=weight,
        source_kind=source_kind,
        evidence=evidence,
    )


def _lowest_indicated_price_component(
    manual_input: ManualSellerInput,
    feature: PropertyFeature,
) -> ScoreComponent | None:
    if manual_input.lowest_indicated_price is None or feature.current_lowest_asking_price is None:
        return None
    if feature.current_lowest_asking_price <= 0:
        return None
    ratio = manual_input.lowest_indicated_price / feature.current_lowest_asking_price
    if ratio <= Decimal("0.90"):
        score = Decimal("85")
    elif ratio <= Decimal("0.97"):
        score = Decimal("65")
    else:
        score = Decimal("35")
    confidence = manual_input.negotiability_confidence or Decimal("75")
    return ScoreComponent(
        name="manual_lowest_indicated_price",
        score=score,
        confidence=_clamp_score(confidence),
        weight=Decimal("20"),
        source_kind=manual_input.source_kind,
        evidence=[
            "Manual lowest indicated price compared with current asking price.",
            *manual_input.evidence,
        ],
    )


def _effective_cash_preference(
    llm_analyses: list[LlmAnalysis],
    manual_input: ManualSellerInput | None,
    manual_precedence_applied: list[str],
) -> tuple[bool | None, Decimal | None]:
    if (
        manual_input is not None
        and manual_input.cash_preferred is not None
        and _manual_confidence_has_precedence(manual_input.cash_preference_confidence)
    ):
        manual_precedence_applied.append("cash_preference")
        return manual_input.cash_preferred, _clamp_score(manual_input.cash_preference_confidence)
    candidates = [
        analysis
        for analysis in llm_analyses
        if analysis.cash_preferred is not None and analysis.cash_preference_confidence is not None
    ]
    if not candidates:
        return None, None
    selected = max(candidates, key=lambda analysis: analysis.cash_preference_confidence)
    return selected.cash_preferred, _clamp_score(selected.cash_preference_confidence)


def _effective_reason_for_sale(
    llm_analyses: list[LlmAnalysis],
    manual_input: ManualSellerInput | None,
    manual_precedence_applied: list[str],
) -> ReasonForSale:
    if (
        manual_input is not None
        and manual_input.reason_for_sale is not None
        and manual_input.reason_for_sale != ReasonForSale.UNKNOWN
        and _manual_confidence_has_precedence(manual_input.reason_for_sale_confidence)
    ):
        manual_precedence_applied.append("reason_for_sale")
        return manual_input.reason_for_sale
    candidates = [
        analysis
        for analysis in llm_analyses
        if analysis.reason_for_sale is not None
        and analysis.reason_for_sale != ReasonForSale.UNKNOWN
        and analysis.reason_for_sale_confidence is not None
    ]
    if not candidates:
        return ReasonForSale.UNKNOWN
    return max(candidates, key=lambda analysis: analysis.reason_for_sale_confidence).reason_for_sale


def _source_legal_risk_flags(data: EffectivePropertyData) -> list[RiskFlagInput]:
    legal_text = data.legal_status_raw
    if not _has_text(legal_text):
        return [
            RiskFlagInput(
                code="CRITICAL_DOCUMENTATION_UNKNOWN",
                severity=RiskSeverity.HIGH,
                gate_effect=RiskGateEffect.VERIFY,
                source_kind=DataSourceKind.DERIVED,
                source_reference="effective_property_data.legal_status_raw",
                confidence=Decimal("35.00"),
                description="Critical legal documentation status is unknown.",
                evidence=["No usable legal-status source text is available."],
            )
        ]
    normalized = legal_text.casefold()
    flags: list[RiskFlagInput] = []
    if _contains_any(normalized, ("1/2", "1/3", "udeo", "suvlas", "deo vlas")):
        flags.append(
            RiskFlagInput(
                code="PARTIAL_OWNERSHIP",
                severity=RiskSeverity.CRITICAL,
                gate_effect=RiskGateEffect.BLOCK,
                source_kind=DataSourceKind.SCRAPED,
                source_reference="effective_property_data.legal_status_raw",
                confidence=Decimal("80.00"),
                description="Listing legal text indicates partial ownership.",
                evidence=[legal_text[:500]],
            )
        )
    if _contains_any(normalized, ("nije uknj", "neuknj", "unregistered", "not registered")):
        flags.append(
            RiskFlagInput(
                code="UNREGISTERED_OR_UNCLEAR",
                severity=RiskSeverity.HIGH,
                gate_effect=RiskGateEffect.VERIFY,
                source_kind=DataSourceKind.SCRAPED,
                source_reference="effective_property_data.legal_status_raw",
                confidence=Decimal("70.00"),
                description="Listing legal text indicates unclear registration.",
                evidence=[legal_text[:500]],
            )
        )
    if _contains_any(normalized, ("legaliz", "ozakonj", "u postupku")):
        flags.append(
            RiskFlagInput(
                code="LEGALIZATION_UNCLEAR",
                severity=RiskSeverity.HIGH,
                gate_effect=RiskGateEffect.VERIFY,
                source_kind=DataSourceKind.SCRAPED,
                source_reference="effective_property_data.legal_status_raw",
                confidence=Decimal("70.00"),
                description="Listing legal text indicates legalization needs verification.",
                evidence=[legal_text[:500]],
            )
        )
    if _contains_any(normalized, ("spor", "sud", "dispute", "lawsuit")):
        flags.append(
            RiskFlagInput(
                code="ACTIVE_DISPUTE",
                severity=RiskSeverity.CRITICAL,
                gate_effect=RiskGateEffect.BLOCK,
                source_kind=DataSourceKind.SCRAPED,
                source_reference="effective_property_data.legal_status_raw",
                confidence=Decimal("80.00"),
                description="Listing legal text indicates a dispute.",
                evidence=[legal_text[:500]],
            )
        )
    return flags


def _llm_risk_flags(llm_analyses: list[LlmAnalysis]) -> list[RiskFlagInput]:
    flags: list[RiskFlagInput] = []
    for analysis in llm_analyses:
        for claim in analysis.structured_output_json.get("legal_claims", []):
            if isinstance(claim, dict):
                flag = _llm_claim_to_flag(analysis, claim)
                if flag is not None:
                    flags.append(flag)
        for signal in analysis.structured_output_json.get("risk_signals", []):
            if isinstance(signal, dict):
                flag = _llm_claim_to_flag(analysis, signal)
                if flag is not None:
                    flags.append(flag)
    return flags


def _llm_claim_to_flag(analysis: LlmAnalysis, claim: dict[str, object]) -> RiskFlagInput | None:
    code = str(claim.get("code") or "").upper()
    if not code:
        return None
    confidence = _decimal_from_value(claim.get("confidence")) or Decimal("0")
    severity = _risk_severity_from_value(claim.get("severity"), code)
    if code in HARD_BLOCK_CODES and confidence >= Decimal("75"):
        gate_effect = RiskGateEffect.BLOCK
    elif code in HARD_BLOCK_CODES | HARD_VERIFY_CODES:
        gate_effect = RiskGateEffect.VERIFY
    elif code in SOFT_RISK_CODES:
        gate_effect = RiskGateEffect.NONE
    else:
        gate_effect = RiskGateEffect.NONE
        severity = RiskSeverity.INFO
    return RiskFlagInput(
        code=code,
        severity=severity,
        gate_effect=gate_effect,
        source_kind=DataSourceKind.LLM,
        source_reference=str(analysis.id),
        confidence=_clamp_score(confidence),
        description=f"LLM extracted risk signal {code}.",
        evidence=_claim_evidence(claim),
    )


def _soft_property_risk_flags(data: EffectivePropertyData) -> list[RiskFlagInput]:
    flags: list[RiskFlagInput] = []
    if data.floor == 0:
        flags.append(
            _soft_flag(
                "GROUND_FLOOR",
                "Property is on the ground floor.",
                source_reference="effective_property_data.floor",
            )
        )
    if data.floor is not None and data.floor >= 7 and data.elevator is False:
        flags.append(
            _soft_flag(
                "HIGH_FLOOR_NO_ELEVATOR",
                "High floor without elevator is a soft risk.",
                severity=RiskSeverity.MEDIUM,
                source_reference="effective_property_data.floor_elevator",
            )
        )
    condition = data.condition_category.casefold() if _has_text(data.condition_category) else ""
    if _contains_any(condition, ("major_renovation", "ruin", "full renovation")):
        flags.append(
            _soft_flag(
                "MAJOR_RENOVATION",
                "Condition indicates major renovation risk.",
                severity=RiskSeverity.HIGH,
                source_reference="effective_property_data.condition_category",
            )
        )
    if data.parking is False:
        flags.append(
            _soft_flag(
                "POOR_PARKING",
                "Parking is not confirmed.",
                severity=RiskSeverity.LOW,
                source_reference="effective_property_data.parking",
            )
        )
    return flags


def _soft_flag(
    code: str,
    description: str,
    *,
    severity: RiskSeverity = RiskSeverity.LOW,
    source_reference: str,
) -> RiskFlagInput:
    return RiskFlagInput(
        code=code,
        severity=severity,
        gate_effect=RiskGateEffect.NONE,
        source_kind=DataSourceKind.DERIVED,
        source_reference=source_reference,
        confidence=Decimal("65.00"),
        description=description,
        evidence=[description],
    )


def _manual_risk_flag(manual_input: ManualRiskInput) -> RiskFlagInput:
    return RiskFlagInput(
        code=manual_input.code.upper(),
        severity=manual_input.severity,
        gate_effect=manual_input.gate_effect,
        source_kind=manual_input.source_kind,
        source_reference=manual_input.source_reference,
        confidence=_clamp_score(manual_input.confidence),
        description=manual_input.description,
        evidence=list(manual_input.evidence),
    )


def _deduplicate_flags(
    flags: list[RiskFlagInput],
    *,
    as_of: datetime,
    property_id: str,
    session: Session,
) -> list[RiskFlagInput]:
    _ = as_of, property_id, session
    best_by_key: dict[tuple[str, RiskGateEffect, DataSourceKind, str | None], RiskFlagInput] = {}
    for flag in flags:
        key = (flag.code, flag.gate_effect, flag.source_kind, flag.source_reference)
        existing = best_by_key.get(key)
        if existing is None or flag.confidence > existing.confidence:
            best_by_key[key] = flag
    return list(best_by_key.values())


def _gate_status(flags: list[RiskFlagInput]) -> RiskGateStatus:
    if any(flag.gate_effect == RiskGateEffect.BLOCK for flag in flags):
        return RiskGateStatus.BLOCK
    if any(flag.gate_effect == RiskGateEffect.VERIFY for flag in flags):
        return RiskGateStatus.VERIFY
    return RiskGateStatus.PASS


def _risk_score(flags: list[RiskFlagInput]) -> Decimal | None:
    if not flags:
        return Decimal("0.00")
    if all(flag.code == "CRITICAL_DOCUMENTATION_UNKNOWN" for flag in flags):
        return None
    score = max(_severity_points(flag.severity) for flag in flags)
    if any(flag.gate_effect == RiskGateEffect.BLOCK for flag in flags):
        score = max(score, Decimal("90"))
    return _clamp_score(score)


def _risk_confidence(flags: list[RiskFlagInput]) -> Decimal:
    if not flags:
        return Decimal("45.00")
    return _clamp_score(max(flag.confidence for flag in flags))


def _severity_points(severity: RiskSeverity) -> Decimal:
    return {
        RiskSeverity.INFO: Decimal("5"),
        RiskSeverity.LOW: Decimal("20"),
        RiskSeverity.MEDIUM: Decimal("45"),
        RiskSeverity.HIGH: Decimal("70"),
        RiskSeverity.CRITICAL: Decimal("95"),
    }[severity]


def _component_json(components: list[ScoreComponent]) -> list[dict[str, object]]:
    return [
        {
            "name": component.name,
            "score": _decimal_to_string(component.score),
            "confidence": _decimal_to_string(component.confidence),
            "weight": _decimal_to_string(component.weight),
            "source_kind": component.source_kind.value,
            "evidence": component.evidence,
        }
        for component in components
    ]


def _weighted_score(components: list[ScoreComponent]) -> Decimal | None:
    if not components:
        return None
    total_weight = sum(component.weight for component in components)
    if total_weight <= 0:
        return None
    return _clamp_score(
        sum(component.score * component.weight for component in components) / total_weight
    )


def _component_confidence(components: list[ScoreComponent]) -> Decimal:
    if not components:
        return Decimal("0.00")
    total_weight = sum(component.weight for component in components)
    if total_weight <= 0:
        return Decimal("0.00")
    weighted_confidence = (
        sum(component.confidence * component.weight for component in components) / total_weight
    )
    coverage_factor = Decimal("0.70") + (
        min(total_weight, Decimal("100")) / Decimal("100")
    ) * Decimal("0.30")
    return _clamp_score(weighted_confidence * coverage_factor)


def _level_from_score(score: Decimal | None) -> AnalysisLevel:
    if score is None:
        return AnalysisLevel.UNKNOWN
    if score >= Decimal("70"):
        return AnalysisLevel.HIGH
    if score >= Decimal("45"):
        return AnalysisLevel.MEDIUM
    return AnalysisLevel.LOW


def _score_from_level(level: AnalysisLevel) -> Decimal:
    return {
        AnalysisLevel.LOW: Decimal("20.00"),
        AnalysisLevel.MEDIUM: Decimal("55.00"),
        AnalysisLevel.HIGH: Decimal("85.00"),
        AnalysisLevel.UNKNOWN: Decimal("0.00"),
    }[level]


def _manual_level_has_precedence(
    level: AnalysisLevel | None,
    confidence: Decimal | None,
) -> bool:
    return (
        level is not None
        and level != AnalysisLevel.UNKNOWN
        and _manual_confidence_has_precedence(confidence)
    )


def _manual_confidence_has_precedence(confidence: Decimal | None) -> bool:
    return confidence is not None and confidence >= MANUAL_PRECEDENCE_MIN_CONFIDENCE


def _manual_risk_has_precedence(manual_input: ManualRiskInput) -> bool:
    return (
        manual_input.source_kind in {DataSourceKind.MANUAL, DataSourceKind.VERIFIED_MANUAL}
        and manual_input.confidence >= MANUAL_PRECEDENCE_MIN_CONFIDENCE
    )


def _primary_llm_analysis(llm_analyses: list[LlmAnalysis]) -> LlmAnalysis | None:
    if not llm_analyses:
        return None
    return max(llm_analyses, key=lambda analysis: analysis.completed_at or analysis.created_at)


def _cash_preference_source(
    llm_analyses: list[LlmAnalysis],
    manual_input: ManualSellerInput | None,
) -> str:
    if (
        manual_input is not None
        and manual_input.cash_preferred is not None
        and _manual_confidence_has_precedence(manual_input.cash_preference_confidence)
    ):
        return "manual"
    if any(analysis.cash_preferred is not None for analysis in llm_analyses):
        return "llm"
    return "unknown"


def _reason_for_sale_source(
    llm_analyses: list[LlmAnalysis],
    manual_input: ManualSellerInput | None,
) -> str:
    if (
        manual_input is not None
        and manual_input.reason_for_sale not in {None, ReasonForSale.UNKNOWN}
        and _manual_confidence_has_precedence(manual_input.reason_for_sale_confidence)
    ):
        return "manual"
    if any(
        analysis.reason_for_sale not in {None, ReasonForSale.UNKNOWN} for analysis in llm_analyses
    ):
        return "llm"
    return "unknown"


def _analysis_evidence(analysis: LlmAnalysis, key: str) -> list[str]:
    values = analysis.evidence_json.get(key)
    if not isinstance(values, list):
        return []
    evidence: list[str] = []
    for value in values:
        if isinstance(value, dict) and _has_text(value.get("text")):
            evidence.append(str(value["text"]))
    return evidence


def _claim_evidence(claim: dict[str, object]) -> list[str]:
    raw_evidence = claim.get("evidence")
    if not isinstance(raw_evidence, list):
        return []
    evidence: list[str] = []
    for item in raw_evidence:
        if isinstance(item, dict) and _has_text(item.get("text")):
            evidence.append(str(item["text"])[:500])
    return evidence


def _seller_change_count(session: Session, property_: Property, *, as_of: datetime) -> int:
    return len(
        session.scalars(
            select(ListingEvent)
            .join(Listing, ListingEvent.listing_id == Listing.id)
            .where(
                Listing.property_id == property_.id,
                ListingEvent.event_type == ListingEventType.SELLER_CHANGED,
                ListingEvent.detected_at <= as_of,
            )
        ).all()
    )


def _risk_severity_from_value(value: object, code: str) -> RiskSeverity:
    if isinstance(value, str):
        try:
            return RiskSeverity(value.upper())
        except ValueError:
            return _default_risk_severity(code)
    return _default_risk_severity(code)


def _default_risk_severity(code: str) -> RiskSeverity:
    if code in HARD_BLOCK_CODES:
        return RiskSeverity.CRITICAL
    if code in HARD_VERIFY_CODES:
        return RiskSeverity.HIGH
    if code in SOFT_RISK_CODES:
        return RiskSeverity.MEDIUM
    return RiskSeverity.INFO


def _decimal_from_value(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _clamp_score(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return min(Decimal("100"), max(Decimal("0"), value)).quantize(
        SCORE_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


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
