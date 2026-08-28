from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from app.sources.four_zida.dto import RawListingCard, RawListingDetail

BASE_URL = "https://www.4zida.rs"
PARSER_VERSION = "four_zida_json_ld_v1"

_JSON_LD_RE = re.compile(
    r"<script\b(?=[^>]*type=[\"']application/ld\+json[\"'])[^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)
_DETAIL_PATH_RE = re.compile(r"^/prodaja-stanova/.+/[0-9a-f]{24}$", re.IGNORECASE)
_DETAIL_URL_RE = re.compile(
    r"https://www\.4zida\.rs(?P<path>/prodaja-stanova/.+/[0-9a-f]{24})",
    re.IGNORECASE,
)
_META_RE = re.compile(
    r"<meta\b(?=[^>]*(?:name|property)=[\"'](?P<name>[^\"']+)[\"'])"
    r"(?=[^>]*content=[\"'](?P<content>[^\"']*)[\"'])[^>]*>",
    re.IGNORECASE,
)
_FLOOR_RE = re.compile(r"(?:na\s+)?(?:\d+\.?\s*spratu|prizemlju|prizemlje)", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedSearchPage:
    cards: list[RawListingCard]
    next_page_url: str | None


def parse_search_page(html: str, page_url: str) -> ParsedSearchPage:
    cards = _cards_from_item_list(html)
    if not cards:
        cards = _cards_from_links(html)
    return ParsedSearchPage(
        cards=_dedupe_cards(cards),
        next_page_url=_next_page_url(html, page_url),
    )


def parse_detail_page(html: str, page_url: str) -> RawListingDetail:
    json_ld_items = _json_ld_items(html)
    listing = _first_typed(json_ld_items, "RealEstateListing") or {}
    offer = _first_typed(json_ld_items, "Offer") or {}
    apartment = _first_typed(json_ld_items, "Apartment") or {}
    place = _first_typed(json_ld_items, "Place") or {}
    seller = _seller(json_ld_items) or {}
    meta = _meta_values(html)

    canonical_url = _canonical_url(str(listing.get("url") or offer.get("url") or page_url))
    external_listing_id = _external_listing_id(canonical_url)
    if external_listing_id is None:
        raise ValueError(f"Cannot derive 4zida listing id from detail URL: {page_url}")

    title = _string_or_none(
        listing.get("name") or apartment.get("name") or meta.get("og:title") or meta.get("title")
    )
    description = _string_or_none(
        listing.get("description")
        or apartment.get("description")
        or meta.get("description")
        or meta.get("og:description")
    )

    address = _dict_or_empty(place.get("address")) or _dict_or_empty(apartment.get("address"))
    area = _dict_or_empty(apartment.get("area")) or _dict_or_empty(apartment.get("floorSize"))

    image_urls = _image_urls(apartment.get("image"))
    seller_name = _string_or_none(seller.get("name"))
    seller_type = _string_or_none(seller.get("@type"))

    return RawListingDetail(
        external_listing_id=external_listing_id,
        url=canonical_url,
        canonical_url=canonical_url,
        title_raw=title,
        description_raw=description,
        price_raw=_string_or_none(offer.get("price")),
        currency_raw=_string_or_none(offer.get("priceCurrency")),
        size_raw=_string_or_none(area.get("value")),
        location_raw=_location_from_address(address) or _location_from_url(canonical_url),
        rooms_raw=_string_or_none(apartment.get("numberOfRooms")),
        floor_raw=_floor_from_description(description),
        seller_raw=seller_name,
        agency_raw=seller_name if seller_type == "Organization" else None,
        property_attributes_raw={
            "identifier": listing.get("identifier"),
            "apartment": _json_safe(apartment),
            "offer": _json_safe(offer),
            "place": _json_safe(place),
            "seller": _json_safe(seller),
        },
        image_urls=image_urls,
        source_published_at_raw=_string_or_none(
            listing.get("datePosted") or listing.get("datePublished")
        ),
        raw_payload_reference=f"{canonical_url}#json-ld",
    )


def _cards_from_item_list(html: str) -> list[RawListingCard]:
    cards: list[RawListingCard] = []
    for item_list in _typed_items(_json_ld_items(html), "ItemList"):
        for list_item in _list_or_empty(item_list.get("itemListElement")):
            list_item_dict = _dict_or_empty(list_item)
            listing = _dict_or_empty(list_item_dict.get("item"))
            url = _string_or_none(list_item_dict.get("url") or listing.get("url"))
            if url is None:
                continue
            canonical_url = _canonical_url(url)
            external_listing_id = _external_listing_id(canonical_url)
            if external_listing_id is None:
                continue
            offer = _dict_or_empty(listing.get("offers"))
            apartment = _dict_or_empty(listing.get("itemOffered"))
            floor_size = _dict_or_empty(apartment.get("floorSize")) or _dict_or_empty(
                apartment.get("area")
            )
            cards.append(
                RawListingCard(
                    external_listing_id=external_listing_id,
                    url=canonical_url,
                    canonical_url=canonical_url,
                    title_raw=_string_or_none(listing.get("name")),
                    price_raw=_string_or_none(offer.get("price")),
                    currency_raw=_string_or_none(offer.get("priceCurrency")),
                    location_raw=_location_from_url(canonical_url),
                    size_raw=_string_or_none(floor_size.get("value")),
                    rooms_raw=_string_or_none(apartment.get("numberOfRooms")),
                    additional_card_data={
                        "position": list_item_dict.get("position"),
                        "image": _json_safe(listing.get("image")),
                        "source_item": _json_safe(listing),
                    },
                )
            )
    return cards


def _cards_from_links(html: str) -> list[RawListingCard]:
    cards: list[RawListingCard] = []
    for match in _HREF_RE.finditer(html):
        href = html_lib.unescape(match.group(1))
        parsed = urlparse(urljoin(BASE_URL, href))
        if not _DETAIL_PATH_RE.match(parsed.path):
            continue
        canonical_url = _canonical_url(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")
        external_listing_id = _external_listing_id(canonical_url)
        if external_listing_id is None:
            continue
        cards.append(
            RawListingCard(
                external_listing_id=external_listing_id,
                url=canonical_url,
                canonical_url=canonical_url,
                location_raw=_location_from_url(canonical_url),
            )
        )
    return cards


def _json_ld_items(html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in _JSON_LD_RE.finditer(html):
        raw_script = html_lib.unescape(match.group(1).strip())
        if not raw_script:
            continue
        try:
            parsed = json.loads(raw_script)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("@graph"), list):
            items.extend(item for item in parsed["@graph"] if isinstance(item, dict))
        elif isinstance(parsed, dict):
            items.append(parsed)
        elif isinstance(parsed, list):
            items.extend(item for item in parsed if isinstance(item, dict))
    return items


def _next_page_url(html: str, page_url: str) -> str | None:
    current = _page_number(page_url)
    parsed_page_url = urlparse(page_url)
    current_path = parsed_page_url.path.rstrip("/")
    candidates: list[tuple[int, str]] = []
    for match in _HREF_RE.finditer(html):
        href = html_lib.unescape(match.group(1))
        url = urljoin(BASE_URL, href)
        parsed = urlparse(url)
        if parsed.path.rstrip("/") != current_path:
            continue
        page_values = parse_qs(parsed.query).get("strana", [])
        if not page_values:
            continue
        try:
            page = int(page_values[0])
        except ValueError:
            continue
        if page > current:
            query = _next_query(parsed_page_url.query, parsed.query, page)
            candidates.append((page, f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query}"))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _next_query(current_query: str, candidate_query: str, page: int) -> str:
    values = {key: list(value) for key, value in parse_qs(current_query).items() if key != "strana"}
    values.update(
        {key: list(value) for key, value in parse_qs(candidate_query).items() if key != "strana"}
    )
    values["strana"] = [str(page)]
    return urlencode(values, doseq=True)


def _page_number(url: str) -> int:
    values = parse_qs(urlparse(url).query).get("strana", [])
    if not values:
        return 1
    try:
        return int(values[0])
    except ValueError:
        return 1


def _dedupe_cards(cards: list[RawListingCard]) -> list[RawListingCard]:
    deduped: dict[str, RawListingCard] = {}
    for card in cards:
        deduped.setdefault(card.external_listing_id, card)
    return list(deduped.values())


def _typed_items(items: list[dict[str, Any]], type_name: str) -> list[dict[str, Any]]:
    return [item for item in items if _has_type(item, type_name)]


def _first_typed(items: list[dict[str, Any]], type_name: str) -> dict[str, Any] | None:
    typed = _typed_items(items, type_name)
    return typed[0] if typed else None


def _has_type(item: dict[str, Any], type_name: str) -> bool:
    item_type = item.get("@type")
    if isinstance(item_type, str):
        return item_type == type_name
    if isinstance(item_type, list):
        return type_name in item_type
    return False


def _seller(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        item_id = _string_or_none(item.get("@id"))
        if item_id and item_id.endswith("#seller"):
            return item
    for item in items:
        if _has_type(item, "RealEstateAgent"):
            return item
    return None


def _canonical_url(url: str) -> str:
    parsed = urlparse(urljoin(BASE_URL, html_lib.unescape(url)))
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def _external_listing_id(url: str) -> str | None:
    path = urlparse(url).path.rstrip("/")
    match = re.search(r"/([0-9a-f]{24})$", path, re.IGNORECASE)
    return match.group(1) if match else None


def _location_from_url(url: str) -> str | None:
    match = _DETAIL_URL_RE.search(url)
    if match is None:
        return None
    location_slug = match.group("path").split("/")[2]
    words = [word for word in location_slug.split("-") if word]
    return " ".join(word.capitalize() for word in words) if words else None


def _location_from_address(address: dict[str, Any]) -> str | None:
    parts = [
        _string_or_none(address.get("streetAddress")),
        _string_or_none(address.get("addressLocality")),
        _string_or_none(address.get("addressRegion")),
        _string_or_none(address.get("addressCountry")),
    ]
    values = [part for part in parts if part]
    return ", ".join(values) if values else None


def _floor_from_description(description: str | None) -> str | None:
    if description is None:
        return None
    match = _FLOOR_RE.search(description)
    return match.group(0) if match else None


def _meta_values(html: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in _META_RE.finditer(html):
        name = html_lib.unescape(match.group("name"))
        content = html_lib.unescape(match.group("content"))
        values[name] = content
    return values


def _image_urls(value: object) -> list[str]:
    urls: list[str] = []
    for item in _list_or_empty(value):
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict):
            url = _string_or_none(item.get("url") or item.get("contentUrl"))
            if url:
                urls.append(url)
    return urls


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_or_empty(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(nested_value) for key, nested_value in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
