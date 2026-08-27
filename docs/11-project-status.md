# Distressed Property Radar - Project Status

> Kratak mutable checkpoint za nastavak rada izmedju Codex sesija.
>
> Ovaj fajl opisuje samo trenutno stanje projekta.
> Specifikacije, arhitektura, phase detalji i changelog ne pripadaju ovde.

## Current State

    Project status: IN_PROGRESS
    Current phase: PHASE 1 - Core Database & Domain Foundation
    Current task: Phase 1 - implement minimal persistence/domain model
    Task state: READY

Phase 0 is complete.

## Completed Phases

    PHASE 0 - Repository & Development Foundation: COMPLETED

## Completed Tasks

- Phase 0 repository foundation is implemented and verified.

## Current Implementation Facts

- Backend: FastAPI application exists under `backend/app`.
- Backend configuration: centralized settings in `backend/app/core/config.py`, loaded from environment variables and optional root `.env`.
- Backend logging: basic startup logging exists and does not log secrets.
- Database: SQLAlchemy engine/session foundation exists in `backend/app/db`.
- Health endpoint: `GET /health` checks application process, PostgreSQL connectivity, and PostGIS availability.
- Migrations: Alembic is configured; current head is `0001_enable_postgis`.
- PostgreSQL/PostGIS: Docker Compose service `postgres` uses `postgis/postgis:16-3.5`.
- Development DB host port: `55432` by default to avoid collisions with local PostgreSQL on `5432`.
- Database storage: Compose uses persistent volume `postgres_data`.
- Test database: Compose initializes `distressed_property_radar_test` for backend integration tests.
- Backend tests: pytest suite covers import/start, health endpoint, DB connection, PostGIS, and Alembic head state.
- Backend lint: Ruff is configured in `backend/pyproject.toml`.
- Frontend: minimal Vite React shell exists under `frontend`.
- Frontend routing: simple routes exist for `/` and `/system`.
- Frontend API config: `VITE_API_BASE_URL` is used by `frontend/src/api.ts`.
- Frontend checks: `npm.cmd run typecheck` and `npm.cmd run build` are configured.
- `.env.example` documents required Phase 0 variable names with local-only example values and no real secrets.
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

    PHASE 1 - Core Database & Domain Foundation

Exact first logical task:

    Add the minimal SQLAlchemy models, domain enums, Alembic migration, and tests for:
    sources, source_runtime_state, properties, listings, listing_events, and job_runs.

Do not implement:

- live scraping;
- property matching;
- comparables;
- valuation;
- frontend property workflow;
- analytical tables from later phases.

## Required Context

Read first:

    AGENTS.md

Then:

    docs/07-phase-plan.md
    -> PHASE 1 - Core Database & Domain Foundation

Relevant specification sections only:

    docs/03-data-model.md
    -> PostgreSQL rules
    -> enum-i potrebni ovoj fazi
    -> sources
    -> source_runtime_state
    -> properties
    -> listings
    -> listing_events
    -> job_runs
    -> database invarijante

    docs/08-testing-specification.md
    -> database/migration tests
    -> Phase 1 required test groups

Existing implementation to inspect:

    backend/app/core/config.py
    backend/app/db/
    backend/alembic/
    backend/tests/
    docker-compose.yml
    .env.example

Do not load later-phase specifications unless a concrete Phase 1 dependency requires them.

## Phase 1 Completion Gate

Phase 1 may be marked `COMPLETED` only when its acceptance criteria from `docs/07-phase-plan.md` are satisfied.

At minimum verify through tests or service layer:

- source can be created;
- listing can be created;
- property can be created;
- listing event can be created;
- data can be read back;
- duplicate `(source_id, external_listing_id)` is prevented;
- migrations run on an empty development database.

If any required criterion remains unresolved:

    Current task: INCOMPLETE

and record the concrete blocker or remaining work instead of advancing to Phase 2.

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
