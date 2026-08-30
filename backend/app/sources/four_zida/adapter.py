from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urljoin

import httpx

from app.sources.four_zida.dto import RawListingCard, RawListingDetail
from app.sources.four_zida.parser import ParsedSearchPage, parse_detail_page, parse_search_page

BASE_URL = "https://www.4zida.rs"
DEFAULT_SEARCH_URLS = (
    "https://www.4zida.rs/prodaja-stanova/zemun-opstina-beograd?m2From=35&m2To=90",
    "https://www.4zida.rs/prodaja-stanova/novi-beograd-beograd?m2From=35&m2To=90",
)

FetchErrorCategory = Literal[
    "HTTP_TIMEOUT",
    "HTTP_CLIENT_ERROR",
    "HTTP_SERVER_ERROR",
    "HTTP_RATE_LIMITED",
    "HTTP_FORBIDDEN",
    "NETWORK_ERROR",
]


class SourceFetchError(RuntimeError):
    def __init__(
        self,
        category: FetchErrorCategory,
        url: str,
        message: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.url = url
        self.status_code = status_code


@dataclass(frozen=True)
class FourZidaConfig:
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


@dataclass(frozen=True)
class SearchPageResult:
    url: str
    parsed_page: ParsedSearchPage


@dataclass(frozen=True)
class DiscoveryResult:
    pages: list[SearchPageResult]
    cards: list[RawListingCard]
    pages_requested: int
    http_errors: int
    parse_errors: int
    complete: bool
    stopped_on_known_boundary: bool = False
    error_messages: list[str] = field(default_factory=list)


class FourZidaAdapter:
    def __init__(
        self,
        config: FourZidaConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or FourZidaConfig()
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> FourZidaAdapter:
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
        canonical_url = urljoin(BASE_URL, url)
        html = await self.fetch_text(canonical_url)
        return parse_detail_page(html, canonical_url)

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
                category = _status_category(response.status_code)
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


def _status_category(status_code: int) -> FetchErrorCategory:
    if status_code == 403:
        return "HTTP_FORBIDDEN"
    if status_code == 429:
        return "HTTP_RATE_LIMITED"
    if 500 <= status_code:
        return "HTTP_SERVER_ERROR"
    return "HTTP_CLIENT_ERROR"
