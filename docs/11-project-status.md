# Distressed Property Radar - Project Status

> Kratak mutable checkpoint za nastavak rada izmedju Codex sesija.
>
> Ovaj fajl opisuje samo trenutno stanje projekta.
> Specifikacije, arhitektura, phase detalji i changelog ne pripadaju ovde.

## Current State

    Project status: IN_PROGRESS
    Current phase: PHASE 6 - Comparable Engine & V1 Valuation
    Current task: Phase 6 - implement comparable selection and V1 valuation
    Task state: READY

Phase 5 is complete.

## Completed Phases

    PHASE 0 - Repository & Development Foundation: COMPLETED
    PHASE 1 - Core Database & Domain Foundation: COMPLETED
    PHASE 2 - First Source: Basic Ingestion: COMPLETED
    PHASE 3 - Continuous Crawling & Listing History: COMPLETED
    PHASE 4 - Property Resolution & Duplicate Matching: COMPLETED
    PHASE 5 - Location, Features & Market Dataset: COMPLETED

## Completed Tasks

- Phase 5 normalized location, effective property data, property features, market dataset recalculation, Data Quality V1, and persistence are implemented and verified.

## Current Implementation Facts

- Backend: FastAPI application exists under `backend/app`.
- Backend configuration: centralized settings in `backend/app/core/config.py`, loaded from environment variables and optional root `.env`.
- Backend logging: basic startup logging exists and does not log secrets.
- Database: SQLAlchemy engine/session foundation exists in `backend/app/db`.
- Domain enums: Phase 1 enums plus `ListingRawRecordType`, `SourceHealthStatus`, `MatchDecision`, and `MatchCandidateStatus` exist in `backend/app/domain/enums.py`.
- ORM models: `Source`, `SourceRuntimeState`, `Property`, `Listing`, `ListingEvent`, `ListingRawRecord`, `PropertyListingLink`, `PropertyMatchCandidate`, `PropertyFeature`, `DataQualityAssessment`, and `JobRun` exist in `backend/app/db/models.py`.
- Migrations: Alembic is configured; current head is `0006_market_dataset`.
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
- Matching module: `backend/app/matching/property_resolution.py` implements deterministic `deterministic_v1` property resolution without ML.
- Matching uses cheap candidate filters before scoring; it does not evaluate every listing against every property.
- Matching scores location, size, rooms, floor, and text signals; hard structured conflicts are rejected instead of forced into possible matches.
- `listings.property_id` stores the current canonical property link.
- `property_listing_links` preserves match provenance/history for automatic, manual, and new-property decisions.
- `property_match_candidates` stores uncertain/rejected candidate state for review and idempotent reruns.
- Manual matches are preserved by automatic reruns and are not silently reassigned.
- Rejected candidates are not recreated as pending candidates by ordinary reruns.
- Matching reruns are idempotent and do not create uncontrolled duplicate properties, links, or candidates.
- Location normalization: `backend/app/locations/normalization.py` implements `location_rules_v1` for the initial target market microzones. V0 stores normalized location directly on `properties`; no separate `locations` taxonomy/table exists yet.
- Market dataset: `backend/app/features/property_dataset.py` computes `property_features_v1`, `effective_property_data_v1`, and `data_quality_v1` for existing matched properties.
- Property features are persisted in `property_features` as recalculable derived/cache values keyed by property and feature version.
- Data Quality V1 is persisted in `data_quality_assessments` with the Analysis Specification weights, critical missing fields, factor points, and rules version.
- Effective property data prefers current property values over listing values, fills only unknown property attributes from linked listings, and carries existing property latitude/longitude without inventing geocodes.
- Phase 5 recalculation is idempotent for the same property/version and updates existing feature/quality rows when canonical listing/history inputs change.
- Parser fixtures exist under `backend/tests/fixtures/four_zida` and do not depend on live portal state.
- Backend tests cover Phase 0/1 checks plus Phase 2/3 parser, normalization, mocked HTTP, pagination, ingestion idempotency, raw records, job summaries, price changes, lifecycle transitions, source health, scheduled job handling, partial-scan safety, zero-result anomaly safety, Phase 4 duplicate matching, ambiguous candidates, non-matches, manual precedence, rejected candidate behavior, idempotent matching, Phase 5 location normalization, historical feature calculation, market age/relist distinction, effective values, Data Quality V1, missing critical fields, and recalculation.
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

    PHASE 6 - Comparable Engine & V1 Valuation

Exact first logical task:

    Implement the minimal Phase 6 comparable selection and V1 valuation flow using
    listing comparables, including comparable_sets/comparable_items/valuations
    persistence, similarity scoring, adaptive radius, location/size/recency filters,
    outlier handling, FMV low/base/high, valuation confidence, explanation, and
    INSUFFICIENT_DATA.

Do not implement:

- production transaction import;
- liquidity analysis;
- seller/risk intelligence;
- LLM extraction;
- opportunity scoring;
- opportunity alerts;
- additional markets or sources.

## Required Context

Read first:

    AGENTS.md

Then:

    docs/07-phase-plan.md
    -> PHASE 6 - Comparable Engine & V1 Valuation

Relevant specification sections only:

    docs/03-data-model.md
    -> comparable_sets
    -> comparable_items
    -> valuations

    docs/05-analysis-specification.md
    -> Comparable Engine
    -> Comparable Similarity
    -> Outliers
    -> Fair Market Value
    -> Valuation Confidence
    -> Valuation Failure
    -> Explainability

    docs/08-testing-specification.md
    -> comparable/valuation tests relevant to Phase 6

Existing implementation to inspect:

    backend/app/domain/enums.py
    backend/app/db/models.py
    backend/alembic/
    backend/app/features/
    backend/app/locations/
    backend/app/ingestion/
    backend/app/matching/
    backend/tests/

Do not load later-phase specifications unless a concrete Phase 6 dependency requires them.

## Phase 6 Completion Gate

Phase 6 may be marked `COMPLETED` only when its acceptance criteria from `docs/07-phase-plan.md` are satisfied.

At minimum verify that a relevant property can reproducibly produce:

- market-reasonable listing comparables;
- no mixing of listing comps with transaction comps;
- explainable outlier handling;
- FMV low/base/high;
- valuation confidence that reacts to input quality;
- INSUFFICIENT_DATA instead of false FMV;
- enough comparable references to reconstruct WHY.

Before Phase 7, manually review a representative sample of valuations. If valuations are poor, improve location, effective data, comps, data quality, or valuation before building downstream opportunity logic.

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
