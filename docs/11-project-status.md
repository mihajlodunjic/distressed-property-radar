# Distressed Property Radar - Project Status

> Kratak mutable checkpoint za nastavak rada izmedju Codex sesija.
>
> Ovaj fajl opisuje samo trenutno stanje projekta.
> Specifikacije, arhitektura, phase detalji i changelog ne pripadaju ovde.

## Current State

    Project status: IN_PROGRESS
    Current phase: PHASE 4 - Property Resolution & Duplicate Matching
    Current task: Phase 4 - implement property resolution and duplicate matching
    Task state: READY

Phase 3 is complete.

## Completed Phases

    PHASE 0 - Repository & Development Foundation: COMPLETED
    PHASE 1 - Core Database & Domain Foundation: COMPLETED
    PHASE 2 - First Source: Basic Ingestion: COMPLETED
    PHASE 3 - Continuous Crawling & Listing History: COMPLETED

## Completed Tasks

- Phase 3 continuous crawling, source health, listing lifecycle/history, and job handling are implemented and verified for `four_zida`.

## Current Implementation Facts

- Backend: FastAPI application exists under `backend/app`.
- Backend configuration: centralized settings in `backend/app/core/config.py`, loaded from environment variables and optional root `.env`.
- Backend logging: basic startup logging exists and does not log secrets.
- Database: SQLAlchemy engine/session foundation exists in `backend/app/db`.
- Domain enums: Phase 1 enums plus `ListingRawRecordType` and `SourceHealthStatus` exist in `backend/app/domain/enums.py`.
- ORM models: `Source`, `SourceRuntimeState`, `Property`, `Listing`, `ListingEvent`, `ListingRawRecord`, and `JobRun` exist in `backend/app/db/models.py`.
- Migrations: Alembic is configured; current head is `0004_continuous_crawling_state`.
- Bootstrap sources: migrations seed stable `manual` and `four_zida` sources with `source_runtime_state` rows.
- Critical listing invariant: `listings` enforces `UNIQUE(source_id, external_listing_id)`.
- `listing_raw_records` stores deduped CARD/DETAIL raw payloads by listing, record type, and content hash.
- `listings` keeps lifecycle state including `ACTIVE`, `NOT_SEEN`, `REMOVED`, timestamps, state hashes, and `consecutive_not_seen_count`.
- `source_runtime_state` tracks source health, last success/attempt, mode-specific success timestamps, recent HTTP/parse errors, and zero-result anomalies.
- `job_runs` records crawl metrics including pages requested, cards seen/parsed, new/changed listings, not-seen count, details fetched, parse errors, and HTTP errors.
- First source: `backend/app/sources/four_zida` implements an HTTP-first 4zida adapter.
- 4zida discovery uses current target-market URLs for Zemun and Novi Beograd apartment sales with `m2From=35&m2To=90`.
- 4zida adapter supports pagination, known-listing boundary stopping, mocked/live HTTP, retry/error classification, and detail fetch.
- 4zida parser reads server-rendered JSON-LD ItemList/detail objects and falls back to listing links for identity only.
- 4zida crawler modes exist: `FAST_DISCOVERY`, `ACTIVE_MARKET_SCAN`, and `DEEP_RECONCILIATION`.
- CLI command: run from `backend` with `.\.venv\Scripts\python.exe -m app.ingestion.four_zida_discovery --mode fast-discovery --max-pages-per-market 1`.
- Fast discovery persists new listings and refreshes known listings without duplicate business events.
- Active market scan refreshes card observations, detects price changes, and only marks missing listings from complete non-anomalous scans.
- Deep reconciliation confirms `NOT_SEEN` listings and records `REMOVED` only on explicit 404/410 detail confirmation.
- Reappeared listings transition back to `ACTIVE` with one `REAPPEARED` event.
- Failed, partial, parser-failed, and zero-result anomaly scans do not create false removals.
- Parser fixtures exist under `backend/tests/fixtures/four_zida` and do not depend on live portal state.
- Backend tests cover Phase 0/1 checks plus Phase 2/3 parser, normalization, mocked HTTP, pagination, ingestion idempotency, raw records, job summaries, price changes, lifecycle transitions, source health, scheduled job handling, partial-scan safety, and zero-result anomaly safety.
- Health endpoint: `GET /health` checks application process, PostgreSQL connectivity, and PostGIS availability.
- Frontend: minimal Vite React shell exists under `frontend`.
- `.env.example` documents required variable names with local-only example values and no real secrets.
- Production deployment: none.
- Production data: none.

## Known Blockers

    None

## Known Important Issues

    None

## Production State

    Production deployed: NO
    Production crawler running: NO
    Historical market dataset accumulating: NO - no production crawler is running
    Historical data must be preserved: NO - no production data exists yet

## Next Task

Implement only:

    PHASE 4 - Property Resolution & Duplicate Matching

Exact first logical task:

    Introduce the minimal Phase 4 property-resolution persistence and deterministic
    candidate generation flow that links existing listings to candidate properties,
    records match decisions, creates a new Property when no conservative match exists,
    and preserves every original Listing.

Do not implement:

- valuation;
- liquidity analysis;
- seller/risk intelligence;
- LLM extraction;
- opportunity alerts;
- additional markets or sources.

## Required Context

Read first:

    AGENTS.md

Then:

    docs/07-phase-plan.md
    -> PHASE 4 - Property Resolution & Duplicate Matching

Relevant specification sections only:

    docs/02-system-architecture.md
    -> matching boundary
    -> property/listing separation

    docs/03-data-model.md
    -> properties
    -> property_listing_links
    -> property_match_candidates
    -> merge/split invariants
    -> images, only if needed

    docs/08-testing-specification.md
    -> property/listing identity tests
    -> duplicate matching tests
    -> idempotency tests relevant to Phase 4

Existing implementation to inspect:

    backend/app/domain/enums.py
    backend/app/db/models.py
    backend/alembic/
    backend/app/ingestion/
    backend/tests/

Do not load later-phase specifications unless a concrete Phase 4 dependency requires them.

## Phase 4 Completion Gate

Phase 4 may be marked `COMPLETED` only when its acceptance criteria from `docs/07-phase-plan.md` are satisfied.

At minimum verify that a representative dataset can:

- merge obvious duplicate listings;
- leave uncertain cases for review;
- create a new property when there is no match;
- preserve all original listings;
- rerun matching without uncontrolled duplicate decisions.

Do not use ML for Phase 4 matching.

## Update Rules

After a successful task, update only information needed by the next Codex session:

- `Current State`
- `Completed Phases`
- `Completed Tasks`
- `Current Implementation Facts`
- `Known Blockers`
- `Known Important Issues`
- `Production State`
- `Next Task`
- `Required Context`

Keep `Completed Tasks` limited to significant recent/current-phase milestones.

Git history is the detailed changelog.

Remove resolved blockers/issues instead of accumulating historical notes.

There must be exactly one primary `Next Task`.

When production historical data begins accumulating, explicitly set:

    Historical data must be preserved: YES

From that point onward, database reset/recreation is not a normal development shortcut.

When analytical modules exist, record only currently active significant versions when useful for continuation, for example:

    Matching: matching_v1
    Valuation: valuation_v1
    Risk: risk_rules_v1
    Deal formula: deal_v1
    Opportunity rules: opportunity_v1

Do not store version history here.

## Continuation Contract

A new Codex session should be able to read:

    AGENTS.md
    +
    this file

and immediately know:

    where the project is
    what matters about the current implementation
    whether production data is at risk
    what exact task comes next
    which additional documentation is required

If this file grows into a specification or changelog, compress it again.
