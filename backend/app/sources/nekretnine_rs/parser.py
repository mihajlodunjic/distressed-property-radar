from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from app.sources.dto import RawListingCard, RawListingDetail

BASE_URL = "https://www.nekretnine.rs"
PARSER_VERSION = "nekretnine_rs_html_v1"

_JSON_LD_RE = re.compile(
    r"<script\b(?=[^>]*type=[\"']application/ld\+json[\"'])[^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_ARTICLE_RE = re.compile(r"<article\b(?P<attrs>[^>]*)>(?P<body>.*?)</article>", re.I | re.S)
_ATTR_RE = re.compile(
    r"(?P<name>[a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.DOTALL,
)
_A_TAG_RE = re.compile(r"<a\b(?P<attrs>[^>]*)>", re.I | re.S)
_IMG_TAG_RE = re.compile(r"<img\b(?P<attrs>[^>]*)>", re.I | re.S)
_META_RE = re.compile(
    r"<meta\b(?=[^>]*(?:name|property)=[\"'](?P<name>[^\"']+)[\"'])"
    r"(?=[^>]*content=[\"'](?P<content>[^\"']*)[\"'])[^>]*>",
    re.IGNORECASE,
)
_DETAIL_ID_RE = re.compile(r"(?:/|^)(?P<id>NKRS-\d+)(?:/|$)", re.IGNORECASE)
_TRACKING_QUERY_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}


@dataclass(frozen=True)
class ParsedSearchPage:
    cards: list[RawListingCard]
    next_page_url: str | None


def parse_search_page(html: str, page_url: str) -> ParsedSearchPage:
    cards = _cards_from_json_ld(html)
    if not cards:
        cards = _cards_from_articles(html)
    return ParsedSearchPage(
        cards=_dedupe_cards(cards),
        next_page_url=_next_page_url(html, page_url),
    )


def parse_detail_page(html: str, page_url: str) -> RawListingDetail:
    json_detail = _detail_from_json_ld(html, page_url)
    if json_detail is not None:
        return json_detail
    return _detail_from_html(html, page_url)


def _cards_from_json_ld(html: str) -> list[RawListingCard]:
    cards: list[RawListingCard] = []
    for item_list in _typed_items(_json_ld_items(html), "ItemList"):
        for element in _list_or_empty(item_list.get("itemListElement")):
            list_item = _dict_or_empty(element)
            item = _dict_or_empty(list_item.get("item"))
            url = _string_or_none(list_item.get("url") or item.get("url"))
            if url is None:
                continue
            canonical_url = _canonical_url(url)
            external_listing_id = _external_listing_id(canonical_url)
            if external_listing_id is None:
                continue
            offer = _dict_or_empty(item.get("offers"))
            floor_size = _dict_or_empty(item.get("floorSize")) or _dict_or_empty(item.get("area"))
            cards.append(
                RawListingCard(
                    external_listing_id=external_listing_id,
                    url=_absolute_url(url),
                    canonical_url=canonical_url,
                    title_raw=_string_or_none(item.get("name")),
                    price_raw=_string_or_none(offer.get("price")),
                    currency_raw=_string_or_none(offer.get("priceCurrency")),
                    location_raw=_json_location(item) or _location_from_url(canonical_url),
                    size_raw=_string_or_none(floor_size.get("value")),
                    rooms_raw=_string_or_none(item.get("numberOfRooms")),
                    floor_raw=_string_or_none(item.get("floorLevel")),
                    source_published_at_raw=_string_or_none(
                        item.get("datePosted") or item.get("datePublished")
                    ),
                    additional_card_data={
                        "position": list_item.get("position"),
                        "source_item": _json_safe(item),
                    },
                )
            )
    return cards


def _cards_from_articles(html: str) -> list[RawListingCard]:
    cards: list[RawListingCard] = []
    for match in _ARTICLE_RE.finditer(html):
        attrs = _attrs(match.group("attrs"))
        body = match.group("body")
        raw_url = attrs.get("data-url") or _first_link(body)
        listing_id = attrs.get("data-listing-id")
        if raw_url is None and listing_id is None:
            continue
        canonical_url = _canonical_url(raw_url or f"/oglas/{listing_id}")
        external_listing_id = listing_id or _external_listing_id(canonical_url)
        if external_listing_id is None:
            continue
        cards.append(
            RawListingCard(
                external_listing_id=external_listing_id.upper(),
                url=_absolute_url(raw_url or canonical_url),
                canonical_url=canonical_url,
                title_raw=_text_attr(attrs, "data-title"),
                price_raw=_text_attr(attrs, "data-price"),
                currency_raw=_text_attr(attrs, "data-currency", "data-price"),
                location_raw=_text_attr(attrs, "data-location"),
                size_raw=_text_attr(attrs, "data-size"),
                rooms_raw=_text_attr(attrs, "data-rooms"),
                floor_raw=_text_attr(attrs, "data-floor"),
                source_published_at_raw=_text_attr(attrs, "data-published-at"),
                additional_card_data={"source_card_attrs": dict(sorted(attrs.items()))},
            )
        )
    return cards


def _detail_from_json_ld(html: str, page_url: str) -> RawListingDetail | None:
    items = _json_ld_items(html)
    listing = (
        _first_typed(items, "RealEstateListing")
        or _first_typed(items, "Apartment")
        or _first_typed(items, "Product")
    )
    if listing is None:
        return None
    apartment = _first_typed(items, "Apartment") or listing
    offer = _first_typed(items, "Offer") or _dict_or_empty(listing.get("offers"))
    place = _first_typed(items, "Place") or _dict_or_empty(apartment.get("address"))
    seller = _seller(items) or _dict_or_empty(listing.get("seller"))

    canonical_url = _canonical_url(_string_or_none(listing.get("url")) or page_url)
    external_listing_id = _external_listing_id(canonical_url)
    if external_listing_id is None:
        raise ValueError(f"Cannot derive nekretnine.rs listing id from detail URL: {page_url}")
    floor_size = _dict_or_empty(apartment.get("floorSize")) or _dict_or_empty(apartment.get("area"))
    seller_type = _string_or_none(seller.get("@type"))
    seller_name = _string_or_none(seller.get("name"))
    description = _string_or_none(listing.get("description") or apartment.get("description"))

    return RawListingDetail(
        external_listing_id=external_listing_id,
        url=_absolute_url(page_url),
        canonical_url=canonical_url,
        title_raw=_string_or_none(listing.get("name") or apartment.get("name")),
        description_raw=description,
        price_raw=_string_or_none(offer.get("price")),
        currency_raw=_string_or_none(offer.get("priceCurrency")),
        size_raw=_string_or_none(floor_size.get("value")),
        location_raw=_json_location(apartment)
        or _json_location(place)
        or _location_from_url(page_url),
        rooms_raw=_string_or_none(apartment.get("numberOfRooms")),
        floor_raw=_string_or_none(apartment.get("floorLevel")) or _floor_from_text(description),
        seller_raw=seller_name,
        agency_raw=seller_name if seller_type == "Organization" else None,
        property_attributes_raw={
            "listing": _json_safe(listing),
            "apartment": _json_safe(apartment),
            "offer": _json_safe(offer),
            "place": _json_safe(place),
            "seller": _json_safe(seller),
        },
        image_urls=_image_urls(apartment.get("image") or listing.get("image")),
        source_published_at_raw=_string_or_none(
            listing.get("datePosted") or listing.get("datePublished")
        ),
        raw_payload_reference=f"{canonical_url}#json-ld",
    )


def _detail_from_html(html: str, page_url: str) -> RawListingDetail:
    meta = _meta_values(html)
    body_attrs = _attrs(_first_match(r"<main\b([^>]*)>", html) or "")
    canonical_url = _canonical_url(
        meta.get("og:url") or meta.get("canonical") or body_attrs.get("data-url") or page_url
    )
    external_listing_id = body_attrs.get("data-listing-id") or _external_listing_id(canonical_url)
    if external_listing_id is None:
        raise ValueError(f"Cannot derive nekretnine.rs listing id from detail URL: {page_url}")

    return RawListingDetail(
        external_listing_id=external_listing_id.upper(),
        url=_absolute_url(page_url),
        canonical_url=canonical_url,
        title_raw=body_attrs.get("data-title") or meta.get("og:title") or meta.get("title"),
        description_raw=body_attrs.get("data-description") or _description_from_html(html),
        price_raw=body_attrs.get("data-price"),
        currency_raw=body_attrs.get("data-currency") or body_attrs.get("data-price"),
        size_raw=body_attrs.get("data-size"),
        location_raw=body_attrs.get("data-location") or _location_from_url(canonical_url),
        rooms_raw=body_attrs.get("data-rooms"),
        floor_raw=body_attrs.get("data-floor"),
        seller_raw=body_attrs.get("data-seller"),
        agency_raw=body_attrs.get("data-agency"),
        property_attributes_raw={"html_attrs": dict(sorted(body_attrs.items()))},
        image_urls=_image_urls_from_html(html),
        source_published_at_raw=body_attrs.get("data-published-at"),
        raw_payload_reference=f"{canonical_url}#html",
    )


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
    for match in _A_TAG_RE.finditer(html):
        attrs = _attrs(match.group("attrs"))
        if attrs.get("rel") != "next" and "next" not in attrs.get("class", "").lower():
            continue
        href = attrs.get("href")
        if not href:
            continue
        return _canonical_url(href, keep_query=True, base_url=page_url)
    return None


def _attrs(raw_attrs: str) -> dict[str, str]:
    return {
        match.group("name").lower(): html_lib.unescape(match.group("value")).strip()
        for match in _ATTR_RE.finditer(raw_attrs)
    }


def _first_link(html: str) -> str | None:
    match = _A_TAG_RE.search(html)
    if match is None:
        return None
    return _attrs(match.group("attrs")).get("href")


def _text_attr(attrs: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = attrs.get(key)
        if value:
            return " ".join(value.split())
    return None


def _canonical_url(url: str, *, keep_query: bool = False, base_url: str = BASE_URL) -> str:
    parsed = urlparse(urljoin(base_url, html_lib.unescape(url)))
    query = ""
    if keep_query and parsed.query:
        values = {
            key: value
            for key, value in parse_qs(parsed.query).items()
            if key not in _TRACKING_QUERY_KEYS and key not in {"tracking_token", "page_ref", "ref"}
        }
        query = urlencode(values, doseq=True)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/"),
            "",
            query,
            "",
        )
    )


def _absolute_url(url: str) -> str:
    parsed = urlparse(urljoin(BASE_URL, html_lib.unescape(url)))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _external_listing_id(url: str) -> str | None:
    path = urlparse(url).path.rstrip("/")
    match = _DETAIL_ID_RE.search(path)
    return match.group("id").upper() if match else None


def _json_location(item: dict[str, Any]) -> str | None:
    address = _dict_or_empty(item.get("address"))
    parts = [
        _string_or_none(address.get("streetAddress")),
        _string_or_none(address.get("addressLocality")),
        _string_or_none(address.get("addressRegion")),
        _string_or_none(address.get("addressCountry")),
    ]
    values = [part for part in parts if part]
    return ", ".join(values) if values else None


def _location_from_url(url: str) -> str | None:
    words = [
        word
        for word in urlparse(url).path.replace("_", "-").split("/")
        for word in word.split("-")
        if word and not word.lower().startswith("nkrs") and not word.isdigit()
    ]
    useful = [word.capitalize() for word in words if word.lower() not in {"stambeni", "objekti"}]
    return " ".join(useful[:6]) if useful else None


def _seller(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        item_id = _string_or_none(item.get("@id"))
        if item_id and item_id.endswith("#seller"):
            return item
    for item in items:
        if _has_type(item, "RealEstateAgent") or _has_type(item, "Organization"):
            return item
    return None


def _floor_from_text(text: str | None) -> str | None:
    if text is None:
        return None
    match = re.search(r"(?:sprat|floor)\s*[:\-]?\s*(\d+\s*/\s*\d+|\d+)", text, re.I)
    return match.group(1) if match else None


def _description_from_html(html: str) -> str | None:
    match = re.search(
        r"<(?:div|section)\b[^>]*class=[\"'][^\"']*description[^\"']*[\"'][^>]*>(.*?)</(?:div|section)>",
        html,
        re.I | re.S,
    )
    if match is None:
        return None
    return _strip_tags(match.group(1))


def _image_urls_from_html(html: str) -> list[str]:
    urls: list[str] = []
    for match in _IMG_TAG_RE.finditer(html):
        attrs = _attrs(match.group("attrs"))
        url = attrs.get("src") or attrs.get("data-src")
        if url:
            urls.append(_absolute_url(url))
    return urls


def _image_urls(value: object) -> list[str]:
    urls: list[str] = []
    for item in _list_or_empty(value):
        if isinstance(item, str):
            urls.append(_absolute_url(item))
        elif isinstance(item, dict):
            url = _string_or_none(item.get("url") or item.get("contentUrl"))
            if url:
                urls.append(_absolute_url(url))
    return urls


def _meta_values(html: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in _META_RE.finditer(html):
        name = html_lib.unescape(match.group("name"))
        content = html_lib.unescape(match.group("content"))
        values[name] = content
    return values


def _first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.I | re.S)
    return match.group(1) if match else None


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


def _dedupe_cards(cards: list[RawListingCard]) -> list[RawListingCard]:
    deduped: dict[str, RawListingCard] = {}
    for card in cards:
        deduped.setdefault(card.external_listing_id, card)
    return list(deduped.values())


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


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html_lib.unescape(text).split())


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(nested_value) for key, nested_value in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
