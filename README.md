
# Distressed Property Radar

Private real-estate acquisition and investment decision-support system.

Distressed Property Radar continuously collects and preserves property-market data, resolves listings into physical properties, analyzes value and risk, calculates deal economics, and surfaces opportunities that deserve human attention.

Central product principle:

> **Do not rank listings. Rank potential transactions.**

The system is intentionally conservative.

A valid result is:

```text
NO QUALIFYING OPPORTUNITIES
````

It must not manufacture attractive deals when the available data does not support them.

## Current Status

Implementation status is maintained only in:

```text
docs/11-project-status.md
```

At the time this repository documentation was created:

```text
Project status: NOT STARTED
Current phase: PHASE 0 — Repository & Development Foundation
```

Do not rely on this README for the current implementation state after development begins.

Always use `docs/11-project-status.md` as the current checkpoint.

## Initial Product Scope

Initial implementation focuses on:

```text
Country: Serbia
Market: Belgrade

Initial areas:
- Novi Beograd
- Zemun

Property type:
- APARTMENT

Initial target size:
- approximately 35–90 m²
```

Later markets, property types and advanced capabilities are introduced only when explicitly reached by the implementation plan.

## Core System Flow

Conceptually:

```text
External Sources
      ↓
Listings
      ↓
Canonical Properties
      ↓
Historical Market Data
      ↓
Comparable Analysis
      ↓
Valuation
      ↓
Liquidity / Fast-Sale Analysis
      ↓
Seller & Risk Intelligence
      ↓
Deal Economics
      ↓
Opportunity Assessment
      ↓
Action / Alert
      ↓
Human Feedback
      ↓
Historical Outcomes
```

The implementation is introduced incrementally according to `docs/07-phase-plan.md`.

## Technology Direction

The planned initial architecture is a modular monolith.

### Backend

```text
Python
FastAPI
SQLAlchemy
Alembic
```

### Database

```text
PostgreSQL
PostGIS
```

### Frontend

```text
React
```

### Data Collection

```text
httpx
HTML / JSON parsing
Playwright only where required
```

### Notifications

```text
Telegram Bot API
```

### Runtime

```text
Docker
Docker Compose
single VPS initially
```

Exact technical behavior and implementation boundaries are defined by the canonical specifications.

Do not infer additional infrastructure requirements from this README.

## Repository Structure

Target high-level structure:

```text
/
├── AGENTS.md
├── README.md
│
├── docs/
│   ├── 01-product-specification.md
│   ├── 02-system-architecture.md
│   ├── 03-data-model.md
│   ├── 04-scraping-specification.md
│   ├── 05-analysis-specification.md
│   ├── 06-api-ui-specification.md
│   ├── 07-phase-plan.md
│   ├── 08-testing-specification.md
│   ├── 09-deployment-operations.md
│   ├── 10-codex-execution-guide.md
│   └── 11-project-status.md
│
├── backend/
├── frontend/
├── docker-compose.yml
├── .env.example
└── .gitignore
```

Directories and runtime files should be created only when the relevant implementation phase requires them.

Do not create placeholder implementation for future phases.

## Documentation Map

Each document has one primary responsibility.

### `AGENTS.md`

Repository-wide Codex working rules.

Defines:

> **How implementation work must be performed.**

Read before making changes.

### `docs/01-product-specification.md`

Product requirements and domain meaning.

Defines:

> **What the product must do.**

### `docs/02-system-architecture.md`

Technical organization and module boundaries.

Defines:

> **How the system is structurally organized.**

### `docs/03-data-model.md`

Entities, relationships, history and persistence invariants.

Defines:

> **How system data is represented and preserved.**

### `docs/04-scraping-specification.md`

External-source collection and change tracking.

Defines:

> **How market data is collected and refreshed.**

### `docs/05-analysis-specification.md`

Comparable selection, valuation, liquidity, seller/risk analysis, deal economics and opportunity assessment.

Defines:

> **How collected data becomes an investment analysis.**

### `docs/06-api-ui-specification.md`

Backend API contracts and user-facing workflow.

Defines:

> **How the user interacts with the system.**

### `docs/07-phase-plan.md`

Implementation roadmap.

Defines:

> **When functionality is implemented.**

### `docs/08-testing-specification.md`

Canonical testing requirements.

Defines:

> **How implementation correctness is verified.**

### `docs/09-deployment-operations.md`

Development runtime, production deployment, backups, monitoring and operational procedures.

Defines:

> **How the system is operated.**

### `docs/10-codex-execution-guide.md`

Extended human/Codex workflow reference and prompt examples.

It is not required reading for every normal implementation task unless explicitly referenced.

### `docs/11-project-status.md`

Small mutable project checkpoint.

Defines:

> **Where implementation currently is and what happens next.**

Read at the beginning of every new implementation session.

## Source-of-Truth Rule

Do not use this README to resolve detailed implementation questions.

Use the document that owns the relevant domain.

Examples:

```text
database entity semantics
→ docs/03-data-model.md

scraping behavior
→ docs/04-scraping-specification.md

valuation / deal logic
→ docs/05-analysis-specification.md

API / frontend behavior
→ docs/06-api-ui-specification.md

implementation order
→ docs/07-phase-plan.md

testing expectations
→ docs/08-testing-specification.md

deployment behavior
→ docs/09-deployment-operations.md
```

Repository-wide implementation behavior is defined by `AGENTS.md`.

## Development Workflow

Normal Codex continuation should require only a short user prompt.

Codex should then:

```text
1. read AGENTS.md
2. read docs/11-project-status.md
3. identify the current phase/task
4. read the relevant part of docs/07-phase-plan.md
5. read only the specification sections required for that task
6. inspect the existing implementation and tests
7. implement only the current scope
8. run relevant verification
9. inspect the diff
10. update project-status with the verified result
```

Do not paste the entire project specification into every Codex prompt.

The repository contains the persistent project context.

## Local Development

Canonical setup, startup, migration and test commands should be documented here only after they actually exist in the repository.

Until Phase 0 defines them, do not invent commands.

Expected categories will eventually include:

```text
environment setup
application startup
database migrations
tests
lint / formatting / type checks
Docker development
```

The actual repository configuration is authoritative.

## Production

Production architecture and operational procedures are defined in:

```text
docs/09-deployment-operations.md
```

Do not use this README as a deployment runbook.

## V1 Direction

The first useful system is reached by building the data and analysis pipeline before advanced product expansion.

Priorities are approximately:

```text
repository foundation
↓
database
↓
first source
↓
listing history
↓
property resolution
↓
location / features
↓
comparables
↓
valuation
↓
liquidity / fast-sale
↓
seller / risk intelligence
↓
deal economics
↓
opportunity engine
↓
alerts
```

The exact sequence and acceptance criteria are defined only in `docs/07-phase-plan.md`.

## V1 Non-Goals

Unless explicitly introduced by the current phase, do not assume V1 requires:

```text
microservices
Kubernetes
Kafka
Redis / Celery infrastructure
browser clusters
machine-learning valuation
computer-vision pipelines
multi-country support
land analytics
enterprise multi-user SaaS features
complex real-time infrastructure
```

Future functionality belongs to later phases, not to the initial implementation by default.

## Core Product Constraint

This system is:

> **decision support**

not:

> **an autonomous property-purchasing system**

Its purpose is to help identify, analyze and prioritize potential transactions.

Final legal, technical, financial and investment decisions remain human decisions.
