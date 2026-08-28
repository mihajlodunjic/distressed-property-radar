from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import JobRun, Listing, ListingEvent, ListingRawRecord, Source
from app.domain.enums import ListingEventType
from app.ingestion.four_zida_discovery import FOUR_ZIDA_SOURCE_CODE, run_four_zida_discovery
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


def make_adapter(*, detail_1_html: str | None = None) -> tuple[FourZidaAdapter, httpx.AsyncClient]:
    detail_1 = detail_1_html or fixture("detail_page.html")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == SEARCH_URL:
            return httpx.Response(200, text=fixture("search_page_1.html"))
        if url == DETAIL_1_URL:
            return httpx.Response(200, text=detail_1)
        if url == DETAIL_2_URL:
            return httpx.Response(200, text=fixture("detail_missing_optional.html"))
        return httpx.Response(404, text="not found")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        FourZidaAdapter(
            config=FourZidaConfig(
                search_urls=(SEARCH_URL,),
                retry_count=0,
                min_request_delay_seconds=0,
            ),
            client=client,
        ),
        client,
    )


def test_ingestion_persists_listings_history_raw_records_and_job_summary(
    db_session: Session,
) -> None:
    adapter, client = make_adapter()
    try:
        first_summary = run_four_zida_discovery(
            db_session,
            adapter=adapter,
            max_pages_per_market=1,
        )
    finally:
        asyncio.run(client.aclose())

    assert first_summary.status == "SUCCESS"
    assert first_summary.pages_requested == 1
    assert first_summary.cards_seen == 2
    assert first_summary.cards_parsed == 2
    assert first_summary.new_listings == 2
    assert first_summary.details_fetched == 2

    source = db_session.scalars(select(Source).where(Source.code == FOUR_ZIDA_SOURCE_CODE)).one()
    listings = db_session.scalars(
        select(Listing).where(Listing.source_id == source.id).order_by(Listing.external_listing_id)
    ).all()
    discovered_events = db_session.scalars(
        select(ListingEvent).where(ListingEvent.event_type == ListingEventType.DISCOVERED)
    ).all()
    raw_record_count = db_session.scalar(select(func.count()).select_from(ListingRawRecord))
    job_run = db_session.scalars(
        select(JobRun).where(JobRun.id == UUID(first_summary.job_run_id))
    ).one()

    assert len(listings) == 2
    assert listings[0].asking_price is not None
    assert listings[0].card_state_hash is not None
    assert listings[0].detail_state_hash is not None
    assert len(discovered_events) == 2
    assert raw_record_count == 4
    assert job_run.new_listings == 2
    assert source.runtime_state is not None
    assert source.runtime_state.last_discovered_count == 2


def test_repeated_ingestion_does_not_duplicate_listings_or_discovered_events(
    db_session: Session,
) -> None:
    for _run_number in range(2):
        adapter, client = make_adapter()
        try:
            summary = run_four_zida_discovery(
                db_session,
                adapter=adapter,
                max_pages_per_market=1,
            )
        finally:
            asyncio.run(client.aclose())

    source = db_session.scalars(select(Source).where(Source.code == FOUR_ZIDA_SOURCE_CODE)).one()
    listing_count = db_session.scalar(
        select(func.count()).select_from(Listing).where(Listing.source_id == source.id)
    )
    discovered_count = db_session.scalar(
        select(func.count())
        .select_from(ListingEvent)
        .where(ListingEvent.event_type == ListingEventType.DISCOVERED)
    )
    price_change_count = db_session.scalar(
        select(func.count())
        .select_from(ListingEvent)
        .where(ListingEvent.event_type == ListingEventType.PRICE_CHANGED)
    )
    raw_record_count = db_session.scalar(select(func.count()).select_from(ListingRawRecord))

    assert summary.new_listings == 0
    assert summary.changed_listings == 0
    assert listing_count == 2
    assert discovered_count == 2
    assert price_change_count == 0
    assert raw_record_count == 4


def test_price_change_creates_one_price_changed_event(db_session: Session) -> None:
    adapter, client = make_adapter()
    try:
        run_four_zida_discovery(db_session, adapter=adapter, max_pages_per_market=1)
    finally:
        asyncio.run(client.aclose())

    changed_detail = fixture("detail_page.html").replace('"price": 180000', '"price": 170000')
    adapter, client = make_adapter(detail_1_html=changed_detail)
    try:
        changed_summary = run_four_zida_discovery(
            db_session,
            adapter=adapter,
            max_pages_per_market=1,
        )
    finally:
        asyncio.run(client.aclose())

    adapter, client = make_adapter(detail_1_html=changed_detail)
    try:
        unchanged_summary = run_four_zida_discovery(
            db_session,
            adapter=adapter,
            max_pages_per_market=1,
        )
    finally:
        asyncio.run(client.aclose())

    events = db_session.scalars(
        select(ListingEvent).where(ListingEvent.event_type == ListingEventType.PRICE_CHANGED)
    ).all()

    assert changed_summary.changed_listings == 1
    assert unchanged_summary.changed_listings == 0
    assert len(events) == 1
    assert events[0].old_price is not None
    assert events[0].new_price is not None
    assert str(events[0].old_price) == "180000.00"
    assert str(events[0].new_price) == "170000.00"
