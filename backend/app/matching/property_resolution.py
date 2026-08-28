from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Listing, Property, PropertyListingLink, PropertyMatchCandidate
from app.domain.enums import (
    ListingStatus,
    MatchCandidateStatus,
    MatchDecision,
    PropertyPipelineStatus,
    PropertyType,
)

MATCHING_VERSION = "deterministic_v1"
MATCHING_METHOD = "structured_text_v1"
NEW_PROPERTY_METHOD = "new_property_v1"
MANUAL_METHOD = "manual"

AUTO_MATCH_THRESHOLD = Decimal("0.8800")
POSSIBLE_MATCH_THRESHOLD = Decimal("0.6000")
SCORE_QUANTIZER = Decimal("0.0001")
SIZE_CANDIDATE_WINDOW_M2 = Decimal("25.00")
ROOM_CANDIDATE_WINDOW = Decimal("2.00")

ResolutionAction = Literal[
    "AUTO_MATCH",
    "POSSIBLE_MATCH",
    "NEW_PROPERTY",
    "EXISTING_LINK",
    "MANUAL_PRESERVED",
]

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


@dataclass(frozen=True)
class ScoredPropertyCandidate:
    property: Property
    similarity_score: Decimal
    location_score: Decimal | None
    size_score: Decimal | None
    rooms_score: Decimal | None
    text_score: Decimal | None
    other_score: Decimal | None
    reason_json: dict[str, object]


@dataclass(frozen=True)
class PropertyResolutionResult:
    listing_id: str
    action: ResolutionAction
    property_id: str | None = None
    candidate_id: str | None = None
    similarity_score: Decimal | None = None
    rejected_candidates: int = 0


@dataclass
class PropertyResolutionSummary:
    processed: int = 0
    auto_matched: int = 0
    possible_matches: int = 0
    new_properties: int = 0
    existing_links: int = 0
    manual_preserved: int = 0
    rejected_candidates: int = 0


def resolve_listings_to_properties(
    session: Session,
    *,
    limit: int | None = None,
    matching_version: str = MATCHING_VERSION,
    commit: bool = False,
) -> PropertyResolutionSummary:
    stmt = select(Listing).order_by(Listing.created_at, Listing.id)
    if limit is not None:
        stmt = stmt.limit(limit)
    listings = session.scalars(stmt).all()

    summary = PropertyResolutionSummary()
    for listing in listings:
        result = resolve_listing_to_property(
            session,
            listing,
            matching_version=matching_version,
        )
        summary.processed += 1
        if result.action == "AUTO_MATCH":
            summary.auto_matched += 1
        elif result.action == "POSSIBLE_MATCH":
            summary.possible_matches += 1
        elif result.action == "NEW_PROPERTY":
            summary.new_properties += 1
        elif result.action == "EXISTING_LINK":
            summary.existing_links += 1
        elif result.action == "MANUAL_PRESERVED":
            summary.manual_preserved += 1
        summary.rejected_candidates += result.rejected_candidates

    if commit:
        session.commit()
    return summary


def resolve_listing_to_property(
    session: Session,
    listing: Listing,
    *,
    matching_version: str = MATCHING_VERSION,
    now: datetime | None = None,
) -> PropertyResolutionResult:
    resolved_at = now or _utcnow()
    if listing.property_id is not None:
        property_ = session.get(Property, listing.property_id)
        if property_ is not None:
            _refresh_property_summary(session, property_)
        if _has_current_manual_link(session, listing):
            return PropertyResolutionResult(
                listing_id=str(listing.id),
                action="MANUAL_PRESERVED",
                property_id=str(listing.property_id),
            )
        return PropertyResolutionResult(
            listing_id=str(listing.id),
            action="EXISTING_LINK",
            property_id=str(listing.property_id),
        )

    candidates = generate_property_candidates(
        session,
        listing,
        matching_version=matching_version,
    )
    if candidates:
        best_candidate = candidates[0]
        if _is_auto_match(listing, best_candidate):
            candidate_record = _upsert_candidate(
                session,
                listing=listing,
                scored_candidate=best_candidate,
                status=MatchCandidateStatus.ACCEPTED,
                matching_version=matching_version,
                resolved_at=resolved_at,
            )
            _link_listing_to_property(
                session,
                listing=listing,
                property_=best_candidate.property,
                decision=MatchDecision.AUTO_MATCH,
                confidence=best_candidate.similarity_score,
                matching_method=MATCHING_METHOD,
                matching_version=matching_version,
                reason_json=best_candidate.reason_json,
                confirmed_at=None,
            )
            _refresh_property_summary(session, best_candidate.property)
            return PropertyResolutionResult(
                listing_id=str(listing.id),
                action="AUTO_MATCH",
                property_id=str(best_candidate.property.id),
                candidate_id=str(candidate_record.id),
                similarity_score=best_candidate.similarity_score,
            )

        unresolved = [
            candidate
            for candidate in candidates
            if _existing_candidate_status(session, listing, candidate.property, matching_version)
            != MatchCandidateStatus.REJECTED
        ]
        possible = [
            candidate
            for candidate in unresolved
            if candidate.similarity_score >= POSSIBLE_MATCH_THRESHOLD
            and not _has_hard_structured_conflict(listing, candidate)
        ]
        if possible:
            candidate_record = _upsert_candidate(
                session,
                listing=listing,
                scored_candidate=possible[0],
                status=MatchCandidateStatus.PENDING,
                matching_version=matching_version,
                resolved_at=None,
            )
            return PropertyResolutionResult(
                listing_id=str(listing.id),
                action="POSSIBLE_MATCH",
                candidate_id=str(candidate_record.id),
                similarity_score=possible[0].similarity_score,
            )

        rejected_count = 0
        for candidate in unresolved:
            _upsert_candidate(
                session,
                listing=listing,
                scored_candidate=candidate,
                status=MatchCandidateStatus.REJECTED,
                matching_version=matching_version,
                resolved_at=resolved_at,
            )
            rejected_count += 1

    property_ = _create_property_from_listing(session, listing)
    _link_listing_to_property(
        session,
        listing=listing,
        property_=property_,
        decision=MatchDecision.AUTO_MATCH,
        confidence=Decimal("1.0000"),
        matching_method=NEW_PROPERTY_METHOD,
        matching_version=matching_version,
        reason_json={
            "action": "created_new_property",
            "reason": "no_conservative_existing_property_match",
        },
        confirmed_at=None,
    )
    _refresh_property_summary(session, property_)
    return PropertyResolutionResult(
        listing_id=str(listing.id),
        action="NEW_PROPERTY",
        property_id=str(property_.id),
        similarity_score=Decimal("1.0000"),
        rejected_candidates=rejected_count if candidates else 0,
    )


def generate_property_candidates(
    session: Session,
    listing: Listing,
    *,
    matching_version: str = MATCHING_VERSION,
    limit: int = 20,
) -> list[ScoredPropertyCandidate]:
    stmt = select(Property).where(Property.property_type == PropertyType.APARTMENT)
    if listing.property_id is not None:
        stmt = stmt.where(Property.id != listing.property_id)

    cheap_filters = []
    if listing.size_m2 is not None:
        cheap_filters.append(
            or_(
                Property.size_m2.is_(None),
                Property.size_m2.between(
                    listing.size_m2 - SIZE_CANDIDATE_WINDOW_M2,
                    listing.size_m2 + SIZE_CANDIDATE_WINDOW_M2,
                ),
            )
        )
    if listing.rooms is not None:
        cheap_filters.append(
            or_(
                Property.rooms.is_(None),
                Property.rooms.between(
                    listing.rooms - ROOM_CANDIDATE_WINDOW,
                    listing.rooms + ROOM_CANDIDATE_WINDOW,
                ),
            )
        )
    if not cheap_filters:
        return []

    stmt = stmt.where(*cheap_filters).order_by(Property.created_at, Property.id).limit(limit * 3)
    scored_candidates: list[ScoredPropertyCandidate] = []
    for property_ in session.scalars(stmt).all():
        scored = _score_property_candidate(listing, property_)
        if scored is None:
            continue
        if _existing_candidate_status(session, listing, property_, matching_version) == (
            MatchCandidateStatus.REJECTED
        ):
            continue
        scored_candidates.append(scored)

    return sorted(
        scored_candidates,
        key=lambda candidate: candidate.similarity_score,
        reverse=True,
    )[:limit]


def manually_match_listing_to_property(
    session: Session,
    *,
    listing: Listing,
    property_: Property,
    reason_json: dict[str, object] | None = None,
    matching_version: str = MATCHING_VERSION,
    confirmed_at: datetime | None = None,
) -> PropertyListingLink:
    confirmed = confirmed_at or _utcnow()
    old_property = session.get(Property, listing.property_id) if listing.property_id else None
    link = _link_listing_to_property(
        session,
        listing=listing,
        property_=property_,
        decision=MatchDecision.MANUAL_MATCH,
        confidence=Decimal("1.0000"),
        matching_method=MANUAL_METHOD,
        matching_version=matching_version,
        reason_json=reason_json or {"action": "manual_match"},
        confirmed_at=confirmed,
    )

    candidate = _existing_candidate(session, listing, property_, matching_version)
    if candidate is not None and candidate.status != MatchCandidateStatus.ACCEPTED:
        candidate.status = MatchCandidateStatus.ACCEPTED
        candidate.resolved_at = confirmed

    if old_property is not None and old_property.id != property_.id:
        _refresh_property_summary(session, old_property)
    _refresh_property_summary(session, property_)
    return link


def reject_match_candidate(
    session: Session,
    *,
    candidate: PropertyMatchCandidate,
    resolved_at: datetime | None = None,
) -> PropertyMatchCandidate:
    candidate.status = MatchCandidateStatus.REJECTED
    candidate.resolved_at = resolved_at or _utcnow()
    return candidate


def _score_property_candidate(
    listing: Listing,
    property_: Property,
) -> ScoredPropertyCandidate | None:
    location_score = _location_score(listing, property_)
    size_score = _numeric_score(listing.size_m2, property_.size_m2, Decimal("1"), Decimal("5"))
    rooms_score = _numeric_score(listing.rooms, property_.rooms, Decimal("0.5"), Decimal("1.5"))
    floor_score = _integer_score(listing.floor, property_.floor, exact_window=0, weak_window=1)
    text_score = _text_score(listing, property_)

    if location_score is None and (size_score is None or size_score < Decimal("0.8000")):
        return None

    similarity_score = _weighted_score(
        [
            (location_score, Decimal("0.35")),
            (size_score, Decimal("0.25")),
            (rooms_score, Decimal("0.15")),
            (floor_score, Decimal("0.10")),
            (text_score, Decimal("0.15")),
        ]
    )
    if similarity_score is None:
        return None

    return ScoredPropertyCandidate(
        property=property_,
        similarity_score=similarity_score,
        location_score=location_score,
        size_score=size_score,
        rooms_score=rooms_score,
        text_score=text_score,
        other_score=floor_score,
        reason_json={
            "signals": {
                "location_score": _score_to_json(location_score),
                "size_score": _score_to_json(size_score),
                "rooms_score": _score_to_json(rooms_score),
                "floor_score": _score_to_json(floor_score),
                "text_score": _score_to_json(text_score),
            }
        },
    )


def _is_auto_match(listing: Listing, candidate: ScoredPropertyCandidate) -> bool:
    if candidate.similarity_score < AUTO_MATCH_THRESHOLD:
        return False
    if candidate.location_score is None or candidate.location_score < Decimal("0.8500"):
        return False
    if candidate.size_score is None or candidate.size_score < Decimal("0.9000"):
        return False
    if candidate.rooms_score is not None and candidate.rooms_score < Decimal("0.7500"):
        return False
    if listing.floor is None or candidate.property.floor is None:
        return False
    return candidate.other_score is not None and candidate.other_score >= Decimal("0.6500")


def _has_hard_structured_conflict(
    listing: Listing,
    candidate: ScoredPropertyCandidate,
) -> bool:
    if candidate.size_score == Decimal("0.0000"):
        return True
    if candidate.rooms_score == Decimal("0.0000"):
        return True
    if (
        listing.floor is not None
        and candidate.property.floor is not None
        and abs(listing.floor - candidate.property.floor) > 1
    ):
        return True
    return False


def _upsert_candidate(
    session: Session,
    *,
    listing: Listing,
    scored_candidate: ScoredPropertyCandidate,
    status: MatchCandidateStatus,
    matching_version: str,
    resolved_at: datetime | None,
) -> PropertyMatchCandidate:
    candidate = _existing_candidate(session, listing, scored_candidate.property, matching_version)
    if candidate is None:
        candidate = PropertyMatchCandidate(
            listing=listing,
            candidate_property=scored_candidate.property,
            similarity_score=scored_candidate.similarity_score,
            location_score=scored_candidate.location_score,
            size_score=scored_candidate.size_score,
            rooms_score=scored_candidate.rooms_score,
            image_score=None,
            text_score=scored_candidate.text_score,
            other_score=scored_candidate.other_score,
            matching_version=matching_version,
            status=status,
            resolved_at=resolved_at,
        )
        session.add(candidate)
        session.flush()
        return candidate

    if candidate.status == MatchCandidateStatus.REJECTED:
        return candidate

    candidate.similarity_score = scored_candidate.similarity_score
    candidate.location_score = scored_candidate.location_score
    candidate.size_score = scored_candidate.size_score
    candidate.rooms_score = scored_candidate.rooms_score
    candidate.image_score = None
    candidate.text_score = scored_candidate.text_score
    candidate.other_score = scored_candidate.other_score
    candidate.status = status
    candidate.resolved_at = resolved_at
    return candidate


def _link_listing_to_property(
    session: Session,
    *,
    listing: Listing,
    property_: Property,
    decision: MatchDecision,
    confidence: Decimal,
    matching_method: str,
    matching_version: str,
    reason_json: dict[str, object] | None,
    confirmed_at: datetime | None,
) -> PropertyListingLink:
    existing = session.scalars(
        select(PropertyListingLink).where(
            PropertyListingLink.listing_id == listing.id,
            PropertyListingLink.property_id == property_.id,
            PropertyListingLink.decision == decision,
            PropertyListingLink.matching_version == matching_version,
        )
    ).one_or_none()
    listing.property = property_
    if existing is not None:
        if decision == MatchDecision.MANUAL_MATCH and existing.confirmed_at is None:
            existing.confirmed_at = confirmed_at
        return existing

    link = PropertyListingLink(
        listing=listing,
        property=property_,
        decision=decision,
        match_confidence=_quantize_score(confidence),
        matching_method=matching_method,
        matching_version=matching_version,
        reason_json=reason_json,
        confirmed_at=confirmed_at,
    )
    session.add(link)
    session.flush()
    return link


def _create_property_from_listing(session: Session, listing: Listing) -> Property:
    property_ = Property(
        property_type=PropertyType.APARTMENT,
        country_code="RS",
        city=listing.city_raw,
        municipality=_municipality_from_text(_listing_location_text(listing)),
        micro_location=_clean_text(listing.location_raw),
        street=None,
        size_m2=listing.size_m2,
        rooms=listing.rooms,
        bedrooms=listing.bedrooms,
        floor=listing.floor,
        total_floors=listing.total_floors,
        first_seen_at=listing.first_seen_at,
        last_seen_at=listing.last_seen_at,
        active_listing_count=1 if listing.status == ListingStatus.ACTIVE else 0,
        relist_count=0,
        pipeline_status=PropertyPipelineStatus.NEW,
        pipeline_status_updated_at=_utcnow(),
    )
    session.add(property_)
    session.flush()
    return property_


def _refresh_property_summary(session: Session, property_: Property) -> None:
    linked_listings = session.scalars(
        select(Listing).where(Listing.property_id == property_.id)
    ).all()
    if not linked_listings:
        property_.active_listing_count = 0
        property_.relist_count = 0
        return

    first_seen_values = [
        listing.first_seen_at for listing in linked_listings if listing.first_seen_at
    ]
    last_seen_values = [listing.last_seen_at for listing in linked_listings if listing.last_seen_at]
    if first_seen_values:
        property_.first_seen_at = min(first_seen_values)
    if last_seen_values:
        property_.last_seen_at = max(last_seen_values)
    property_.active_listing_count = sum(
        1 for listing in linked_listings if listing.status == ListingStatus.ACTIVE
    )
    property_.relist_count = max(len(linked_listings) - 1, 0)

    for listing in linked_listings:
        _fill_property_unknowns_from_listing(property_, listing)


def _fill_property_unknowns_from_listing(property_: Property, listing: Listing) -> None:
    if property_.country_code is None:
        property_.country_code = "RS"
    if property_.city is None:
        property_.city = listing.city_raw
    if property_.municipality is None:
        property_.municipality = _municipality_from_text(_listing_location_text(listing))
    if property_.micro_location is None:
        property_.micro_location = _clean_text(listing.location_raw)
    if property_.size_m2 is None:
        property_.size_m2 = listing.size_m2
    if property_.rooms is None:
        property_.rooms = listing.rooms
    if property_.bedrooms is None:
        property_.bedrooms = listing.bedrooms
    if property_.floor is None:
        property_.floor = listing.floor
    if property_.total_floors is None:
        property_.total_floors = listing.total_floors


def _has_current_manual_link(session: Session, listing: Listing) -> bool:
    if listing.property_id is None:
        return False
    return (
        session.scalars(
            select(PropertyListingLink.id).where(
                PropertyListingLink.listing_id == listing.id,
                PropertyListingLink.property_id == listing.property_id,
                PropertyListingLink.decision == MatchDecision.MANUAL_MATCH,
            )
        ).first()
        is not None
    )


def _existing_candidate(
    session: Session,
    listing: Listing,
    property_: Property,
    matching_version: str,
) -> PropertyMatchCandidate | None:
    return session.scalars(
        select(PropertyMatchCandidate).where(
            PropertyMatchCandidate.listing_id == listing.id,
            PropertyMatchCandidate.candidate_property_id == property_.id,
            PropertyMatchCandidate.matching_version == matching_version,
        )
    ).one_or_none()


def _existing_candidate_status(
    session: Session,
    listing: Listing,
    property_: Property,
    matching_version: str,
) -> MatchCandidateStatus | None:
    candidate = _existing_candidate(session, listing, property_, matching_version)
    return candidate.status if candidate is not None else None


def _location_score(listing: Listing, property_: Property) -> Decimal | None:
    listing_text = _listing_location_text(listing)
    property_text = _property_location_text(property_)
    if not listing_text or not property_text:
        return None

    listing_tokens = _tokens(listing_text)
    property_tokens = _tokens(property_text)
    if not listing_tokens or not property_tokens:
        return None
    if property_tokens.issubset(listing_tokens) or listing_tokens.issubset(property_tokens):
        return Decimal("1.0000")

    overlap = listing_tokens & property_tokens
    if not overlap:
        return None
    ratio = Decimal(len(overlap)) / Decimal(min(len(listing_tokens), len(property_tokens)))
    if ratio >= Decimal("0.7500"):
        return Decimal("0.8500")
    if ratio >= Decimal("0.5000"):
        return Decimal("0.6500")
    return Decimal("0.3500")


def _numeric_score(
    listing_value: Decimal | None,
    property_value: Decimal | None,
    strong_window: Decimal,
    weak_window: Decimal,
) -> Decimal | None:
    if listing_value is None or property_value is None:
        return None
    difference = abs(listing_value - property_value)
    if difference == 0:
        return Decimal("1.0000")
    if difference <= strong_window:
        return Decimal("0.9500")
    if difference <= weak_window:
        return Decimal("0.7500")
    if difference <= weak_window * 2:
        return Decimal("0.3500")
    return Decimal("0.0000")


def _integer_score(
    listing_value: int | None,
    property_value: int | None,
    *,
    exact_window: int,
    weak_window: int,
) -> Decimal | None:
    if listing_value is None or property_value is None:
        return None
    difference = abs(listing_value - property_value)
    if difference <= exact_window:
        return Decimal("1.0000")
    if difference <= weak_window:
        return Decimal("0.6500")
    return Decimal("0.0000")


def _text_score(listing: Listing, property_: Property) -> Decimal | None:
    listing_tokens = _tokens(
        " ".join(value for value in (listing.title, listing.description) if value)
    )
    property_tokens = _tokens(
        " ".join(
            value
            for value in (
                property_.street,
                property_.micro_location,
                property_.neighborhood,
                property_.municipality,
            )
            if value
        )
    )
    if not listing_tokens or not property_tokens:
        return None
    intersection = listing_tokens & property_tokens
    if not intersection:
        return Decimal("0.0000")
    return _quantize_score(
        Decimal(len(intersection)) / Decimal(len(listing_tokens | property_tokens))
    )


def _weighted_score(
    weighted_scores: list[tuple[Decimal | None, Decimal]],
) -> Decimal | None:
    usable_scores = [(score, weight) for score, weight in weighted_scores if score is not None]
    if not usable_scores:
        return None
    weighted_total = sum((score * weight for score, weight in usable_scores), Decimal("0"))
    weight_total = sum((weight for _score, weight in usable_scores), Decimal("0"))
    if weight_total == 0:
        return None
    return _quantize_score(weighted_total / weight_total)


def _quantize_score(value: Decimal) -> Decimal:
    return value.quantize(SCORE_QUANTIZER, rounding=ROUND_HALF_UP)


def _score_to_json(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _listing_location_text(listing: Listing) -> str:
    return " ".join(
        value
        for value in (
            listing.location_raw,
            listing.city_raw,
            listing.title,
            listing.canonical_url,
            listing.url,
        )
        if value
    ).lower()


def _property_location_text(property_: Property) -> str:
    return " ".join(
        value
        for value in (
            property_.street,
            property_.micro_location,
            property_.neighborhood,
            property_.municipality,
            property_.city,
        )
        if value
    ).lower()


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if len(token) > 1}


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    return text or None


def _municipality_from_text(value: str) -> str | None:
    normalized = value.lower().replace("-", " ")
    if "novi beograd" in normalized:
        return "Novi Beograd"
    if "zemun" in normalized:
        return "Zemun"
    return None


def _utcnow() -> datetime:
    return datetime.now(UTC)
