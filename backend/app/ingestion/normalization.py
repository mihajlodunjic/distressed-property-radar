from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.domain.enums import CurrencyCode, SellerType
from app.sources.dto import RawListingCard, RawListingDetail

_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?(?:\.\d{3})*")
_FLOOR_NUMBER_RE = re.compile(r"(\d+)")
_TOTAL_FLOORS_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


@dataclass(frozen=True)
class NormalizedListingData:
    title: str | None
    description: str | None
    asking_price: Decimal | None
    currency: CurrencyCode | None
    size_m2: Decimal | None
    price_per_m2: Decimal | None
    city_raw: str | None
    location_raw: str | None
    rooms: Decimal | None
    floor: int | None
    total_floors: int | None
    seller_type: SellerType
    seller_name: str | None
    agency_name: str | None


def normalize_listing(
    card: RawListingCard,
    detail: RawListingDetail | None = None,
) -> NormalizedListingData:
    title = _first_text(detail.title_raw if detail else None, card.title_raw)
    description = _first_text(detail.description_raw if detail else None)
    price_raw = _first_text(detail.price_raw if detail else None, card.price_raw)
    currency_raw = _first_text(
        detail.currency_raw if detail else None,
        card.currency_raw,
        price_raw,
    )
    size_raw = _first_text(detail.size_raw if detail else None, card.size_raw)
    rooms_raw = _first_text(detail.rooms_raw if detail else None, card.rooms_raw)
    floor_raw = _first_text(detail.floor_raw if detail else None, card.floor_raw, description)
    location_raw = _first_text(detail.location_raw if detail else None, card.location_raw)

    asking_price = parse_decimal(price_raw, scale=2)
    currency = parse_currency(currency_raw)
    size_m2 = parse_decimal(size_raw, scale=2)
    rooms = parse_decimal(rooms_raw, scale=2)
    price_per_m2 = _price_per_m2(asking_price, size_m2)
    floor = parse_floor(floor_raw)
    total_floors = parse_total_floors(floor_raw)
    agency_name = _first_text(detail.agency_raw if detail else None)
    seller_name = _first_text(detail.seller_raw if detail else None)

    return NormalizedListingData(
        title=title,
        description=description,
        asking_price=asking_price,
        currency=currency,
        size_m2=size_m2,
        price_per_m2=price_per_m2,
        city_raw=_city_from_location(location_raw),
        location_raw=location_raw,
        rooms=rooms,
        floor=floor,
        total_floors=total_floors,
        seller_type=parse_seller_type(seller_name=seller_name, agency_name=agency_name),
        seller_name=seller_name,
        agency_name=agency_name,
    )


def parse_decimal(raw_value: object, scale: int) -> Decimal | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, int | float | Decimal):
        try:
            return Decimal(str(raw_value)).quantize(_quantizer(scale), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return None

    text = str(raw_value)
    match = _NUMBER_RE.search(text.replace(" ", ""))
    if match is None:
        return None
    value = match.group(0)
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif value.count(".") > 1:
        value = value.replace(".", "")
    elif "." in value and len(value.rsplit(".", maxsplit=1)[1]) == 3:
        value = value.replace(".", "")
    try:
        return Decimal(value).quantize(_quantizer(scale), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def parse_currency(raw_value: object) -> CurrencyCode | None:
    if raw_value is None:
        return None
    text = str(raw_value).upper()
    if "EUR" in text or "EURO" in text or "\u20ac" in text:
        return CurrencyCode.EUR
    if "RSD" in text or "DIN" in text:
        return CurrencyCode.RSD
    return None


def parse_floor(raw_value: object) -> int | None:
    if raw_value is None:
        return None
    text = str(raw_value).lower()
    if "prizem" in text:
        return 0
    match = _FLOOR_NUMBER_RE.search(text)
    if match is None:
        return None
    return int(match.group(1))


def parse_total_floors(raw_value: object) -> int | None:
    if raw_value is None:
        return None
    match = _TOTAL_FLOORS_RE.search(str(raw_value))
    if match is None:
        return None
    return int(match.group(2))


def parse_seller_type(seller_name: str | None, agency_name: str | None) -> SellerType:
    if agency_name:
        return SellerType.AGENCY
    text = " ".join(value for value in (seller_name, agency_name) if value).lower()
    if "agenc" in text or "nekretnine" in text:
        return SellerType.AGENCY
    if "invest" in text:
        return SellerType.INVESTOR
    if "vlasnik" in text:
        return SellerType.OWNER
    return SellerType.UNKNOWN


def _price_per_m2(price: Decimal | None, size: Decimal | None) -> Decimal | None:
    if price is None or size is None or size <= 0:
        return None
    return (price / size).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _city_from_location(location_raw: str | None) -> str | None:
    if location_raw and "beograd" in location_raw.lower():
        return "Beograd"
    return None


def _first_text(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _quantizer(scale: int) -> Decimal:
    return Decimal("1").scaleb(-scale)
