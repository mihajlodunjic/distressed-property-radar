from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import JobRun, Listing, ListingEvent, Source
from app.domain.enums import ListingEventType, ListingStatus, SourceHealthStatus
from app.ingestion.four_zida_discovery import (
    FOUR_ZIDA_SOURCE_CODE,
    CrawlMode,
    ensure_four_zida_source,
    run_four_zida_crawl,
    run_four_zida_discovery,
    run_scheduled_four_zida_crawl,
)
from app.sources.four_zida.adapter import FourZidaAdapter, FourZidaConfig

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "four_zida"
SEARCH_URL = "https://www.4zida.rs/prodaja-stanova/zemun-opstina-beograd"
DETAIL_1_URL = (
    "https://www.4zida.rs/prodaja-stanova/gornji-grad-zemun-opstina-beograd/"
    "dvoiposoban-stan/64aaaaaaaaaaaaaaaaaaaaaa"
)
DETAIL_2_URL = (
    "https://www.4zida.rs/prodaja-stanova/prvomajska-zemun-opstina-beograd/"
    "dvosoban-stan/65bbbbbbbbbbbbbbbbbbbbbb"
)


def fixture(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


def make_adapter(
    search_fixture: str,
    *,
    detail_2_status: int = 200,
) -> tuple[FourZidaAdapter, httpx.AsyncClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == SEARCH_URL:
            return httpx.Response(200, text=fixture(search_fixture))
        if url == DETAIL_1_URL:
            return httpx.Response(200, text=fixture("detail_page.html"))
        if url == DETAIL_2_URL:
            if detail_2_status == 200:
                return httpx.Response(200, text=fixture("detail_missing_optional.html"))
            return httpx.Response(detail_2_status, text="gone")
        return httpx.Response(404, text="not found")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = FourZidaAdapter(
        config=FourZidaConfig(
            search_urls=(SEARCH_URL,),
            retry_count=0,
            min_request_delay_seconds=0,
        ),
        client=client,
    )
    return adapter, client


def run_with_adapter(
    db_session: Session,
    search_fixture: str,
    *,
    mode: CrawlMode,
    detail_2_status: int = 200,
):
    adapter, client = make_adapter(search_fixture, detail_2_status=detail_2_status)
    try:
        return run_four_zida_crawl(
            db_session,
            mode=mode,
            adapter=adapter,
            max_pages_per_market=1,
        )
    finally:
        asyncio.run(client.aclose())


def seed_two_listings(db_session: Session) -> None:
    adapter, client = make_adapter("search_page_complete_same.html")
    try:
        run_four_zida_discovery(db_session, adapter=adapter, max_pages_per_market=1)
    finally:
        asyncio.run(client.aclose())


def listing(db_session: Session, external_listing_id: str) -> Listing:
    return db_session.scalars(
        select(Listing).where(Listing.external_listing_id == external_listing_id)
    ).one()


def event_count(db_session: Session, event_type: ListingEventType) -> int:
    return db_session.scalar(
        select(func.count()).select_from(ListingEvent).where(ListingEvent.event_type == event_type)
    )


def test_active_market_scan_detects_price_change_without_detail_fetch(
    db_session: Session,
) -> None:
    seed_two_listings(db_session)

    changed = run_with_adapter(
        db_session,
        "search_page_price_changed.html",
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
    )
    unchanged = run_with_adapter(
        db_session,
        "search_page_price_changed.html",
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
    )

    assert changed.status == "SUCCESS"
    assert changed.details_fetched == 0
    assert changed.changed_listings == 1
    assert unchanged.changed_listings == 0
    assert event_count(db_session, ListingEventType.PRICE_CHANGED) == 1
    assert listing(db_session, "64aaaaaaaaaaaaaaaaaaaaaa").asking_price == 170000


def test_lifecycle_moves_active_to_not_seen_removed_and_reappeared(
    db_session: Session,
) -> None:
    seed_two_listings(db_session)

    first_missing = run_with_adapter(
        db_session,
        "search_page_complete_one_listing.html",
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
    )
    second_missing = run_with_adapter(
        db_session,
        "search_page_complete_one_listing.html",
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
    )

    missing_listing = listing(db_session, "65bbbbbbbbbbbbbbbbbbbbbb")
    assert first_missing.not_seen_count == 1
    assert first_missing.changed_listings == 1
    assert second_missing.not_seen_count == 1
    assert second_missing.changed_listings == 0
    assert missing_listing.status == ListingStatus.NOT_SEEN
    assert missing_listing.consecutive_not_seen_count == 2
    assert event_count(db_session, ListingEventType.STATUS_CHANGED) == 1
    assert event_count(db_session, ListingEventType.REMOVED) == 0

    adapter, client = make_adapter("search_page_complete_one_listing.html", detail_2_status=404)
    try:
        removed = run_four_zida_crawl(
            db_session,
            mode=CrawlMode.DEEP_RECONCILIATION,
            adapter=adapter,
            max_pages_per_market=1,
        )
    finally:
        asyncio.run(client.aclose())

    missing_listing = listing(db_session, "65bbbbbbbbbbbbbbbbbbbbbb")
    assert removed.status == "SUCCESS"
    assert removed.not_seen_count == 1
    assert removed.removed_count == 1
    assert missing_listing.status == ListingStatus.REMOVED
    assert missing_listing.removed_at is not None
    assert event_count(db_session, ListingEventType.REMOVED) == 1

    reappeared = run_with_adapter(
        db_session,
        "search_page_complete_same.html",
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
    )

    missing_listing = listing(db_session, "65bbbbbbbbbbbbbbbbbbbbbb")
    assert reappeared.reappeared_count == 1
    assert missing_listing.status == ListingStatus.ACTIVE
    assert missing_listing.removed_at is None
    assert missing_listing.consecutive_not_seen_count == 0
    assert event_count(db_session, ListingEventType.REAPPEARED) == 1


def test_failed_active_scan_does_not_mark_not_seen_or_removed(db_session: Session) -> None:
    seed_two_listings(db_session)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="source failure")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = FourZidaAdapter(
        config=FourZidaConfig(
            search_urls=(SEARCH_URL,),
            retry_count=0,
            min_request_delay_seconds=0,
        ),
        client=client,
    )
    try:
        summary = run_four_zida_crawl(
            db_session,
            mode=CrawlMode.ACTIVE_MARKET_SCAN,
            adapter=adapter,
            max_pages_per_market=1,
        )
    finally:
        asyncio.run(client.aclose())

    source = db_session.scalars(select(Source).where(Source.code == FOUR_ZIDA_SOURCE_CODE)).one()
    assert summary.status == "FAILED"
    assert summary.not_seen_count == 0
    assert event_count(db_session, ListingEventType.STATUS_CHANGED) == 0
    assert event_count(db_session, ListingEventType.REMOVED) == 0
    assert {item.status for item in source.listings} == {ListingStatus.ACTIVE}
    assert source.runtime_state is not None
    assert source.runtime_state.health_status == SourceHealthStatus.FAILED


def test_parser_failure_updates_health_without_lifecycle_changes(db_session: Session) -> None:
    seed_two_listings(db_session)

    class ParseFailingAdapter(FourZidaAdapter):
        async def fetch_search_page(self, _url: str):
            raise ValueError("broken parser")

    summary = run_four_zida_crawl(
        db_session,
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
        adapter=ParseFailingAdapter(
            config=FourZidaConfig(
                search_urls=(SEARCH_URL,),
                retry_count=0,
                min_request_delay_seconds=0,
            )
        ),
        max_pages_per_market=1,
    )

    source = db_session.scalars(select(Source).where(Source.code == FOUR_ZIDA_SOURCE_CODE)).one()
    assert summary.status == "FAILED"
    assert summary.parse_errors == 1
    assert summary.http_errors == 0
    assert summary.not_seen_count == 0
    assert event_count(db_session, ListingEventType.STATUS_CHANGED) == 0
    assert {item.status for item in source.listings} == {ListingStatus.ACTIVE}
    assert source.runtime_state is not None
    assert source.runtime_state.health_status == SourceHealthStatus.FAILED
    assert source.runtime_state.recent_parse_error_count == 1


def test_partial_active_scan_does_not_mark_missing_listings(db_session: Session) -> None:
    seed_two_listings(db_session)

    summary = run_with_adapter(
        db_session,
        "search_page_1.html",
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
    )

    source = db_session.scalars(select(Source).where(Source.code == FOUR_ZIDA_SOURCE_CODE)).one()
    assert summary.status == "PARTIAL"
    assert summary.complete is False
    assert summary.not_seen_count == 0
    assert event_count(db_session, ListingEventType.STATUS_CHANGED) == 0
    assert {item.status for item in source.listings} == {ListingStatus.ACTIVE}
    assert source.runtime_state is not None
    assert source.runtime_state.health_status == SourceHealthStatus.DEGRADED


def test_zero_result_anomaly_is_degraded_and_does_not_change_lifecycle(
    db_session: Session,
) -> None:
    seed_two_listings(db_session)

    summary = run_with_adapter(
        db_session,
        "search_page_empty.html",
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
    )

    source = db_session.scalars(select(Source).where(Source.code == FOUR_ZIDA_SOURCE_CODE)).one()
    assert summary.status == "PARTIAL"
    assert summary.zero_result_anomaly is True
    assert summary.not_seen_count == 0
    assert event_count(db_session, ListingEventType.STATUS_CHANGED) == 0
    assert {item.status for item in source.listings} == {ListingStatus.ACTIVE}
    assert source.runtime_state is not None
    assert source.runtime_state.health_status == SourceHealthStatus.DEGRADED
    assert source.runtime_state.consecutive_zero_result_count == 1


def test_disabled_source_gets_no_scheduled_job(db_session: Session) -> None:
    source = ensure_four_zida_source(db_session)
    source.is_enabled = False
    before_jobs = db_session.scalar(select(func.count()).select_from(JobRun))

    summary = run_scheduled_four_zida_crawl(
        db_session,
        mode=CrawlMode.FAST_DISCOVERY,
        interval_seconds=0,
    )

    after_jobs = db_session.scalar(select(func.count()).select_from(JobRun))
    assert summary is None
    assert after_jobs == before_jobs
    assert source.runtime_state is not None
    assert source.runtime_state.health_status == SourceHealthStatus.DISABLED


def test_scheduled_crawl_respects_interval(db_session: Session) -> None:
    source = ensure_four_zida_source(db_session)
    runtime_state = source.runtime_state
    assert runtime_state is not None
    runtime_state.last_attempt_at = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)

    summary = run_scheduled_four_zida_crawl(
        db_session,
        mode=CrawlMode.FAST_DISCOVERY,
        interval_seconds=3600,
        now=runtime_state.last_attempt_at + timedelta(minutes=10),
    )

    assert summary is None
    assert db_session.scalar(select(func.count()).select_from(JobRun)) == 0
