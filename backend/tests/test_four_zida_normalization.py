from __future__ import annotations

from decimal import Decimal

from app.domain.enums import CurrencyCode, SellerType
from app.ingestion.normalization import (
    normalize_listing,
    parse_decimal,
    parse_floor,
    parse_total_floors,
)
from app.sources.four_zida.dto import RawListingCard, RawListingDetail


def test_normalize_listing_basic_fields() -> None:
    card = RawListingCard(
        external_listing_id="64aaaaaaaaaaaaaaaaaaaaaa",
        url="https://www.4zida.rs/prodaja-stanova/gornji-grad-zemun-opstina-beograd/dvoiposoban-stan/64aaaaaaaaaaaaaaaaaaaaaa",
        canonical_url="https://www.4zida.rs/prodaja-stanova/gornji-grad-zemun-opstina-beograd/dvoiposoban-stan/64aaaaaaaaaaaaaaaaaaaaaa",
        title_raw="Test ulica",
        price_raw="180000",
        currency_raw="EUR",
        location_raw="Gornji Grad Zemun Opstina Beograd",
        size_raw="60",
        rooms_raw="2.5",
    )
    detail = RawListingDetail(
        external_listing_id=card.external_listing_id,
        url=card.url,
        canonical_url=card.canonical_url,
        title_raw="Dvoiposoban stan na prodaju",
        description_raw="Stan je na 5. spratu.",
        price_raw="180.000 EUR",
        currency_raw="EUR",
        size_raw="60 m2",
        location_raw="Test ulica, RS",
        rooms_raw="2,5",
        floor_raw="na 5. spratu",
        agency_raw="Test nekretnine",
    )

    normalized = normalize_listing(card, detail)

    assert normalized.title == "Dvoiposoban stan na prodaju"
    assert normalized.asking_price == Decimal("180000.00")
    assert normalized.currency == CurrencyCode.EUR
    assert normalized.size_m2 == Decimal("60.00")
    assert normalized.price_per_m2 == Decimal("3000.00")
    assert normalized.rooms == Decimal("2.50")
    assert normalized.floor == 5
    assert normalized.city_raw is None
    assert normalized.seller_type == SellerType.AGENCY


def test_invalid_price_is_unknown_not_zero() -> None:
    assert parse_decimal("Cena na upit", scale=2) is None


def test_floor_helpers_handle_ground_and_total_floor_format() -> None:
    assert parse_floor("prizemlje") == 0
    assert parse_floor("2/5") == 2
    assert parse_total_floors("2/5") == 5
