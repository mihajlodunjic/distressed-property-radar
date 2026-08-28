from __future__ import annotations

from pathlib import Path

from app.sources.four_zida.parser import parse_detail_page, parse_search_page

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "four_zida"
SEARCH_URL = "https://www.4zida.rs/prodaja-stanova/zemun-opstina-beograd"
DETAIL_URL = (
    "https://www.4zida.rs/prodaja-stanova/gornji-grad-zemun-opstina-beograd/"
    "dvoiposoban-stan/64aaaaaaaaaaaaaaaaaaaaaa"
)


def fixture(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


def test_search_page_parser_extracts_valid_cards_and_next_page() -> None:
    parsed = parse_search_page(fixture("search_page_1.html"), SEARCH_URL)

    assert len(parsed.cards) == 2
    assert parsed.next_page_url == f"{SEARCH_URL}?strana=2"

    first = parsed.cards[0]
    assert first.external_listing_id == "64aaaaaaaaaaaaaaaaaaaaaa"
    assert first.canonical_url == DETAIL_URL
    assert first.title_raw == "Test ulica"
    assert first.price_raw == "180000"
    assert first.currency_raw == "EUR"
    assert first.size_raw == "60"
    assert first.rooms_raw == "2.5"
    assert first.location_raw == "Gornji Grad Zemun Opstina Beograd"


def test_search_page_parser_handles_last_page() -> None:
    parsed = parse_search_page(fixture("search_page_2.html"), f"{SEARCH_URL}?strana=2")

    assert len(parsed.cards) == 1
    assert parsed.next_page_url is None


def test_search_page_parser_preserves_active_filters_on_next_page() -> None:
    parsed = parse_search_page(
        fixture("search_page_1.html"),
        f"{SEARCH_URL}?m2From=35&m2To=90",
    )

    assert parsed.next_page_url == f"{SEARCH_URL}?m2From=35&m2To=90&strana=2"


def test_detail_page_parser_extracts_detail_fields() -> None:
    detail = parse_detail_page(fixture("detail_page.html"), DETAIL_URL)

    assert detail.external_listing_id == "64aaaaaaaaaaaaaaaaaaaaaa"
    assert detail.canonical_url == DETAIL_URL
    assert detail.title_raw == "Dvoiposoban stan na prodaju, Test ulica, 180.000 EUR, 60m2"
    assert detail.description_raw is not None
    assert detail.price_raw == "180000"
    assert detail.currency_raw == "EUR"
    assert detail.size_raw == "60"
    assert detail.rooms_raw == "2.5"
    assert detail.floor_raw == "na 5. spratu"
    assert detail.location_raw == "Test ulica, RS"
    assert detail.agency_raw == "Test nekretnine"
    assert detail.image_urls == [
        "https://cdn.example.test/image-1.webp",
        "https://cdn.example.test/image-2.webp",
    ]


def test_detail_page_parser_keeps_identity_when_optional_data_is_missing() -> None:
    detail = parse_detail_page(
        fixture("detail_missing_optional.html"),
        (
            "https://www.4zida.rs/prodaja-stanova/prvomajska-zemun-opstina-beograd/"
            "dvosoban-stan/65bbbbbbbbbbbbbbbbbbbbbb"
        ),
    )

    assert detail.external_listing_id == "65bbbbbbbbbbbbbbbbbbbbbb"
    assert detail.title_raw == "Dvosoban stan na prodaju, Prvomajska"
    assert detail.price_raw is None
    assert detail.agency_raw is None
