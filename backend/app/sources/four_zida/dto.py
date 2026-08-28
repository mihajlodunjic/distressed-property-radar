from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RawListingCard:
    external_listing_id: str
    url: str
    canonical_url: str
    title_raw: str | None = None
    price_raw: str | None = None
    currency_raw: str | None = None
    location_raw: str | None = None
    size_raw: str | None = None
    rooms_raw: str | None = None
    floor_raw: str | None = None
    source_published_at_raw: str | None = None
    additional_card_data: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RawListingDetail:
    external_listing_id: str
    url: str
    canonical_url: str
    title_raw: str | None = None
    description_raw: str | None = None
    price_raw: str | None = None
    currency_raw: str | None = None
    size_raw: str | None = None
    location_raw: str | None = None
    rooms_raw: str | None = None
    floor_raw: str | None = None
    seller_raw: str | None = None
    agency_raw: str | None = None
    property_attributes_raw: dict[str, object] = field(default_factory=dict)
    image_urls: list[str] = field(default_factory=list)
    source_published_at_raw: str | None = None
    raw_payload_reference: str | None = None
