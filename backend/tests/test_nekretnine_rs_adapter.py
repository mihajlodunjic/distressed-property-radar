from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from app.sources.adapter_contract import SourceFetchError
from app.sources.dto import RawListingCard
from app.sources.nekretnine_rs.adapter import NekretnineRsAdapter, NekretnineRsConfig
from app.sources.nekretnine_rs.parser import ParsedSearchPage

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "nekretnine_rs"
SEARCH_URL = (
    "https://www.nekretnine.rs/stambeni-objekti/stanovi/beograd-zemun/prodaja/"
    "?kvadratura_min=35&kvadratura_max=90"
)
NEXT_URL = (
    "https://www.nekretnine.rs/stambeni-objekti/stanovi/beograd-zemun/prodaja"
    "?kvadratura_min=35&kvadratura_max=90&page=2"
)


def fixture(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


def test_discover_cards_follows_pagination_with_mocked_http() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url) == SEARCH_URL:
            return httpx.Response(200, text=fixture("search_page_1.html"))
        if str(request.url) == NEXT_URL:
            return httpx.Response(200, text=fixture("search_page_2.html"))
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = NekretnineRsAdapter(
        config=NekretnineRsConfig(
            search_urls=(SEARCH_URL,),
            retry_count=0,
            min_request_delay_seconds=0,
        ),
        client=client,
    )

    try:
        result = asyncio.run(adapter.discover_cards(max_pages_per_market=2))
    finally:
        asyncio.run(client.aclose())

    assert requested_urls == [SEARCH_URL, NEXT_URL]
    assert result.pages_requested == 2
    assert result.http_errors == 0
    assert [card.external_listing_id for card in result.cards] == [
        "NKRS-1001",
        "NKRS-1002",
        "NKRS-1003",
    ]


def test_fetch_retries_transient_server_error() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500)
        return httpx.Response(200, text=fixture("search_page_1.html"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = NekretnineRsAdapter(
        config=NekretnineRsConfig(
            search_urls=(SEARCH_URL,),
            retry_count=1,
            min_request_delay_seconds=0,
        ),
        client=client,
    )

    try:
        parsed = asyncio.run(adapter.fetch_search_page(SEARCH_URL))
    finally:
        asyncio.run(client.aclose())

    assert attempts == 2
    assert len(parsed.cards) == 2


def test_timeout_is_classified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = NekretnineRsAdapter(
        config=NekretnineRsConfig(
            search_urls=(SEARCH_URL,),
            retry_count=0,
            min_request_delay_seconds=0,
        ),
        client=client,
    )

    try:
        with pytest.raises(SourceFetchError) as exc_info:
            asyncio.run(adapter.fetch_search_page(SEARCH_URL))
    finally:
        asyncio.run(client.aclose())

    assert exc_info.value.category == "HTTP_TIMEOUT"


def test_discover_cards_stops_after_known_listing_boundary() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url) == SEARCH_URL:
            return httpx.Response(200, text=fixture("search_page_1.html"))
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = NekretnineRsAdapter(
        config=NekretnineRsConfig(
            search_urls=(SEARCH_URL,),
            retry_count=0,
            min_request_delay_seconds=0,
        ),
        client=client,
    )

    try:
        result = asyncio.run(
            adapter.discover_cards(
                max_pages_per_market=5,
                known_listing_ids={"NKRS-1001", "NKRS-1002"},
                known_listing_stop_threshold=2,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert requested_urls == [SEARCH_URL]
    assert result.complete is True
    assert result.stopped_on_known_boundary is True
    assert [card.external_listing_id for card in result.cards] == ["NKRS-1001", "NKRS-1002"]


def test_repeated_next_page_url_does_not_loop_forever() -> None:
    class RepeatingAdapter(NekretnineRsAdapter):
        async def fetch_search_page(self, url: str) -> ParsedSearchPage:
            return ParsedSearchPage(
                cards=[
                    RawListingCard(
                        external_listing_id="NKRS-LOOP",
                        url=f"{SEARCH_URL}/NKRS-LOOP",
                        canonical_url=f"{SEARCH_URL}/NKRS-LOOP",
                    )
                ],
                next_page_url=url,
            )

    result = asyncio.run(
        RepeatingAdapter(
            config=NekretnineRsConfig(
                search_urls=(SEARCH_URL,),
                retry_count=0,
                min_request_delay_seconds=0,
            )
        ).discover_cards(max_pages_per_market=5)
    )

    assert result.pages_requested == 1
    assert len(result.cards) == 1
