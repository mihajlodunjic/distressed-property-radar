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
    CurrencyCode,
    DataSourceKind,
    ListingEventType,
    ListingRawRecordType,
    ListingStatus,
    MatchCandidateStatus,
    MatchDecision,
    PropertyPipelineStatus,
    PropertyType,
    SellerType,
    SourceHealthStatus,
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
