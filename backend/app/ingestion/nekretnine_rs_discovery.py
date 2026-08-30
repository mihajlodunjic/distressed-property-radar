from __future__ import annotations

import argparse
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Source
from app.ingestion.source_crawl import (
    DEFAULT_FAST_DISCOVERY_INTERVAL_SECONDS,
    DEFAULT_KNOWN_LISTING_STOP_THRESHOLD,
    DEFAULT_REMOVAL_NOT_SEEN_SCAN_THRESHOLD,
    CrawlMode,
    IngestionSummary,
    SourceCrawlDefinition,
    ensure_source,
    run_scheduled_source_crawl,
    run_scheduled_source_crawl_async,
    run_source_crawl,
    run_source_crawl_async,
    run_source_crawl_loop,
    run_source_crawl_loop_async,
    run_source_discovery,
    run_source_discovery_async,
)
from app.sources.adapter_contract import ListingSourceAdapter
from app.sources.nekretnine_rs.adapter import (
    DEFAULT_SEARCH_URLS,
    NekretnineRsAdapter,
    NekretnineRsConfig,
)
from app.sources.nekretnine_rs.parser import BASE_URL, PARSER_VERSION

NEKRETNINE_RS_SOURCE_CODE = "nekretnine_rs"
NEKRETNINE_RS_BASE_URL = BASE_URL


def make_nekretnine_rs_definition(
    config: NekretnineRsConfig | None = None,
) -> SourceCrawlDefinition:
    return SourceCrawlDefinition(
        code=NEKRETNINE_RS_SOURCE_CODE,
        name="Nekretnine.rs",
        base_url=NEKRETNINE_RS_BASE_URL,
        parser_version=PARSER_VERSION,
        make_adapter=lambda: NekretnineRsAdapter(config=config),
    )


NEKRETNINE_RS_DEFINITION = make_nekretnine_rs_definition()


async def run_nekretnine_rs_crawl_async(
    session: Session,
    *,
    mode: CrawlMode = CrawlMode.FAST_DISCOVERY,
    job_type: str | None = None,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    known_listing_stop_threshold: int = DEFAULT_KNOWN_LISTING_STOP_THRESHOLD,
    removal_not_seen_scan_threshold: int = DEFAULT_REMOVAL_NOT_SEEN_SCAN_THRESHOLD,
    force_detail_fetch_existing: bool = False,
    commit: bool = False,
) -> IngestionSummary:
    return await run_source_crawl_async(
        session,
        definition=NEKRETNINE_RS_DEFINITION,
        mode=mode,
        job_type=job_type,
        adapter=adapter,
        max_pages_per_market=max_pages_per_market,
        detail_limit=detail_limit,
        known_listing_stop_threshold=known_listing_stop_threshold,
        removal_not_seen_scan_threshold=removal_not_seen_scan_threshold,
        force_detail_fetch_existing=force_detail_fetch_existing,
        commit=commit,
    )


async def run_nekretnine_rs_discovery_async(
    session: Session,
    *,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    commit: bool = False,
) -> IngestionSummary:
    return await run_source_discovery_async(
        session,
        definition=NEKRETNINE_RS_DEFINITION,
        adapter=adapter,
        max_pages_per_market=max_pages_per_market,
        detail_limit=detail_limit,
        commit=commit,
    )


def run_nekretnine_rs_discovery(
    session: Session,
    *,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    commit: bool = False,
) -> IngestionSummary:
    return run_source_discovery(
        session,
        definition=NEKRETNINE_RS_DEFINITION,
        adapter=adapter,
        max_pages_per_market=max_pages_per_market,
        detail_limit=detail_limit,
        commit=commit,
    )


def run_nekretnine_rs_crawl(
    session: Session,
    *,
    mode: CrawlMode = CrawlMode.FAST_DISCOVERY,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    known_listing_stop_threshold: int = DEFAULT_KNOWN_LISTING_STOP_THRESHOLD,
    removal_not_seen_scan_threshold: int = DEFAULT_REMOVAL_NOT_SEEN_SCAN_THRESHOLD,
    force_detail_fetch_existing: bool = False,
    commit: bool = False,
) -> IngestionSummary:
    return run_source_crawl(
        session,
        definition=NEKRETNINE_RS_DEFINITION,
        mode=mode,
        adapter=adapter,
        max_pages_per_market=max_pages_per_market,
        detail_limit=detail_limit,
        known_listing_stop_threshold=known_listing_stop_threshold,
        removal_not_seen_scan_threshold=removal_not_seen_scan_threshold,
        force_detail_fetch_existing=force_detail_fetch_existing,
        commit=commit,
    )


async def run_scheduled_nekretnine_rs_crawl_async(
    session: Session,
    *,
    mode: CrawlMode = CrawlMode.FAST_DISCOVERY,
    interval_seconds: int = DEFAULT_FAST_DISCOVERY_INTERVAL_SECONDS,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    known_listing_stop_threshold: int = DEFAULT_KNOWN_LISTING_STOP_THRESHOLD,
    removal_not_seen_scan_threshold: int = DEFAULT_REMOVAL_NOT_SEEN_SCAN_THRESHOLD,
    commit: bool = False,
    now: datetime | None = None,
) -> IngestionSummary | None:
    return await run_scheduled_source_crawl_async(
        session,
        definition=NEKRETNINE_RS_DEFINITION,
        mode=mode,
        interval_seconds=interval_seconds,
        adapter=adapter,
        max_pages_per_market=max_pages_per_market,
        detail_limit=detail_limit,
        known_listing_stop_threshold=known_listing_stop_threshold,
        removal_not_seen_scan_threshold=removal_not_seen_scan_threshold,
        commit=commit,
        now=now,
    )


def run_scheduled_nekretnine_rs_crawl(
    session: Session,
    *,
    mode: CrawlMode = CrawlMode.FAST_DISCOVERY,
    interval_seconds: int = DEFAULT_FAST_DISCOVERY_INTERVAL_SECONDS,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    known_listing_stop_threshold: int = DEFAULT_KNOWN_LISTING_STOP_THRESHOLD,
    removal_not_seen_scan_threshold: int = DEFAULT_REMOVAL_NOT_SEEN_SCAN_THRESHOLD,
    commit: bool = False,
    now: datetime | None = None,
) -> IngestionSummary | None:
    return run_scheduled_source_crawl(
        session,
        definition=NEKRETNINE_RS_DEFINITION,
        mode=mode,
        interval_seconds=interval_seconds,
        adapter=adapter,
        max_pages_per_market=max_pages_per_market,
        detail_limit=detail_limit,
        known_listing_stop_threshold=known_listing_stop_threshold,
        removal_not_seen_scan_threshold=removal_not_seen_scan_threshold,
        commit=commit,
        now=now,
    )


def ensure_nekretnine_rs_source(session: Session) -> Source:
    return ensure_source(session, NEKRETNINE_RS_DEFINITION)


async def run_nekretnine_rs_crawl_loop_async(
    session: Session,
    *,
    mode: CrawlMode = CrawlMode.FAST_DISCOVERY,
    iterations: int = 1,
    interval_seconds: int = DEFAULT_FAST_DISCOVERY_INTERVAL_SECONDS,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    known_listing_stop_threshold: int = DEFAULT_KNOWN_LISTING_STOP_THRESHOLD,
    removal_not_seen_scan_threshold: int = DEFAULT_REMOVAL_NOT_SEEN_SCAN_THRESHOLD,
    commit: bool = False,
) -> list[IngestionSummary]:
    return await run_source_crawl_loop_async(
        session,
        definition=NEKRETNINE_RS_DEFINITION,
        mode=mode,
        iterations=iterations,
        interval_seconds=interval_seconds,
        adapter=adapter,
        max_pages_per_market=max_pages_per_market,
        detail_limit=detail_limit,
        known_listing_stop_threshold=known_listing_stop_threshold,
        removal_not_seen_scan_threshold=removal_not_seen_scan_threshold,
        commit=commit,
    )


def run_nekretnine_rs_crawl_loop(
    session: Session,
    *,
    mode: CrawlMode = CrawlMode.FAST_DISCOVERY,
    iterations: int = 1,
    interval_seconds: int = DEFAULT_FAST_DISCOVERY_INTERVAL_SECONDS,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    known_listing_stop_threshold: int = DEFAULT_KNOWN_LISTING_STOP_THRESHOLD,
    removal_not_seen_scan_threshold: int = DEFAULT_REMOVAL_NOT_SEEN_SCAN_THRESHOLD,
    commit: bool = False,
) -> list[IngestionSummary]:
    return run_source_crawl_loop(
        session,
        definition=NEKRETNINE_RS_DEFINITION,
        mode=mode,
        iterations=iterations,
        interval_seconds=interval_seconds,
        adapter=adapter,
        max_pages_per_market=max_pages_per_market,
        detail_limit=detail_limit,
        known_listing_stop_threshold=known_listing_stop_threshold,
        removal_not_seen_scan_threshold=removal_not_seen_scan_threshold,
        commit=commit,
    )


def _market_urls(markets: list[str]) -> tuple[str, ...]:
    if "all" in markets:
        return DEFAULT_SEARCH_URLS
    urls: list[str] = []
    if "zemun" in markets:
        urls.append(
            "https://www.nekretnine.rs/stambeni-objekti/stanovi/beograd-zemun/prodaja/"
            "?kvadratura_min=35&kvadratura_max=90"
        )
    if "novi-beograd" in markets:
        urls.append(
            "https://www.nekretnine.rs/stambeni-objekti/stanovi/beograd-novi-beograd/prodaja/"
            "?kvadratura_min=35&kvadratura_max=90"
        )
    return tuple(urls)


def _mode_from_cli(value: str) -> CrawlMode:
    return CrawlMode(value.replace("-", "_").upper())


def _main() -> None:
    from app.db.session import SessionLocal

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run Nekretnine.rs crawler.")
    parser.add_argument(
        "--mode",
        choices=["fast-discovery", "active-market-scan", "deep-reconciliation"],
        default="fast-discovery",
    )
    parser.add_argument("--max-pages-per-market", type=int, default=1)
    parser.add_argument("--detail-limit", type=int, default=None)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=DEFAULT_FAST_DISCOVERY_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--known-listing-stop-threshold",
        type=int,
        default=DEFAULT_KNOWN_LISTING_STOP_THRESHOLD,
    )
    parser.add_argument(
        "--removal-not-seen-scan-threshold",
        type=int,
        default=DEFAULT_REMOVAL_NOT_SEEN_SCAN_THRESHOLD,
    )
    parser.add_argument(
        "--market",
        action="append",
        choices=["all", "zemun", "novi-beograd"],
        default=None,
    )
    args = parser.parse_args()

    mode = _mode_from_cli(args.mode)
    config = NekretnineRsConfig(
        search_urls=_market_urls(args.market or ["all"]),
        timeout_seconds=settings.nekretnine_rs_timeout_seconds,
        retry_count=settings.nekretnine_rs_retry_count,
        min_request_delay_seconds=settings.nekretnine_rs_min_request_delay_seconds,
        max_concurrency=settings.nekretnine_rs_max_concurrency,
    )
    definition = make_nekretnine_rs_definition(config)
    with SessionLocal() as session:
        adapter = NekretnineRsAdapter(config=config)
        if args.iterations == 1:
            summary = run_source_crawl(
                session,
                definition=definition,
                mode=mode,
                adapter=adapter,
                max_pages_per_market=args.max_pages_per_market,
                detail_limit=args.detail_limit,
                known_listing_stop_threshold=args.known_listing_stop_threshold,
                removal_not_seen_scan_threshold=args.removal_not_seen_scan_threshold,
                commit=True,
            )
            output: dict[str, object] | list[dict[str, object]] = summary.to_jsonable()
        else:
            summaries = run_source_crawl_loop(
                session,
                definition=definition,
                mode=mode,
                adapter=adapter,
                iterations=args.iterations,
                interval_seconds=args.interval_seconds,
                max_pages_per_market=args.max_pages_per_market,
                detail_limit=args.detail_limit,
                known_listing_stop_threshold=args.known_listing_stop_threshold,
                removal_not_seen_scan_threshold=args.removal_not_seen_scan_threshold,
                commit=True,
            )
            output = [summary.to_jsonable() for summary in summaries]
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    _main()
