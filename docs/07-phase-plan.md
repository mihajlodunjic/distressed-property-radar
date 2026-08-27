# Distressed Property Radar — Implementation Phase Plan

## 1. Svrha dokumenta

Ovaj dokument definiše **redosled implementacije sistema**.

Njegova uloga je da za svaki trenutni razvojni korak odredi:

- cilj;
- prerequisite;
- Required Context;
- scope;
- rezultat;
- acceptance criteria;
- šta se još ne implementira.

Phase Plan određuje:

> **KADA se capability implementira.**

Ostali canonical dokumenti određuju:

> **ŠTA capability znači i KAKO mora da se ponaša.**

Ne ponavljati njihove detaljne specifikacije ovde.

## 2. Canonical dokumenti

Koristiti:

    AGENTS.md
    docs/01-product-specification.md
    docs/02-system-architecture.md
    docs/03-data-model.md
    docs/04-scraping-specification.md
    docs/05-analysis-specification.md
    docs/06-api-ui-specification.md
    docs/08-testing-specification.md
    docs/09-deployment-operations.md
    docs/11-project-status.md

`docs/11-project-status.md` određuje **trenutnu fazu i sledeći task**.

Ovaj dokument ne treba koristiti kao status tracker.

# 3. Pravilo faza

Faze se po default-u implementiraju redom.

Sledeća faza ne počinje dok trenutna nema:

    required implementation complete
    +
    relevant tests passing
    +
    migrations valid
    +
    application starts
    +
    acceptance criteria satisfied

Mala priprema za buduću fazu dozvoljena je samo kada sprečava očigledan veliki rewrite.

Ne implementirati buduću funkcionalnost samo zato što je već opisana u specifikacijama.

# 4. Scope jednog Codex task-a

Jedna faza može imati više Codex task-ova.

Jedan task treba da bude dovoljno mali da se može:

- implementirati;
- testirati;
- pregledati;
- završiti bez nepovezanih promena.

Svaki task mora imati:

    CURRENT PHASE
    CURRENT TASK
    REQUIRED CONTEXT
    ACCEPTANCE CRITERIA

Detaljna Codex pravila su u `AGENTS.md`.

Ne kopirati velike specifikacije u prompt kada ih Codex može pročitati iz repository-ja.

# 5. Redosled faza

    PHASE 0   Repository & Development Foundation
    PHASE 1   Core Database & Domain Foundation
    PHASE 2   First Source — Basic Ingestion
    PHASE 3   Continuous Crawling & Listing History
    PHASE 4   Property Resolution & Duplicate Matching
    PHASE 5   Location, Features & Market Dataset
    PHASE 6   Comparable Engine & V1 Valuation
    PHASE 7   Liquidity & Fast-Sale Analysis
    PHASE 8   LLM Seller Intelligence & Risk
    PHASE 9   Deal Engine & Investment Profiles
    PHASE 10  Opportunity Engine & Telegram Alerts
    PHASE 11  First Usable Dashboard
    PHASE 12  Watchlist, Reanalysis & Change Intelligence
    PHASE 13  Acquisition CRM & Human Feedback
    PHASE 14  Reliability, Monitoring & Production Hardening
    PHASE 15  Second Source & Cross-Portal Validation
    PHASE 16  Historical Evaluation & Shadow Portfolio
    PHASE 17  Transaction Data Enrichment
    PHASE 18  Model Calibration & Advanced Analytics
    PHASE 19  Land Support
    PHASE 20+ Additional Markets / Advanced Domains

# 6. PHASE 0 — Repository & Development Foundation

## Cilj

Napraviti minimalnu tehničku osnovu na kojoj naredne faze mogu pouzdano da se grade.

## Required Context

Pre implementacije čitati samo relevantne delove:

    AGENTS.md

    docs/02-system-architecture.md
    - Technology Direction
    - backend/frontend boundaries
    - configuration
    - environments

    docs/08-testing-specification.md
    - test foundation

    docs/09-deployment-operations.md
    - development environment requirements

## Scope

Minimalna repository struktura:

    /
      AGENTS.md
      README.md
      docs/
      backend/
      frontend/
      docker-compose.yml
      .env.example
      .gitignore

Ako validna struktura već postoji, ne reorganizovati je bez potrebe.

### Backend

Postaviti:

- Python project;
- FastAPI application;
- settings/configuration;
- logging;
- PostgreSQL connection;
- SQLAlchemy;
- Alembic;
- health endpoint;
- test setup.

### Database

Development environment:

    PostgreSQL
    PostGIS
    persistent dev volume

Ne kreirati kompletan finalni data model.

### Frontend

Napraviti minimalni React skeleton:

- application starts;
- routing radi;
- API base config postoji;
- osnovni shell postoji.

Ne praviti dashboard unapred.

### Development workflow

Mora postojati jasan način za:

- pokretanje stack-a;
- migrations;
- backend testove;
- frontend pokretanje/build;
- health proveru.

## Acceptance Criteria

Phase 0 je završena kada:

- backend se pokreće;
- frontend se pokreće;
- PostgreSQL connection radi;
- PostGIS je dostupan;
- Alembic migration workflow radi;
- health endpoint radi;
- test suite može da se pokrene;
- `.env.example` dokumentuje required variables bez secrets;
- repository nema commitovane secrets.

## Van scope-a

Još ne implementirati:

- scraping;
- listings business flow;
- valuation;
- LLM;
- Telegram;
- CRM;
- production dashboard.

# 7. PHASE 1 — Core Database & Domain Foundation

## Cilj

Napraviti minimalni persistence/domain model potreban da sistem počne da akumulira tržišne podatke.

## Required Context

    docs/03-data-model.md
    - PostgreSQL pravila
    - enum-i potrebni ovoj fazi
    - sources
    - source_runtime_state
    - properties
    - listings
    - listing_events
    - job_runs
    - database invarijante

    docs/08-testing-specification.md
    - database/migration tests

## Scope

Implementirati samo trenutno potrebne entitete:

    sources
    source_runtime_state
    properties
    listings
    listing_events
    job_runs

Matching tabele mogu sačekati Phase 4.

Ne kreirati sve buduće analytical tabele.

## Obavezne invarijante

Posebno:

    UNIQUE(source_id, external_listing_id)

Money koristi `NUMERIC` / `Decimal`.

Timestamp-i su timezone-aware.

UNKNOWN semantika koristi nullable vrednosti gde je potrebno.

Listing lifecycle mora podržati najmanje relevantne:

    ACTIVE
    NOT_SEEN
    REMOVED
    UNKNOWN

## Source Bootstrap

Omogućiti reproducibilan način da prvi source postoji u bazi.

Može biti:

- migration seed;
- bootstrap;
- jednostavan admin/setup command.

Izabrati najjednostavnije rešenje koje odgovara postojećoj aplikaciji.

## Acceptance Criteria

Moguće je kroz test/service layer:

- kreirati source;
- kreirati listing;
- kreirati property;
- kreirati listing event;
- pročitati podatke nazad;
- sprečiti duplicate `(source_id, external_listing_id)`;
- izvršiti migrations na praznoj development bazi.

## Van scope-a

Ne implementirati:

- live scraping;
- property matching;
- comparables;
- valuation;
- frontend property workflow.

# 8. PHASE 2 — First Source: Basic Ingestion

## Cilj

Prvi put preuzeti **realne listing-e sa jednog source-a** i pouzdano ih sačuvati.

## Required Context

    docs/04-scraping-specification.md
    - Source Adapter
    - Raw DTO
    - Listing Identity
    - HTTP pre Browsera
    - Pagination
    - Filters
    - Retry / Error Classification

    docs/03-data-model.md
    - listings
    - listing_raw_records, ako se uvode
    - listing_events
    - sources / source_runtime_state
    - job_runs

## Scope

Samo:

    1 source
    APARTMENT
    sale listings
    current target market

Ne širiti market u istoj fazi.

## Deliverables

### Source Adapter

Implementirati minimalni adapter contract potreban prvom source-u.

Ne praviti generic plugin platform.

### Listing-page Fetch

Podržati:

- URL/query construction;
- pagination;
- timeout;
- rate limiting;
- bounded retry;
- error classification.

Koristiti HTTP ako je dovoljan.

### Card Parser

Parsirati koliko source omogućava, minimalno identity:

    external_listing_id
    url

i korisne dostupne:

    title_raw
    price_raw
    location_raw
    size_raw

### Detail Parser

Za novi listing fetchovati detail kada je potreban.

Sačuvati dovoljno relevantnog raw/normalized sadržaja za buduće faze.

### Normalization V0

Implementirati samo ono što trenutni source zahteva, npr:

    price
    currency
    size
    rooms
    floor
    basic location strings

Ne uvoditi advanced geocoding.

### Persistence

Novi listing se upisuje jednom.

Prvi validni discovery proizvodi `DISCOVERED` history event kada je taj event deo trenutnog modela.

Ponovno procesiranje istog listing-a ne pravi duplicate listing/event.

### Fixtures

Sačuvati representative card/detail fixtures za parser testove.

## Acceptance Criteria

Manual discovery nad realnim source-om:

- fetchuje listing pages;
- parsira validne cards;
- fetchuje potrebne details;
- normalizuje osnovne podatke;
- upisuje listing-e;
- ne duplira listing-e pri ponovnom run-u;
- pravi očekivani discovery history;
- evidentira job summary;
- parser testovi ne zavise od live portala.

## Van scope-a

Još ne implementirati:

- continuous monitoring;
- removal detection;
- duplicate property matching;
- valuation;
- LLM;
- opportunity alerts.

# 9. PHASE 3 — Continuous Crawling & Listing History

## Cilj

Pretvoriti one-time ingestion u kontinuirani market monitoring sistem.

Od završetka ove faze istorijski dataset treba da počne stalno da raste.

## Required Context

    docs/04-scraping-specification.md
    - Incremental Crawling
    - Fast Discovery
    - Active Market Scan
    - Deep Reconciliation
    - Listing Lifecycle
    - Change Detection
    - Adaptive Polling
    - Source Health
    - Failure Isolation

    docs/03-data-model.md
    - listing lifecycle
    - listing_events
    - source_runtime_state
    - job_runs

## Scope

Implementirati minimalno potrebne:

    FAST_DISCOVERY
    ACTIVE_MARKET_SCAN
    DEEP_RECONCILIATION

za prvi source.

## Fast Discovery

Periodično proveravati newest feed.

Podržati:

- configurable interval;
- known-listing boundary;
- job state;
- health update.

## Market Scan

Lightweight card-state scan treba najmanje da podrži:

- `last_seen` refresh;
- price change detection;
- potential disappearance.

## Change Detection

Uvesti relevantni state comparison/hash i field-level diff.

Minimum business event:

    PRICE_CHANGED

Dodavati druge change event-e samo kada ih current source/workflow zahteva.

## Lifecycle

Implementirati konzervativni:

    ACTIVE
    → NOT_SEEN
    → REMOVED

i:

    NOT_SEEN / REMOVED
    → ACTIVE

uz reappearance history.

`PARTIAL` ili `FAILED` scan ne sme proizvoditi masovne removals.

## Source Health

Pratiti najmanje:

- last success;
- HTTP failures;
- parse failures;
- zero-result anomalies;
- job summaries.

## Acceptance Criteria

Sistem tokom ponovljenih crawl ciklusa ispravno razlikuje:

    NEW
    UNCHANGED
    PRICE_CHANGED
    NOT_SEEN
    REMOVED
    REAPPEARED

bez duplicate business event-a i bez false removal-a zbog crawler/parser failure-a.

## Stop Gate

Pre nastavka proveriti realan continuous run.

Ako crawler ne može pouzdano da radi duži period bez history corruption-a, ne prelaziti na analytics.

## Dataset-First Rule

Od ove faze stabilan crawler treba da nastavi da prikuplja istoriju dok se grade kasnije faze.

Ne čekati završetak valuation-a da bi dataset počeo da raste.

# 10. PHASE 4 — Property Resolution & Duplicate Matching

## Cilj

Preći sa listing-centric dataset-a na canonical property-centric dataset.

## Required Context

    docs/02-system-architecture.md
    - matching boundary
    - property/listing separation

    docs/03-data-model.md
    - properties
    - property_listing_links
    - property_match_candidates
    - merge/split invarijante
    - images, samo ako su potrebne

## Scope

Uvesti minimalan matching persistence model potreban za:

    listing
    → candidate property
    → match decision
    → canonical property

## Matching V1

Koristiti dostupne determinističke signale:

- normalized location;
- size;
- rooms;
- floor;
- price/context;
- selected text similarity.

Ne koristiti ML.

## Candidate Generation

Prvo napraviti jeftin candidate filter.

Ne raditi globalno:

    every listing × every property

## Decisions

Podržati semantički:

    AUTO_MATCH
    POSSIBLE_MATCH
    REJECTED / NO_MATCH
    MANUAL_MATCH, kada manual workflow postoji

Auto-match threshold mora biti konzervativan.

Bolje:

    POSSIBLE_MATCH

nego pogrešan property merge.

## New Property

Ako nema dovoljno pouzdanog match-a:

    create new Property

Ne forsirati match radi smanjenja broja property-ja.

## Images

Perceptual hash uvoditi samo ako realna matching evaluacija pokaže da structured/text signals nisu dovoljni.

## Acceptance Criteria

Representative dataset može:

- spojiti očigledne duplicate listing-e;
- ostaviti neizvestan slučaj za review;
- kreirati novi property kada nema match;
- očuvati sve originalne listing-e;
- ponovo pokrenuti matching bez nekontrolisanih duplicate odluka.

# 11. PHASE 5 — Location, Features & Market Dataset

## Cilj

Napraviti stabilne analytical inpute za Comparable Engine.

## Required Context

    docs/03-data-model.md
    - properties
    - locations
    - property_features
    - Effective Property Data / provenance

    docs/05-analysis-specification.md
    - Effective Property Data
    - Data Quality

## Scope

### Location

Normalizovati najmanje:

    city
    municipality
    neighborhood
    micro_location
    lat/lng kada pouzdano postoje
    location confidence

Za početni market koristiti mali praktični skup microzone pravila.

Ne modelovati ceo Beograd unapred.

### PostGIS

Kada koordinate postoje, koristiti ga za:

- distance;
- radius filtering.

### Property Features

Implementirati features potrebne neposredno narednim analytics fazama, npr:

    price_per_m2
    listing_age_days
    property_market_age_days
    active_listing_count
    known_listing_count
    price_cut_count
    total_price_drop_pct
    price_drop_30d_pct
    days_since_last_price_cut
    largest_price_cut_pct
    relist_count

### Effective Property Data

Napraviti jedno jasno current analytical representation.

Ne praviti potpuno generički override/provenance engine ako još nije potreban.

### Data Quality V1

Implementirati prvu verziju iz Analysis Specification-a.

## Acceptance Criteria

Za relevantan property moguće je reproducibilno dobiti:

    normalized location
    effective attributes
    historical derived features
    Data Quality
    missing critical fields

Promena canonical/history inputa omogućava ponovni calculation.

# 12. PHASE 6 — Comparable Engine & V1 Valuation

## Cilj

Napraviti prvu upotrebljivu i objašnjivu procenu tržišne vrednosti.

## Required Context

    docs/03-data-model.md
    - comparable_sets
    - comparable_items
    - valuations

    docs/05-analysis-specification.md
    - Comparable Engine
    - Comparable Similarity
    - Outliers
    - Fair Market Value
    - Valuation Confidence
    - Valuation Failure
    - Explainability

## Važna granica

Ako transaction podaci još ne postoje, V1 koristi:

    LISTING COMPS

kao asking-market evidence.

Ne predstavljati ih kao realizovane transaction cene.

## Scope

Implementirati:

    comparable selection
    similarity score
    adaptive radius
    size/location filters
    recency
    outlier handling
    FMV LOW / BASE / HIGH
    Valuation Confidence
    explanation
    INSUFFICIENT_DATA

Svaki historical result mora imati dovoljne:

    as_of
    model_version
    comparable references

za kasniji backtesting.

## Acceptance Criteria

Na representative real properties:

- comps su tržišno razumni;
- transaction/listing tipovi se ne mešaju;
- outliers su objašnjivi;
- FMV je reproducibilan;
- confidence reaguje na kvalitet inputa;
- insufficient data ne proizvodi lažni FMV;
- može se rekonstruisati `WHY`.

## Real-World Validation Gate

Pre Phase 7 ručno pregledati representative sample valuacija.

Ne meriti samo „da li code radi“.

Proveriti:

> Da li comps stvarno imaju smisla?

## Critical Stop Gate

Ako valuacije deluju loše, ne graditi sofisticiran downstream Opportunity Engine.

Prvo popraviti:

    location
    effective data
    comps
    data quality
    valuation

Loš FMV kvari sve naredne finansijske rezultate.

# 13. PHASE 7 — Liquidity & Fast-Sale Analysis

## Cilj

Odvojiti normalnu tržišnu vrednost od konzervativne exit vrednosti.

## Required Context

    docs/03-data-model.md
    - liquidity_assessments
    - fast_sale_estimates

    docs/05-analysis-specification.md
    - Liquidity
    - Fast-Sale Value
    - Valuation Confidence interactions
    - Explainability

## Scope

Implementirati rules-based V1:

    Liquidity Score
    Liquidity Confidence
    positive/negative factors

    Fast-Sale LOW
    Fast-Sale BASE
    Fast-Sale HIGH

Fast-Sale koristi postojeći FMV, liquidity, confidence i relevantnu dispersion/config logiku.

Ne uvoditi probabilistički:

    P(sale <= 30d)

bez odgovarajućeg outcome dataseta.

## Acceptance Criteria

Property sa validnim valuation inputom može dobiti:

- liquidity score;
- liquidity confidence;
- explanation;
- Fast-Sale low/base/high;
- target-day context;

bez LLM finansijske matematike.

# 14. PHASE 8 — LLM Seller Intelligence & Risk

## Cilj

Dodati structured extraction iz nestrukturisanog listing teksta i prvi Risk Engine.

## Required Context

    docs/03-data-model.md
    - llm_analyses
    - risk_assessments
    - risk_flags
    - provenance/manual precedence

    docs/05-analysis-specification.md
    - LLM Analysis
    - Seller Motivation
    - Negotiability
    - Risk Engine
    - Hard/Soft Risks
    - Risk Conflict Resolution

## Scope

### LLM Client

Jedan mali provider adapter.

Ne praviti multi-provider platform.

### Structured Output

Schema mora podržati relevantne:

    seller motivation
    negotiability
    cash preference
    reason for sale
    condition
    legal claims
    risk signals
    evidence

### Caching

Isti semantic input ne analizirati ponovo bez potrebe.

Koristiti input hash/version.

### Failure

LLM failure je non-fatal.

Scraping, history i ostala nezavisna analiza nastavljaju da rade.

### Seller Intelligence

Kombinovati LLM sa determinističkim signalima kao:

- price cuts;
- market age;
- relisting;
- seller changes.

### Risk Engine

Implementirati:

    PASS
    VERIFY
    BLOCK

uz mali, pouzdan V1 set rules.

Ne predstavljati source/LLM legal claim kao verified fact.

## Acceptance Criteria

Representative listing-i pokazuju da:

- structured schema validation radi;
- `UNKNOWN` radi;
- evidence se čuva;
- invalid/hallucinated output ne postaje domain truth;
- seller motivation nije Risk Gate;
- verified/manual precedence radi;
- LLM outage ne ruši ingestion ili ostatak pipeline-a.

# 15. PHASE 9 — Deal Engine & Investment Profiles

## Cilj

Pretvoriti market analysis u determinističku ekonomiku potencijalne kupovine.

## Required Context

    docs/03-data-model.md
    - cost_profiles
    - investment_profiles
    - deal_analyses
    - deal_scenarios

    docs/05-analysis-specification.md
    - Deal Engine
    - Cost Profiles
    - Total Cost Basis
    - Net Profit
    - ROI
    - Capital Days
    - Risk Reserve
    - Max Buy Price
    - Required Negotiation
    - Deal Scenarios

## Scope

Implementirati:

    Cost Profile
    Investment Profile
    Deal Analysis
    DOWNSIDE
    BASE
    UPSIDE

Canonical metrics:

    Total Cost Basis
    Net Profit
    ROI
    Annualized ROI
    Capital Days
    Profit / Capital-Day
    Max Buy
    Required Negotiation

## Financial Correctness

Koristiti:

    Decimal / NUMERIC

Ne floating-point.

Troškovi i thresholds nisu rasuti kao hardcoded konstante.

Max Buy solver mora korektno raditi i kada cost zavisi od purchase price-a.

LLM se ne koristi za calculation.

## Acceptance Criteria

Unit/integration testovi pokrivaju najmanje:

- fixed costs;
- percentage costs;
- zero/negative margin;
- Max Buy equation;
- required negotiation;
- ROI;
- annualized ROI;
- scenario differences;
- Decimal precision.

Representative rezultati mogu se nezavisno ručno proveriti.

# 16. PHASE 10 — Opportunity Engine & Telegram Alerts

## Cilj

Napraviti prvi kompletan automatic acquisition flow:

    NEW / CHANGED PROPERTY
    → ANALYSIS
    → DEAL
    → OPPORTUNITY
    → ACTION
    → TELEGRAM

## Required Context

    docs/01-product-specification.md
    - Action Queue
    - Alert philosophy
    - Telegram

    docs/03-data-model.md
    - opportunity_assessments
    - alerts

    docs/05-analysis-specification.md
    - Opportunity Assessment
    - Hard Conditions
    - Recommended Actions
    - Hard Gate
    - Ranking
    - No-Deal Behavior

    docs/06-api-ui-specification.md
    - decision summary
    - Telegram deep link

## Scope

Implementirati rules-based:

    IGNORE
    WATCH
    REVIEW
    CALL
    URGENT_CALL

`DUE_DILIGENCE` može biti uključen ako trenutni workflow to već zahteva.

## Hard Gate

Risk/business hard conditions se proveravaju pre score/ranking-a.

High seller motivation ne kompenzuje lošu ekonomiku.

## Ranking

V1 mora biti jednostavan i objašnjiv.

Prioritet imaju direktne ekonomske i downside metrike.

## Telegram

Implementirati najmanje:

    alert persistence
    PENDING / SENT / FAILED
    dedupe
    Telegram sender
    concise message
    property deep link

Scraper operational alert i property opportunity alert ostaju različite kategorije.

## Alert Philosophy

Threshold-i su konzervativni.

Cilj nije veliki broj alertova.

Validan rezultat:

    NO QUALIFYING OPPORTUNITIES

## Acceptance Criteria

Testni/new property može bez ručne intervencije proći:

    ingestion
    → property
    → analysis
    → deal
    → opportunity
    → alert

Isti unchanged opportunity state ne šalje isti alert ponovo.

Hard `BLOCK` ne može biti nadjačan Opportunity Score-om.

# 17. MILESTONE A — Prvi stvarno koristan sistem

Posle Phase 10 sistem treba da:

> kontinuirano prati jedan source i alertuje kada novi ili promenjeni apartment property izgleda dovoljno interesantno za ljudsku proveru.

Pre velikog daljeg razvoja koristiti sistem nad stvarnim market podacima.

Proveriti:

- da li discovery hvata realne nove listing-e;
- da li price changes rade;
- koliko matching grešaka postoji;
- da li comps imaju smisla;
- da li valuation deluje konzervativno;
- koliko alertova stiže;
- koliko alertova zaista vredi otvoriti.

Ako osnovni output nije dobar, popraviti njega pre dodavanja novih feature-a.

# 18. PHASE 11 — First Usable Dashboard

## Cilj

Omogućiti svakodnevno korišćenje bez direktnog rada sa bazom, skriptama ili terminalom.

## Required Context

    docs/06-api-ui-specification.md
    - V0 UI Scope
    - V0 API Scope
    - Action Queue
    - Property Detail
    - Sources
    - API principles
    - partial analysis
    - authentication assumptions

    docs/09-deployment-operations.md
    - production access/security requirements

## Scope

Prvo implementirati:

    Action Queue
    Properties List
    Property Detail
    Source Health
    Basic Settings

Property Detail prioritet:

    Decision Header
    Deal Summary
    History
    Listings
    Comparables
    Valuation
    Liquidity
    Seller
    Risk

Prikazati samo capability-je koji backend već ima.

## Auth

Production dashboard/API mora biti privatno zaštićen.

Ne graditi public registration ili multi-role auth.

## Van scope-a

Ne prioritetizovati:

- fancy charts;
- complex map;
- kanban CRM;
- drag-and-drop;
- advanced analytics;
- elaborate visual effects.

## Acceptance Criteria

Korisnik kroz browser može:

- videti Action Queue;
- razumeti zašto je kandidat preporučen;
- otvoriti Property Detail;
- videti relevantnu history;
- videti analysis/deal/risk rezultate;
- otvoriti originalni listing;
- videti source health.

# 19. PHASE 12 — Watchlist, Reanalysis & Change Intelligence

## Cilj

Efikasno pratiti property-je koji trenutno nisu deal, ali to mogu postati.

## Required Context

    docs/03-data-model.md
    - watch_rules
    - analytical current/stale state

    docs/05-analysis-specification.md
    - Re-analysis
    - invalidation rules
    - Watch Threshold Crossing

    docs/06-api-ui-specification.md
    - Watch
    - Watchlist
    - What Changed
    - Reanalysis API

## Scope

Implementirati:

    Watchlist
    Watch Rules
    What Changed
    automatic selective reanalysis
    action upgrades

Početni triggeri:

    ANY_PRICE_CHANGE
    PRICE_BELOW
    PRICE_DROP_PERCENT
    DESCRIPTION_CHANGE
    SELLER_CHANGE

Relevantan trigger prvo pokreće current re-analysis, pa tek onda alert decision.

## Acceptance Criteria

Scenario radi end-to-end:

    WATCH
    asking €155k
    ↓
    price change
    €139k
    ↓
    reanalysis
    ↓
    CALL
    ↓
    Telegram alert

bez korišćenja stale deal rezultata.

# 20. PHASE 13 — Acquisition CRM & Human Feedback

## Cilj

Početi da akumulira podatke koji ne postoje na portalima.

## Required Context

    docs/03-data-model.md
    - property_reviews
    - interactions
    - call_feedback
    - visit_feedback
    - offers
    - skip_records
    - property_outcomes
    - property_overrides
    - manual precedence

    docs/05-analysis-specification.md
    - manual precedence
    - seller feedback
    - risk/deal re-analysis

    docs/06-api-ui-specification.md
    - Pipeline
    - Log Call
    - Log Visit
    - Offers
    - Skip
    - related APIs

## Scope

Implementirati samo acquisition-specific workflow:

    pipeline status
    review
    call feedback
    visit feedback
    offers
    skip reasons
    manual estimates
    notes

Ne praviti generic CRM.

## Reanalysis

Relevantan manual input treba da može selektivno invalidirati/refresh-ovati:

    seller intelligence
    risk
    valuation, ako se promenio relevantan property fact
    deal
    opportunity

Manual/verified data ne sme biti prepisan scraping-om ili LLM-om.

## Acceptance Criteria

Jedan stvarni kandidat može biti praćen:

    alert
    → reviewed
    → call
    → visit
    → offer
    → outcome

bez external spreadsheet-a za osnovne acquisition podatke.

# 21. PHASE 14 — Reliability, Monitoring & Production Hardening

## Cilj

Pretvoriti funkcionalan prototip u sistem koji može kontinuirano i bezbedno da radi.

## Required Context

    docs/09-deployment-operations.md

    docs/04-scraping-specification.md
    - Source Health
    - failure isolation
    - recovery

    docs/08-testing-specification.md
    - reliability
    - recovery
    - integration tests

## Scope

Fokus:

    source health
    job reliability
    retries
    failed analysis recovery
    database backup
    persistent storage
    log retention/rotation
    process restart behavior
    security
    resource limits
    raw retention

Posebno proveriti scraper anomalies:

    zero-result anomaly
    parse-rate collapse
    important field disappearance
    unexpectedly empty discovery

## Restart Safety

API/worker restart ne sme:

- duplirati business events;
- gubiti listing/history;
- ponovo slati deduped alert;
- prepisati manual data.

## Backup

Pre ozbiljnog oslanjanja na historical dataset mora postojati automatizovan database backup i proverljiv restore workflow.

## Acceptance Criteria

Sistem bez data corruption-a podnosi relevantne:

    API restart
    worker restart
    temporary DB failure
    temporary source outage
    LLM outage
    Telegram outage

Recovery behavior je dokumentovan i testiran tamo gde je praktično.

# 22. PHASE 15 — Second Source & Cross-Portal Validation

## Cilj

Dokazati da sistem podržava više source-ova bez dupliranja celog ingestion pipeline-a.

## Required Context

    docs/02-system-architecture.md
    - Source Adapter
    - module boundaries
    - matching

    docs/03-data-model.md
    - Listing vs Property
    - matching history
    - provenance
    - images, ako se koriste

    docs/04-scraping-specification.md
    - adapter contract
    - adding a new source

## Scope

Dodati drugi source kroz novi adapter.

Ne menjati zajednički pipeline samo da bi se prilagodio jednom portalu, osim kada zajedničkom domain-u stvarno nedostaje capability.

## Cross-Source Matching

Posebno evaluirati slučajeve:

    same property
    different portal
    different agency
    different price
    different size claim
    different title
    same/similar images

Ako realni accuracy zahteva, sada je prikladan trenutak za perceptual image hashing.

## Property History

Canonical property treba da objedini source-level podatke bez gubitka odvojenih listing histories.

## Acceptance Criteria

Jedna fizička nekretnina prisutna na dva source-a može biti predstavljena kao:

    1 Property
    2 Listings
    2 independent listing histories
    1 current property-level analysis

uz očuvan provenance svakog podatka.

# 23. MILESTONE B — Real Market Radar

Posle Phase 15 sistem treba da poseduje:

    multi-source monitoring
    cross-portal property identity
    listing/property history
    price history
    seller history
    valuation
    liquidity / fast-sale
    risk
    deal economics
    opportunity alerts
    human feedback

Od ovog trenutka historical dataset postaje značajan proprietary asset sistema.

# 24. PHASE 16 — Historical Evaluation & Shadow Portfolio

## Cilj

Izmeriti koliko analytical preporuke zaista vrede pre ozbiljnog kapitalnog oslanjanja na njih.

## Required Context

    docs/03-data-model.md
    - property_outcomes
    - shadow_deals
    - analytical history
    - model versioning

    docs/05-analysis-specification.md
    - Historical as_of
    - Look-Ahead Bias
    - Backtesting
    - False Positives / Negatives
    - Confidence Calibration

## Scope

Implementirati potrebno za:

    Shadow Deals
    historical opportunity snapshots
    outcomes
    as-of analysis
    backtesting

## As-Of Invarijanta

Historical analysis koristi samo podatke dostupne:

    <= as_of

Ne koristiti future:

- price cuts;
- transactions;
- listing text;
- manual feedback;
- outcomes.

## Shadow Deal

Korisnik može sačuvati simuliranu kupovinu sa relevantnim:

    date
    buy price
    expected exit
    expected holding
    linked analysis

Original assumptions se ne rewrite-uju kasnijim current analysis-om.

## Evaluation

Pratiti gde je moguće:

    Alert Precision
    Call-Worthy Rate
    Valuation Error
    Downside Failures
    Simulated Profitability
    Missed Opportunities

## Acceptance Criteria

Za historical datum/property moguće je odgovoriti:

> Šta je sistem tada znao, izračunao i preporučio?

bez look-ahead bias-a.

# 25. PHASE 17 — Transaction Data Enrichment

## Cilj

Smanjiti zavisnost valuation-a od asking listing comps.

## Precondition

Pre implementacije konkretnog source-a mora biti poznato:

- legal/access status;
- licensing/uslovi korišćenja;
- format;
- coverage;
- precision;
- update cadence.

Ne projektovati import/parser za izmišljeni format.

## Required Context

    docs/03-data-model.md
    - transaction_records
    - transaction_property_matches
    - comparable_sets/items

    docs/05-analysis-specification.md
    - Comparable Types
    - Transaction Recency
    - Fair Value
    - Valuation Confidence

## Scope

Kada realni podaci postoje, implementirati:

    transaction ingestion/import
    normalization
    location/geocoding
    transaction comparables
    optional property matching

## Valuation

Transaction comps dobijaju odgovarajuću veću source-quality težinu.

Listing comps ostaju važni kao current asking-market context.

## Acceptance Criteria

Valuation explanation jasno razlikuje, na primer:

    6 Transaction Comps
    8 Listing Comps

i pokazuje njihov različit analytical tretman.

# 26. PHASE 18 — Model Calibration & Advanced Analytics

## Cilj

Preći sa inicijalnih heuristika na pravila/model koji su kalibrisani sopstvenim historical dataset-om.

## Precondition

Ne počinjati bez dovoljnog dataseta i baseline metrike.

## Required Context

    docs/05-analysis-specification.md
    - Backtesting
    - Valuation Metrics
    - Confidence Calibration
    - Seller Feedback
    - Model Evolution
    - Future ML boundaries

    docs/08-testing-specification.md
    - statistical/model evaluation

## Prioritet

Prvo kalibrisati postojeće transparentne komponente:

- comparable weights;
- listing/transaction treatment;
- confidence;
- Fast-Sale assumptions;
- liquidity;
- seller motivation;
- segment-specific rules.

## ML

Tek posle stabilnog baseline-a razmotriti ML valuation.

Svaki novi model mora biti poređen sa current transparent baseline-om na out-of-sample podacima.

Ako ne poboljšava relevantne metrike:

> ne koristiti ga.

Ne uvoditi ML radi tehnološke sofisticiranosti.

# 27. PHASE 19 — Land Support

## Cilj

Dodati `LAND` kao zaseban fully-supported property pipeline.

## Precondition

Apartment pipeline mora biti stabilan i dokazano koristan.

Postojanje `LAND` enum-a nije dovoljan razlog za implementaciju.

## Prvi korak

Pre code-a napisati zasebnu:

    Land Analysis Specification

koja definiše domain koji apartment dokumenti trenutno ne pokrivaju.

## Required Context

Tek nakon Land specifikacije koristiti relevantne:

    docs/01-product-specification.md
    docs/02-system-architecture.md
    docs/03-data-model.md
    docs/05-analysis-specification.md

uz novu Land specifikaciju.

## Scope

Tek kada je specificirano, mogu se uvesti:

    land-specific data
    parcel/location support
    land comparables
    planning/buildability
    land valuation
    land liquidity
    land risk
    land deal analysis
    land opportunity rules

Apartment valuation/risk formule se ne koriste kao Land pipeline.

## Ključne buduće oblasti

Posebnu pažnju zahtevaju:

- legal road access;
- buildability;
- ownership;
- planning constraints;
- parcel characteristics.

Ako buildable area nije pouzdano poznata, ne izmišljati `price/buildable_m²`.

# 28. PHASE 20+ — Additional Markets / Advanced Domains

Naredne faze nisu unapred fiksirane.

Mogući pravci:

    remaining Belgrade
    other Serbian cities
    Montenegro

    public auctions
    enforcement/bankruptcy
    bank sales

    advanced image analysis
    renovation CV

    parcel assembly
    off-market acquisition
    developer sourcing

Svaki veliki novi domain zahteva novu ili proširenu specifikaciju pre implementacije.

Ne pretpostavljati da postojeći apartment workflow automatski odgovara novom tržištu/domain-u.

# 29. Infrastruktura koja nema unapred određenu fazu

Ne uvoditi sledeće samo zato što projekat raste:

    Redis
    Celery
    Kafka
    microservices
    Kubernetes
    browser farm
    proxy infrastructure
    vector database
    distributed workers

Uvesti tek kada realan bottleneck zahteva capability.

## Redis / Celery Trigger

Razmotriti tek ako postoji konkretan problem kao:

- persistent job backlog;
- više worker servera;
- ozbiljna priority/retry orchestration složenost;
- analysis workload ugrožava crawling;
- PostgreSQL job claiming više nije dovoljan.

Do tada koristiti jednostavniju arhitekturu.

## Scaling

Skalirati na osnovu merenja:

    CPU
    RAM
    DB Load
    Crawl Duration
    Job Backlog
    Browser Usage
    Storage

Prvi korak je često jači VPS, ne distribuirana arhitektura.

# 30. Globalno odložene funkcionalnosti

Dok product scope ili realna potreba ne kažu drugačije, ne graditi:

- enterprise multi-tenant SaaS;
- organizations;
- billing/subscriptions;
- native mobile app;
- WebSocket svuda;
- generic vector search infrastructure;
- local large LLM infrastructure;
- automatic legal decision engine;
- large CV pipeline;
- kompleksni distributed scraping cluster.

# 31. Migration pravilo

Svaka faza dodaje samo schema koji stvarno koristi.

Konceptualno:

    Phase 1
    → core source/listing/property data

    Phase 4
    → matching

    Phase 6
    → comparables / valuation

    Phase 8
    → LLM / risk

    Phase 9
    → deal data

    Phase 10
    → opportunity / alerts

Ne kreirati finalnu schema u Phase 1.

# 32. Testing pravilo

Kritična nova logika dobija testove u istoj fazi.

Posebno ne odlagati testove za:

    parsers
    idempotency
    change detection
    matching
    valuation
    financial math
    hard gates
    alert dedupe

Detaljna test pravila su u `docs/08-testing-specification.md`.

# 33. Real-World Validation

Unit/integration test nije dovoljan dokaz kvaliteta market heuristike.

Posle ključnih faza uraditi representative manual review.

## Posle Phase 2–3

Proveriti realne scraped podatke i history.

## Posle Phase 4

Proveriti match/non-match odluke.

## Posle Phase 6

Proveriti realne comps i FMV.

## Posle Phase 10

Proveriti alert kvalitet.

Codex može napraviti tooling potreban za pregled.

Ne sme pretpostaviti da je tržišni model dobar samo zato što testovi prolaze.

# 34. Stop Gates

## Posle Phase 3

Ne nastavljati sa oslanjanjem na historical analytics ako crawler korumpira ili gubi istoriju.

## Posle Phase 6

Ako comps/FMV nisu razumni, popraviti valuation foundation pre sofisticiranog Opportunity Engine-a.

## Posle Phase 10

Ako veliki procenat alertova nema smisla:

- ne dodavati odmah više source-ova;
- prvo popraviti threshold-e, confidence, liquidity, risk i deal assumptions.

## Pre ML-a

Moraju postojati:

    baseline metrics
    historical dataset
    ground-truth subset
    train/validation/test methodology

## Pre Land-a

Apartment sistem prvo mora dokazati:

    reliable collection
    correct history
    useful property resolution
    useful analysis
    useful opportunity selection

# 35. Minimalni put do prvog korisnog sistema

Glavni backend acquisition V1:

    Phase 0
    ↓
    Phase 1
    ↓
    Phase 2
    ↓
    Phase 3
    ↓
    Phase 4
    ↓
    Phase 5
    ↓
    Phase 6
    ↓
    Phase 7
    ↓
    Phase 8
    ↓
    Phase 9
    ↓
    Phase 10

Frontend pre Phase 11 nije obavezan za glavnu engine funkciju ako se rezultati mogu bezbedno proveravati drugim development/admin načinom i Telegram već šalje alerts.

Ne preskakati radi brzine:

- listing history;
- property identity;
- Valuation Confidence;
- hard risk gates;
- financial correctness.

# 36. Glavni milestone-i

## Milestone 1 — Data Collector

Posle Phase 3:

> sistem kontinuirano i pouzdano gradi listing history.

## Milestone 2 — Property Intelligence

Posle Phase 6:

> postoji property identity, market history, comparable context i V1 FMV.

## Milestone 3 — Acquisition Engine

Posle Phase 10:

> sistem automatski analizira i alertuje potencijalne transakcije.

## Milestone 4 — Operating System

Posle Phase 13:

> acquisition actions i human feedback žive u sistemu.

## Milestone 5 — Real Market Radar

Posle Phase 15:

> multi-source history i cross-portal property identity povećavaju tržišnu prednost.

## Milestone 6 — Proprietary Decision Dataset

Posle Phase 16+:

> historical inputs, system decisions, human actions i outcomes omogućavaju ozbiljnu kalibraciju.

# 37. Pravilo završetka svake faze

Pre promene statusa faze u `COMPLETED` proveriti:

- implementation scope;
- migrations;
- relevant tests;
- application startup;
- existing critical behavior;
- acceptance criteria;
- unresolved blockers.

`docs/11-project-status.md` zatim ažurirati tako da sadrži:

    Current Phase
    Current Task
    Completed
    In Progress
    Blocked
    Next Task
    Required Context

Ne praviti dodatne status dokumente.

# 38. Konačni princip Phase Plan-a

Razvoj prati stvaranje stvarne vrednosti:

    PRIKUPI PODATKE
    ↓
    OČUVAJ ISTORIJU
    ↓
    RAZREŠI PROPERTY IDENTITET
    ↓
    IZGRADI KVALITETNE MARKET INPUTE
    ↓
    PROCENI VREDNOST
    ↓
    PROCENI LIKVIDNOST I FAST-SALE
    ↓
    PROCENI SELLER I RISK
    ↓
    IZRAČUNAJ DEAL
    ↓
    RANGIRAJ POTENCIJALNE TRANSAKCIJE
    ↓
    ALERTUJ
    ↓
    PRIKUPI HUMAN FEEDBACK
    ↓
    MERI OUTCOME
    ↓
    KALIBRIŠI

Ne preskakati direktno na:

    AI
    +
    fancy dashboard
    +
    mnogo source-ova

pre nego što postoje pouzdani historical podaci, property identity i finansijski korektan core.

Najvažniji cilj ranog razvoja je:

> **što ranije početi da gradi tačnu istorijsku bazu tržišta, a zatim svaku narednu fazu koristiti da tu bazu pretvori u kvalitetniju investicionu odluku.**