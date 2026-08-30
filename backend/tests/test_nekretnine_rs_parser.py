from __future__ import annotations

from pathlib import Path

from app.sources.nekretnine_rs.parser import parse_detail_page, parse_search_page

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "nekretnine_rs"
SEARCH_URL = (
    "https://www.nekretnine.rs/stambeni-objekti/stanovi/beograd-zemun/prodaja/"
    "?kvadratura_min=35&kvadratura_max=90"
)
DETAIL_1001_URL = (
    "https://www.nekretnine.rs/stambeni-objekti/stanovi/test-ulica-gornji-grad-zemun/NKRS-1001"
)


def fixture(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


def test_search_page_parser_extracts_cards_canonical_urls_and_next_page() -> None:
    parsed = parse_search_page(fixture("search_page_1.html"), SEARCH_URL)

    assert len(parsed.cards) == 2
    assert parsed.next_page_url == (
        "https://www.nekretnine.rs/stambeni-objekti/stanovi/beograd-zemun/prodaja"
        "?kvadratura_min=35&kvadratura_max=90&page=2"
    )

    first = parsed.cards[0]
    assert first.external_listing_id == "NKRS-1001"
    assert first.url.endswith("NKRS-1001/?utm_source=feed")
    assert first.canonical_url == DETAIL_1001_URL
    assert first.title_raw == "Stan Test ulica, Gornji grad"
    assert first.price_raw == "179.000 EUR"
    assert first.currency_raw == "EUR"
    assert first.size_raw == "60 m2"
    assert first.rooms_raw == "2.5"
    assert first.floor_raw == "5/8"
    assert first.location_raw == "Test ulica, RS"


def test_search_page_parser_deduplicates_repeated_source_cards() -> None:
    parsed = parse_search_page(fixture("search_page_duplicate_cards.html"), SEARCH_URL)

    assert [card.external_listing_id for card in parsed.cards] == ["NKRS-1001"]
    assert parsed.cards[0].canonical_url == DETAIL_1001_URL


def test_detail_page_parser_extracts_json_ld_detail_fields() -> None:
    detail = parse_detail_page(fixture("detail_1001.html"), DETAIL_1001_URL)

    assert detail.external_listing_id == "NKRS-1001"
    assert detail.canonical_url == DETAIL_1001_URL
    assert detail.title_raw == "Stan Test ulica, Gornji grad"
    assert detail.description_raw is not None
    assert detail.price_raw == "179000"
    assert detail.currency_raw == "EUR"
    assert detail.size_raw == "60"
    assert detail.rooms_raw == "2.5"
    assert detail.floor_raw == "5/8"
    assert detail.location_raw == "Test ulica, Zemun, Beograd, RS"
    assert detail.agency_raw == "Nekretnine RS Agency"
    assert detail.image_urls == [
        "https://cdn.nekretnine.test/NKRS-1001-1.jpg",
        "https://cdn.nekretnine.test/NKRS-1001-2.jpg",
    ]


def test_detail_page_parser_handles_html_fallback() -> None:
    detail = parse_detail_page(
        fixture("detail_1002.html"),
        "https://www.nekretnine.rs/stambeni-objekti/stanovi/prvomajska-zemun/NKRS-1002",
    )

    assert detail.external_listing_id == "NKRS-1002"
    assert detail.title_raw == "Dvosoban stan Prvomajska"
    assert detail.price_raw == "145.000 EUR"
    assert detail.size_raw == "55 m2"
    assert detail.agency_raw == "Druga agencija"
    assert detail.image_urls == ["https://cdn.nekretnine.test/NKRS-1002-1.jpg"]
