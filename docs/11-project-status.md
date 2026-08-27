# Distressed Property Radar - Project Status

> Kratak mutable checkpoint za nastavak rada izmedju Codex sesija.
>
> Ovaj fajl opisuje samo trenutno stanje projekta.
> Specifikacije, arhitektura, phase detalji i changelog ne pripadaju ovde.

## Current State

    Project status: IN_PROGRESS
    Current phase: PHASE 2 - First Source: Basic Ingestion
    Current task: Phase 2 - implement first-source basic ingestion
    Task state: READY

Phase 1 is complete.

## Completed Phases

    PHASE 0 - Repository & Development Foundation: COMPLETED
    PHASE 1 - Core Database & Domain Foundation: COMPLETED

## Completed Tasks

- Phase 1 minimal persistence/domain model is implemented and verified.

## Current Implementation Facts

- Backend: FastAPI application exists under `backend/app`.
- Backend configuration: centralized settings in `backend/app/core/config.py`, loaded from environment variables and optional root `.env`.
- Backend logging: basic startup logging exists and does not log secrets.
- Database: SQLAlchemy engine/session foundation exists in `backend/app/db`.
- Domain enums: Phase 1 enums exist in `backend/app/domain/enums.py`.
- ORM models: `Source`, `SourceRuntimeState`, `Property`, `Listing`, `ListingEvent`, and `JobRun` exist in `backend/app/db/models.py`.
- Migrations: Alembic is configured; current head is `0002_core_domain_foundation`.
- Bootstrap source: migration seeds a stable `manual` source and `source_runtime_state` row.
- Critical Phase 1 invariant: `listings` enforces `UNIQUE(source_id, external_listing_id)`.
- Money and area fields use PostgreSQL `NUMERIC`; timestamps use `TIMESTAMPTZ`.
- UNKNOWN semantics are represented with nullable fields where `UNKNOWN` differs from `false`, `0`, or an empty string.
- Listing lifecycle supports `ACTIVE`, `NOT_SEEN`, `REMOVED`, and `UNKNOWN`.
- PostgreSQL/PostGIS: Docker Compose service `postgres` uses `postgis/postgis:16-3.5`.
- Development DB host port: `55432` by default to avoid collisions with local PostgreSQL on `5432`.
- Database storage: Compose uses persistent volume `postgres_data`.
- Test database: Compose initializes `distressed_property_radar_test` for backend integration tests.
- Backend tests: pytest suite covers Phase 0 checks plus Phase 1 tables, bootstrap source, create/read records, listing uniqueness, source-scoped external IDs, nullable UNKNOWN semantics, numeric precision, lifecycle statuses, and timezone-aware timestamps.
- Backend lint: Ruff is configured in `backend/pyproject.toml`.
- Health endpoint: `GET /health` checks application process, PostgreSQL connectivity, and PostGIS availability.
- Frontend: minimal Vite React shell exists under `frontend`.
- Frontend routing: simple routes exist for `/` and `/system`.
- Frontend API config: `VITE_API_BASE_URL` is used by `frontend/src/api.ts`.
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
    Historical market dataset accumulating: NO
    Historical data must be preserved: NO - no production data exists yet

## Next Task

Implement only:

    PHASE 2 - First Source: Basic Ingestion

Exact first logical task:

    Implement the minimal first-source adapter contract and one-time discovery flow for one
    APARTMENT sale source in the current target market, using HTTP first if sufficient.

Do not implement:

- continuous monitoring;
- removal detection;
- duplicate property matching;
- valuation;
- LLM;
- opportunity alerts.

## Required Context

Read first:

    AGENTS.md

Then:

    docs/07-phase-plan.md
    -> PHASE 2 - First Source: Basic Ingestion

Relevant specification sections only:

    docs/04-scraping-specification.md
    -> Source Adapter
    -> Raw DTO
    -> Listing Identity
    -> HTTP pre Browsera
    -> Pagination
    -> Filters
    -> Retry / Error Classification

    docs/03-data-model.md
    -> listings
    -> listing_raw_records, only if introduced by Phase 2
    -> listing_events
    -> sources / source_runtime_state
    -> job_runs

    docs/08-testing-specification.md
    -> parser fixture tests
    -> mocked HTTP source integration
    -> ingestion idempotency tests
    -> Phase 2 required test groups

Existing implementation to inspect:

    backend/app/domain/enums.py
    backend/app/db/models.py
    backend/app/db/
    backend/alembic/
    backend/tests/
    docker-compose.yml
    .env.example

Do not load later-phase specifications unless a concrete Phase 2 dependency requires them.

## Phase 2 Completion Gate

Phase 2 may be marked `COMPLETED` only when its acceptance criteria from `docs/07-phase-plan.md` are satisfied.

At minimum verify:

- manual discovery fetches listing pages from one real source;
- cards parse valid listing identities and useful raw fields;
- needed details are fetched;
- basic data is normalized;
- listings are persisted;
- repeated run does not duplicate listings;
- expected discovery history is created;
- job summary is recorded;
- parser tests do not depend on live portal state.

If any required criterion remains unresolved:

    Current task: INCOMPLETE

and record the concrete blocker or remaining work instead of advancing to Phase 3.

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
