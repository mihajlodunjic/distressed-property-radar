# Distressed Property Radar - Project Status

> Kratak mutable checkpoint za nastavak rada izmedju Codex sesija.
>
> Ovaj fajl opisuje samo trenutno stanje projekta.
> Specifikacije, arhitektura, phase detalji i changelog ne pripadaju ovde.

## Current State

    Project status: IN_PROGRESS
    Current phase: PHASE 12 - Watchlist, Reanalysis & Change Intelligence
    Current task: Phase 12 - implement watchlist, watch rules, change intelligence, selective reanalysis, and action upgrades
    Task state: READY

Phase 11 is complete.

## Completed Phases

    PHASE 0 - Repository & Development Foundation: COMPLETED
    PHASE 1 - Core Database & Domain Foundation: COMPLETED
    PHASE 2 - First Source: Basic Ingestion: COMPLETED
    PHASE 3 - Continuous Crawling & Listing History: COMPLETED
    PHASE 4 - Property Resolution & Duplicate Matching: COMPLETED
    PHASE 5 - Location, Features & Market Dataset: COMPLETED
    PHASE 6 - Comparable Engine & V1 Valuation: COMPLETED
    PHASE 7 - Liquidity & Fast-Sale Analysis: COMPLETED
    PHASE 8 - LLM Seller Intelligence & Risk: COMPLETED
    PHASE 9 - Deal Engine & Investment Profiles: COMPLETED
    PHASE 10 - Opportunity Engine & Telegram Alerts: COMPLETED
    PHASE 11 - First Usable Dashboard: COMPLETED

## Completed Tasks

- Phase 11 private V0 dashboard/API is implemented and verified: Action Queue, Properties List, Property Detail, Source Health, Basic Settings, loading/empty/error/auth/UNKNOWN/STALE/BLOCK states, and frontend/backend tests/checks.

## Current Implementation Facts

- Backend: FastAPI application exists under `backend/app`.
- Backend configuration: centralized settings in `backend/app/core/config.py`, loaded from environment variables and optional root `.env`.
- Backend logging: basic startup logging exists and does not log secrets.
- Database: SQLAlchemy engine/session foundation exists in `backend/app/db`.
- Domain enums: Phase 1 enums plus `ListingRawRecordType`, `SourceHealthStatus`, `MatchDecision`, `MatchCandidateStatus`, `ComparableType`, `ValuationStatus`, `ValuationModelType`, `LiquidityStatus`, `FastSaleStatus`, `AnalysisLevel`, `ReasonForSale`, `LlmAnalysisStatus`, `RiskGateStatus`, `RiskSeverity`, `RiskGateEffect`, `DealAnalysisStatus`, `DealScenarioType`, `OpportunityAction`, `AlertChannel`, `AlertType`, and `AlertStatus` exist in `backend/app/domain/enums.py`.
- ORM models: `Source`, `SourceRuntimeState`, `Property`, `Listing`, `ListingEvent`, `ListingRawRecord`, `PropertyListingLink`, `PropertyMatchCandidate`, `PropertyFeature`, `DataQualityAssessment`, `ComparableSet`, `ComparableItem`, `Valuation`, `LiquidityAssessment`, `FastSaleEstimate`, `LlmAnalysis`, `SellerAssessment`, `RiskAssessment`, `RiskFlag`, `CostProfile`, `InvestmentProfile`, `DealAnalysis`, `DealScenario`, `OpportunityAssessment`, `Alert`, and `JobRun` exist in `backend/app/db/models.py`.
- Migrations: Alembic is configured; current head is `0011_opportunity_alerts`.
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
- Valuation module: `backend/app/valuation/comparable_engine.py` implements `comparable_engine_v1` and `valuation_v1`.
- Phase 6 V1 uses `LISTING` comparables only as asking-market evidence and does not model transaction comps as realized transaction prices.
- Comparable sets and items are persisted with `as_of`, engine version, search parameters, listing/property references, snapshot price data, similarity, distance, recency age, weight, inclusion flag, and exclusion reason.
- Valuations are immutable historical results linked to a comparable set; repeated same-input valuation runs create new valuation rows with reproducible values.
- Valuation status can be `SUCCESS` or `INSUFFICIENT_DATA`; insufficient-data results do not invent FMV values.
- V1 valuation uses deterministic weighted similarity, adaptive radius, size filtering, listing recency, IQR price-outlier exclusion, weighted-median asking EUR/m2, capped target adjustments, FMV low/base/high, confidence factors, and explanation JSON.
- Liquidity module: `backend/app/liquidity/liquidity_engine.py` implements `liquidity_rules_v1` and `fast_sale_v1`.
- Liquidity assessments are immutable historical results linked to properties and, when available, the successful valuation input.
- Liquidity V1 uses deterministic property/market factors, separates positive factors, negative factors, and unknown important factors, and leaves sale-probability fields null because no outcome model exists.
- Fast-sale estimates are persisted separately from FMV, link to the valuation and liquidity assessment inputs, carry target-day context, and keep `target_probability` null.
- Fast-Sale V1 derives low/base/high from Phase 6 FMV, liquidity level, valuation confidence, valuation dispersion, and target horizon; it does not use LLM financial math or probabilistic sale timing.
- Insufficient Phase 6 valuation input creates explicit `INSUFFICIENT_DATA` liquidity/fast-sale rows without fabricated liquidity scores or fast-sale values.
- LLM analysis module: `backend/app/intelligence/llm_analysis.py` implements a small HTTP JSON provider adapter, `seller_risk_prompt_v1`, schema validation, semantic input hashing, successful-result caching, evidence capture, invalid-output rows, and non-fatal provider failure rows.
- Seller/risk module: `backend/app/intelligence/seller_risk.py` implements `seller_intelligence_v1` and `risk_rules_v1`.
- `llm_analyses` persists structured LLM outputs by listing, input hash, prompt version, provider, and model; LLM values remain claims and do not overwrite property facts.
- `seller_assessments` persists effective seller motivation, negotiability, cash preference, reason for sale, confidence, source evidence, model version, and manual-precedence explanations.
- `risk_assessments` and `risk_flags` persist PASS/VERIFY/BLOCK gate results, hard/soft flags, provenance, confidence, evidence, and rules version.
- Phase 8 risk logic keeps seller motivation separate from the Risk Gate; verified/manual risk input can suppress weaker scraped/derived/LLM claims without deleting historical source rows.
- Deal module: `backend/app/deals/deal_engine.py` implements `deal_formula_v1` and `deal_scenario_rules_v1`.
- Cost assumptions are persisted in `cost_profiles` JSON rule fields; the engine supports fixed amounts, purchase-price percentages, exit-price percentages, and per-day holding costs without LLM math.
- Investment criteria are persisted in `investment_profiles`, including minimum profit, downside profit, ROI, holding days, liquidity/confidence thresholds, risk reserve, desired profit, and version.
- `deal_analyses` are immutable historical results linked to property, valuation, liquidity, fast-sale, risk, cost profile, and investment profile inputs.
- `deal_scenarios` persists one DOWNSIDE, BASE, and UPSIDE child row per successful deal analysis, with assumptions JSON preserving cost breakdown and scenario-specific renovation/holding assumptions.
- Phase 9 deal math uses Decimal-only Total Cost Basis, Net Sale Proceeds, Net Profit, ROI, linear Annualized ROI, Capital Days, Profit / Capital-Day, Max Buy, and Required Negotiation.
- Unknown required financial inputs such as renovation cost create explicit `INSUFFICIENT_DATA` deal rows instead of fabricated zero-cost calculations.
- Opportunity module: `backend/app/opportunities/opportunity_engine.py` implements `opportunity_rules_v1`.
- `opportunity_assessments` persists historical recommended action, score, ranking, reason codes, explanations, rules version, and semantic `state_hash`.
- Phase 10 actions are rules-based: `IGNORE`, `WATCH`, `REVIEW`, `CALL`, and `URGENT_CALL`.
- Hard gates, minimum data, confidence thresholds, and economic thresholds run before ranking/action alert eligibility; hard `BLOCK`, low-confidence, and negative/failed-economics states cannot produce `CALL` or `URGENT_CALL`.
- Opportunity ranking is simple and explainable, prioritizing expected profit, downside profit, ROI, profit per capital-day, and required negotiation.
- `alerts` persists Telegram opportunity/operational alert records with `PENDING`, `SENT`, `FAILED`, and `SUPPRESSED` states, unique `dedupe_key`, payload, provider metadata, attempt count, and failure reason.
- Alert dedupe uses property, recommended action, and semantic opportunity `state_hash`; unchanged opportunity states do not create duplicate logical alerts.
- Telegram delivery is implemented behind `backend/app/opportunities/telegram.py`; automated tests use fake providers, not the real Telegram API.
- Only `CALL` and `URGENT_CALL` opportunity actions are Telegram alert-eligible in Phase 10.
- Dashboard API: `backend/app/api/dashboard.py` exposes read-only `GET /api/v1/action-queue`, `GET /api/v1/properties`, `GET /api/v1/properties/{id}`, `GET /api/v1/properties/{id}/history`, `GET /api/v1/sources`, and `GET /api/v1/settings`.
- API access: `backend/app/api/dependencies.py` provides DB-session dependency and a single-user bearer-token guard. If `API_ACCESS_TOKEN` is configured it is required; production fails closed when the token is missing. Local development/test can run without a token.
- API routing/CORS: `backend/app/main.py` registers `/api/v1/health`, the dashboard router, and non-wildcard CORS origins from `CORS_ALLOWED_ORIGINS`.
- Action Queue API uses backend opportunity/deal/valuation/liquidity/risk read models, excludes `IGNORE` by default, returns summary counts, source warnings, pagination, whitelist sorting/filtering, and preserves `null` as UNKNOWN.
- Property Detail API returns decision header, listings, listing history, comparables, valuation, liquidity/fast-sale, seller, risk flags, deal economics/scenarios/costs, and freshness/statuses. Stale display state is derived from listing inputs newer than current analysis `as_of`; historical rows are not overwritten.
- Source Health API returns one row per source with runtime state, latest job summary, recent errors, parse health, enabled state, and dashboard warnings.
- Settings API is read-only and reports investment/cost profile summaries, notification/configuration booleans, CORS origins, and source counts without exposing secret values.
- Frontend dashboard: `frontend/src/App.tsx` implements Action Queue, Properties, Property Detail, Source Health, and Settings routes against the implemented `/api/v1` contracts.
- Frontend API client stores the optional private API token in session storage and never hardcodes a token in source.
- Frontend status/format helpers preserve UNKNOWN instead of converting it to zero/false/empty display values and render STALE/FAILED/BLOCK as explicit text statuses.
- Parser fixtures exist under `backend/tests/fixtures/four_zida` and do not depend on live portal state.
- Backend tests cover Phase 0/1 checks plus Phase 2/3 parser, normalization, mocked HTTP, pagination, ingestion idempotency, raw records, job summaries, price changes, lifecycle transitions, source health, scheduled job handling, partial-scan safety, zero-result anomaly safety, Phase 4 duplicate matching, ambiguous candidates, non-matches, manual precedence, rejected candidate behavior, idempotent matching, Phase 5 location normalization, historical feature calculation, market age/relist distinction, effective values, Data Quality V1, missing critical fields, recalculation, Phase 6 comparable filtering/ranking, listing/transaction distinction, outliers, valuation, confidence behavior, insufficient data, historical `as_of` protection, Phase 7 liquidity rules, UNKNOWN behavior, Fast-Sale Value ordering, target-day behavior, versioned persistence, Phase 8 LLM schema validation, UNKNOWN preservation, cache behavior, provider outage behavior, deterministic seller signals, manual seller/risk precedence, Risk Gate behavior, soft risks, evidence persistence, Phase 9 fixed/percentage costs, sale costs, total cost basis, net proceeds, profit, ROI, annualized ROI, risk reserve, Max Buy, required negotiation, scenario calculations, invalid inputs, Decimal precision, and versioned persistence.
- Backend tests also cover Phase 10 action classification, hard gates, confidence/downside thresholds, reason codes, ranking, full opportunity-to-notification flow, alert lifecycle, retry, dedupe, action upgrade, and operational/opportunity alert separation.
- Backend tests also cover Phase 11 private API auth, Action Queue contract, empty queue, no obvious Action Queue N+1 query pattern, Property Detail UNKNOWN/STALE/BLOCK/history/analysis sections, Source Health, Settings secrecy, and `/api/v1/health`.
- Frontend tests cover UNKNOWN rendering and critical status formatting for STALE/FAILED/BLOCK. Frontend build/typecheck is configured through `npm run build`; no separate frontend lint script exists.
- Health endpoints: `GET /health` and `GET /api/v1/health` check application process, PostgreSQL connectivity, and PostGIS availability.
- Frontend: Vite React dashboard exists under `frontend`.
- `.env.example` documents required variable names with local-only example values and no real secrets, including empty `API_ACCESS_TOKEN`, `LLM_API_KEY`, Telegram token/chat values, and configured CORS origin names.
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

    PHASE 12 - Watchlist, Reanalysis & Change Intelligence

Exact first logical task:

    Implement watchlist persistence and API/UI actions for WATCH properties,
    including watch rules and What Changed output, so triggered listing changes
    run selective reanalysis before opportunity/action-alert decisions.

Do not implement:

- Phase 13 acquisition CRM/human feedback;
- generic CRM or kanban workflow;
- portfolio/transaction import;
- multi-channel notification infrastructure beyond existing Telegram alerts;
- additional markets or sources.

## Required Context

Read first:

    AGENTS.md

Then:

    docs/07-phase-plan.md
    -> PHASE 12 - Watchlist, Reanalysis & Change Intelligence

Relevant specification sections only:

    docs/03-data-model.md
    -> watch_rules
    -> analytical current/stale state

    docs/05-analysis-specification.md
    -> Re-analysis
    -> invalidation rules
    -> Watch Threshold Crossing

    docs/06-api-ui-specification.md
    -> Watch
    -> Watchlist
    -> What Changed
    -> Reanalysis API

    docs/08-testing-specification.md
    -> Phase 12 watch trigger/reanalysis tests

Existing implementation to inspect:

    backend/app/api/
    backend/app/db/models.py
    backend/app/opportunities/
    backend/app/deals/
    backend/app/valuation/
    backend/app/liquidity/
    backend/app/intelligence/
    backend/app/ingestion/
    backend/app/crawling/
    frontend/
    backend/tests/

Do not load Phase 13+ specifications unless a concrete Phase 12 dependency requires them.

## Phase 12 Completion Gate

Phase 12 may be marked `COMPLETED` only when its acceptance criteria from `docs/07-phase-plan.md` are satisfied.

At minimum verify:

- a WATCH property can have a watch rule;
- a relevant listing change triggers current selective reanalysis;
- What Changed output explains the trigger;
- a WATCH property can upgrade to CALL after reanalysis;
- Telegram alert decision uses fresh analysis and does not use stale deal results.

Do not implement Phase 13 acquisition CRM/human feedback behavior.

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
