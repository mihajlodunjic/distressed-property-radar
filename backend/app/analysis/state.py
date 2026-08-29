from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ComparableSet,
    DealAnalysis,
    FastSaleEstimate,
    LiquidityAssessment,
    LlmAnalysis,
    OpportunityAssessment,
    Property,
    PropertyAnalysisState,
    PropertyFeature,
    RiskAssessment,
    SellerAssessment,
    Valuation,
)
from app.domain.enums import (
    AnalysisStatus,
    DealAnalysisStatus,
    FastSaleStatus,
    LiquidityStatus,
    LlmAnalysisStatus,
    ValuationStatus,
)

ANALYSIS_MODULES = (
    "features",
    "matching",
    "comparable",
    "valuation",
    "liquidity",
    "fast_sale",
    "llm",
    "seller",
    "risk",
    "deal",
    "opportunity",
)

MODULE_STATUS_COLUMNS = {module: f"{module}_status" for module in ANALYSIS_MODULES}


def get_or_create_analysis_state(
    session: Session,
    property_: Property,
) -> PropertyAnalysisState:
    state = property_.analysis_state
    if state is not None:
        return state

    state = PropertyAnalysisState(property=property_)
    session.add(state)
    _initialize_from_latest_rows(session, state, property_)
    session.flush()
    return state


def mark_modules_stale(
    session: Session,
    property_: Property,
    modules: Iterable[str],
    *,
    as_of: datetime | None = None,
    error: str | None = None,
) -> PropertyAnalysisState:
    state = get_or_create_analysis_state(session, property_)
    timestamp = _aware_datetime(as_of or _utcnow())
    for module in _validated_modules(modules):
        setattr(state, MODULE_STATUS_COLUMNS[module], AnalysisStatus.STALE)
    if error is not None:
        state.last_error = error
    state.updated_at = timestamp
    session.flush()
    return state


def mark_modules_pending(
    session: Session,
    property_: Property,
    modules: Iterable[str],
    *,
    as_of: datetime | None = None,
) -> PropertyAnalysisState:
    state = get_or_create_analysis_state(session, property_)
    timestamp = _aware_datetime(as_of or _utcnow())
    for module in _validated_modules(modules):
        setattr(state, MODULE_STATUS_COLUMNS[module], AnalysisStatus.PENDING)
    state.last_analysis_started_at = timestamp
    state.updated_at = timestamp
    session.flush()
    return state


def mark_modules_success(
    session: Session,
    property_: Property,
    statuses: Mapping[str, AnalysisStatus | str],
    *,
    as_of: datetime | None = None,
) -> PropertyAnalysisState:
    state = get_or_create_analysis_state(session, property_)
    timestamp = _aware_datetime(as_of or _utcnow())
    for module, status in statuses.items():
        _validate_module(module)
        setattr(state, MODULE_STATUS_COLUMNS[module], AnalysisStatus(status))
    state.last_analysis_completed_at = timestamp
    state.last_error = None
    state.updated_at = timestamp
    session.flush()
    return state


def status_from_analysis_row(row: Any | None, latest_input_at: datetime | None = None) -> str:
    if row is None:
        return AnalysisStatus.NOT_RUN.value
    row_as_of = getattr(row, "as_of", None)
    if latest_input_at is not None and row_as_of is not None and latest_input_at > row_as_of:
        return AnalysisStatus.STALE.value
    raw_status = getattr(row, "status", None)
    if raw_status in {
        ValuationStatus.INSUFFICIENT_DATA,
        LiquidityStatus.INSUFFICIENT_DATA,
        FastSaleStatus.INSUFFICIENT_DATA,
        DealAnalysisStatus.INSUFFICIENT_DATA,
    }:
        return AnalysisStatus.INSUFFICIENT_DATA.value
    if raw_status in {
        ValuationStatus.SUCCESS,
        LiquidityStatus.SUCCESS,
        FastSaleStatus.SUCCESS,
        DealAnalysisStatus.SUCCESS,
        LlmAnalysisStatus.SUCCESS,
    }:
        return AnalysisStatus.SUCCESS.value
    if raw_status in {LlmAnalysisStatus.FAILED, LlmAnalysisStatus.INVALID_OUTPUT}:
        return AnalysisStatus.FAILED.value
    if raw_status == LlmAnalysisStatus.PENDING:
        return AnalysisStatus.PENDING.value
    return AnalysisStatus.SUCCESS.value


def _initialize_from_latest_rows(
    session: Session,
    state: PropertyAnalysisState,
    property_: Property,
) -> None:
    if _latest_feature(session, property_) is not None:
        state.features_status = AnalysisStatus.SUCCESS
    if _latest_for_property(session, ComparableSet, property_) is not None:
        state.comparable_status = AnalysisStatus.SUCCESS
    latest_llm = _latest_llm_for_property(session, property_)
    if latest_llm is not None:
        state.llm_status = AnalysisStatus(status_from_analysis_row(latest_llm))

    latest_rows = {
        "valuation": _latest_for_property(session, Valuation, property_),
        "liquidity": _latest_for_property(session, LiquidityAssessment, property_),
        "fast_sale": _latest_for_property(session, FastSaleEstimate, property_),
        "seller": _latest_for_property(session, SellerAssessment, property_),
        "risk": _latest_for_property(session, RiskAssessment, property_),
        "deal": _latest_for_property(session, DealAnalysis, property_),
        "opportunity": _latest_for_property(session, OpportunityAssessment, property_),
    }
    for module, row in latest_rows.items():
        if row is not None:
            setattr(
                state, MODULE_STATUS_COLUMNS[module], AnalysisStatus(status_from_analysis_row(row))
            )


def _latest_feature(session: Session, property_: Property) -> PropertyFeature | None:
    return session.scalars(
        select(PropertyFeature)
        .where(PropertyFeature.property_id == property_.id)
        .order_by(
            PropertyFeature.computed_at.desc(),
            PropertyFeature.created_at.desc(),
            PropertyFeature.id.desc(),
        )
    ).first()


def _latest_llm_for_property(session: Session, property_: Property) -> LlmAnalysis | None:
    return session.scalars(
        select(LlmAnalysis)
        .where(LlmAnalysis.property_id == property_.id)
        .order_by(
            LlmAnalysis.completed_at.desc().nullslast(),
            LlmAnalysis.created_at.desc(),
            LlmAnalysis.id.desc(),
        )
    ).first()


def _latest_for_property(
    session: Session,
    model: type[Any],
    property_: Property,
) -> Any | None:
    return session.scalars(
        select(model)
        .where(model.property_id == property_.id)
        .order_by(model.as_of.desc(), model.created_at.desc(), model.id.desc())
    ).first()


def _validated_modules(modules: Iterable[str]) -> list[str]:
    validated: list[str] = []
    for module in modules:
        validated.append(_validate_module(module))
    return validated


def _validate_module(module: str) -> str:
    if module not in MODULE_STATUS_COLUMNS:
        raise ValueError(f"Unknown analysis module: {module}")
    return module


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _utcnow() -> datetime:
    return datetime.now(UTC)
