from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.enums import (
    AlertChannel,
    AlertStatus,
    AlertType,
    AnalysisLevel,
    AnalysisStatus,
    ComparableType,
    CurrencyCode,
    DataSourceKind,
    DealAnalysisStatus,
    DealScenarioType,
    FastSaleStatus,
    InteractionType,
    LiquidityStatus,
    ListingEventType,
    ListingRawRecordType,
    ListingStatus,
    LlmAnalysisStatus,
    MatchCandidateStatus,
    MatchDecision,
    OfferStatus,
    OpportunityAction,
    PropertyOutcomeType,
    PropertyPipelineStatus,
    PropertyReviewDecision,
    PropertyType,
    ReasonForSale,
    RiskGateEffect,
    RiskGateStatus,
    RiskSeverity,
    SellerType,
    SkipReasonCode,
    SourceHealthStatus,
    ValuationModelType,
    ValuationStatus,
    WatchRuleType,
)


def _uuid_pk() -> uuid.UUID:
    return uuid.uuid4()


def _enum_column(enum_class: type[object], length: int) -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        enum_class,
        native_enum=False,
        values_callable=lambda enum_values: [item.value for item in enum_values],
        validate_strings=True,
        length=length,
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    source_type: Mapped[DataSourceKind] = mapped_column(
        _enum_column(DataSourceKind, 32),
        nullable=False,
    )
    base_url: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_discovery: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_market_scan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_detail_fetch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_transaction_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    runtime_state: Mapped[SourceRuntimeState | None] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        uselist=False,
    )
    listings: Mapped[list[Listing]] = relationship(back_populates="source")
    job_runs: Mapped[list[JobRun]] = relationship(back_populates="source")


class SourceRuntimeState(Base):
    __tablename__ = "source_runtime_state"

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_discovery_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_market_scan_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_type: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    recent_http_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recent_parse_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_zero_result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    health_status: Mapped[SourceHealthStatus] = mapped_column(
        _enum_column(SourceHealthStatus, 20),
        nullable=False,
        default=SourceHealthStatus.HEALTHY,
    )
    last_discovered_count: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    source: Mapped[Source] = relationship(back_populates="runtime_state")


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_type: Mapped[PropertyType] = mapped_column(
        _enum_column(PropertyType, 32),
        nullable=False,
    )
    country_code: Mapped[str | None] = mapped_column(String(2))
    city: Mapped[str | None] = mapped_column(String(120))
    municipality: Mapped[str | None] = mapped_column(String(120))
    neighborhood: Mapped[str | None] = mapped_column(String(120))
    micro_location: Mapped[str | None] = mapped_column(String(255))
    street: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    location_precision: Mapped[str | None] = mapped_column(String(50))
    location_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    size_m2: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    rooms: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    floor: Mapped[int | None] = mapped_column(Integer)
    total_floors: Mapped[int | None] = mapped_column(Integer)
    elevator: Mapped[bool | None] = mapped_column(Boolean)
    construction_year: Mapped[int | None] = mapped_column(Integer)
    building_type: Mapped[str | None] = mapped_column(String(100))
    heating_type: Mapped[str | None] = mapped_column(String(100))
    parking: Mapped[bool | None] = mapped_column(Boolean)
    garage: Mapped[bool | None] = mapped_column(Boolean)
    terrace: Mapped[bool | None] = mapped_column(Boolean)
    condition_category: Mapped[str | None] = mapped_column(String(100))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_listing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_market_age_days: Mapped[int | None] = mapped_column(Integer)
    relist_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pipeline_status: Mapped[PropertyPipelineStatus] = mapped_column(
        _enum_column(PropertyPipelineStatus, 40),
        nullable=False,
        default=PropertyPipelineStatus.NEW,
    )
    pipeline_status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    listings: Mapped[list[Listing]] = relationship(back_populates="property")
    listing_links: Mapped[list[PropertyListingLink]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    match_candidates: Mapped[list[PropertyMatchCandidate]] = relationship(
        back_populates="candidate_property",
        cascade="all, delete-orphan",
    )
    features: Mapped[list[PropertyFeature]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    data_quality_assessments: Mapped[list[DataQualityAssessment]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    comparable_sets: Mapped[list[ComparableSet]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    valuations: Mapped[list[Valuation]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    liquidity_assessments: Mapped[list[LiquidityAssessment]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    fast_sale_estimates: Mapped[list[FastSaleEstimate]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    llm_analyses: Mapped[list[LlmAnalysis]] = relationship(back_populates="property")
    seller_assessments: Mapped[list[SellerAssessment]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    risk_assessments: Mapped[list[RiskAssessment]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    deal_analyses: Mapped[list[DealAnalysis]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    opportunity_assessments: Mapped[list[OpportunityAssessment]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[list[Alert]] = relationship(back_populates="property")
    analysis_state: Mapped[PropertyAnalysisState | None] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
        uselist=False,
    )
    watch_rules: Mapped[list[WatchRule]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    watch_trigger_events: Mapped[list[WatchTriggerEvent]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    reviews: Mapped[list[PropertyReview]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    interactions: Mapped[list[Interaction]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    offers: Mapped[list[Offer]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    skip_records: Mapped[list[SkipRecord]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    outcomes: Mapped[list[PropertyOutcome]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    overrides: Mapped[list[PropertyOverride]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )
    pipeline_events: Mapped[list[PipelineStatusEvent]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
    )


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source_id", "external_listing_id", name="uq_listings_source_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_listing_id: Mapped[str] = mapped_column(String(255), nullable=False)
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="SET NULL"),
    )
    url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    asking_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[CurrencyCode | None] = mapped_column(_enum_column(CurrencyCode, 3))
    size_m2: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price_per_m2: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    city_raw: Mapped[str | None] = mapped_column(String(255))
    location_raw: Mapped[str | None] = mapped_column(Text)
    rooms: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    floor: Mapped[int | None] = mapped_column(Integer)
    total_floors: Mapped[int | None] = mapped_column(Integer)
    elevator: Mapped[bool | None] = mapped_column(Boolean)
    construction_year: Mapped[int | None] = mapped_column(Integer)
    building_type: Mapped[str | None] = mapped_column(String(100))
    heating_type: Mapped[str | None] = mapped_column(String(100))
    parking: Mapped[bool | None] = mapped_column(Boolean)
    garage: Mapped[bool | None] = mapped_column(Boolean)
    terrace: Mapped[bool | None] = mapped_column(Boolean)
    condition_raw: Mapped[str | None] = mapped_column(String(255))
    legal_status_raw: Mapped[str | None] = mapped_column(String(255))
    seller_type: Mapped[SellerType] = mapped_column(
        _enum_column(SellerType, 40),
        nullable=False,
        default=SellerType.UNKNOWN,
    )
    seller_name: Mapped[str | None] = mapped_column(String(255))
    agency_name: Mapped[str | None] = mapped_column(String(255))
    seller_phone: Mapped[str | None] = mapped_column(String(100))
    seller_contact_raw: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ListingStatus] = mapped_column(
        _enum_column(ListingStatus, 20),
        nullable=False,
        default=ListingStatus.UNKNOWN,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_detail_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_card_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    card_state_hash: Mapped[str | None] = mapped_column(String(128))
    detail_state_hash: Mapped[str | None] = mapped_column(String(128))
    llm_input_hash: Mapped[str | None] = mapped_column(String(128))
    crawl_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_not_seen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    source: Mapped[Source] = relationship(back_populates="listings")
    property: Mapped[Property | None] = relationship(back_populates="listings")
    events: Mapped[list[ListingEvent]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
    )
    raw_records: Mapped[list[ListingRawRecord]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
    )
    property_links: Mapped[list[PropertyListingLink]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
    )
    match_candidates: Mapped[list[PropertyMatchCandidate]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
    )
    comparable_items: Mapped[list[ComparableItem]] = relationship(back_populates="listing")
    llm_analyses: Mapped[list[LlmAnalysis]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
    )


class ListingEvent(Base):
    __tablename__ = "listing_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[ListingEventType] = mapped_column(
        _enum_column(ListingEventType, 40),
        nullable=False,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    old_value_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    new_value_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    new_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    listing: Mapped[Listing] = relationship(back_populates="events")


class PropertyAnalysisState(Base):
    __tablename__ = "property_analysis_state"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        primary_key=True,
    )
    features_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    matching_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    comparable_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    valuation_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    liquidity_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    fast_sale_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    llm_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    seller_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    risk_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    deal_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    opportunity_status: Mapped[AnalysisStatus] = mapped_column(
        _enum_column(AnalysisStatus, 20),
        nullable=False,
        default=AnalysisStatus.NOT_RUN,
    )
    last_analysis_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_analysis_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="analysis_state")


class WatchRule(Base):
    __tablename__ = "watch_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rule_type: Mapped[WatchRuleType | None] = mapped_column(
        _enum_column(WatchRuleType, 32),
    )
    threshold_numeric: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    rule_config_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    last_triggered_change_key: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    property: Mapped[Property] = relationship(back_populates="watch_rules")
    trigger_events: Mapped[list[WatchTriggerEvent]] = relationship(
        back_populates="watch_rule",
        cascade="all, delete-orphan",
    )


class WatchTriggerEvent(Base):
    __tablename__ = "watch_trigger_events"
    __table_args__ = (
        UniqueConstraint(
            "watch_rule_id",
            "change_key",
            name="uq_watch_trigger_events_rule_change_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    watch_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("watch_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    listing_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listing_events.id", ondelete="SET NULL"),
    )
    trigger_type: Mapped[WatchRuleType | None] = mapped_column(
        _enum_column(WatchRuleType, 32),
    )
    change_key: Mapped[str] = mapped_column(String(255), nullable=False)
    summary_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    invalidated_modules_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    reanalyzed_modules_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    previous_opportunity_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunity_assessments.id", ondelete="SET NULL"),
    )
    new_opportunity_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunity_assessments.id", ondelete="SET NULL"),
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("alerts.id", ondelete="SET NULL"),
    )
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    watch_rule: Mapped[WatchRule] = relationship(back_populates="trigger_events")
    property: Mapped[Property] = relationship(back_populates="watch_trigger_events")


class PropertyReview(Base):
    __tablename__ = "property_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decision: Mapped[PropertyReviewDecision] = mapped_column(
        _enum_column(PropertyReviewDecision, 24),
        nullable=False,
    )
    manual_fmv: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    manual_fast_sale_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    manual_max_buy_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="reviews")


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    interaction_type: Mapped[InteractionType] = mapped_column(
        _enum_column(InteractionType, 24),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="interactions")
    call_feedback: Mapped[CallFeedback | None] = relationship(
        back_populates="interaction",
        cascade="all, delete-orphan",
        uselist=False,
    )
    visit_feedback: Mapped[VisitFeedback | None] = relationship(
        back_populates="interaction",
        cascade="all, delete-orphan",
        uselist=False,
    )


class CallFeedback(Base):
    __tablename__ = "call_feedback"

    interaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interactions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seller_motivation: Mapped[AnalysisLevel | None] = mapped_column(_enum_column(AnalysisLevel, 16))
    reason_for_sale: Mapped[ReasonForSale | None] = mapped_column(_enum_column(ReasonForSale, 40))
    lowest_indicated_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    cash_preferred: Mapped[bool | None] = mapped_column(Boolean)
    desired_closing_days: Mapped[int | None] = mapped_column(Integer)
    viewing_available: Mapped[bool | None] = mapped_column(Boolean)
    claimed_registered: Mapped[bool | None] = mapped_column(Boolean)
    claimed_owner_1_1: Mapped[bool | None] = mapped_column(Boolean)
    claimed_mortgage: Mapped[bool | None] = mapped_column(Boolean)
    tenant_present: Mapped[bool | None] = mapped_column(Boolean)
    structured_notes_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    interaction: Mapped[Interaction] = relationship(back_populates="call_feedback")


class VisitFeedback(Base):
    __tablename__ = "visit_feedback"

    interaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interactions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    condition_category: Mapped[str | None] = mapped_column(String(100))
    estimated_renovation_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    estimated_renovation_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    estimated_renovation_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    layout_score: Mapped[int | None] = mapped_column(Integer)
    light_score: Mapped[int | None] = mapped_column(Integer)
    noise_score: Mapped[int | None] = mapped_column(Integer)
    building_score: Mapped[int | None] = mapped_column(Integer)
    entrance_score: Mapped[int | None] = mapped_column(Integer)
    parking_score: Mapped[int | None] = mapped_column(Integer)
    elevator_verified: Mapped[bool | None] = mapped_column(Boolean)
    visible_defects_json: Mapped[list[object]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    manual_fmv: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    manual_fast_sale_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    manual_max_buy_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    interaction: Mapped[Interaction] = relationship(back_populates="visit_feedback")


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[CurrencyCode] = mapped_column(_enum_column(CurrencyCode, 3), nullable=False)
    offer_type: Mapped[str | None] = mapped_column(String(40))
    conditions_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    status: Mapped[OfferStatus] = mapped_column(_enum_column(OfferStatus, 20), nullable=False)
    seller_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    counteroffer_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="offers")


class SkipRecord(Base):
    __tablename__ = "skip_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason_code: Mapped[SkipReasonCode] = mapped_column(
        _enum_column(SkipReasonCode, 32),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    skipped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    property: Mapped[Property] = relationship(back_populates="skip_records")


class PropertyOutcome(Base):
    __tablename__ = "property_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    outcome_type: Mapped[PropertyOutcomeType] = mapped_column(
        _enum_column(PropertyOutcomeType, 32),
        nullable=False,
    )
    outcome_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[CurrencyCode | None] = mapped_column(_enum_column(CurrencyCode, 3))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    source_kind: Mapped[DataSourceKind | None] = mapped_column(_enum_column(DataSourceKind, 32))
    source_reference: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="outcomes")


class PropertyOverride(Base):
    __tablename__ = "property_overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    source_kind: Mapped[DataSourceKind] = mapped_column(
        _enum_column(DataSourceKind, 32),
        nullable=False,
    )
    source_reference: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="overrides")


class PipelineStatusEvent(Base):
    __tablename__ = "pipeline_status_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_status: Mapped[PropertyPipelineStatus | None] = mapped_column(
        _enum_column(PropertyPipelineStatus, 40)
    )
    new_status: Mapped[PropertyPipelineStatus] = mapped_column(
        _enum_column(PropertyPipelineStatus, 40),
        nullable=False,
    )
    source_kind: Mapped[DataSourceKind] = mapped_column(
        _enum_column(DataSourceKind, 32),
        nullable=False,
    )
    source_reference: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="pipeline_events")


class ListingRawRecord(Base):
    __tablename__ = "listing_raw_records"
    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "record_type",
            "content_hash",
            name="uq_listing_raw_records_listing_type_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    record_type: Mapped[ListingRawRecordType] = mapped_column(
        _enum_column(ListingRawRecordType, 16),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    parser_version: Mapped[str | None] = mapped_column(String(100))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    listing: Mapped[Listing] = relationship(back_populates="raw_records")


class PropertyListingLink(Base):
    __tablename__ = "property_listing_links"
    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "property_id",
            "decision",
            "matching_version",
            name="uq_property_listing_links_listing_property_decision_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="RESTRICT"),
        nullable=False,
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[MatchDecision] = mapped_column(
        _enum_column(MatchDecision, 24),
        nullable=False,
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    matching_method: Mapped[str] = mapped_column(String(100), nullable=False)
    matching_version: Mapped[str] = mapped_column(String(100), nullable=False)
    reason_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    property: Mapped[Property] = relationship(back_populates="listing_links")
    listing: Mapped[Listing] = relationship(back_populates="property_links")


class PropertyMatchCandidate(Base):
    __tablename__ = "property_match_candidates"
    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "candidate_property_id",
            "matching_version",
            name="uq_property_match_candidates_listing_property_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="RESTRICT"),
        nullable=False,
    )
    similarity_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    location_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    size_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    rooms_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    image_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    text_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    other_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    matching_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[MatchCandidateStatus] = mapped_column(
        _enum_column(MatchCandidateStatus, 16),
        nullable=False,
        default=MatchCandidateStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    listing: Mapped[Listing] = relationship(back_populates="match_candidates")
    candidate_property: Mapped[Property] = relationship(back_populates="match_candidates")


class PropertyFeature(Base):
    __tablename__ = "property_features"
    __table_args__ = (
        UniqueConstraint(
            "property_id",
            "feature_version",
            name="uq_property_features_property_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    price_per_m2: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    listing_age_days: Mapped[int | None] = mapped_column(Integer)
    property_market_age_days: Mapped[int | None] = mapped_column(Integer)
    active_listing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    known_listing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relist_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_lowest_asking_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    current_highest_asking_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    total_price_drop_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    price_drop_7d_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    price_drop_30d_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    price_cut_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    days_since_last_price_cut: Mapped[int | None] = mapped_column(Integer)
    largest_price_cut_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    owner_listing_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    agency_listing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="features")


class DataQualityAssessment(Base):
    __tablename__ = "data_quality_assessments"
    __table_args__ = (
        UniqueConstraint(
            "property_id",
            "rules_version",
            name="uq_data_quality_assessments_property_rules",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    missing_critical_fields_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    positive_factors_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="data_quality_assessments")


class ComparableSet(Base):
    __tablename__ = "comparable_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    comparable_engine_version: Mapped[str] = mapped_column(String(100), nullable=False)
    search_parameters_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="comparable_sets")
    items: Mapped[list[ComparableItem]] = relationship(
        back_populates="comparable_set",
        cascade="all, delete-orphan",
    )
    valuations: Mapped[list[Valuation]] = relationship(
        back_populates="comparable_set",
        cascade="all, delete-orphan",
    )


class ComparableItem(Base):
    __tablename__ = "comparable_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    comparable_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("comparable_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    comparable_type: Mapped[ComparableType] = mapped_column(
        _enum_column(ComparableType, 24),
        nullable=False,
    )
    transaction_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="SET NULL"),
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="SET NULL"),
    )
    similarity_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    distance_m: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    age_days_at_analysis: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_per_m2: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    included_in_valuation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    exclusion_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    comparable_set: Mapped[ComparableSet] = relationship(back_populates="items")
    listing: Mapped[Listing | None] = relationship(back_populates="comparable_items")
    comparable_property: Mapped[Property | None] = relationship(foreign_keys=[property_id])


class Valuation(Base):
    __tablename__ = "valuations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    comparable_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("comparable_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ValuationStatus] = mapped_column(
        _enum_column(ValuationStatus, 32),
        nullable=False,
    )
    fair_value_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    fair_value_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    fair_value_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[CurrencyCode] = mapped_column(_enum_column(CurrencyCode, 3), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    data_quality_at_analysis: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    model_type: Mapped[ValuationModelType] = mapped_column(
        _enum_column(ValuationModelType, 40),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_summary_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    explanation_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="valuations")
    comparable_set: Mapped[ComparableSet] = relationship(back_populates="valuations")
    liquidity_assessments: Mapped[list[LiquidityAssessment]] = relationship(
        back_populates="valuation",
    )
    fast_sale_estimates: Mapped[list[FastSaleEstimate]] = relationship(
        back_populates="valuation",
    )
    deal_analyses: Mapped[list[DealAnalysis]] = relationship(back_populates="valuation")


class LiquidityAssessment(Base):
    __tablename__ = "liquidity_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    valuation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("valuations.id", ondelete="SET NULL"),
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[LiquidityStatus] = mapped_column(
        _enum_column(LiquidityStatus, 32),
        nullable=False,
    )
    liquidity_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    probability_sale_30d: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    probability_sale_60d: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    probability_sale_90d: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    positive_factors_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    negative_factors_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="liquidity_assessments")
    valuation: Mapped[Valuation | None] = relationship(back_populates="liquidity_assessments")
    fast_sale_estimates: Mapped[list[FastSaleEstimate]] = relationship(
        back_populates="liquidity_assessment",
    )
    deal_analyses: Mapped[list[DealAnalysis]] = relationship(
        back_populates="liquidity_assessment",
    )


class FastSaleEstimate(Base):
    __tablename__ = "fast_sale_estimates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    valuation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("valuations.id", ondelete="SET NULL"),
    )
    liquidity_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("liquidity_assessments.id", ondelete="SET NULL"),
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[FastSaleStatus] = mapped_column(
        _enum_column(FastSaleStatus, 32),
        nullable=False,
    )
    value_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    value_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    value_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    target_days: Mapped[int] = mapped_column(Integer, nullable=False)
    target_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    explanation_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="fast_sale_estimates")
    valuation: Mapped[Valuation | None] = relationship(back_populates="fast_sale_estimates")
    liquidity_assessment: Mapped[LiquidityAssessment | None] = relationship(
        back_populates="fast_sale_estimates",
    )
    deal_analyses: Mapped[list[DealAnalysis]] = relationship(
        back_populates="fast_sale_estimate",
    )


class LlmAnalysis(Base):
    __tablename__ = "llm_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="SET NULL"),
    )
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[LlmAnalysisStatus] = mapped_column(
        _enum_column(LlmAnalysisStatus, 32),
        nullable=False,
    )
    seller_motivation_level: Mapped[AnalysisLevel | None] = mapped_column(
        _enum_column(AnalysisLevel, 16),
    )
    seller_motivation_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    cash_preferred: Mapped[bool | None] = mapped_column(Boolean)
    cash_preference_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    negotiability_level: Mapped[AnalysisLevel | None] = mapped_column(
        _enum_column(AnalysisLevel, 16)
    )
    negotiability_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    reason_for_sale: Mapped[ReasonForSale | None] = mapped_column(
        _enum_column(ReasonForSale, 40),
    )
    reason_for_sale_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    condition_category: Mapped[str | None] = mapped_column(String(100))
    condition_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    structured_output_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    listing: Mapped[Listing] = relationship(back_populates="llm_analyses")
    property: Mapped[Property | None] = relationship(back_populates="llm_analyses")
    seller_assessments: Mapped[list[SellerAssessment]] = relationship(
        back_populates="primary_llm_analysis",
    )


class SellerAssessment(Base):
    __tablename__ = "seller_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    primary_llm_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_analyses.id", ondelete="SET NULL"),
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    seller_motivation_level: Mapped[AnalysisLevel] = mapped_column(
        _enum_column(AnalysisLevel, 16),
        nullable=False,
    )
    seller_motivation_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    seller_motivation_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    negotiability_level: Mapped[AnalysisLevel] = mapped_column(
        _enum_column(AnalysisLevel, 16),
        nullable=False,
    )
    negotiability_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    negotiability_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cash_preferred: Mapped[bool | None] = mapped_column(Boolean)
    cash_preference_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    reason_for_sale: Mapped[ReasonForSale] = mapped_column(
        _enum_column(ReasonForSale, 40),
        nullable=False,
    )
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="seller_assessments")
    primary_llm_analysis: Mapped[LlmAnalysis | None] = relationship(
        back_populates="seller_assessments",
    )


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hard_gate_status: Mapped[RiskGateStatus] = mapped_column(
        _enum_column(RiskGateStatus, 16),
        nullable=False,
    )
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="risk_assessments")
    flags: Mapped[list[RiskFlag]] = relationship(
        back_populates="risk_assessment",
        cascade="all, delete-orphan",
    )
    deal_analyses: Mapped[list[DealAnalysis]] = relationship(back_populates="risk_assessment")


class RiskFlag(Base):
    __tablename__ = "risk_flags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    risk_assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[RiskSeverity] = mapped_column(_enum_column(RiskSeverity, 16), nullable=False)
    gate_effect: Mapped[RiskGateEffect] = mapped_column(
        _enum_column(RiskGateEffect, 16),
        nullable=False,
    )
    source_kind: Mapped[DataSourceKind] = mapped_column(
        _enum_column(DataSourceKind, 32),
        nullable=False,
    )
    source_reference: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    risk_assessment: Mapped[RiskAssessment] = relationship(back_populates="flags")


class CostProfile(Base):
    __tablename__ = "cost_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    currency: Mapped[CurrencyCode] = mapped_column(_enum_column(CurrencyCode, 3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    purchase_tax_rule_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    notary_rule_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    lawyer_rule_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    agency_rule_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    sale_cost_rule_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    holding_cost_rule_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    financing_rule_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    other_cost_rule_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    deal_analyses: Mapped[list[DealAnalysis]] = relationship(back_populates="cost_profile")


class InvestmentProfile(Base):
    __tablename__ = "investment_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_expected_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_downside_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_roi: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    max_expected_holding_days: Mapped[int | None] = mapped_column(Integer)
    min_liquidity_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    min_valuation_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    default_risk_reserve: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    desired_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    deal_analyses: Mapped[list[DealAnalysis]] = relationship(back_populates="investment_profile")


class DealAnalysis(Base):
    __tablename__ = "deal_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    valuation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("valuations.id", ondelete="SET NULL"),
    )
    liquidity_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("liquidity_assessments.id", ondelete="SET NULL"),
    )
    fast_sale_estimate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fast_sale_estimates.id", ondelete="SET NULL"),
    )
    risk_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_assessments.id", ondelete="SET NULL"),
    )
    cost_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cost_profiles.id", ondelete="RESTRICT"),
    )
    investment_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investment_profiles.id", ondelete="RESTRICT"),
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[DealAnalysisStatus] = mapped_column(
        _enum_column(DealAnalysisStatus, 32),
        nullable=False,
    )
    assumed_purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    asking_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    purchase_costs: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    renovation_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    sale_costs: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    taxes: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    financing_costs: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    holding_costs: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    risk_reserve: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    other_costs: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    total_cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    expected_exit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    max_buy_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    required_negotiation_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    required_negotiation_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    expected_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    downside_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    upside_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    roi: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    annualized_roi: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    expected_holding_days: Mapped[int | None] = mapped_column(Integer)
    capital_days: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    profit_per_capital_day: Mapped[Decimal | None] = mapped_column(Numeric(18, 10))
    formula_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_summary_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    explanation_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="deal_analyses")
    valuation: Mapped[Valuation | None] = relationship(back_populates="deal_analyses")
    liquidity_assessment: Mapped[LiquidityAssessment | None] = relationship(
        back_populates="deal_analyses",
    )
    fast_sale_estimate: Mapped[FastSaleEstimate | None] = relationship(
        back_populates="deal_analyses",
    )
    risk_assessment: Mapped[RiskAssessment | None] = relationship(
        back_populates="deal_analyses",
    )
    cost_profile: Mapped[CostProfile | None] = relationship(back_populates="deal_analyses")
    investment_profile: Mapped[InvestmentProfile | None] = relationship(
        back_populates="deal_analyses",
    )
    scenarios: Mapped[list[DealScenario]] = relationship(
        back_populates="deal_analysis",
        cascade="all, delete-orphan",
    )
    opportunity_assessments: Mapped[list[OpportunityAssessment]] = relationship(
        back_populates="deal_analysis",
    )


class DealScenario(Base):
    __tablename__ = "deal_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    deal_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario_type: Mapped[DealScenarioType] = mapped_column(
        _enum_column(DealScenarioType, 16),
        nullable=False,
    )
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    exit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    profit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    roi: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    holding_days: Mapped[int] = mapped_column(Integer, nullable=False)
    assumptions_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    deal_analysis: Mapped[DealAnalysis] = relationship(back_populates="scenarios")


class OpportunityAssessment(Base):
    __tablename__ = "opportunity_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    deal_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_analyses.id", ondelete="SET NULL"),
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recommended_action: Mapped[OpportunityAction] = mapped_column(
        _enum_column(OpportunityAction, 24),
        nullable=False,
    )
    opportunity_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ranking_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    reason_codes_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    explanation_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(100), nullable=False)
    state_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    property: Mapped[Property] = relationship(back_populates="opportunity_assessments")
    deal_analysis: Mapped[DealAnalysis | None] = relationship(
        back_populates="opportunity_assessments",
    )
    alerts: Mapped[list[Alert]] = relationship(
        back_populates="opportunity_assessment",
        cascade="all, delete-orphan",
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_alerts_dedupe_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="SET NULL"),
    )
    opportunity_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunity_assessments.id", ondelete="SET NULL"),
    )
    channel: Mapped[AlertChannel] = mapped_column(
        _enum_column(AlertChannel, 32),
        nullable=False,
    )
    alert_type: Mapped[AlertType] = mapped_column(
        _enum_column(AlertType, 32),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(100))
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        _enum_column(AlertStatus, 20),
        nullable=False,
    )
    send_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)

    property: Mapped[Property | None] = relationship(back_populates="alerts")
    opportunity_assessment: Mapped[OpportunityAssessment | None] = relationship(
        back_populates="alerts",
    )


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid_pk)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    items_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cards_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cards_parsed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_listings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_listings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_seen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parse_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    source: Mapped[Source | None] = relationship(back_populates="job_runs")
