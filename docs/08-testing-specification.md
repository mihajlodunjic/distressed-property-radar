# Distressed Property Radar — Testing Specification

## 1. Svrha dokumenta

Ovaj dokument definiše šta mora biti testirano i na kom nivou da bi Distressed Property Radar ostao pouzdan dok raste.

Source of truth je za:

- unit testove;
- parser fixture testove;
- database integration testove;
- API testove;
- background job/orchestration testove;
- analytical i financial testove;
- end-to-end testove;
- regression zaštitu;
- live smoke testove;
- historical/backtesting testove;
- testing obaveze pri završetku task-a i faze.

Ne definiše:

- business formule;
- scraping ponašanje;
- data-model semantiku;
- deployment proceduru;
- redosled implementacije.

Za njih koristiti canonical specifikacije.

# 2. Prioritet testiranja

Najvažniji testovi sprečavaju greške koje mogu da:

- izgube listing/property istoriju;
- kreiraju duplicate listing-e ili events;
- prijave lažnu promenu;
- pogrešno proglase listing uklonjenim;
- pogrešno spoje property-je;
- prepišu manual/verified podatak;
- izračunaju pogrešan FMV ili Max Buy;
- sakriju hard risk;
- pošalju pogrešan ili duplicate alert;
- koriste future data u historical analysis-u.

Prioritet:

    DATA INTEGRITY
    >
    FINANCIAL CORRECTNESS
    >
    HARD RISK CORRECTNESS
    >
    ANALYTICAL CORRECTNESS
    >
    WORKFLOW CORRECTNESS
    >
    PERFORMANCE
    >
    VISUAL DETAILS

# 3. Testing piramida

Preferirati:

    mnogo unit testova
    dovoljno integration testova
    mali broj E2E testova
    vrlo mali broj live external smoke testova

Ne koristiti E2E za logiku koja može pouzdano biti pokrivena malim determinističkim unit testom.

# 4. Kategorije

Relevantne kategorije:

    unit
    database integration
    parser fixture
    mocked source integration
    API integration
    job/orchestration
    frontend behavior
    end-to-end pipeline
    live external smoke
    historical/backtesting
    regression

Ne mora svaka faza imati svaku kategoriju.

# 5. Test Environment

Testovi nikada ne koriste production bazu.

Integration testovi koji proveravaju PostgreSQL behavior treba da koriste izolovan:

    PostgreSQL + PostGIS

po mogućnosti iste glavne verzije kao development/production.

Ne koristiti SQLite kao zamenu kada se test oslanja na:

- PostgreSQL constraints;
- `NUMERIC`;
- JSONB;
- PostGIS;
- locking;
- PostgreSQL-specific SQL behavior.

Čiste funkcije testirati bez baze.

# 6. Determinizam

Standardni automated testovi ne smeju zavisiti od:

- trenutnog live portala;
- trenutnih real-estate cena;
- realnog LLM output-a;
- realnog Telegram API-ja;
- wall-clock vremena;
- nekontrolisanog random-a;
- external geocoding-a.

Kontrolisati ili mockovati takve dependency-je.

# 7. Time

Business funkcije koje zavise od vremena treba da dozvole kontrolisan `now`.

Primer:

    first_seen_at = 2026-08-01
    now           = 2026-08-21

očekivano:

    age = 20 days

Ne rasipati direktni `datetime.now()` duboko kroz business code ako time testiranje postaje nedeterminističko.

# 8. Money

Financial testovi koriste `Decimal`.

Primer očekivanog rezultata:

    Decimal("138500.00")

Ne validirati finansijske formule approximate float comparison-om kada se rezultat može tačno izraziti.

Rounding policy mora biti zaključan testovima tamo gde utiče na rezultat.

# 9. Test Isolation

Svaki test treba da može da radi:

- samostalno;
- u proizvoljnom redosledu;
- bez stanja koje je ostavio prethodni test.

Database testovi koriste odgovarajući:

- transaction rollback;
- clean schema;
- isolated database fixture.

Ne uvoditi parallel execution kao početni zahtev.

Ako se kasnije uvede, test DB mora biti izolovan po worker-u.

# 10. Test Naming

Naziv testa treba da opisuje behavior.

Dobro:

    test_same_listing_state_does_not_create_duplicate_event

Loše:

    test_listing_2

Za unit test preferirati jednu jasnu invariant-u po testu.

# 11. Arrange / Act / Assert

Test treba lako da pokazuje:

    Arrange
    Act
    Assert

Komentari sa tim nazivima nisu obavezni ako je struktura već jasna.

# 12. Parametrizovani Testovi

Koristiti parametrizovane/table-driven testove za:

- parser matrix;
- normalization edge cases;
- financial edge cases;
- Opportunity rules;
- Risk rules;
- status transitions.

Ne duplirati deset skoro identičnih test funkcija bez potrebe.

# 13. Mocking Granice

Tipično mockovati:

    network
    LLM provider
    Telegram
    external geocoder
    current time

Ne mockovati predmet testa.

Integration test koji proverava persistence treba, gde je praktično, da koristi stvarne:

    ORM
    PostgreSQL
    constraints
    application services

# 14. Test Helpers

Ako setup postane repetitivan, dozvoljeni su mali helper-i/factory funkcije poput:

    make_source(...)
    make_listing(...)
    make_property(...)
    make_valuation(...)

Ne graditi veliki generički test framework.

# 15. Migration Testovi

Minimalno mora raditi:

    fresh database
    → migrate to head

Za rizične migrations proveriti i:

    previous migration
    → new migration

Poseban test/provera je potrebna kada migration:

- dropuje ili prebacuje podatke;
- menja semantiku;
- uvodi `NOT NULL` nad postojećim redovima;
- radi data backfill;
- menja critical uniqueness/foreign-key behavior.

# 16. Core Database Constraints

Testirati critical database invarijante iz `03-data-model.md`.

Minimum:

- listing uniqueness;
- source-scoped external ID;
- nullable UNKNOWN semantics;
- money precision;
- timezone-aware timestamps;
- historical retention.

# 17. Listing Uniqueness

Scenario:

    source_id = A
    external_listing_id = 123

obrađen/upisan više puta.

Očekivanje:

    exactly 1 listing

Application layer može vratiti postojeći red ili database constraint može odbiti duplicate prema implementaciji.

# 18. External ID je Source-Scoped

Scenario:

    Source A / ID 123
    Source B / ID 123

Očekivanje:

    2 different listings

Uniqueness je:

    (source_id, external_listing_id)

ne samo `external_listing_id`.

# 19. UNKNOWN Semantika

Testirati tri-state vrijednosti.

Primer:

    elevator = null

ostaje različito od:

    elevator = false

Isto pravilo primeniti na druga polja gde UNKNOWN ima različitu semantiku od `false` ili `0`.

# 20. Historical Retention

`REMOVED` listing ostaje queryable zajedno sa istorijskim eventima.

Lifecycle promena ne sme implicitno fizički izbrisati historical data.

# 21. Parser Fixture Princip

Svaki production source parser mora imati fixture testove koji ne koriste mrežu.

Tok:

    fixture HTML/JSON
    → parser
    → RawListingCard / RawListingDetail

Fixture treba da bude:

- mali koliko može;
- realističan;
- stabilan;
- dovoljan da zadrži strukturu koju parser stvarno koristi.

Ne čuvati višemegabajtni HTML kada mali reprezentativni fixture testira isto ponašanje.

# 22. Minimalni Source Fixtures

Po source-u minimum:

    normal listing/search page
    normal detail page
    listing/detail without optional data

Kako se realni edge case pojavi, dodati fixture za njega, npr:

    price on request
    owner listing
    agency listing
    sponsored listing
    removed listing
    malformed field

Ne izmišljati desetine budućih edge case fixture-a unapred.

# 23. External Listing ID Parser

Za svaki source obavezno testirati stabilnu extraction strategiju za:

    external_listing_id

Ovo je critical dependency idempotency-ja.

# 24. Price Parser Matrix

Testovi treba da pokriju source-relevantne formate.

Primeri:

    "185.000 €"
    → 185000 EUR

    "185000 EUR"
    → 185000 EUR

    "185 000 €"
    → 185000 EUR

    "18.500.000 RSD"
    → 18500000 RSD

    "na upit"
    → amount = null

    "dogovor"
    → amount = null

    "1 €"
    → 1 EUR

Parser ne odlučuje da li je `1 €` tržišno realna vrednost.

To je zasebna validation/anomaly odgovornost.

# 25. Size Parser

Pokriti relevantne formate kao:

    "72 m²"
    → 72

    "72,5 m2"
    → 72.5

    "72.50"
    → prema dokumentovanoj source semantici

Posebno zaštititi lokalni decimal separator.

# 26. Floor Parser

Pokriti realne source formate koje adapter podržava, npr:

    "5/8"
    → floor 5, total_floors 8

    "V sprat"
    → floor 5

    "prizemlje"
    → definisana ground-floor semantika

    "visoko prizemlje"
    → definisana kategorija/normalizacija

    "potkrovlje"
    → ne izmišljati numeric floor ako nije poznat

Test očekivanje mora pratiti canonical domain semantiku.

# 27. Currency

Ako source ima implicitnu currency:

- testirati samo eksplicitno definisano source pravilo;
- ne zaključivati currency iz magnitude cene.

# 28. Mocked HTTP Source Integration

Bez live interneta testirati flow:

    HTTP response
    → adapter/parser
    → raw DTO

Obavezno pokriti:

- success;
- relevant error classification;
- timeout/retry behavior gde je deo trenutne implementacije.

# 29. Pagination

Testirati:

    page 1
    page 2
    last page

i zaštitu od infinite loop-a ako source ponavlja istu stranicu ili cursor.

# 30. Discovery Boundary

Ako:

    5 NEW
    10 KNOWN

i:

    known_listing_stop_threshold = 10

discovery treba da obradi 5 novih i završi prema source policy-ju.

Ako stari sponsored listing stoji na vrhu, ne sme sam izazvati early stop ako policy zahteva uzastopni poznati window.

# 31. Ingestion Idempotency

Jedan od najvažnijih testova projekta.

Isti card/detail state obrađen više puta mora dati:

    1 listing
    1 DISCOVERED event
    0 false change events

Dozvoljen je observation update kao:

    last_seen_at

kada je business semantika odgovarajuća.

# 32. Price Change

Početno:

    180000

zatim:

    170000

Očekivanje:

    exactly 1 PRICE_CHANGED
    old = 180000
    new = 170000

Treće procesiranje:

    170000

ne kreira novi price event.

# 33. Description Change

Ako normalization definiše whitespace kao nebitan, promena:

    "Hitna prodaja."

u:

    "  Hitna   prodaja.\n"

ne treba da bude semantic change.

Promena:

    "Prodaje se stan."

u:

    "Hitna prodaja zbog odlaska."

mora biti detektovana.

# 34. Failed Scan Safety

Scenario:

    100 active listings
    scan fails after first page

Listing-i sa neobrađenih stranica ne smeju zbog toga preći u removal lifecycle.

Ovo je critical data-integrity test.

# 35. Zero-Result Anomaly

Ako source koji normalno vraća listing-e iznenada vrati:

    0

bez potvrde da je to validno kompletno tržišno stanje:

    mass removal MUST NOT happen

Parser/source failure ne sme izgledati kao empty market.

# 36. Listing Lifecycle

Testirati source policy kroz:

    ACTIVE
    → NOT_SEEN
    → REMOVED
    → ACTIVE

sa odgovarajućim eventima.

Posebno proveriti da jedan missed observation ne potvrđuje removal ako policy zahteva više dokaza.

# 37. Source Health

Minimum:

- successful crawl ažurira `last_success`;
- failed crawl ažurira error state;
- parser degradation menja health prema rules;
- zero-result anomaly nije healthy success bez provere;
- disabled source ne dobija nove scheduled jobs.

# 38. Matching Test Strategija

Matching koristiti kontrolisane property/listing parove.

Testirati najmanje:

    obvious match
    obvious non-match
    ambiguous candidate
    manual precedence
    rejected candidate behavior
    idempotent re-run

# 39. Obvious Match

Primer:

    same micro-location
    72 m² vs 72 m²
    same rooms
    same floor
    strong text/image similarity

Očekivanje:

    high match score

i, ako konfigurisan threshold dozvoljava:

    AUTO_MATCH

# 40. Obvious Non-Match

Primer:

    same street
    72 m² vs 95 m²
    3 rooms vs 4 rooms
    floor 2 vs floor 8

Očekivanje:

    reject / no match

prema canonical matching semantics.

# 41. Ambiguous Match

Primer:

    same building
    similar size
    same rooms
    floor unknown
    no useful image evidence

Ako score pripada uncertainty zoni:

    POSSIBLE_MATCH

Ne forsirati auto-match.

# 42. Manual Match Precedence

Ako korisnik potvrdi:

    MANUAL_MATCH

ponovno pokretanje automatic matcher-a ne sme samo raskinuti tu vezu.

# 43. Manual Reject

Ako candidate bude ručno odbijen, ordinary re-run ne treba svaki put da vraća isti unresolved candidate.

Ponovno razmatranje je dozvoljeno samo ako canonical matching logic eksplicitno kaže da nova verzija/promenjeni input to opravdava.

# 44. Merge / Split

Ako capability postoji, testirati da merge očuva:

- sve listing-e;
- listing events;
- matching history;
- interactions;
- historical analyses.

Split mora moći ponovo da razdvoji listing association bez rewrite-a istorijskih činjenica.

Ne pisati test za future capability koji još nije implementiran.

# 45. Property Feature Testovi

Derived feature-i moraju imati determinističke unit testove.

Posebno:

- listing age;
- property market age;
- price cut count;
- total price drop;
- largest price cut;
- days since last cut;
- relist count.

# 46. Property Market Age

Scenario:

    Listing A first seen day 0
    Listing B relisted day 50
    both belong to same Property

Property market age ne sme postati samo age Listing B ako canonical semantics kaže da je ista nekretnina.

# 47. Price History Features

Za:

    200k
    → 190k
    → 180k

proveriti:

- total price drop;
- number of cuts;
- largest cut;
- days since last cut;

prema canonical formuli.

Ponovno računanje iz iste history mora dati isti rezultat.

# 48. Data Quality

Koristiti nekoliko jasno definisanih profiles.

## High Quality

Property sa gotovo svim relevantnim poznatim inputima treba da ima visok score prema current rules.

## Low Quality

Property sa npr:

    municipality
    asking price
    size

ali bez drugih relevantnih podataka mora imati značajno slabiji score.

## UNKNOWN

UNKNOWN field ne dobija puni completeness credit.

## Critical Missing

Ako nedostaje critical input, testirati da `missing_critical_fields` to eksplicitno pokazuje čak i ako aggregate score nije veoma nizak.

## Version

Promena Data Quality rules/config-a treba da bude vidljiva kroz odgovarajuću version semantiku.

# 49. Comparable Engine

Koristiti sintetički/kontrolisan market dataset.

Ne testirati algorithm correctness nad trenutno živim tržištem.

Pokriti:

- radius filtering;
- adaptive radius;
- size filtering;
- similarity ordering;
- transaction/listing distinction;
- recency;
- outlier handling;
- exclusion reason;
- historical `as_of`.

# 50. Radius

Za target i comp udaljenosti:

    100m
    400m
    900m
    2km

testirati expected candidate inclusion kroz konfigurisan adaptive radius.

Ako se radius širi, similarity/selection treba da prati current rules.

# 51. Size Filtering

Za target:

    70 m²

testirati npr:

    68
    75
    88
    120

uz expected include/fallback/reject behavior iz trenutne konfiguracije.

# 52. Similarity Ordering

Sve ostalo približno jednako, property koji je:

- bliži;
- sličnije površine;
- istog room segmenta;

treba da bude rangiran bolje od očigledno slabijeg comp-a.

Ne zaključavati test na internu implementaciju ako je behavioral ordering dovoljan.

# 53. Transaction vs Listing

Transaction comp i Listing comp moraju ostati različiti source types kroz analytical output.

Test treba da padne ako se oba nehotice mapiraju u isti tip.

# 54. Comparable Outlier

Kontrolisan primer €/m²:

    3000
    3050
    3100
    3080
    9000

Očekivati da `9000` bude downweighted/excluded prema current rules.

Output mora imati reason poput:

    PRICE_OUTLIER

ili odgovarajući canonical code.

# 55. Valuation Reproducibility

Isti:

    property
    comparable set
    model version
    config

mora dati isti valuation rezultat.

# 56. FMV Ordering

Uvek proveriti:

    fair_value_low
    <=
    fair_value_base
    <=
    fair_value_high

Ako model prekrši ordering, test pada.

# 57. Valuation Insufficient Data

Bez dovoljno validnih market inputa:

    status = INSUFFICIENT_DATA

i ne sme postojati izmišljena FMV cifra.

# 58. Valuation Confidence

Behavioral testovi treba da potvrde da, sve ostalo jednako:

- više kvalitetnih comps poboljšava confidence;
- kvalitetni transaction comps imaju bolji evidence contribution od slabih listing-only comps;
- veća dispersion smanjuje confidence;
- critical missing data smanjuje confidence.

Ne testirati samo tačan broj ako je cilj behavior i weights se često kalibrišu.

# 59. Dispersion

Comp set:

    3000
    3020
    3050

treba da ima bolji dispersion confidence signal od:

    2500
    3100
    3900

prema trenutnom modelu.

# 60. Adjustment Limits

Ako zbir target adjustments pređe configured cap, testirati explicit canonical behavior:

- cap;
- reject;
- low-confidence;

zavisno od current Analysis Specification-a.

Ne dozvoliti accidental unlimited adjustment.

# 61. Historical Valuation

Ako:

    as_of = June 1

comp koji postaje dostupan:

    June 10

ne sme biti deo comparable set-a.

Ovo je critical look-ahead protection.

# 62. Liquidity

Koristiti jasne controlled profiles.

Sve ostalo jednako, npr:

    common-size apartment
    good microzone
    elevator
    normal floor

treba da dobije bolji liquidity behavior od:

    unusual size
    weak location
    high floor without elevator

prema trenutnim rules.

# 63. Liquidity UNKNOWN

Ako parking nije poznat:

    parking = UNKNOWN

ne sme automatski postati:

    parking = bad

UNKNOWN treba da ima canonical neutral/confidence effect.

# 64. Fast-Sale

Za isti FMV, sve ostalo jednako:

    better liquidity

treba da dozvoli bolju Fast-Sale procenu od low-liquidity property-ja prema current modelu.

Obavezno:

    fast_sale_low
    <=
    fast_sale_base
    <=
    fast_sale_high

I prema V1 semantici tipično:

    fast_sale_base <= fair_value_base

osim ako buduća model version eksplicitno definiše drugačije.

# 65. LLM Test Strategy

Standardni automated suite ne poziva pravi LLM.

Mockovati provider.

Odvojeno testirati:

1. client behavior;
2. schema validation;
3. application integration;
4. caching;
5. failure fallback.

# 66. LLM Schema Validation

Pokriti:

- valid structured output;
- missing required schema field;
- invalid enum;
- invalid confidence range;
- malformed JSON;
- free text umesto required schema.

Invalid output treba da završi u definisanom:

    INVALID_OUTPUT

ili:

    FAILED

state-u, ne kao valid domain result.

# 67. LLM UNKNOWN

Output kao:

    seller_motivation = UNKNOWN

je validan structured rezultat.

Ne pretvarati ga u error ili izmišljenu kategoriju.

# 68. LLM Hallucination Protection

LLM-derived podatak ne sme postati verified property fact bez odgovarajućeg provenance/verification procesa.

Ako evidence validation postoji, testirati da unsupported evidence bude odbijen ili označen prema implementaciji.

# 69. LLM Caching

Isti:

    listing
    input_hash
    prompt_version
    model

ne treba bez razloga ponovo da pozove provider.

Mock provider call count je dovoljan za test.

Promena relevantnog description inputa treba da napravi novi analysis input.

Promena samo `last_seen_at` ne treba.

# 70. LLM Outage

Provider exception treba da proizvede:

    listing/property preserved
    LLM status = FAILED

dok nezavisni delovi pipeline-a nastavljaju da rade.

# 71. Seller Intelligence

Testirati determinističke i LLM signale odvojeno.

Primer:

    repeated large price cuts
    +
    long market age

može povećati seller motivation i bez LLM-a prema current rules.

# 72. Manual Seller Precedence

Ako manual call feedback kaže:

    seller not motivated

a LLM kaže:

    HIGH

effective seller state mora pratiti canonical precedence pravilo.

Automatski reanalysis ne sme pregaziti manual/verified input.

# 73. Risk Engine

Hard-gate testovi su critical.

Pokriti najmanje:

    PASS
    VERIFY
    BLOCK
    soft risk
    provenance precedence

# 74. BLOCK

Input koji pouzdano aktivira hard block rule mora dati:

    hard_gate_status = BLOCK

bez obzira na:

- profit;
- valuation;
- liquidity;
- seller urgency.

# 75. VERIFY

Nepoznata/nepotvrđena kritična informacija treba da daje `VERIFY` gde current rules to zahtevaju.

Ne pretvarati UNKNOWN u PASS samo zato što nema negativnog podatka.

# 76. PASS Semantika

Test treba da štiti semantiku:

    PASS
    !=
    verified legally clean

PASS samo znači da current rules nisu našli blocker koji zahteva VERIFY/BLOCK.

# 77. Risk Precedence

Verified/manual fact ima odgovarajući prioritet nad slabijim source claim/LLM inference-om.

# 78. Soft Risk

Soft risk ne sme postati `BLOCK` ako current rules version to ne definiše.

# 79. Deal Engine

Deal Engine ima jednu od najviših potrebnih pokrivenosti poslovne logike u projektu.

Minimum:

- fixed costs;
- percentage costs;
- sale costs;
- total cost basis;
- net proceeds;
- profit;
- ROI;
- annualized ROI;
- risk reserve;
- Max Buy;
- required negotiation;
- scenario calculations;
- invalid inputs;
- Decimal precision.

# 80. Fixed-Cost Deal

Napraviti ručno proverljiv fixture/scenario.

Primer:

    purchase = 130000
    fixed purchase costs = 5000
    renovation = 5000
    holding = 1000
    net sale proceeds = 165000

Ručno zaključati expected:

    total cost basis
    net profit
    ROI

prema canonical formula version-u.

# 81. Percentage Costs

Ako Cost Profile sadrži npr:

    purchase cost = 2.5%

test mora potvrditi da:

- koristi tačnu osnovicu;
- procenat nije slučajno 25%;
- cost se računa tačno jednom.

# 82. Max Buy Solver

Pokriti više ručno proverljivih slučajeva:

    only fixed costs
    fixed + percentage buy costs
    fixed required profit
    minimum ROI
    combined profit + ROI constraints

Rezultat treba nezavisno proveriti formulom/kalkulatorom.

# 83. Max Buy Monotonicity

Sve ostalo jednako:

Ako:

    required profit increases

onda:

    Max Buy must not increase

Ako:

    conservative exit increases

onda:

    Max Buy must not decrease

Property-based/parametrized test je poželjan ako pojednostavljuje ovu proveru.

# 84. Required Negotiation

Za:

    asking = 150000
    max_buy = 140000

očekivati:

    negotiation amount = 10000
    negotiation pct = 10000 / 150000

uz canonical rounding.

Ako:

    asking = 135000
    max_buy = 140000

required negotiation ne treba da bude negativan:

    required negotiation = 0

Positive safety gap može biti drugo polje.

# 85. Scenario Ordering

Za normalno konstruisan controlled test očekivati:

    downside_profit
    <=
    base_profit
    <=
    upside_profit

Ako current scenario semantics legitimno mogu prekršiti ordering, testirati eksplicitnu definiciju umesto implicitnog očekivanja.

# 86. Invalid Deal Input

Pokriti najmanje:

    negative holding days
    invalid monetary values
    division by zero
    invalid capital denominator

`holding_days = 0` mora imati eksplicitno definisano annualized-ROI ponašanje.

Ne dozvoliti accidental runtime divide-by-zero.

# 87. Annualized ROI

Izabrana formula mora biti zaključana testovima.

Promena formule zahteva odgovarajući:

    formula_version

Ne dozvoliti da dva mesta u codebase-u koriste različite definicije iste metrike.

# 88. Opportunity Engine

Rules-based actions treba da imaju table-driven testove.

Minimum:

    IGNORE
    WATCH
    REVIEW
    CALL
    URGENT_CALL

plus hard-gate i threshold edge cases.

# 89. IGNORE

Primer:

    expected profit = negative
    seller motivation = HIGH

Očekivanje prema V1 pravilima:

    IGNORE

Seller urgency ne popravlja negativnu ekonomiku.

# 90. WATCH

Primer:

    potentially good property
    asking > Max Buy
    repeated price cuts

Očekivanje:

    WATCH

ako konfiguracija tako definiše.

# 91. REVIEW

Primer:

    apparent large discount
    low valuation confidence

Očekivanje:

    REVIEW

umesto agresivne akcije.

# 92. CALL

Primer:

    acceptable economics after modest negotiation
    sufficient confidence
    risk != BLOCK

Očekivanje:

    CALL

prema current threshold-ima.

# 93. URGENT_CALL

Napraviti najmanje jedan kompletan positive scenario koji zadovoljava sve current critical conditions.

Test ne sme samo mockovati finalnu action funkciju.

# 94. BLOCK Overrides Opportunity

Critical regression test:

    expected profit = excellent
    liquidity = excellent
    seller motivation = HIGH
    risk = BLOCK

Rezultat ne sme biti:

    CALL / URGENT_CALL

ako current hard-gate rules to zabranjuju.

# 95. Confidence Threshold

Property ispod minimum confidence-a ne sme dobiti action koji zahteva viši confidence.

Boundary cases oko threshold-a treba parametrizovati.

# 96. Downside Threshold

Visok Base Profit uz neprihvatljiv Downside mora biti degradiran prema current opportunity rules.

# 97. Opportunity Explanation

Action result mora da sadrži odgovarajuće:

    reason_codes

Ne testirati samo finalni enum.

# 98. Watch Rules

Primer:

    PRICE_BELOW = 142000

Cena:

    150000 → 145000

ne triggeruje.

Zatim:

    145000 → 141000

triggeruje jednom.

Sledeći scan sa:

    141000

ne proizvodi isti threshold-crossed alert bez nove relevantne business promene.

# 99. Alerts

Telegram provider se mockuje.

Testirati odvojeno:

- alert creation;
- delivery state;
- retry;
- dedupe;
- action upgrade;
- operational vs opportunity category.

# 100. Alert Creation

Relevantan opportunity event treba prvo da napravi:

    PENDING

alert record.

Tek zatim se poziva notification provider.

# 101. Successful Delivery

Mock success:

    PENDING
    → SENT

uz odgovarajući `sent_at` i provider metadata ako se čuvaju.

# 102. Failed Delivery

Mock Telegram failure:

    PENDING
    → FAILED

Property analysis/opportunity rezultat ostaje sačuvan.

Notification failure ne rollback-uje analytical work.

# 103. Alert Retry

Ako postoji retry, isti business alert treba da bude ponovo dostavljen kroz postojeći alert record ili canonical retry flow.

Retry ne sme kreirati novi logical opportunity alert samo zato što je prvi provider request pao.

# 104. Alert Deduplication

Isti unchanged opportunity state obrađen više puta treba da proizvede:

    1 meaningful alert

ne više identičnih Telegram poruka.

# 105. Action Upgrade

Promena:

    WATCH
    → CALL

može legitimno proizvesti novi alert jer je business state promenjen.

# 106. Operational Alert Separation

Scraper/source warning ne sme postati property Opportunity Alert.

Oba mogu koristiti isti notification transport, ali ostaju različite semantičke kategorije.

# 107. Job / Orchestration Testovi

Mockovati spoljne dependency-je, ali koristiti stvarne application services kada je to predmet testa.

Pokriti:

- discovery;
- partial item failure;
- global source failure;
- analysis orchestration;
- retry/restart idempotency.

# 108. Discovery Job

Testirati da job:

- započne validno;
- evidentira source attempt;
- obrađuje listing-e;
- čuva job summary;
- ažurira source success/failure stanje.

# 109. Partial Item Failure

Ako 1 od 20 listing-a pukne zbog lokalne parse/data greške:

    processed = 19
    failed = 1

ako failure nije globalan za ceo source.

Jedan malformed listing ne odbacuje preostalih 19.

# 110. Global Source Failure

Ako listing-page fetch potpuno padne:

- ne generisati false removals;
- source/job treba da ima failure state;
- postojeći market history ostaje netaknut.

# 111. Analysis Orchestration

Kontrolisano testirati flow:

    features
    → comps
    → valuation
    → liquidity / fast-sale
    → LLM
    → risk
    → deal
    → opportunity

Optional module failure treba da proizvede očekivani partial state kada downstream semantika to dozvoljava.

# 112. Invalidation

Critical test grupa za sprečavanje korišćenja stare analize.

Pokriti najmanje:

    price change
    description change
    location correction
    manual feedback
    merge/split
    relevant new comp data

samo za capability-je koji su implementirani.

# 113. Price Invalidation

Price change najmanje invalidira:

    deal
    opportunity

i druge module prema current dependency specification-u.

Ne invalidirati FMV automatski ako current model namerno ne koristi target asking price.

# 114. Description Invalidation

Relevantna description promena invalidira najmanje current:

    LLM
    seller analysis
    relevant risk
    opportunity

Ako extraction promeni property attribute kao `condition`, invalidirati i sve module koji ga koriste.

# 115. Location Invalidation

Location correction mora invalidirati relevantne:

    comparable set
    valuation
    liquidity
    fast-sale
    deal
    opportunity

# 116. Reanalysis History

Scenario:

    valuation run A exists
    ↓
    input changes
    ↓
    reanalysis
    ↓
    valuation run B exists

Očekivanje:

    A remains queryable
    B becomes current result

Historical analysis se ne overwrite-uje.

# 117. Manual Data vs Background Work

Ako background analysis traje dok se upisuje manual/verified podatak:

- manual write ostaje;
- stale background result ne sme pregaziti manual podatak;
- latest analysis state treba da se invalidira/requeue-uje ako je potrebno.

# 118. API Test Princip

FastAPI endpoint testirati preko HTTP test client-a.

Ne smatrati direktno pozivanje route Python funkcije dovoljnim API testom.

API test treba da pokrije:

    HTTP
    validation
    auth, kada postoji
    application service
    serialization

# 119. Health API

Testirati:

    GET /health

za canonical success response.

Ako health ima dependency details, testirati samo ono što current endpoint ugovor garantuje.

# 120. Pagination

Pokriti:

    default page
    explicit page
    page_size
    max page_size
    invalid page/page_size
    empty page

# 121. Filter / Sort Validation

Primer invalidnog filtera:

    min_price = abc

mora dati validation error.

Unknown sort field treba da bude:

- odbijen; ili
- pretvoren u eksplicitno definisan safe fallback.

Raw user sort input ne sme direktno postati SQL `ORDER BY`.

# 122. Not Found

Primer:

    GET /properties/nonexistent

treba da vrati canonical:

    404

ne generic 500.

# 123. UNKNOWN API Representation

Backend `null` ostaje:

    null

Ne transformisati ga implicitno u:

    false
    0
    ""

# 124. Business Write Atomicity

Za command koji predstavlja jednu business operaciju proveriti da njegove persistence promene ostaju konzistentne.

Primer `Skip`:

    create skip record
    +
    update pipeline state

treba da bude jedna application operation.

Ne ostaviti half-written state.

# 125. Call / Visit / Offer Validation

Za svaki implemented write endpoint testirati:

- valid payload;
- invalid enum;
- invalid amount/date;
- property/entity not found;
- persistence;
- relevant downstream invalidation/reanalysis.

# 126. Reanalysis Endpoint

Ako contract vraća:

    QUEUED

test treba da potvrdi non-blocking behavior.

Ne čekati realni LLM/analysis pipeline unutar HTTP test-a.

# 127. Deal Calculator API

Za fixed input:

    API result
    =
    direct Deal Engine result

Ovo štiti od dupliranja finansijske matematike u API route-u.

# 128. Authentication

Kada auth postoji, minimum:

    unauthenticated read rejected
    unauthenticated write rejected
    authenticated read works
    authenticated write works

Ako se koristi cookie/session auth, testirati relevantne CSRF/session protections definisane konkretnom implementacijom.

# 129. Frontend Test Princip

Ne testirati svaki CSS detalj.

Fokusirati se na behavior koji utiče na decision making ili write actions.

Relevantni component/integration testovi mogu uključiti:

- UNKNOWN renders as unknown;
- BLOCK ima jasan tekstualni status;
- Action Queue prikazuje ključne economics;
- empty/loading/error/stale states se razlikuju;
- manual form validation;
- write action šalje očekivani API command.

# 130. Frontend API Mocking

Component testovi po default-u koriste mocked API/server layer.

Ne zahtevati pravi backend za svaki frontend test.

Mali E2E set može koristiti kompletan stack.

# 131. E2E Strategija

E2E koristiti samo za kritične vertikalne tokove.

Ne pokušavati svaki edge case pokriti browser E2E testom.

# 132. E2E — New Listing

Mock source flow:

    discovery
    → card/detail parsing
    → normalization
    → persistence

Očekivanje:

- listing postoji;
- property postoji kada current phase to zahteva;
- history je korektna;
- nema duplicate-a.

# 133. E2E — Price Cut

    existing listing
    → mocked lower price
    → PRICE_CHANGED
    → required stale states
    → reanalysis

Proveriti da se ne duplira price event.

# 134. E2E — Opportunity Alert

    candidate
    → analysis
    → opportunity action
    → PENDING alert
    → mocked Telegram
    → SENT

Ne koristiti realni Telegram provider.

# 135. E2E — Watch Upgrade

    WATCH
    → price cut
    → threshold crossed
    → reanalysis
    → action upgrade
    → alert

Proveriti da se alert zasniva na novom analysis state-u, ne starom deal rezultatu.

# 136. E2E — Human Feedback

Kada CRM postoji:

    property
    → call/visit feedback
    → effective input changes
    → relevant reanalysis
    → deal/opportunity update

Manual input mora ostati očuvan.

# 137. Live Source Smoke Tests

Jedina standardna testing kategorija koja pristupa stvarnom listing source-u.

Mora biti:

- mala;
- kontrolisana;
- odvojena od determinističkog suite-a.

Cilj nije proveriti konkretnu cenu.

Cilj je proveriti npr:

    source reachable
    plausible listing content returned
    at least one card parseable
    critical field presence within expected range

# 138. Live Smoke nije Standard CI Gate

Live source failure može značiti:

- source unavailable;
- markup change;
- rate limiting;
- network problem;
- application bug.

Zbog toga live smoke ne treba da bude blocking standardni CI test bez eksplicitnog razloga.

Tretirati ga i kao Source Health signal.

# 139. Real LLM Smoke

Nije deo standardnog suite-a.

Povremeno može proveriti:

- provider credentials;
- structured-output compatibility;
- selected model availability;
- prompt/schema compatibility.

Odvojen je zbog troška i nondeterminism-a.

# 140. Telegram Smoke

Ne slati stvarnu Telegram poruku pri svakom test run-u.

Dozvoljena je manual/operational:

    Send Test Notification

provera kada je potrebna.

# 141. Performance Testing

Ne praviti veliki load-test framework prerano.

Prvo meriti realni workload.

Dodavati performance regression test samo gde postoji konkretan rizik.

# 142. Market Scan Performance Smoke

Kada market scan postoji, koristan controlled scenario je:

    1,000 mocked listing cards

koji mogu da budu:

    parsed
    compared
    persisted/updated

bez očiglednog N+1 ili ekstremnog slowdown-a.

Ne zaključavati prerano agresivne latency granice.

# 143. Query Regression

Za Action Queue i Properties list proveravati da broj query-ja ne raste linearno po svakom row-u zbog očiglednog N+1.

Primer problema:

    100 rows
    ×
    separate analytics queries per row

Performance cilj treba da bude zasnovan na realnom dataset-u.

# 144. Matching Scale

Candidate generation ne sme postati:

    every new listing
    ×
    every property

kada dataset poraste.

Po potrebi instrumentirati broj evaluated candidates.

# 145. Backtesting Testovi

Kada historical evaluation postoji, testirati posebno:

- look-ahead;
- future listing changes;
- future comps;
- future manual feedback;
- model/version semantics;
- shadow-deal immutability.

# 146. General Look-Ahead Test

Za:

    as_of = T

u bazi postoje:

    input before T
    input after T

Historical analytical query sme da koristi samo input dostupne do `T`.

# 147. Future Price Change Leak

Ako listing kasnije dobije nižu cenu, backtest ranijeg datuma ne sme je videti.

# 148. Future Comparable Leak

Transaction/listing comp koji nastane posle `as_of` ne sme ući u historical comparable set.

# 149. Future Manual Feedback Leak

Call, visit ili manual override posle historical decision time-a ne sme uticati na raniju simulaciju.

# 150. Stored Historical Version

Ako historical result kaže:

    valuation_model_version = v2

display/query stored historical result ne sme ga slučajno predstaviti kao da je proizveden trenutnim `v5`.

Ako se radi explicit historical reprocessing kroz novu verziju, to mora biti novi rezultat/context.

# 151. Shadow Deal

Simulated buy čuva originalne:

- buy assumptions;
- linked analysis;
- expected exit;
- holding;
- expected economics.

Kasnija promena Investment Profile-a ne menja retroaktivno historical Shadow Deal.

# 152. Property-Type Separation

APARTMENT testovi ne predstavljaju automatski LAND testove.

Kada LAND uđe u scope, dodati zasebne testove za njegovu domain logiku, posebno:

- buildability;
- land comparables;
- buildable-area metrics;
- Land hard gates.

# 153. Regression Rule

Svaki reproduktivan bug koji može da se vrati treba, gde je razumno, dobiti regression test.

Workflow:

    reproduce
    → failing test
    → fix
    → passing regression test

Posebno za:

- parser bugs;
- duplicate/history bugs;
- matching greške;
- financial formula bugs;
- hard-gate bugs;
- alert duplication.

# 154. Production-Derived Fixtures

Ako production podatak reprodukuje bug:

- sačuvati samo minimum potreban za reprodukciju;
- ukloniti nepotrebne lične/osetljive podatke;
- ne kopirati ceo production payload ako mali sanitized fixture radi isto.

# 155. Production Incident Priority

Ako bug može da:

    corrupt data
    lose listing history
    create false removals
    calculate wrong critical economics
    bypass hard risk
    send false critical alerts

prioritet:

    reproduce
    → regression test
    → fix
    → inspect existing data impact

pre nastavka običnog feature rada.

# 156. CI

Kada CI postoji, koristiti samo toolchain koji je projekat stvarno usvojio.

Tipičan pipeline može uključiti:

    backend format check
    backend lint
    backend type check, if configured
    backend tests

    frontend lint
    frontend build
    frontend tests, if configured

Ne uvoditi alat samo zato što je naveden kao primer.

Live external smoke nije deo standardnog blocking CI pipeline-a.

# 157. Coverage

Ne juriti arbitraran globalni coverage procenat.

Visoku pokrivenost zahtevati za critical deterministic modules:

    ingestion/change detection
    matching core
    valuation core
    deal engine
    risk hard gates
    opportunity rules
    alert dedupe

CRUD boilerplate ne mora imati 100% coverage.

# 158. Mutation-Style Quality Check

Za critical invariant zapitati se:

> Da li bi test pao ako neko slučajno promeni najvažniji operator/uslov?

Primeri:

    + → -
    2.5% → 25%
    old_price ↔ new_price
    BLOCK check removed
    source_id removed from listing uniqueness
    <= changed to >= in threshold

Ako takva greška prolazi suite, critical test coverage nije dovoljna.

# 159. Manual Validation nije Automated Test

Ručno pregledati:

- realne scraped podatke;
- matching;
- comps;
- valuation;
- Opportunity alerts.

Ali:

> „pogledao sam i deluje dobro“

nije zamena za automated idempotency, migration ili financial test.

# 160. Automated Test nije Market Validation

Obrnuto:

    all tests PASS

ne znači:

> valuation model je dobar za realno tržište.

Automated testovi potvrđuju da implementacija radi prema definisanoj logici.

Real-data review i historical outcomes potvrđuju da li je sama logika korisna.

# 161. Required Test Groups po Fazama

Phase Plan određuje scope; ova sekcija određuje minimalne testing oblasti.

## Phase 0

Minimum:

- backend import/start;
- health endpoint;
- DB connection;
- PostGIS;
- migrations;
- test runner;
- frontend build ako frontend postoji.

## Phase 1

Minimum:

- migrations;
- constraints;
- listing uniqueness;
- UNKNOWN semantics;
- Decimal/NUMERIC;
- relationships.

## Phase 2

Minimum:

- parser fixtures;
- identity parser;
- normalization;
- mocked HTTP;
- pagination;
- ingestion idempotency;
- first persistence flow.

## Phase 3

Minimum:

- discovery boundary;
- change detection;
- price history;
- failed scan safety;
- zero-result anomaly;
- lifecycle;
- source health;
- job isolation.

## Phase 4

Minimum:

- obvious match;
- non-match;
- ambiguous match;
- manual precedence;
- idempotent matching;
- merge/split behavior gde postoji.

## Phase 5

Minimum:

- normalization/location;
- features;
- market age;
- effective values;
- Data Quality;
- recomputation.

## Phase 6

Minimum:

- comparable filtering/ranking;
- transaction/listing distinction;
- outliers;
- valuation;
- confidence;
- insufficient data;
- historical `as_of`.

## Phase 7

Minimum:

- liquidity rules;
- UNKNOWN behavior;
- Fast-Sale;
- ordering;
- explainability metadata.

## Phase 8

Minimum:

- LLM schema;
- UNKNOWN;
- caching;
- outage;
- seller signals;
- manual precedence;
- Risk Gate;
- BLOCK/VERIFY/PASS.

## Phase 9

Minimum:

- every critical Deal formula;
- Max Buy;
- ROI;
- scenario calculations;
- Decimal precision;
- invalid inputs.

## Phase 10

Minimum:

- every Recommended Action;
- Hard Gate;
- confidence/downside thresholds;
- reason codes;
- alert lifecycle;
- alert dedupe;
- full opportunity-to-notification flow.

## Phase 11

Minimum:

- critical API contracts;
- auth;
- Action Queue;
- Property Detail critical states;
- UNKNOWN/STALE/BLOCK UI.

## Phase 12

Minimum:

- watch triggers;
- trigger dedupe;
- invalidation;
- fresh reanalysis before action upgrade;
- Watch → Action alert.

## Phase 13

Minimum:

- call/visit/offer writes;
- pipeline transitions;
- manual precedence;
- skip atomicity;
- feedback-triggered reanalysis.

## Phase 14

Minimum:

- restart/retry idempotency;
- source outages;
- optional-provider outages;
- recovery;
- backup/restore checks defined by Operations specification.

## Phase 15

Minimum:

- second-source adapter fixtures;
- shared ingestion regression;
- cross-source matching;
- multiple listing histories per property.

## Phase 16

Minimum:

- look-ahead protection;
- as-of reconstruction;
- shadow-deal immutability;
- outcome/history queries.

## Phase 17+

Dodavati testing scope zajedno sa novim domain capability-jem.

Ne prepisivati ceo test suite samo zbog nove faze.

# 162. Test Execution pri Codex Task-u

Pri završetku malog task-a pokrenuti:

1. najrelevantnije nove/izmenjene testove;
2. dovoljan regression subset za pogođeni modul.

Nije obavezno pokrenuti veoma spor full E2E suite za sitnu izolovanu parser izmenu ako nema razloga.

Pre završetka cele faze pokrenuti kompletan trenutno standardni automated suite, osim eksplicitno odvojenih live smoke testova.

# 163. Test Reporting

Codex u završnom izveštaju razlikuje:

    PASS
    FAIL
    NOT RUN

Ako test nije mogao da se izvrši zbog environment-a:

    NOT RUN

Ne tvrditi da je prošao.

Ako postoji failure, navesti da li je:

- uveden trenutnim task-om;
- pre-existing;
- environmental;
- external smoke failure.

# 164. Flaky Testovi

Deterministički flaky test nije prihvatljivo normalno stanje.

Ne rešavati ga sa:

    retry test 5 times until green

osim ako je test eksplicitno external nondeterministic smoke test.

Popraviti uzrok.

# 165. Temporary Skip

Test se može privremeno skipovati samo uz jasan dokumentovan razlog.

Ne koristiti masovni `skip`/`xfail` da bi suite izgledao zeleno.

Critical failing regression test ne treba skipovati da bi feature bio proglašen završenim.

# 166. Najvažniji Regression Set

Ako bi projekat morao da zadrži samo mali broj najvažnijih testova, minimum bi štitio sledeće:

1. isti source listing ne nastaje dva puta;
2. isti listing state ne pravi duplicate event;
3. prava promena cene pravi tačno jedan event;
4. failed/partial scan ne proizvodi false removal;
5. UNKNOWN ne postaje `false`/`0`;
6. manual match nije prepisan automatic matcher-om;
7. reanalysis ne briše historical analysis;
8. valuation ne koristi future comparable;
9. listing comp ne postaje transaction comp;
10. Max Buy calculation je tačan;
11. percentage costs nisu pogrešno primenjeni;
12. hard `BLOCK` sprečava zabranjenu Opportunity akciju;
13. stale input pokreće odgovarajuću invalidaciju;
14. isti opportunity state ne šalje isti alert više puta;
15. manual/verified podatak nije prepisan background analysis-om.

# 167. Canonical Ownership

Business i product očekivanja:

    docs/01-product-specification.md

Architecture boundaries:

    docs/02-system-architecture.md

Database constraints i persistence semantics:

    docs/03-data-model.md

Scraping behavior:

    docs/04-scraping-specification.md

Analytical formulas i rules:

    docs/05-analysis-specification.md

API/UI behavior:

    docs/06-api-ui-specification.md

Testing scope po development fazi:

    docs/07-phase-plan.md

Production/runtime recovery behavior:

    docs/09-deployment-operations.md

Ovaj dokument poseduje:

> **način na koji se critical ponašanje iz tih specifikacija automatski i ponovljivo verifikuje.**

# 168. Konačni Testing Princip

Test suite štiti od dve različite klase grešaka.

## Technical / Integrity Bugs

Primeri:

    parser broke
    duplicate listing created
    duplicate change event created
    failed crawl caused mass removal
    job retry corrupted state
    formula implemented incorrectly
    manual value overwritten
    API accepted invalid input

## Analytical Implementation Bugs

Primeri:

    future comp leaked into backtest
    transaction/listing types merged
    UNKNOWN treated as false
    Risk BLOCK ignored
    stale analysis presented as current
    Opportunity threshold applied in wrong direction

Test suite ipak ne može sam da dokaže da je tržišni model dobar.

Konačni kvalitet nastaje iz:

    AUTOMATED TESTS
    +
    REAL-DATA REVIEW
    +
    HISTORICAL VALIDATION
    +
    ACTUAL OUTCOMES

Automated testovi garantuju:

> **sistem se ponaša onako kako je specifikacija definisala.**

Realni market podaci i ishodi odgovaraju na drugo pitanje:

> **da li su same definisane heuristike i modeli zaista korisni za donošenje investicionih odluka?**