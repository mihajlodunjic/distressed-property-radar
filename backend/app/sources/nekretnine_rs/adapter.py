from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from app.sources.adapter_contract import (
    DiscoveryResult,
    SearchPageResult,
    SourceFetchError,
    status_category,
)
from app.sources.dto import RawListingCard, RawListingDetail
from app.sources.nekretnine_rs.parser import (
    BASE_URL,
    ParsedSearchPage,
    parse_detail_page,
    parse_search_page,
)

DEFAULT_SEARCH_URLS = (
    "https://www.nekretnine.rs/stambeni-objekti/stanovi/beograd-zemun/prodaja/"
    "?kvadratura_min=35&kvadratura_max=90",
    "https://www.nekretnine.rs/stambeni-objekti/stanovi/beograd-novi-beograd/prodaja/"
    "?kvadratura_min=35&kvadratura_max=90",
)


@dataclass(frozen=True)
class NekretnineRsConfig:
    search_urls: tuple[str, ...] = DEFAULT_SEARCH_URLS
    timeout_seconds: float = 20.0
    retry_count: int = 2
    min_request_delay_seconds: float = 0.2
    max_concurrency: int = 1
    user_agent: str = "DistressedPropertyRadar/0.1 (+private research crawler)"

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.retry_count < 0:
            raise ValueError("retry_count must be non-negative")
        if self.min_request_delay_seconds < 0:
            raise ValueError("min_request_delay_seconds must be non-negative")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")


class NekretnineRsAdapter:
    def __init__(
        self,
        config: NekretnineRsConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or NekretnineRsConfig()
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> NekretnineRsAdapter:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": self.config.user_agent},
            )
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def discover_cards(
        self,
        max_pages_per_market: int = 1,
        *,
        known_listing_ids: set[str] | None = None,
        known_listing_stop_threshold: int | None = None,
    ) -> DiscoveryResult:
        if max_pages_per_market < 1:
            raise ValueError("max_pages_per_market must be at least 1")
        if known_listing_stop_threshold is not None and known_listing_stop_threshold < 1:
            raise ValueError("known_listing_stop_threshold must be at least 1")

        pages: list[SearchPageResult] = []
        cards_by_id: dict[str, RawListingCard] = {}
        pages_requested = 0
        http_errors = 0
        parse_errors = 0
        complete = True
        stopped_on_known_boundary = False
        error_messages: list[str] = []

        for search_url in self.config.search_urls:
            seen_urls: set[str] = set()
            next_url: str | None = search_url
            consecutive_known = 0
            for page_index in range(max_pages_per_market):
                if next_url is None or next_url in seen_urls:
                    break
                seen_urls.add(next_url)
                pages_requested += 1
                try:
                    parsed_page = await self.fetch_search_page(next_url)
                except SourceFetchError as exc:
                    http_errors += 1
                    complete = False
                    error_messages.append(f"{exc.category} {exc.url}: {exc}")
                    break
                except ValueError as exc:
                    parse_errors += 1
                    complete = False
                    error_messages.append(f"PARSE_ERROR {next_url}: {exc}")
                    break

                pages.append(SearchPageResult(url=next_url, parsed_page=parsed_page))
                for card in parsed_page.cards:
                    cards_by_id.setdefault(card.external_listing_id, card)
                    if known_listing_ids is None:
                        continue
                    if card.external_listing_id in known_listing_ids:
                        consecutive_known += 1
                    else:
                        consecutive_known = 0
                    if (
                        known_listing_stop_threshold is not None
                        and consecutive_known >= known_listing_stop_threshold
                    ):
                        stopped_on_known_boundary = True
                        next_url = None
                        break
                else:
                    next_url = parsed_page.next_page_url
                    if next_url is not None and page_index == max_pages_per_market - 1:
                        complete = False
                    continue

                if stopped_on_known_boundary:
                    break
                next_url = parsed_page.next_page_url
                if next_url is not None and page_index == max_pages_per_market - 1:
                    complete = False

        return DiscoveryResult(
            pages=pages,
            cards=list(cards_by_id.values()),
            pages_requested=pages_requested,
            http_errors=http_errors,
            parse_errors=parse_errors,
            complete=complete,
            stopped_on_known_boundary=stopped_on_known_boundary,
            error_messages=error_messages,
        )

    async def fetch_search_page(self, url: str) -> ParsedSearchPage:
        html = await self.fetch_text(url)
        return parse_search_page(html, url)

    async def fetch_detail(self, url: str) -> RawListingDetail:
        html = await self.fetch_text(url)
        return parse_detail_page(html, url)

    async def fetch_text(self, url: str) -> str:
        if self._client is None:
            async with self:
                return await self.fetch_text(url)

        last_error: SourceFetchError | None = None
        for attempt in range(self.config.retry_count + 1):
            if self.config.min_request_delay_seconds > 0:
                await asyncio.sleep(self.config.min_request_delay_seconds)
            try:
                response = await self._client.get(url)
            except httpx.TimeoutException as exc:
                last_error = SourceFetchError("HTTP_TIMEOUT", url, str(exc) or "request timed out")
            except httpx.HTTPError as exc:
                last_error = SourceFetchError("NETWORK_ERROR", url, str(exc))
            else:
                if 200 <= response.status_code < 300:
                    return response.text
                category = status_category(response.status_code)
                last_error = SourceFetchError(
                    category,
                    url,
                    f"HTTP {response.status_code}",
                    status_code=response.status_code,
                )
                if category in {"HTTP_CLIENT_ERROR", "HTTP_FORBIDDEN"}:
                    break

            if attempt >= self.config.retry_count:
                break

        if last_error is None:
            last_error = SourceFetchError("NETWORK_ERROR", url, "request failed")
        raise last_error


def canonical_base_url() -> str:
    return BASE_URL
