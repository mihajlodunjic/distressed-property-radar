from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    JobRun,
    Listing,
    ListingEvent,
    ListingRawRecord,
    Source,
    SourceRuntimeState,
)
from app.domain.enums import (
    DataSourceKind,
    ListingEventType,
    ListingRawRecordType,
    ListingStatus,
    SellerType,
    SourceHealthStatus,
)
from app.ingestion.normalization import NormalizedListingData, normalize_listing
from app.sources.adapter_contract import ListingSourceAdapter, SourceFetchError
from app.sources.dto import RawListingCard, RawListingDetail
from app.watchlist.watchlist_service import evaluate_watch_rules_for_listing_event

TARGET_SIZE_MIN = Decimal("35")
TARGET_SIZE_MAX = Decimal("90")
DEFAULT_KNOWN_LISTING_STOP_THRESHOLD = 10
DEFAULT_REMOVAL_NOT_SEEN_SCAN_THRESHOLD = 2
DEFAULT_FAST_DISCOVERY_INTERVAL_SECONDS = 1800
DEFAULT_TARGET_LOCATION_MARKERS = ("zemun", "novi-beograd", "novi beograd")


class CrawlMode(StrEnum):
    FAST_DISCOVERY = "FAST_DISCOVERY"
    ACTIVE_MARKET_SCAN = "ACTIVE_MARKET_SCAN"
    DEEP_RECONCILIATION = "DEEP_RECONCILIATION"


@dataclass(frozen=True)
class SourceCrawlDefinition:
    code: str
    name: str
    base_url: str
    parser_version: str
    make_adapter: Callable[[], ListingSourceAdapter]
    target_size_min: Decimal = TARGET_SIZE_MIN
    target_size_max: Decimal = TARGET_SIZE_MAX
    target_location_markers: tuple[str, ...] = DEFAULT_TARGET_LOCATION_MARKERS
    source_type: DataSourceKind = DataSourceKind.SCRAPED
    supports_discovery: bool = True
    supports_market_scan: bool = True
    supports_detail_fetch: bool = True


@dataclass(frozen=True)
class IngestionSummary:
    job_run_id: str
    status: str
    pages_requested: int
    cards_seen: int
    cards_parsed: int
    new_listings: int
    changed_listings: int
    details_fetched: int
    parse_errors: int
    http_errors: int
    items_failed: int
    mode: str = CrawlMode.FAST_DISCOVERY.value
    complete: bool = True
    stopped_on_known_boundary: bool = False
    zero_result_anomaly: bool = False
    not_seen_count: int = 0
    removed_count: int = 0
    reappeared_count: int = 0

    def to_jsonable(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ListingPersistResult:
    is_new: bool = False
    is_changed: bool = False
    is_reappeared: bool = False
    events: tuple[ListingEvent, ...] = ()


@dataclass(frozen=True)
class MissingObservationResult:
    observed_count: int = 0
    changed_count: int = 0


async def run_source_crawl_async(
    session: Session,
    *,
    definition: SourceCrawlDefinition,
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
    mode = CrawlMode(mode)
    source = ensure_source(session, definition)
    runtime_state = _ensure_runtime_state(session, source)

    if not source.is_enabled:
        runtime_state.health_status = SourceHealthStatus.DISABLED
        if commit:
            session.commit()
        return _empty_summary(status="DISABLED", mode=mode)

    if mode == CrawlMode.DEEP_RECONCILIATION:
        return await _run_source_deep_reconciliation_async(
            session,
            definition=definition,
            source=source,
            runtime_state=runtime_state,
            adapter=adapter,
            detail_limit=detail_limit,
            removal_not_seen_scan_threshold=removal_not_seen_scan_threshold,
            commit=commit,
        )

    started_at = _utcnow()
    runtime_state.last_attempt_at = started_at

    job_run = JobRun(
        job_type=job_type or _job_type(definition, mode),
        source=source,
        started_at=started_at,
        status="RUNNING",
    )
    session.add(job_run)
    session.flush()

    cards_seen = 0
    cards_parsed = 0
    new_listings = 0
    changed_listings = 0
    details_fetched = 0
    parse_errors = 0
    http_errors = 0
    items_failed = 0
    not_seen_count = 0
    removed_count = 0
    reappeared_count = 0
    zero_result_anomaly = False
    discovery_complete = False
    stopped_on_known_boundary = False
    error_messages: list[str] = []

    owns_adapter = adapter is None
    active_adapter = adapter or definition.make_adapter()

    try:
        known_listing_ids = (
            _known_listing_ids(session, source) if mode == CrawlMode.FAST_DISCOVERY else None
        )
        if owns_adapter:
            async with active_adapter:
                discovery = await active_adapter.discover_cards(
                    max_pages_per_market,
                    known_listing_ids=known_listing_ids,
                    known_listing_stop_threshold=known_listing_stop_threshold
                    if known_listing_ids is not None
                    else None,
                )
        else:
            discovery = await active_adapter.discover_cards(
                max_pages_per_market,
                known_listing_ids=known_listing_ids,
                known_listing_stop_threshold=known_listing_stop_threshold
                if known_listing_ids is not None
                else None,
            )

        cards_seen = sum(len(getattr(page.parsed_page, "cards", [])) for page in discovery.pages)
        cards_parsed = len(discovery.cards)
        parse_errors += discovery.parse_errors
        http_errors += discovery.http_errors
        error_messages.extend(discovery.error_messages)
        discovery_complete = discovery.complete
        stopped_on_known_boundary = discovery.stopped_on_known_boundary
        zero_result_anomaly = (
            discovery.pages_requested > 0
            and cards_parsed == 0
            and discovery.http_errors == 0
            and discovery.parse_errors == 0
        )
        lifecycle_scan_complete = (
            mode == CrawlMode.ACTIVE_MARKET_SCAN
            and discovery.complete
            and not zero_result_anomaly
            and not error_messages
        )
        if mode == CrawlMode.ACTIVE_MARKET_SCAN and not discovery.complete:
            error_messages.append("PARTIAL_SCAN: active market scan did not cover full scope")
        if zero_result_anomaly:
            error_messages.append("ZERO_RESULT_ANOMALY: expected source cards but parsed zero")

        for index, card in enumerate(discovery.cards):
            detail: RawListingDetail | None = None
            listing = _find_listing(session, source, card.external_listing_id)
            should_fetch_detail = _should_fetch_detail(
                listing=listing,
                mode=mode,
                item_index=index,
                detail_limit=detail_limit,
                force_existing=force_detail_fetch_existing,
            )
            if should_fetch_detail:
                try:
                    detail = await active_adapter.fetch_detail(card.url)
                    details_fetched += 1
                except SourceFetchError as exc:
                    http_errors += 1
                    items_failed += 1
                    error_messages.append(f"{exc.category} {exc.url}: {exc}")
                except ValueError as exc:
                    parse_errors += 1
                    items_failed += 1
                    error_messages.append(f"PARSE_ERROR {card.url}: {exc}")

            result = _persist_listing(session, definition, source, card, detail, _utcnow())
            if result.is_new:
                new_listings += 1
            if result.is_changed:
                changed_listings += 1
            if result.is_reappeared:
                reappeared_count += 1
            _evaluate_watch_events(session, result.events)

        if lifecycle_scan_complete:
            missing_result = _mark_missing_listing_observations(
                session,
                definition,
                source,
                observed_listing_ids={card.external_listing_id for card in discovery.cards},
                observed_at=_utcnow(),
            )
            not_seen_count = missing_result.observed_count
            changed_listings += missing_result.changed_count

        finished_at = _utcnow()
        status = _job_status(
            error_messages=error_messages,
            cards_parsed=cards_parsed,
            zero_result_anomaly=zero_result_anomaly,
        )
        _finish_job_run(
            job_run,
            finished_at=finished_at,
            status=status,
            items_discovered=cards_parsed,
            items_processed=cards_parsed,
            items_changed=changed_listings,
            items_failed=items_failed,
            pages_requested=discovery.pages_requested,
            cards_seen=cards_seen,
            cards_parsed=cards_parsed,
            new_listings=new_listings,
            changed_listings=changed_listings,
            not_seen_count=not_seen_count,
            details_fetched=details_fetched,
            parse_errors=parse_errors,
            http_errors=http_errors,
            error_messages=error_messages,
        )
        _mark_runtime_finished(
            runtime_state,
            mode=mode,
            finished_at=finished_at,
            job_status=status,
            discovered_count=cards_parsed,
            parse_errors=parse_errors,
            http_errors=http_errors,
            zero_result_anomaly=zero_result_anomaly,
            error_messages=error_messages,
        )
    except Exception as exc:
        finished_at = _utcnow()
        items_failed += 1
        error_messages.append(f"{type(exc).__name__}: {exc}")
        _finish_job_run(
            job_run,
            finished_at=finished_at,
            status="FAILED",
            items_discovered=cards_parsed,
            items_processed=cards_parsed,
            items_changed=changed_listings,
            items_failed=items_failed,
            pages_requested=0,
            cards_seen=cards_seen,
            cards_parsed=cards_parsed,
            new_listings=new_listings,
            changed_listings=changed_listings,
            not_seen_count=not_seen_count,
            details_fetched=details_fetched,
            parse_errors=parse_errors,
            http_errors=http_errors,
            error_messages=error_messages,
        )
        _mark_runtime_error(runtime_state, finished_at=finished_at, error=exc)
        if commit:
            session.commit()
        raise

    if commit:
        session.commit()

    return IngestionSummary(
        job_run_id=str(job_run.id),
        status=job_run.status,
        pages_requested=job_run.pages_requested,
        cards_seen=job_run.cards_seen,
        cards_parsed=job_run.cards_parsed,
        new_listings=job_run.new_listings,
        changed_listings=job_run.changed_listings,
        details_fetched=job_run.details_fetched,
        parse_errors=job_run.parse_errors,
        http_errors=job_run.http_errors,
        items_failed=job_run.items_failed,
        mode=mode.value,
        complete=discovery_complete
        if mode == CrawlMode.ACTIVE_MARKET_SCAN
        else not bool(error_messages),
        stopped_on_known_boundary=stopped_on_known_boundary,
        zero_result_anomaly=zero_result_anomaly,
        not_seen_count=job_run.not_seen_count,
        removed_count=removed_count,
        reappeared_count=reappeared_count,
    )


async def run_source_discovery_async(
    session: Session,
    *,
    definition: SourceCrawlDefinition,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    commit: bool = False,
) -> IngestionSummary:
    return await run_source_crawl_async(
        session,
        definition=definition,
        mode=CrawlMode.FAST_DISCOVERY,
        job_type=f"{definition.code}_manual_discovery",
        adapter=adapter,
        max_pages_per_market=max_pages_per_market,
        detail_limit=detail_limit,
        force_detail_fetch_existing=True,
        commit=commit,
    )


def run_source_discovery(
    session: Session,
    *,
    definition: SourceCrawlDefinition,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    commit: bool = False,
) -> IngestionSummary:
    return asyncio.run(
        run_source_discovery_async(
            session,
            definition=definition,
            adapter=adapter,
            max_pages_per_market=max_pages_per_market,
            detail_limit=detail_limit,
            commit=commit,
        )
    )


def run_source_crawl(
    session: Session,
    *,
    definition: SourceCrawlDefinition,
    mode: CrawlMode = CrawlMode.FAST_DISCOVERY,
    adapter: ListingSourceAdapter | None = None,
    max_pages_per_market: int = 1,
    detail_limit: int | None = None,
    known_listing_stop_threshold: int = DEFAULT_KNOWN_LISTING_STOP_THRESHOLD,
    removal_not_seen_scan_threshold: int = DEFAULT_REMOVAL_NOT_SEEN_SCAN_THRESHOLD,
    force_detail_fetch_existing: bool = False,
    commit: bool = False,
) -> IngestionSummary:
    return asyncio.run(
        run_source_crawl_async(
            session,
            definition=definition,
            mode=mode,
            adapter=adapter,
            max_pages_per_market=max_pages_per_market,
            detail_limit=detail_limit,
            known_listing_stop_threshold=known_listing_stop_threshold,
            removal_not_seen_scan_threshold=removal_not_seen_scan_threshold,
            force_detail_fetch_existing=force_detail_fetch_existing,
            commit=commit,
        )
    )


async def run_scheduled_source_crawl_async(
    session: Session,
    *,
    definition: SourceCrawlDefinition,
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
    source = ensure_source(session, definition)
    runtime_state = _ensure_runtime_state(session, source)
    if not source.is_enabled:
        runtime_state.health_status = SourceHealthStatus.DISABLED
        if commit:
            session.commit()
        return None

    due_at = now or _utcnow()
    if (
        interval_seconds > 0
        and runtime_state.last_attempt_at is not None
        and due_at - runtime_state.last_attempt_at < timedelta(seconds=interval_seconds)
    ):
        return None

    return await run_source_crawl_async(
        session,
        definition=definition,
        mode=mode,
        adapter=adapter,
        max_pages_per_market=max_pages_per_market,
        detail_limit=detail_limit,
        known_listing_stop_threshold=known_listing_stop_threshold,
        removal_not_seen_scan_threshold=removal_not_seen_scan_threshold,
        commit=commit,
    )


def run_scheduled_source_crawl(
    session: Session,
    *,
    definition: SourceCrawlDefinition,
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
    return asyncio.run(
        run_scheduled_source_crawl_async(
            session,
            definition=definition,
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
    )


async def run_source_crawl_loop_async(
    session: Session,
    *,
    definition: SourceCrawlDefinition,
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
    if iterations < 1:
        raise ValueError("iterations must be at least 1")

    summaries: list[IngestionSummary] = []
    for iteration in range(iterations):
        summary = await run_source_crawl_async(
            session,
            definition=definition,
            mode=mode,
            adapter=adapter,
            max_pages_per_market=max_pages_per_market,
            detail_limit=detail_limit,
            known_listing_stop_threshold=known_listing_stop_threshold,
            removal_not_seen_scan_threshold=removal_not_seen_scan_threshold,
            commit=commit,
        )
        summaries.append(summary)
        if iteration < iterations - 1:
            await asyncio.sleep(max(interval_seconds, 0))
    return summaries


def run_source_crawl_loop(
    session: Session,
    *,
    definition: SourceCrawlDefinition,
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
    return asyncio.run(
        run_source_crawl_loop_async(
            session,
            definition=definition,
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
    )


def ensure_source(session: Session, definition: SourceCrawlDefinition) -> Source:
    source = session.scalars(select(Source).where(Source.code == definition.code)).one_or_none()
    if source is not None:
        return source
    source = Source(
        name=definition.name,
        code=definition.code,
        source_type=definition.source_type,
        base_url=definition.base_url,
        is_enabled=True,
        supports_discovery=definition.supports_discovery,
        supports_market_scan=definition.supports_market_scan,
        supports_detail_fetch=definition.supports_detail_fetch,
        runtime_state=SourceRuntimeState(),
    )
    session.add(source)
    session.flush()
    return source


async def _run_source_deep_reconciliation_async(
    session: Session,
    *,
    definition: SourceCrawlDefinition,
    source: Source,
    runtime_state: SourceRuntimeState,
    adapter: ListingSourceAdapter | None,
    detail_limit: int | None,
    removal_not_seen_scan_threshold: int,
    commit: bool,
) -> IngestionSummary:
    started_at = _utcnow()
    runtime_state.last_attempt_at = started_at
    job_run = JobRun(
        job_type=_job_type(definition, CrawlMode.DEEP_RECONCILIATION),
        source=source,
        started_at=started_at,
        status="RUNNING",
    )
    session.add(job_run)
    session.flush()

    details_fetched = 0
    http_errors = 0
    parse_errors = 0
    items_failed = 0
    changed_listings = 0
    removed_count = 0
    reappeared_count = 0
    error_messages: list[str] = []

    candidates = [
        listing
        for listing in session.scalars(
            select(Listing).where(
                Listing.source_id == source.id,
                Listing.status == ListingStatus.NOT_SEEN,
                Listing.consecutive_not_seen_count >= removal_not_seen_scan_threshold,
            )
        ).all()
        if _listing_in_current_target_scope(listing, definition)
    ]
    if detail_limit is not None:
        candidates = candidates[:detail_limit]

    owns_adapter = adapter is None
    active_adapter = adapter or definition.make_adapter()

    try:
        if owns_adapter:
            await active_adapter.__aenter__()
        for listing in candidates:
            detail_url = listing.canonical_url or listing.url
            if detail_url is None:
                parse_errors += 1
                items_failed += 1
                error_messages.append(
                    f"PARSE_ERROR {listing.external_listing_id}: missing detail URL"
                )
                continue
            try:
                detail = await active_adapter.fetch_detail(detail_url)
                details_fetched += 1
            except SourceFetchError as exc:
                if exc.status_code in {404, 410}:
                    _mark_removed(session, listing=listing, detected_at=_utcnow())
                    removed_count += 1
                    changed_listings += 1
                    continue
                http_errors += 1
                items_failed += 1
                error_messages.append(f"{exc.category} {exc.url}: {exc}")
            except ValueError as exc:
                parse_errors += 1
                items_failed += 1
                error_messages.append(f"PARSE_ERROR {detail_url}: {exc}")
            else:
                card = _card_from_detail(detail, definition)
                result = _persist_listing(session, definition, source, card, detail, _utcnow())
                if result.is_changed:
                    changed_listings += 1
                if result.is_reappeared:
                    reappeared_count += 1
                _evaluate_watch_events(session, result.events)
        if owns_adapter:
            await active_adapter.__aexit__(None, None, None)
    except Exception as exc:
        if owns_adapter:
            await active_adapter.__aexit__(type(exc), exc, exc.__traceback__)
        finished_at = _utcnow()
        error_messages.append(f"{type(exc).__name__}: {exc}")
        _finish_job_run(
            job_run,
            finished_at=finished_at,
            status="FAILED",
            items_discovered=0,
            items_processed=len(candidates),
            items_changed=changed_listings,
            items_failed=items_failed + 1,
            pages_requested=0,
            cards_seen=0,
            cards_parsed=0,
            new_listings=0,
            changed_listings=changed_listings,
            not_seen_count=len(candidates),
            details_fetched=details_fetched,
            parse_errors=parse_errors,
            http_errors=http_errors,
            error_messages=error_messages,
        )
        _mark_runtime_error(runtime_state, finished_at=finished_at, error=exc)
        if commit:
            session.commit()
        raise

    finished_at = _utcnow()
    status = _job_status(error_messages=error_messages, cards_parsed=len(candidates))
    _finish_job_run(
        job_run,
        finished_at=finished_at,
        status=status,
        items_discovered=0,
        items_processed=len(candidates),
        items_changed=changed_listings,
        items_failed=items_failed,
        pages_requested=0,
        cards_seen=0,
        cards_parsed=0,
        new_listings=0,
        changed_listings=changed_listings,
        not_seen_count=len(candidates),
        details_fetched=details_fetched,
        parse_errors=parse_errors,
        http_errors=http_errors,
        error_messages=error_messages,
    )
    _mark_runtime_finished(
        runtime_state,
        mode=CrawlMode.DEEP_RECONCILIATION,
        finished_at=finished_at,
        job_status=status,
        discovered_count=0,
        parse_errors=parse_errors,
        http_errors=http_errors,
        zero_result_anomaly=False,
        error_messages=error_messages,
    )
    if commit:
        session.commit()

    return IngestionSummary(
        job_run_id=str(job_run.id),
        status=job_run.status,
        pages_requested=job_run.pages_requested,
        cards_seen=job_run.cards_seen,
        cards_parsed=job_run.cards_parsed,
        new_listings=job_run.new_listings,
        changed_listings=job_run.changed_listings,
        details_fetched=job_run.details_fetched,
        parse_errors=job_run.parse_errors,
        http_errors=job_run.http_errors,
        items_failed=job_run.items_failed,
        mode=CrawlMode.DEEP_RECONCILIATION.value,
        not_seen_count=job_run.not_seen_count,
        removed_count=removed_count,
        reappeared_count=reappeared_count,
    )


def _persist_listing(
    session: Session,
    definition: SourceCrawlDefinition,
    source: Source,
    card: RawListingCard,
    detail: RawListingDetail | None,
    seen_at: datetime,
) -> ListingPersistResult:
    normalized = normalize_listing(card, detail)
    listing = session.scalars(
        select(Listing).where(
            Listing.source_id == source.id,
            Listing.external_listing_id == card.external_listing_id,
        )
    ).one_or_none()

    card_hash = _stable_hash(_card_payload(card))
    detail_hash = _stable_hash(_detail_payload(detail)) if detail else None

    if listing is None:
        listing = Listing(
            source=source,
            external_listing_id=card.external_listing_id,
            url=card.url,
            canonical_url=card.canonical_url,
            status=ListingStatus.ACTIVE,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            last_card_seen_at=seen_at,
            last_detail_fetch_at=seen_at if detail else None,
            consecutive_not_seen_count=0,
            card_state_hash=card_hash,
            detail_state_hash=detail_hash,
        )
        _apply_normalized_data(listing, normalized, allow_null_price=True)
        session.add(listing)
        session.flush()
        card_record = _add_raw_record(
            session,
            definition=definition,
            listing=listing,
            record_type=ListingRawRecordType.CARD,
            source_url=card.url,
            payload=_card_payload(card),
            content_hash=card_hash,
        )
        if detail is not None and detail_hash is not None:
            _add_raw_record(
                session,
                definition=definition,
                listing=listing,
                record_type=ListingRawRecordType.DETAIL,
                source_url=detail.url,
                payload=_detail_payload(detail),
                content_hash=detail_hash,
            )
        discovered_event = ListingEvent(
            listing=listing,
            event_type=ListingEventType.DISCOVERED,
            detected_at=seen_at,
            old_value_json=None,
            new_value_json={
                "status": ListingStatus.ACTIVE.value,
                "external_listing_id": card.external_listing_id,
                "url": card.canonical_url,
            },
            source_record_id=card_record.id,
        )
        session.add(discovered_event)
        session.flush()
        return ListingPersistResult(is_new=True, events=(discovered_event,))

    old_price = listing.asking_price
    old_status = listing.status
    old_description = listing.description
    old_seller = _seller_snapshot(listing)
    listing.last_seen_at = seen_at
    listing.last_card_seen_at = seen_at
    if detail is not None:
        listing.last_detail_fetch_at = seen_at
    listing.url = card.url
    listing.canonical_url = card.canonical_url
    listing.status = ListingStatus.ACTIVE
    listing.removed_at = None
    listing.consecutive_not_seen_count = 0
    listing.card_state_hash = card_hash
    if detail_hash is not None:
        listing.detail_state_hash = detail_hash

    _apply_normalized_data(
        listing,
        normalized,
        allow_null_price=normalized.asking_price is not None,
    )
    card_record = _add_raw_record(
        session,
        definition=definition,
        listing=listing,
        record_type=ListingRawRecordType.CARD,
        source_url=card.url,
        payload=_card_payload(card),
        content_hash=card_hash,
    )
    detail_record = None
    if detail is not None and detail_hash is not None:
        detail_record = _add_raw_record(
            session,
            definition=definition,
            listing=listing,
            record_type=ListingRawRecordType.DETAIL,
            source_url=detail.url,
            payload=_detail_payload(detail),
            content_hash=detail_hash,
        )

    is_changed = False
    is_reappeared = old_status in {ListingStatus.NOT_SEEN, ListingStatus.REMOVED}
    events: list[ListingEvent] = []
    if is_reappeared:
        events.append(
            ListingEvent(
                listing=listing,
                event_type=ListingEventType.REAPPEARED,
                detected_at=seen_at,
                old_value_json={"status": old_status.value},
                new_value_json={"status": ListingStatus.ACTIVE.value},
                source_record_id=detail_record.id if detail_record is not None else card_record.id,
            )
        )
        is_changed = True

    new_price = listing.asking_price
    if old_price is not None and new_price is not None and old_price != new_price:
        events.append(
            ListingEvent(
                listing=listing,
                event_type=ListingEventType.PRICE_CHANGED,
                detected_at=seen_at,
                old_value_json={"asking_price": _decimal_to_string(old_price)},
                new_value_json={"asking_price": _decimal_to_string(new_price)},
                old_price=old_price,
                new_price=new_price,
                source_record_id=detail_record.id if detail_record is not None else card_record.id,
            )
        )
        is_changed = True

    if old_description != listing.description:
        events.append(
            ListingEvent(
                listing=listing,
                event_type=ListingEventType.DESCRIPTION_CHANGED,
                detected_at=seen_at,
                old_value_json={"description": old_description},
                new_value_json={"description": listing.description},
                source_record_id=detail_record.id if detail_record is not None else card_record.id,
            )
        )
        is_changed = True

    new_seller = _seller_snapshot(listing)
    if old_seller != new_seller:
        events.append(
            ListingEvent(
                listing=listing,
                event_type=ListingEventType.SELLER_CHANGED,
                detected_at=seen_at,
                old_value_json=old_seller,
                new_value_json=new_seller,
                source_record_id=detail_record.id if detail_record is not None else card_record.id,
            )
        )
        is_changed = True

    if events:
        session.add_all(events)
        session.flush()
    return ListingPersistResult(
        is_changed=is_changed,
        is_reappeared=is_reappeared,
        events=tuple(events),
    )


def _apply_normalized_data(
    listing: Listing,
    data: NormalizedListingData,
    *,
    allow_null_price: bool,
) -> None:
    if data.title is not None:
        listing.title = data.title
    if data.description is not None:
        listing.description = data.description
    if data.asking_price is not None or allow_null_price:
        listing.asking_price = data.asking_price
        listing.currency = data.currency
        listing.price_per_m2 = data.price_per_m2
    if data.size_m2 is not None:
        listing.size_m2 = data.size_m2
    if data.city_raw is not None:
        listing.city_raw = data.city_raw
    if data.location_raw is not None:
        listing.location_raw = data.location_raw
    if data.rooms is not None:
        listing.rooms = data.rooms
    if data.floor is not None:
        listing.floor = data.floor
    if data.total_floors is not None:
        listing.total_floors = data.total_floors
    if data.seller_type != SellerType.UNKNOWN or listing.seller_type == SellerType.UNKNOWN:
        listing.seller_type = data.seller_type
    if data.seller_name is not None:
        listing.seller_name = data.seller_name
    if data.agency_name is not None:
        listing.agency_name = data.agency_name


def _seller_snapshot(listing: Listing) -> dict[str, object]:
    return {
        "seller_type": listing.seller_type.value,
        "seller_name": listing.seller_name,
        "agency_name": listing.agency_name,
    }


def _evaluate_watch_events(session: Session, events: tuple[ListingEvent, ...]) -> None:
    if not events:
        return
    settings = get_settings()
    for event in events:
        evaluate_watch_rules_for_listing_event(
            session,
            event,
            app_base_url=settings.app_base_url,
        )


def _find_listing(session: Session, source: Source, external_listing_id: str) -> Listing | None:
    return session.scalars(
        select(Listing).where(
            Listing.source_id == source.id,
            Listing.external_listing_id == external_listing_id,
        )
    ).one_or_none()


def _known_listing_ids(session: Session, source: Source) -> set[str]:
    return set(
        session.scalars(
            select(Listing.external_listing_id).where(Listing.source_id == source.id)
        ).all()
    )


def _should_fetch_detail(
    *,
    listing: Listing | None,
    mode: CrawlMode,
    item_index: int,
    detail_limit: int | None,
    force_existing: bool = False,
) -> bool:
    if detail_limit is not None and item_index >= detail_limit:
        return False
    if listing is None:
        return True
    if force_existing:
        return True
    if listing.detail_state_hash is None:
        return True
    return mode == CrawlMode.DEEP_RECONCILIATION


def _mark_missing_listing_observations(
    session: Session,
    definition: SourceCrawlDefinition,
    source: Source,
    *,
    observed_listing_ids: set[str],
    observed_at: datetime,
) -> MissingObservationResult:
    candidates = session.scalars(
        select(Listing).where(
            Listing.source_id == source.id,
            Listing.status.in_([ListingStatus.ACTIVE, ListingStatus.NOT_SEEN]),
        )
    ).all()
    missing_count = 0
    changed_count = 0
    for listing in candidates:
        if listing.external_listing_id in observed_listing_ids:
            continue
        if not _listing_in_current_target_scope(listing, definition):
            continue
        missing_count += 1
        old_status = listing.status
        listing.consecutive_not_seen_count += 1
        listing.next_check_at = observed_at
        if old_status == ListingStatus.ACTIVE:
            listing.status = ListingStatus.NOT_SEEN
            changed_count += 1
            session.add(
                ListingEvent(
                    listing=listing,
                    event_type=ListingEventType.STATUS_CHANGED,
                    detected_at=observed_at,
                    old_value_json={"status": ListingStatus.ACTIVE.value},
                    new_value_json={"status": ListingStatus.NOT_SEEN.value},
                )
            )
    return MissingObservationResult(observed_count=missing_count, changed_count=changed_count)


def _listing_in_current_target_scope(listing: Listing, definition: SourceCrawlDefinition) -> bool:
    if listing.size_m2 is None:
        return False
    if listing.size_m2 < definition.target_size_min or listing.size_m2 > definition.target_size_max:
        return False
    location_text = " ".join(
        value
        for value in (
            listing.location_raw,
            listing.city_raw,
            listing.canonical_url,
            listing.url,
        )
        if value
    ).lower()
    return any(marker in location_text for marker in definition.target_location_markers)


def _mark_removed(session: Session, *, listing: Listing, detected_at: datetime) -> None:
    if listing.status == ListingStatus.REMOVED:
        return
    old_status = listing.status
    listing.status = ListingStatus.REMOVED
    listing.removed_at = detected_at
    session.add(
        ListingEvent(
            listing=listing,
            event_type=ListingEventType.REMOVED,
            detected_at=detected_at,
            old_value_json={"status": old_status.value},
            new_value_json={"status": ListingStatus.REMOVED.value},
        )
    )


def _card_from_detail(
    detail: RawListingDetail,
    definition: SourceCrawlDefinition,
) -> RawListingCard:
    return RawListingCard(
        external_listing_id=detail.external_listing_id,
        url=detail.url,
        canonical_url=detail.canonical_url,
        title_raw=detail.title_raw,
        price_raw=detail.price_raw,
        currency_raw=detail.currency_raw,
        location_raw=detail.location_raw,
        size_raw=detail.size_raw,
        rooms_raw=detail.rooms_raw,
        floor_raw=detail.floor_raw,
        source_published_at_raw=detail.source_published_at_raw,
        additional_card_data={"source": f"{definition.code}_deep_reconciliation_detail"},
    )


def _add_raw_record(
    session: Session,
    *,
    definition: SourceCrawlDefinition,
    listing: Listing,
    record_type: ListingRawRecordType,
    source_url: str,
    payload: dict[str, object],
    content_hash: str,
) -> ListingRawRecord:
    existing = session.scalars(
        select(ListingRawRecord).where(
            ListingRawRecord.listing_id == listing.id,
            ListingRawRecord.record_type == record_type,
            ListingRawRecord.content_hash == content_hash,
        )
    ).one_or_none()
    if existing is not None:
        return existing
    record = ListingRawRecord(
        listing=listing,
        record_type=record_type,
        source_url=source_url,
        raw_payload=payload,
        content_type="application/json",
        content_hash=content_hash,
        parser_version=definition.parser_version,
    )
    session.add(record)
    session.flush()
    return record


def _card_payload(card: RawListingCard) -> dict[str, object]:
    return {
        "external_listing_id": card.external_listing_id,
        "url": card.url,
        "canonical_url": card.canonical_url,
        "title_raw": card.title_raw,
        "price_raw": card.price_raw,
        "currency_raw": card.currency_raw,
        "location_raw": card.location_raw,
        "size_raw": card.size_raw,
        "rooms_raw": card.rooms_raw,
        "floor_raw": card.floor_raw,
        "source_published_at_raw": card.source_published_at_raw,
        "additional_card_data": card.additional_card_data,
    }


def _detail_payload(detail: RawListingDetail | None) -> dict[str, object]:
    if detail is None:
        return {}
    return {
        "external_listing_id": detail.external_listing_id,
        "url": detail.url,
        "canonical_url": detail.canonical_url,
        "title_raw": detail.title_raw,
        "description_raw": detail.description_raw,
        "price_raw": detail.price_raw,
        "currency_raw": detail.currency_raw,
        "size_raw": detail.size_raw,
        "location_raw": detail.location_raw,
        "rooms_raw": detail.rooms_raw,
        "floor_raw": detail.floor_raw,
        "seller_raw": detail.seller_raw,
        "agency_raw": detail.agency_raw,
        "property_attributes_raw": detail.property_attributes_raw,
        "image_urls": detail.image_urls,
        "source_published_at_raw": detail.source_published_at_raw,
        "raw_payload_reference": detail.raw_payload_reference,
    }


def _stable_hash(payload: dict[str, object]) -> str:
    import hashlib

    encoded = json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return _decimal_to_string(value)
    return str(value)


def _decimal_to_string(value: Decimal) -> str:
    return format(value, "f")


def _ensure_runtime_state(session: Session, source: Source) -> SourceRuntimeState:
    if source.runtime_state is not None:
        return source.runtime_state
    runtime_state = SourceRuntimeState(source=source)
    session.add(runtime_state)
    session.flush()
    return runtime_state


def _finish_job_run(
    job_run: JobRun,
    *,
    finished_at: datetime,
    status: str,
    items_discovered: int,
    items_processed: int,
    items_changed: int,
    items_failed: int,
    pages_requested: int,
    cards_seen: int,
    cards_parsed: int,
    new_listings: int,
    changed_listings: int,
    not_seen_count: int,
    details_fetched: int,
    parse_errors: int,
    http_errors: int,
    error_messages: list[str],
) -> None:
    job_run.finished_at = finished_at
    job_run.status = status
    job_run.items_discovered = items_discovered
    job_run.items_processed = items_processed
    job_run.items_changed = items_changed
    job_run.items_failed = items_failed
    job_run.pages_requested = pages_requested
    job_run.cards_seen = cards_seen
    job_run.cards_parsed = cards_parsed
    job_run.new_listings = new_listings
    job_run.changed_listings = changed_listings
    job_run.not_seen_count = not_seen_count
    job_run.details_fetched = details_fetched
    job_run.parse_errors = parse_errors
    job_run.http_errors = http_errors
    job_run.error_summary = "\n".join(error_messages)[:4000] if error_messages else None


def _mark_runtime_finished(
    runtime_state: SourceRuntimeState,
    *,
    mode: CrawlMode,
    finished_at: datetime,
    job_status: str,
    discovered_count: int,
    parse_errors: int,
    http_errors: int,
    zero_result_anomaly: bool,
    error_messages: list[str],
) -> None:
    if job_status == "SUCCESS":
        runtime_state.last_success_at = finished_at
        if mode == CrawlMode.FAST_DISCOVERY:
            runtime_state.last_discovery_success_at = finished_at
        elif mode == CrawlMode.ACTIVE_MARKET_SCAN:
            runtime_state.last_market_scan_success_at = finished_at
    runtime_state.last_discovered_count = discovered_count
    runtime_state.recent_parse_error_count = parse_errors
    runtime_state.recent_http_error_count = http_errors
    if zero_result_anomaly:
        runtime_state.consecutive_zero_result_count += 1
    else:
        runtime_state.consecutive_zero_result_count = 0
    runtime_state.health_status = _health_status(
        job_status=job_status,
        parse_errors=parse_errors,
        http_errors=http_errors,
        zero_result_anomaly=zero_result_anomaly,
    )
    if error_messages:
        runtime_state.last_error_at = finished_at
        runtime_state.last_error_type = job_status
        runtime_state.last_error_message = "\n".join(error_messages)[:4000]
    else:
        runtime_state.last_error_at = None
        runtime_state.last_error_type = None
        runtime_state.last_error_message = None


def _mark_runtime_error(
    runtime_state: SourceRuntimeState,
    *,
    finished_at: datetime,
    error: Exception,
) -> None:
    runtime_state.last_error_at = finished_at
    runtime_state.last_error_type = type(error).__name__
    runtime_state.last_error_message = str(error)[:4000]
    runtime_state.health_status = SourceHealthStatus.FAILED
    runtime_state.recent_http_error_count += 1 if isinstance(error, SourceFetchError) else 0


def _job_status(
    *,
    error_messages: list[str],
    cards_parsed: int,
    zero_result_anomaly: bool = False,
) -> str:
    if not error_messages:
        return "SUCCESS"
    if cards_parsed > 0 or zero_result_anomaly:
        return "PARTIAL"
    return "FAILED"


def _health_status(
    *,
    job_status: str,
    parse_errors: int,
    http_errors: int,
    zero_result_anomaly: bool,
) -> SourceHealthStatus:
    if job_status == "FAILED":
        return SourceHealthStatus.FAILED
    if job_status == "PARTIAL" or parse_errors > 0 or http_errors > 0 or zero_result_anomaly:
        return SourceHealthStatus.DEGRADED
    return SourceHealthStatus.HEALTHY


def _empty_summary(*, status: str, mode: CrawlMode) -> IngestionSummary:
    return IngestionSummary(
        job_run_id="",
        status=status,
        pages_requested=0,
        cards_seen=0,
        cards_parsed=0,
        new_listings=0,
        changed_listings=0,
        details_fetched=0,
        parse_errors=0,
        http_errors=0,
        items_failed=0,
        mode=mode.value,
        complete=False,
    )


def _job_type(definition: SourceCrawlDefinition, mode: CrawlMode) -> str:
    return f"{definition.code}_{mode.value.lower()}"


def _utcnow() -> datetime:
    return datetime.now(UTC)
