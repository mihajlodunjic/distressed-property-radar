from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Listing,
    ListingEvent,
    ListingRawRecord,
    Property,
    PropertyFeature,
    PropertyListingLink,
    PropertyMatchCandidate,
    Source,
)
from app.domain.enums import (
    CurrencyCode,
    DataSourceKind,
    ListingEventType,
    ListingStatus,
    MatchCandidateStatus,
    MatchDecision,
    SellerType,
    SourceHealthStatus,
)
from app.features.property_dataset import (
    build_effective_property_data,
    recalculate_property_market_dataset,
)
from app.ingestion.four_zida_discovery import (
    FOUR_ZIDA_SOURCE_CODE,
    CrawlMode,
    ensure_four_zida_source,
    run_four_zida_discovery,
)
from app.ingestion.nekretnine_rs_discovery import (
    NEKRETNINE_RS_SOURCE_CODE,
    ensure_nekretnine_rs_source,
    run_nekretnine_rs_crawl,
    run_nekretnine_rs_discovery,
)
from app.matching.property_resolution import resolve_listing_to_property
from app.sources.four_zida.adapter import FourZidaAdapter, FourZidaConfig
from app.sources.nekretnine_rs.adapter import NekretnineRsAdapter, NekretnineRsConfig

FOUR_ZIDA_FIXTURES = Path(__file__).parent / "fixtures" / "four_zida"
NEKRETNINE_RS_FIXTURES = Path(__file__).parent / "fixtures" / "nekretnine_rs"
FOUR_ZIDA_SEARCH_URL = "https://www.4zida.rs/prodaja-stanova/zemun-opstina-beograd"
FOUR_ZIDA_DETAIL_1_URL = (
    "https://www.4zida.rs/prodaja-stanova/gornji-grad-zemun-opstina-beograd/"
    "dvoiposoban-stan/64aaaaaaaaaaaaaaaaaaaaaa"
)
NEKRETNINE_RS_SEARCH_URL = (
    "https://www.nekretnine.rs/stambeni-objekti/stanovi/beograd-zemun/prodaja/"
    "?kvadratura_min=35&kvadratura_max=90"
)


def four_zida_fixture(name: str) -> str:
    return (FOUR_ZIDA_FIXTURES / name).read_text(encoding="utf-8")


def nekretnine_rs_fixture(name: str) -> str:
    return (NEKRETNINE_RS_FIXTURES / name).read_text(encoding="utf-8")


def make_four_zida_adapter(search_fixture: str = "search_page_complete_one_listing.html"):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == FOUR_ZIDA_SEARCH_URL:
            return httpx.Response(200, text=four_zida_fixture(search_fixture))
        if url == FOUR_ZIDA_DETAIL_1_URL:
            return httpx.Response(200, text=four_zida_fixture("detail_page.html"))
        return httpx.Response(404, text="not found")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = FourZidaAdapter(
        config=FourZidaConfig(
            search_urls=(FOUR_ZIDA_SEARCH_URL,),
            retry_count=0,
            min_request_delay_seconds=0,
        ),
        client=client,
    )
    return adapter, client


def make_nekretnine_rs_adapter(search_fixture: str = "search_page_complete_one_listing.html"):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        path = request.url.path
        if url == NEKRETNINE_RS_SEARCH_URL:
            return httpx.Response(200, text=nekretnine_rs_fixture(search_fixture))
        if path.endswith("/NKRS-1001/"):
            return httpx.Response(200, text=nekretnine_rs_fixture("detail_1001.html"))
        if path.endswith("/NKRS-1002/"):
            return httpx.Response(200, text=nekretnine_rs_fixture("detail_1002.html"))
        return httpx.Response(404, text="not found")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = NekretnineRsAdapter(
        config=NekretnineRsConfig(
            search_urls=(NEKRETNINE_RS_SEARCH_URL,),
            retry_count=0,
            min_request_delay_seconds=0,
        ),
        client=client,
    )
    return adapter, client


def ingest_four_zida(
    db_session: Session, search_fixture: str = "search_page_complete_one_listing.html"
):
    adapter, client = make_four_zida_adapter(search_fixture)
    try:
        return run_four_zida_discovery(db_session, adapter=adapter, max_pages_per_market=1)
    finally:
        asyncio.run(client.aclose())


def ingest_nekretnine_rs(
    db_session: Session,
    search_fixture: str = "search_page_complete_one_listing.html",
):
    adapter, client = make_nekretnine_rs_adapter(search_fixture)
    try:
        return run_nekretnine_rs_discovery(db_session, adapter=adapter, max_pages_per_market=1)
    finally:
        asyncio.run(client.aclose())


def crawl_nekretnine_rs(
    db_session: Session,
    search_fixture: str,
    *,
    mode: CrawlMode,
):
    adapter, client = make_nekretnine_rs_adapter(search_fixture)
    try:
        return run_nekretnine_rs_crawl(
            db_session,
            mode=mode,
            adapter=adapter,
            max_pages_per_market=1,
        )
    finally:
        asyncio.run(client.aclose())


def listing_for_source(db_session: Session, source_code: str, external_listing_id: str) -> Listing:
    return db_session.scalars(
        select(Listing)
        .join(Source)
        .where(
            Source.code == source_code,
            Listing.external_listing_id == external_listing_id,
        )
    ).one()


def count_rows(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model))


def create_listing(
    session: Session,
    source: Source,
    external_listing_id: str,
    *,
    location: str,
    size_m2: str,
    rooms: str,
    floor: int | None,
    title: str | None = None,
    first_seen_offset_days: int = 0,
) -> Listing:
    seen_at = datetime(2026, 8, 30, 12, 0, tzinfo=UTC) + timedelta(days=first_seen_offset_days)
    listing = Listing(
        source=source,
        external_listing_id=external_listing_id,
        url=f"https://example.test/{external_listing_id}",
        canonical_url=f"https://example.test/{external_listing_id}",
        title=title or location,
        asking_price=Decimal("150000.00"),
        currency=CurrencyCode.EUR,
        size_m2=Decimal(size_m2),
        rooms=Decimal(rooms),
        city_raw="Beograd",
        location_raw=location,
        floor=floor,
        seller_type=SellerType.AGENCY,
        status=ListingStatus.ACTIVE,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
    )
    session.add(listing)
    session.flush()
    return listing


def test_second_source_is_seeded_with_runtime_state(db_session: Session) -> None:
    source = ensure_nekretnine_rs_source(db_session)

    assert source.code == NEKRETNINE_RS_SOURCE_CODE
    assert source.source_type == DataSourceKind.SCRAPED
    assert source.base_url == "https://www.nekretnine.rs"
    assert source.supports_discovery is True
    assert source.supports_market_scan is True
    assert source.supports_detail_fetch is True
    assert source.runtime_state is not None


def test_shared_ingestion_keeps_first_and_second_source_listing_identity_separate(
    db_session: Session,
) -> None:
    four_summary = ingest_four_zida(db_session)
    nek_summary = ingest_nekretnine_rs(db_session)
    four_source = db_session.scalars(
        select(Source).where(Source.code == FOUR_ZIDA_SOURCE_CODE)
    ).one()
    nek_source = db_session.scalars(
        select(Source).where(Source.code == NEKRETNINE_RS_SOURCE_CODE)
    ).one()

    assert four_summary.status == "SUCCESS"
    assert nek_summary.status == "SUCCESS"
    assert four_summary.new_listings == 1
    assert nek_summary.new_listings == 1
    assert count_rows(db_session, Listing) == 2
    assert count_rows(db_session, ListingEvent) == 2
    assert count_rows(db_session, ListingRawRecord) == 4
    assert len(four_source.listings) == 1
    assert len(nek_source.listings) == 1
    assert four_source.runtime_state is not None
    assert nek_source.runtime_state is not None
    assert four_source.runtime_state.health_status == SourceHealthStatus.HEALTHY
    assert nek_source.runtime_state.health_status == SourceHealthStatus.HEALTHY


def test_cross_source_obvious_match_keeps_one_property_two_listings_and_two_histories(
    db_session: Session,
) -> None:
    ingest_four_zida(db_session)
    ingest_nekretnine_rs(db_session)
    four_listing = listing_for_source(
        db_session,
        FOUR_ZIDA_SOURCE_CODE,
        "64aaaaaaaaaaaaaaaaaaaaaa",
    )
    nek_listing = listing_for_source(db_session, NEKRETNINE_RS_SOURCE_CODE, "NKRS-1001")

    first = resolve_listing_to_property(db_session, four_listing)
    second = resolve_listing_to_property(db_session, nek_listing)
    property_ = db_session.get(Property, four_listing.property_id)
    assert property_ is not None
    recalculate_property_market_dataset(db_session, property_)
    effective = build_effective_property_data(db_session, property_)

    assert first.action == "NEW_PROPERTY"
    assert second.action == "AUTO_MATCH"
    assert four_listing.property_id == nek_listing.property_id
    assert count_rows(db_session, Property) == 1
    assert count_rows(db_session, PropertyListingLink) == 2
    assert count_rows(db_session, PropertyFeature) == 1
    assert property_.active_listing_count == 2
    assert property_.relist_count == 1
    assert {event.listing_id for event in db_session.scalars(select(ListingEvent)).all()} == {
        four_listing.id,
        nek_listing.id,
    }
    links = db_session.scalars(select(PropertyListingLink)).all()
    assert {link.listing_id for link in links} == {four_listing.id, nek_listing.id}
    assert {link.decision for link in links} == {MatchDecision.AUTO_MATCH}
    assert effective.provenance["size_m2"] == "property"
    assert not any(value.startswith("verified") for value in effective.provenance.values())


def test_cross_source_non_match_creates_separate_property_and_rejected_candidate(
    db_session: Session,
) -> None:
    first_source = ensure_four_zida_source(db_session)
    second_source = ensure_nekretnine_rs_source(db_session)
    first_listing = create_listing(
        db_session,
        first_source,
        "phase15-first",
        location="Takovska 10, Palilula",
        size_m2="72.00",
        rooms="3.00",
        floor=2,
    )
    second_listing = create_listing(
        db_session,
        second_source,
        "phase15-non-match",
        location="Takovska 10, Palilula",
        size_m2="95.00",
        rooms="4.00",
        floor=8,
        first_seen_offset_days=1,
    )
    resolve_listing_to_property(db_session, first_listing)

    result = resolve_listing_to_property(db_session, second_listing)

    candidate = db_session.scalars(select(PropertyMatchCandidate)).one()
    assert result.action == "NEW_PROPERTY"
    assert second_listing.property_id != first_listing.property_id
    assert count_rows(db_session, Property) == 2
    assert candidate.status == MatchCandidateStatus.REJECTED
    assert candidate.listing_id == second_listing.id


def test_cross_source_ambiguous_match_remains_pending_without_canonical_link(
    db_session: Session,
) -> None:
    first_source = ensure_four_zida_source(db_session)
    second_source = ensure_nekretnine_rs_source(db_session)
    first_listing = create_listing(
        db_session,
        first_source,
        "phase15-ambiguous-first",
        location="Bircaninova 15, Savski Venac",
        size_m2="72.00",
        rooms="3.00",
        floor=None,
    )
    second_listing = create_listing(
        db_session,
        second_source,
        "phase15-ambiguous-second",
        location="Bircaninova 15, Savski Venac",
        size_m2="73.00",
        rooms="3.00",
        floor=None,
        first_seen_offset_days=1,
    )
    resolve_listing_to_property(db_session, first_listing)

    result = resolve_listing_to_property(db_session, second_listing)

    candidate = db_session.scalars(select(PropertyMatchCandidate)).one()
    assert result.action == "POSSIBLE_MATCH"
    assert second_listing.property_id is None
    assert candidate.status == MatchCandidateStatus.PENDING
    assert candidate.listing_id == second_listing.id
    assert count_rows(db_session, PropertyListingLink) == 1


def test_second_source_active_scan_price_change_and_reappeared_listing_preserve_history(
    db_session: Session,
) -> None:
    ingest_nekretnine_rs(db_session, "search_page_complete_same.html")
    changed = crawl_nekretnine_rs(
        db_session,
        "search_page_price_changed.html",
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
    )
    first_missing = crawl_nekretnine_rs(
        db_session,
        "search_page_price_changed_one_listing.html",
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
    )
    reappeared = crawl_nekretnine_rs(
        db_session,
        "search_page_price_changed_complete_same.html",
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
    )

    listing = listing_for_source(db_session, NEKRETNINE_RS_SOURCE_CODE, "NKRS-1002")
    assert changed.changed_listings == 1
    assert first_missing.not_seen_count == 1
    assert reappeared.reappeared_count == 1
    assert listing.status == ListingStatus.ACTIVE
    assert listing.removed_at is None
    assert count_rows(db_session, Listing) == 2
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ListingEvent)
            .where(ListingEvent.event_type == ListingEventType.PRICE_CHANGED)
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ListingEvent)
            .where(ListingEvent.event_type == ListingEventType.REAPPEARED)
        )
        == 1
    )


def test_second_source_outage_and_parser_failure_do_not_create_false_removals(
    db_session: Session,
) -> None:
    ingest_four_zida(db_session)
    ingest_nekretnine_rs(db_session, "search_page_complete_same.html")
    four_listing = listing_for_source(
        db_session,
        FOUR_ZIDA_SOURCE_CODE,
        "64aaaaaaaaaaaaaaaaaaaaaa",
    )
    nek_source = db_session.scalars(
        select(Source).where(Source.code == NEKRETNINE_RS_SOURCE_CODE)
    ).one()

    def outage_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="source outage")

    outage_client = httpx.AsyncClient(transport=httpx.MockTransport(outage_handler))
    outage_adapter = NekretnineRsAdapter(
        config=NekretnineRsConfig(
            search_urls=(NEKRETNINE_RS_SEARCH_URL,),
            retry_count=0,
            min_request_delay_seconds=0,
        ),
        client=outage_client,
    )
    try:
        outage_summary = run_nekretnine_rs_crawl(
            db_session,
            mode=CrawlMode.ACTIVE_MARKET_SCAN,
            adapter=outage_adapter,
            max_pages_per_market=1,
        )
    finally:
        asyncio.run(outage_client.aclose())

    class ParserFailingAdapter(NekretnineRsAdapter):
        async def fetch_search_page(self, _url: str):
            raise ValueError("broken parser")

    parser_failure = run_nekretnine_rs_crawl(
        db_session,
        mode=CrawlMode.ACTIVE_MARKET_SCAN,
        adapter=ParserFailingAdapter(
            config=NekretnineRsConfig(
                search_urls=(NEKRETNINE_RS_SEARCH_URL,),
                retry_count=0,
                min_request_delay_seconds=0,
            )
        ),
        max_pages_per_market=1,
    )

    assert outage_summary.status == "FAILED"
    assert parser_failure.status == "FAILED"
    assert outage_summary.not_seen_count == 0
    assert parser_failure.not_seen_count == 0
    assert count_rows(db_session, Listing) == 3
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ListingEvent)
            .where(ListingEvent.event_type == ListingEventType.REMOVED)
        )
        == 0
    )
    assert {listing.status for listing in nek_source.listings} == {ListingStatus.ACTIVE}
    assert four_listing.status == ListingStatus.ACTIVE
    assert four_listing.property_id is None
    assert nek_source.runtime_state is not None
    assert nek_source.runtime_state.health_status == SourceHealthStatus.FAILED
    assert nek_source.runtime_state.recent_parse_error_count == 1
