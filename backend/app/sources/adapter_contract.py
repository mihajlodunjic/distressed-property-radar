from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, Self

from app.sources.dto import RawListingCard, RawListingDetail

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
class SearchPageResult:
    url: str
    parsed_page: object


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


class ListingSourceAdapter(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *_exc_info: object) -> None: ...

    async def discover_cards(
        self,
        max_pages_per_market: int = 1,
        *,
        known_listing_ids: set[str] | None = None,
        known_listing_stop_threshold: int | None = None,
    ) -> DiscoveryResult: ...

    async def fetch_detail(self, url: str) -> RawListingDetail: ...


def status_category(status_code: int) -> FetchErrorCategory:
    if status_code == 403:
        return "HTTP_FORBIDDEN"
    if status_code == 429:
        return "HTTP_RATE_LIMITED"
    if 500 <= status_code:
        return "HTTP_SERVER_ERROR"
    return "HTTP_CLIENT_ERROR"
