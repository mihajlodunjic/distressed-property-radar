
# Distressed Property Radar — System Architecture

## 1. Svrha dokumenta

Ovaj dokument definiše **tehničku arhitekturu Distressed Property Radar sistema**.

Ovo je source of truth za:

- arhitektonski stil;
- glavne backend module;
- odgovornosti i granice modula;
- dependency direction;
- glavne runtime odgovornosti;
- tok podataka kroz sistem;
- background job arhitekturu;
- koordinaciju ingestion i analysis procesa;
- granice između source, operational, analytical i manual podataka;
- integraciju sa spoljnim servisima;
- osnovne failure-isolation principe;
- arhitektonske uslove za kasnije skaliranje.

Ovaj dokument ne definiše:

- poslovne kriterijume dobrog deala;
- detaljnu SQL šemu;
- konkretne database kolone i indekse;
- portal-specific crawling i parsing pravila;
- tačne valuation/liquidity/risk/deal formule;
- API endpoint ugovore;
- frontend layout;
- test matrix;
- production deployment topologiju i server sizing;
- redosled implementacionih faza.

Za te oblasti koristiti njihove canonical specifikacije.


## 2. Arhitektonski stil

Sistem se inicijalno implementira kao:

> **modularni monolit sa background processing-om.**

To znači:

- jedan repository;
- jedan backend codebase;
- jedan centralni domain model;
- jedna PostgreSQL/PostGIS baza;
- jasno odvojeni logički moduli;
- background poslovi mogu raditi u jednom ili više procesa;
- odvajanje procesa ne znači automatski odvajanje u mikroservise.

Ne uvoditi mikroservise samo zato što različite aktivnosti mogu da rade paralelno.

Na primer:

```text
API process
worker process
scheduler process
````

mogu biti različiti runtime procesi, ali i dalje pripadaju istoj aplikaciji.

## 3. Arhitektonski prioriteti

Redosled prioriteta je:

```text
1. data integrity
2. tačna istorija
3. pouzdan ingestion
4. failure isolation
5. jasne modularne granice
6. explainable analytics
7. pravovremene opportunity akcije
8. performanse
9. UI polish
```

Najvažniji dugoročni asset sistema je istorijski dataset.

Zbog toga ingestion ne sme biti zavisan od dostupnosti svakog downstream modula.

## 4. Centralna runtime invarijanta

Sistem mora biti projektovan tako da:

> **prikupljanje i čuvanje tržišnih podataka može da nastavi da radi čak i kada analiza, LLM provider, Telegram ili frontend privremeno ne rade.**

Primer:

```text
Source available
Analysis provider unavailable

→ listing se ipak prikuplja
→ history se ipak čuva
→ analysis dobija PENDING/FAILED stanje
→ naknadni retry može nastaviti obradu
```

Ne rollback-ovati validan ingestion samo zato što downstream processing nije uspeo.

## 5. Tehnološka osnova

Početna tehnološka osnova projekta:

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

### HTTP data collection

```text
httpx
HTML / JSON parsing
```

Parser biblioteka može biti izabrana prema stvarnoj potrebi projekta.

### Browser automation

```text
Playwright
```

samo kada konkretan source zahteva browser runtime.

### Frontend

```text
React
```

### Notifications

```text
Telegram Bot API
```

### Runtime packaging

```text
Docker
Docker Compose
```

Konkretan production deployment pripada `docs/09-deployment-operations.md`.

## 6. Šta se namerno ne uvodi unapred

Bez stvarnog problema koji to zahteva ne uvoditi:

```text
microservices
Kafka
Kubernetes
service mesh
distributed tracing platform
multiple application databases
Redis
Celery
pgvector
browser cluster
generic plugin framework
complex event bus
CQRS framework
```

Neke od ovih tehnologija mogu postati opravdane kasnije.

Arhitektura samo treba da ostavi razuman put ka njima, ne da ih implementira unapred.

## 7. Glavne runtime odgovornosti

Konceptualno sistem ima:

```text
Frontend
   ↓ HTTP
FastAPI Application
   ↓
PostgreSQL + PostGIS
```

i background izvršavanja za:

```text
source discovery
market scanning
reconciliation
analysis
maintenance
notifications
```

U ranim fazama više ovih odgovornosti može raditi unutar jednog worker procesa.

Važno je da logičke granice ostanu jasne čak i kada runtime deployment još nije fizički razdvojen.

## 8. Predložena backend struktura

Konceptualna struktura:

```text
backend/
  app/
    api/
    core/
    db/
    domain/

    sources/
    ingestion/
    normalization/
    matching/
    locations/
    features/

    comparables/
    valuation/
    liquidity/
    llm/
    risk/
    deals/
    opportunities/

    alerts/
    feedback/
    portfolio/

    jobs/
```

Nazivi mogu biti blago prilagođeni kada postojeći kod opravdava bolju organizaciju.

Ne praviti module unapred kao prazne placeholder-e.

Modul nastaje kada njegova faza i odgovornost stvarno postoje.

## 9. `core`

`core` sadrži tehničke osnove zajedničke većem delu aplikacije.

Primeri:

* configuration/settings;
* logging setup;
* zajednički application exceptions;
* mali broj shared constants;
* zaista zajedničke datetime/config helper-e.

`core` ne sme sadržati:

* valuation logiku;
* scraping logiku;
* deal formule;
* risk pravila;
* portal-specific kod.

Ne koristiti `core` kao generički `utils` folder.

## 10. `db`

`db` je odgovoran za tehnički pristup persistence sloju.

Može sadržati:

* connection/session konfiguraciju;
* SQLAlchemy setup;
* ORM base;
* Alembic integration;
* zajedničke persistence primitive kada stvarno postoje.

Ne sadrži domain odluke samo zato što rade nad bazom.

Detaljan data model pripada:

```text
docs/03-data-model.md
```

## 11. `domain`

`domain` sadrži tipove koji imaju zajedničko poslovno značenje kroz više modula.

Primeri mogu uključivati:

```text
PropertyType
ListingStatus
SourceType
ActionType
RiskGateStatus
PipelineStatus
```

`domain` treba da bude nezavisan od:

* konkretnih portala;
* CSS selektora;
* provider-specific SDK-a;
* frontend presentation detalja.

Ne praviti nepotrebnu drugu kopiju svakog ORM modela samo da bi se formalno imao „domain layer“.

## 12. `sources`

`sources` izoluje sve portal-specific ponašanje.

Svaki source treba da ima svoju jasnu granicu.

Primer:

```text
sources/
  portal_a/
    adapter.py
    parser.py

  portal_b/
    adapter.py
    parser.py
```

Source-specific informacije ostaju u odgovarajućem source modulu:

* URL struktura;
* pagination;
* query parametri;
* endpoint-i;
* HTML struktura;
* selektori;
* parsing;
* source-specific request ponašanje.

Promena jednog portala ne sme zahtevati promenu valuation, deal ili UI logike.

## 13. Source Adapter Contract

Source adapter treba da izloži mali stabilan application contract.

Konceptualno:

```python
class ListingSourceAdapter:
    async def discover_latest(...):
        ...

    async def scan_active_page(...):
        ...

    async def fetch_detail(...):
        ...
```

Tačni DTO-i i metode određuju se prema scraping specifikaciji i stvarnim potrebama implementacije.

Source adapter je odgovoran za:

> **dobavljanje i parsiranje source podataka.**

Nije odgovoran za:

* property matching;
* valuation;
* LLM analysis;
* risk;
* deal calculation;
* opportunity ranking;
* alert odluku.

## 14. HTTP i browser granica

Za source koji može pouzdano da se obrađuje običnim HTTP pristupom:

```text
Source Adapter
→ HTTP fetch
→ parser
```

ne koristiti browser automation.

Ako browser runtime stvarno jeste potreban:

```text
Source Adapter
     ↓
Browser Fetcher
```

Browser execution treba da ostane izolovan od ostatka ingestion logike.

Ostatak sistema ne treba da zna da li je podatak preuzet preko `httpx` ili Playwright-a.

## 15. Scraping detalji nisu deo ove specifikacije

Ova arhitektura zahteva:

* source isolation;
* incremental ingestion;
* card/detail razdvajanje;
* idempotent processing;
* failure isolation.

Ali konkretna pravila kao što su:

* stranice koje se obilaze;
* discovery boundary;
* crawl intervali;
* rate limits;
* retry pravila po portalu;
* selectors;
* removal detection;
* pagination strategija;

pripadaju:

```text
docs/04-scraping-specification.md
```

## 16. `ingestion`

`ingestion` je application granica između source adaptera i internog data sistema.

Njegova konceptualna odgovornost:

```text
source result
↓
identify source listing
↓
preserve required raw input
↓
normalize
↓
compare with known state
↓
persist valid changes/history
↓
produce downstream work when required
```

`ingestion` ne zna:

* CSS selektore;
* valuation formule;
* opportunity thresholds;
* Telegram formatting.

## 17. Card i Detail podaci

Arhitektura mora dozvoliti razliku između:

```text
LISTING CARD DATA
```

i:

```text
LISTING DETAIL DATA
```

Card podatak se koristi za jeftinije:

* discovery;
* identifikaciju;
* lightweight change detection.

Detail podatak se učitava kada je stvarno potreban.

Cilj je da sistem ne radi skupe detail fetch-eve za svaki poznati listing pri svakom scan-u.

## 18. Incremental ingestion

Osnovni arhitektonski princip collection sloja je:

> **incremental processing.**

Konceptualno:

```text
new listing
→ process required data

relevant state changed
→ process affected data

unchanged
→ refresh observation state
→ avoid expensive downstream work
```

Tačan crawling algoritam pripada Scraping Specification-u.

## 19. Tri vrste market procesa

Na arhitektonskom nivou razlikovati tri odgovornosti.

### Fast Discovery

Cilj:

> brzo otkrivanje novih listing-a.

Ne mora prolaziti kroz kompletno aktivno tržište pri svakom izvršavanju.

### Active Market Scan

Cilj:

> pratiti relevantne promene već poznatog aktivnog tržišta.

Na primer:

* price change;
* listing state;
* novi listing ID;
* nestanak sa pregledanih stranica.

### Deep Reconciliation

Sporiji proces za stvari koje ne zahtevaju minimalnu latency.

Na primer:

* potencijalno uklonjeni listing;
* relisting;
* matching re-evaluation;
* source consistency;
* nepotpuni podaci.

Detaljni algoritmi svih procesa pripadaju Scraping Specification-u.

## 20. Change events

Relevantna promena source ili manual stanja treba da može da pokrene downstream processing.

Konceptualni događaji mogu biti:

```text
LISTING_DISCOVERED
PRICE_CHANGED
DESCRIPTION_CHANGED
SELLER_CHANGED
LISTING_REMOVED
LISTING_RELISTED
PROPERTY_MATCH_CHANGED
LOCATION_CHANGED
MANUAL_DATA_CHANGED
```

Ovo ne zahteva Kafka ili poseban event-bus sistem.

U modularnom monolitu događaj može biti predstavljen kroz:

* application service poziv;
* persistence zapis;
* background job;
* drugu jednostavnu lokalnu mehaniku.

Bitno je semantičko razdvajanje događaja, ne infrastruktura.

## 21. Idempotency

Ingestion i background processing moraju biti bezbedni za retry gde god je moguće.

Konceptualni source listing identitet zasniva se na:

```text
source
+
external_listing_id
```

u skladu sa Data Model specifikacijom.

Ponovna obrada istog nepromenjenog source state-a ne sme proizvesti:

* novi duplicate listing;
* lažni price event;
* duplicate property;
* identičan duplicate alert.

Detaljne database constraint-e definiše Data Model.

## 22. `normalization`

`normalization` prevodi source-specific representation u zajednički interni oblik.

Primer:

```text
"185.000 EUR"
"185000 €"
"185.000€"
```

mogu postati ista normalizovana monetary vrednost.

Normalizer može obrađivati stvari poput:

* cenu;
* currency;
* površinu;
* sobnost;
* sprat;
* property type;
* enum/boolean atribute;
* osnovni location representation;
* tekstualni cleanup.

Normalizer ne treba da izmišlja podatke kojih nema.

## 23. Raw i normalized podaci

Arhitektura mora razlikovati:

```text
raw source value
```

od:

```text
normalized value
```

Primer:

```text
raw:
"V sprat"

normalized:
floor = 5
```

Ako rezultat nije dovoljno pouzdan:

```text
floor = null
```

dok relevantan raw input ostaje dostupan prema pravilima Data Model-a.

Reprocessing boljim parserom treba da bude moguć kada je odgovarajući istorijski input sačuvan.

## 24. Storage slojevi

Konceptualno razlikovati najmanje:

```text
RAW SOURCE DATA

NORMALIZED OPERATIONAL DATA

DERIVED ANALYTICAL DATA

MANUAL / USER DATA
```

Ovo razdvajanje je važno da:

* novi scrape ne uništi manual podatak;
* nova analiza ne izgubi staru analizu;
* bolji parser može reprocess-ovati raw input;
* provenance ostane poznat;
* current source state ne postane isto što i analytical state.

## 25. `matching`

`matching` rešava odnos:

```text
LISTING
↓
PROPERTY
```

Odgovornosti mogu uključivati:

* candidate generation;
* similarity evaluation;
* automatic high-confidence match;
* possible-match rezultat;
* manual confirmation support;
* merge/split workflow kada je potreban.

Matching ne menja identitet originalnog listing-a.

Više listing-a može ostati povezano sa jednim canonical property-jem.

## 26. Matching tok

Konceptualno:

```text
normalized listing
↓
candidate properties
↓
cheap eligibility filters
↓
similarity analysis
↓
high confidence?
    YES → link
    NO
      ↓
uncertain?
    YES → possible match
    NO  → create new property
```

Tačna pravila, pragovi i podaci za matching pripadaju odgovarajućim domain/data/analysis specifikacijama.

## 27. Image similarity

Ako se slike kasnije koriste za duplicate detection, image processing treba da proizvodi ponovo upotrebljiv derived signal, npr:

```text
perceptual hash
```

Matching može koristiti taj signal.

Image similarity ne treba sama da bude dovoljan dokaz za automatsko spajanje property-ja kada postoje jaki konfliktni podaci.

Ne uvoditi computer-vision pipeline dok ga trenutna faza ne zahteva.

## 28. `locations`

`locations` predstavlja zajednički location sloj.

Može biti odgovoran za:

* normalizovanu geografsku hijerarhiju;
* geocoding kada postoji;
* microzone mapping;
* location confidence;
* spatial query pomoć;
* udaljenosti.

PostGIS je canonical alat za prostorne database operacije.

## 29. Location hijerarhija

Konceptualno:

```text
Country
↓
City
↓
Municipality
↓
Neighborhood
↓
Microzone
↓
Street
↓
Coordinate
```

Ne moraju svi nivoi biti poznati.

Listing/property se mora moći sačuvati i kada location informacija nije kompletna.

## 30. `features`

`features` predstavlja determinističke derived podatke koji služe drugim analytical modulima.

Primeri mogu uključivati:

```text
price_per_m2
listing_age
property_market_age
total_price_drop_pct
number_of_price_cuts
days_since_last_price_cut
relist_count
active_listing_count
```

Exact feature set uvodi se samo kada ga trenutna analiza zaista koristi.

## 31. Derived-data invalidation

Promena jednog inputa ne treba da izazove ponovno računanje svega.

Sistem treba vremenom da koristi dependency-aware invalidation.

Primer:

```text
PRICE_CHANGED
↓
price-dependent features stale
↓
affected deal/opportunity outputs stale
```

Drugi primer:

```text
LOCATION_CHANGED
↓
comparable set stale
↓
valuation stale
↓
affected downstream analysis stale
```

Ne implementirati generički dependency framework unapred.

Početi eksplicitnim application pravilima i proširivati ih kada stvarno postoji više zavisnosti.

## 32. `comparables`

`comparables` je odgovoran za:

```text
target property
↓
candidate comparable data
↓
eligibility/filtering
↓
similarity/relevance
↓
ranked comparable set
```

Comparable modul:

> **ne računa finalni FMV.**

Njegov rezultat koristi `valuation`.

## 33. Comparable provenance

Arhitektura mora očuvati razliku između najmanje:

```text
TRANSACTION COMPARABLE
LISTING COMPARABLE
```

Valuation rezultat mora imati dovoljan trag do comps korišćenih za njegov calculation.

Time ostaju mogući:

* explainability;
* historical comparison;
* backtesting;
* model-version analysis.

## 34. `valuation`

`valuation` prima relevantan snapshot podataka i proizvodi strukturirani valuation rezultat.

Konceptualni input:

```text
property
features
comparable set
configuration/model version
```

Konceptualni output:

```text
fair_value_low
fair_value_base
fair_value_high
confidence
explanation metadata
model_version
```

`valuation` ne:

* šalje Telegram;
* bira Action Queue status;
* radi scraping;
* menja source podatke.

## 35. Valuation implementacije

Početna implementacija može biti jednostavna rules/statistical strategija definisana Analysis Specification-om.

Kasnije drugi valuation model može zameniti ili dopuniti prvi.

Arhitektura treba da dozvoli verzionisanje analytical rezultata, ali ne treba unapred praviti kompleksan ML framework.

Tek kada stvarno postoji druga implementacija ima smisla uvoditi odgovarajuću strategy granicu.

## 36. `liquidity`

`liquidity` procenjuje tržišnu prodajnost property-ja.

Konceptualno koristi:

* property characteristics;
* location;
* market features;
* relevantne istorijske podatke.

Output treba da bude strukturiran i objašnjiv.

Na primer:

```text
liquidity result
confidence
positive factors
negative factors
model version
```

Tačne vrednosti i formula pripadaju Analysis Specification-u.

## 37. `llm`

LLM funkcionalnost mora biti izolovan analytical/enrichment sloj.

Odgovornosti:

* kontrolisan input;
* provider call;
* structured output;
* schema validation;
* prompt/model version;
* failure state;
* caching/reuse kada je primenljivo.

LLM modul ne računa:

* finansijske formule;
* Max Buy;
* ROI;
* finalnu valuation matematiku.

LLM failure ne sme blokirati očuvanje source podataka.

## 38. LLM provider granica

Provider-specific kod treba izolovati iza malog client/adapter sloja.

Konceptualno:

```text
Application Analysis
↓
LLM Client
↓
Provider
```

Promena modela/provider-a ne treba da zahteva izmene kroz:

* risk;
* opportunities;
* ingestion;
* UI.

Ne graditi multi-provider framework dok ne postoji stvarna potreba.

## 39. LLM re-analysis

LLM poziv ne treba ponavljati ako se njegov relevantan input nije promenio.

Arhitektura treba da dozvoli:

```text
relevant input fingerprint/hash
+
analysis version
```

kako bi prethodni validan rezultat mogao da bude ponovo iskorišćen.

Promena tehničkog polja poput:

```text
last_seen_at
```

ne treba sama da pokrene novu semantic analizu teksta.

## 40. `risk`

`risk` kombinuje relevantne strukturirane i izvedene signale.

Konceptualni output treba da razdvaja najmanje:

```text
hard gate status
risk flags
soft risk factors
confidence/provenance
```

Risk analiza nije profesionalni pravni due diligence.

## 41. Hard-gate tok

Konceptualno:

```text
property data
+
source claims
+
structured analytical signals
+
manual/verified facts
↓
risk rules
↓
PASS / VERIFY / BLOCK
```

Pouzdaniji manual/verified podatak ne sme biti tiho prepisan slabijim source ili analytical signalom.

Exact risk pravila pripadaju Analysis Specification-u.

## 42. `deals`

`deals` je deterministički finansijski calculation sloj.

Konceptualno prima:

* purchase-price scenario;
* exit assumptions;
* costs;
* renovation;
* holding;
* financing;
* taxes/config;
* risk reserve;
* profit requirements.

Može proizvoditi:

```text
total cost basis
max buy price
expected profit
downside profit
ROI
annualized ROI
capital days
profit per capital-day
scenario results
```

Tačne formule pripadaju:

```text
docs/05-analysis-specification.md
```

## 43. Deal engine mora biti izolovan od source-a

Dozvoljeni tok:

```text
source
↓
normalized/verified data
↓
analysis inputs
↓
deal engine
```

Nedozvoljeni coupling:

```text
deal calculator
→ scrape portal directly
```

Finansijska logika mora moći da se testira bez mreže i bez source adaptera.

## 44. `opportunities`

`opportunities` kombinuje relevantne analytical rezultate i Investment Profile kako bi proizveo decision-support rezultat.

Konceptualni input može uključivati:

```text
valuation
fast-sale estimate
deal result
liquidity
risk
confidence
seller signals
investment profile
```

Konceptualni output:

```text
recommended action
ranking metrics
reasons
```

Opportunity se određuje tek nakon relevantnih hard-gate provera.

## 45. Recommended Action i Pipeline Status

Arhitektura mora razlikovati:

```text
recommended_action
```

od:

```text
user_pipeline_status
```

Primer:

```text
recommended_action = URGENT_CALL
pipeline_status = NEW
```

Nakon korisničkog poziva:

```text
pipeline_status = CALLED
```

dok analytical action može:

* ostati isti;
* biti unapređen;
* biti smanjen.

To su različiti state machine-ovi.

## 46. Source state i Analysis state

Takođe razlikovati:

```text
listing/source state
analysis state
property state
recommended action
pipeline status
notification state
```

Primer:

```text
listing = ACTIVE
analysis = FAILED
```

je potpuno validno stanje.

Ne koristiti jedno generičko `status` polje za semantički različite stvari.

## 47. `alerts`

`alerts` dobija već izračunat Opportunity rezultat.

Odgovoran je za:

* notification eligibility;
* prioritet;
* deduplication;
* reason;
* delivery state;
* summary payload.

`alerts` ne računa:

* FMV;
* Max Buy;
* liquidity;
* risk.

## 48. Alert deduplication

Isti property ne treba da dobija identičan notification pri svakom scan-u.

Novi alert može imati smisla kada postoji novi decision-relevant event, na primer:

```text
new high-priority property
action upgraded
large price change
watch threshold crossed
major seller signal
important risk change
```

Alert record treba da postoji odvojeno od Telegram delivery pokušaja.

## 49. Telegram granica

Tok:

```text
Opportunity
↓
Alert Decision
↓
Alert Record
↓
Telegram Client
```

Ako Telegram nije dostupan:

```text
Alert Record ostaje
Delivery može failovati/retry
```

ali:

```text
ingestion nastavlja
analysis ostaje sačuvan
deal calculation se ne rollback-uje
```

## 50. `feedback`

`feedback` čuva strukturirane podatke koje unosi korisnik.

Može uključivati:

* call feedback;
* visit feedback;
* manual estimates;
* verified facts;
* skip reason;
* offer;
* counteroffer;
* outcome;
* notes.

Ovaj podatak ima različito poreklo i nivo pouzdanosti od scraped ili LLM-derived podataka.

## 51. Manual-data precedence

Sistem mora razlikovati najmanje:

```text
scraped/source value
derived deterministic value
LLM interpretation
manual user value
verified manual fact
```

Jedan nivo ne sme nekontrolisano overwrite-ovati drugi.

Kada analytics zahteva jednu effective vrednost, precedence pravila moraju biti eksplicitna u canonical domain/analysis specifikaciji.

## 52. `portfolio`

`portfolio` služi za funkcionalnosti poput:

* shadow deal-a;
* stvarno kupljenih property-ja kada ta faza dođe;
* praćenja investicionog outcome-a;
* istorijske evaluacije.

Portfolio nije dependency osnovnog ingestion pipeline-a.

Market collection mora raditi i ako portfolio funkcionalnost još nije implementirana.

## 53. `jobs`

`jobs` je orchestration sloj za background izvršavanje.

Primeri konceptualnih entrypoint-a:

```text
run_source_discovery
run_market_scan
run_reconciliation
run_property_analysis
recalculate_opportunity
send_pending_alerts
```

Job treba da pozove application/domain service.

Ne stavljati kompletan business workflow direktno u cron ili scheduler callback.

## 54. Scheduler

Arhitektura mora podržati periodične poslove različite učestalosti.

Minimalne kategorije:

```text
fast discovery
active market scan
reconciliation
maintenance
```

Tačni intervali i source-specific scheduling pravila pripadaju Scraping Specification-u.

Scheduling u početku treba rešiti najjednostavnijim pouzdanim mehanizmom dovoljnim za trenutnu fazu.

Ne uvoditi distributed queue samo zbog postojanja periodičnih poslova.

## 55. PostgreSQL kao početni coordination layer

Dok je sistem mali, PostgreSQL može da čuva jednostavna coordination stanja kao što su:

```text
next_check_at
processing state
analysis state
pending alert
job state
```

Ako postoji samo jedan worker za datu odgovornost, ne uvoditi kompleksan distributed-lock sistem.

Ako se kasnije pojavi konkurentna obrada istog work seta, mogu se koristiti pouzdani PostgreSQL concurrency mehanizmi.

Queue infrastruktura dolazi tek kada trenutni pristup postane stvarno ograničenje.

## 56. Sync i async

Async koristiti prvenstveno tamo gde postoji stvarni I/O benefit:

* HTTP;
* browser operations;
* external APIs;
* drugi network-bound poslovi.

Čista business calculation logika može ostati synchronous.

Ne pretvarati ceo backend u async samo zato što scraper koristi async HTTP client.

## 57. Analysis orchestration

Treba da postoji application orchestration granica koja zna dependency redosled analize.

Konceptualno:

```text
analyze_property(property_id)
```

može koordinisati:

```text
required features
↓
comparables
↓
valuation
↓
liquidity
↓
required text analysis
↓
risk
↓
deal
↓
opportunity
```

Pojedinačni moduli ne treba međusobno da stvaraju circular callback mrežu.

## 58. Dependency direction

Poželjni glavni smer:

```text
sources
↓
ingestion
↓
normalization
↓
matching / locations / features
↓
comparables
↓
valuation / liquidity / llm
↓
risk
↓
deals
↓
opportunities
↓
alerts
```

`feedback` može promeniti effective analytical input, ali kroz odgovarajući application service.

Frontend/API route ne treba direktno da poziva duboke interne funkcije iz više modula kako bi ručno orkestrirao ovaj graph.

## 59. Fast Analysis Path

Za nov potencijalno relevantan property mora postojati put do dovoljno kvalitetne prve odluke bez čekanja svih mogućih enrichment procesa.

Konceptualno:

```text
discover
↓
required detail
↓
normalize
↓
persist history
↓
match/create property
↓
minimum required features
↓
minimum required comps
↓
valuation
↓
required seller/risk analysis
↓
liquidity
↓
deal
↓
opportunity
↓
possible alert
```

Fast Path koristi samo podatke potrebne za pravovremenu odluku.

## 60. Slow Enrichment Path

Sporija naknadna obrada može uključivati:

* deeper matching;
* dodatne comps;
* image similarity;
* historical enrichment;
* reconciliation;
* dodatne eksterne podatke;
* kompleksniju kasniju analizu.

Slow processing ne treba da spreči pravovremeni alert kada Fast Path već ima dovoljan kvalitet podataka.

## 61. Partial processing

Property/listing ne sme biti izgubljen zato što jedan downstream modul nije uspeo.

Primer:

```text
ingestion = SUCCESS
normalization = SUCCESS
matching = SUCCESS
LLM = FAILED
```

Listing i property ostaju sačuvani.

LLM/analysis dobija sopstveno failure stanje.

Kasniji retry nastavlja samo potrebni deo.

## 62. Failure isolation

Glavne failure granice:

```text
one listing failure
!=
whole batch failure

one source failure
!=
all sources failure

LLM failure
!=
ingestion failure

Telegram failure
!=
analysis failure

frontend failure
!=
background collection failure
```

Izuzetak su situacije gde centralna infrastruktura, kao što je baza, onemogućava bezbedno čuvanje rezultata.

Tada je bolje zaustaviti write nego izgubiti data integrity.

## 63. API sloj

FastAPI route treba da bude tanak.

Tipična odgovornost:

```text
validate request
↓
authorization/application checks
↓
call application service
↓
serialize response
```

API route ne treba direktno da:

* parsira HTML;
* računa valuation;
* računa Max Buy;
* implementira risk formulu;
* orkestrira veliki broj repository poziva.

## 64. Read i Write potrebe

Nije potreban CQRS framework.

Ali arhitektura može razlikovati:

```text
commands / write services
```

od:

```text
queries / read services
```

Kompleksan dashboard read može imati specijalizovan query service.

Nije potrebno forsirati svaki read kroz isti domain workflow koji se koristi za write operacije.

## 65. Frontend granica

Frontend koristi backend API kao source of truth za analytical rezultate.

Frontend ne implementira canonical business formule za:

* FMV;
* liquidity;
* risk gate;
* Max Buy;
* ROI;
* Opportunity Action.

Može računati trivijalne presentation vrednosti samo kada to ne može dovesti do business inconsistency.

## 66. External integrations

Svaka značajna spoljna integracija treba da bude izolovana iza malog client/adapter sloja.

Primer:

```text
TelegramClient
LLMClient
GeocodingClient
```

Business moduli ne treba širom codebase-a direktno da koriste provider-specific SDK.

Cilj nije generički integration framework, već mala kontrolisana granica.

## 67. Data provenance

Za decision-relevant podatke mora biti moguće utvrditi njihovo poreklo.

Primer:

```text
registered = true
source = listing claim
```

ili:

```text
location
source = manual correction
```

ili:

```text
seller motivation
source = LLM analysis v3
```

Konkretan persistence model provenance-a definiše Data Model Specification.

## 68. Historical deletion semantics

Nestanak listing-a sa source-a nije database delete događaj.

Konceptualno:

```text
source listing disappears
↓
lifecycle/history state changes
```

ne:

```text
DELETE listing
```

Property takođe ne nestaje zato što trenutno nema aktivan listing.

Source koji se više ne koristi treba moći da bude deaktiviran bez gubitka istorijskih podataka.

## 69. Reprocessing

Arhitektura mora dozvoliti naknadno ponovno procesiranje istorijskih inputa.

Primer:

```text
better parser
↓
historical raw input
↓
new normalized result
```

ili:

```text
new valuation version
↓
selected historical/current property snapshot
↓
new analysis
```

Nova obrada ne treba automatski da fizički zameni stari analytical rezultat ako je istorija potrebna za explainability ili backtesting.

## 70. Manual re-analysis

Korisnik ili maintenance workflow treba kasnije da može eksplicitno da zatraži:

```text
reanalyze property
```

To znači:

> ponovo izračunaj relevantne derived rezultate.

Ne znači:

> izbriši staru istoriju i pravi se da prethodna analiza nije postojala.

## 71. Historical analysis i backtesting

Current-state application code ne sme arhitektonski onemogućiti istorijsku rekonstrukciju.

Kasniji backtesting treba da ima način da analizira:

```text
data available as of T
```

umesto da implicitno koristi današnje stanje baze.

Detaljna pravila look-ahead zaštite i analytical backtesting-a pripadaju Analysis i Testing specifikacijama.

## 72. Health granice

Sistem treba konceptualno da razlikuje:

```text
Application Health
Database Health
Source Health
Analysis Health
Notification Health
```

Primer:

```text
API = healthy
database = healthy
source A = failing
source B = healthy
Telegram = degraded
```

nije isto kao:

```text
whole system = DOWN
```

Detaljni monitoring i alerting pripadaju Deployment/Operations specifikaciji.

## 73. Observability

Početna arhitektura treba da bude dovoljno observable kroz jednostavne mehanizme:

* strukturisane logove;
* job/source state;
* failure status;
* osnovne health informacije.

Background log treba, kada postoji, da omogući povezivanje sa relevantnim identitetom:

```text
job
source
external_listing_id
listing_id
property_id
```

Ne uvoditi observability platformu unapred ako obični logovi i stanje u bazi rešavaju trenutni problem.

## 74. Configuration

Konfiguracija treba da bude centralizovana kroz projektni settings sistem.

Kategorije mogu uključivati:

```text
database
environment
source configuration
scheduling
external providers
Telegram
investment defaults
feature flags
```

Secrets dolaze iz environment variables.

Portal-specific config treba da ostane povezan sa source slojem umesto da bude rasut kroz application kod.

## 75. Feature flags

Koristiti feature flag samo kada postoji realna potreba da se funkcionalnost kontrolisano uključi ili isključi.

Primeri kasnijih potreba mogu biti:

```text
ENABLE_LLM_ANALYSIS
ENABLE_TELEGRAM_ALERTS
```

Ne uvoditi generičku feature-management platformu.

Ako funkcionalnost još nije implementirana, često je bolje jednostavno je ne imati nego praviti placeholder iza flag-a.

## 76. Environment granica

Minimalno razlikovati:

```text
development
test
production
```

Arhitektura mora omogućiti da:

* test koristi izolovane dependency-je;
* production koristi persistent podatke;
* development ne utiče na production state.

Konkretne env varijable i runtime procedure pripadaju Deployment Specification-u.

## 77. Security granica

Pošto je sistem privatni single-user alat, V1 ne zahteva kompleksan authorization model.

Ipak:

> production API/dashboard ne sme biti javno otvoren bez zaštite.

Ne graditi bez potrebe:

* javnu registraciju;
* role matrix;
* multi-tenant auth;
* OAuth ekosistem.

Tačan production access model pripada Deployment/Operations specifikaciji.

## 78. PostGIS

PostGIS je deo canonical persistence tehnologije i koristi se kada postoje geografski upiti poput:

* distance;
* radius;
* spatial filtering;
* geo candidate generation;
* map/query potrebe.

Ne implementirati masovne spatial operacije ručno u Python-u kada PostgreSQL/PostGIS već rešava problem pouzdano.

## 79. `pgvector`

`pgvector` nije početni dependency.

Može se razmotriti tek ako stvarna funkcionalnost zahteva embeddings, npr:

* semantic description similarity;
* napredni duplicate matching.

Do tada ga ne uvoditi samo zbog potencijalne buduće AI funkcionalnosti.

## 80. Image storage

Početna arhitektura ne zahteva lokalno trajno skladištenje svih source fotografija.

Kada je dovoljno, mogu se čuvati stvari poput:

```text
source image URL
order/index
derived hash
metadata
```

Ako kasnije postoji realna potreba za trajnim image storage-om, može se uvesti odgovarajući object storage.

Ne uvoditi ga unapred.

## 81. Skaliranje

Sistem ne treba unapred projektovati kao distributed platform.

Prvi koraci skaliranja treba da budu:

1. identifikovati stvarni bottleneck;
2. optimizovati query/index;
3. smanjiti nepotrebnu obradu;
4. batch-ovati gde ima smisla;
5. kontrolisati concurrency;
6. odvojiti runtime proces koji stvarno pravi problem.

Tek zatim razmatrati dodatnu infrastrukturu.

## 82. Horizontalno skaliranje source processing-a

Source adapteri treba da ostanu dovoljno izolovani da kasnije različiti workers mogu obrađivati različite source-ove.

Konceptualno je moguće:

```text
worker A
→ source 1

worker B
→ source 2

browser worker
→ browser-required source
```

ali svi i dalje koriste isti canonical domain/data sistem.

Ne implementirati distributed source scheduling dok jedan ili mali broj procesa zadovoljava stvarni workload.

## 83. Queue evolution

Početni background model ne zahteva Redis/Celery.

Queue infrastruktura postaje kandidat kada postoje stvarni problemi kao što su:

* veći concurrent workload;
* veliki persistent backlog;
* više worker servera;
* priority queues;
* kompleksniji retry requirements;
* trenutni database coordination više nije dovoljno pouzdan ili jednostavan.

Tada se može uvesti queue iza postojećih application/job granica bez rewrite-a business modula.

## 84. Property-type evolucija

Zajednički delovi sistema mogu podržavati različite property type-ove tamo gde semantika zaista jeste ista:

```text
source ingestion
history
basic matching infrastructure
common identity
manual feedback
```

Ali specifična analiza ne treba da se prisilno deli.

Na primer budući:

```text
APARTMENT
→ apartment valuation pipeline

LAND
→ land valuation pipeline
```

Ne praviti veliki broj:

```python
if property_type == ...
```

grana kroz postojeće apartment funkcije kada drugi analytical domain stvarno postane podržan.

Ali takođe ne praviti apstraktni property-type plugin framework pre nego što drugi pravi pipeline postoji.

## 85. End-to-end tok

Kompletan konceptualni sistemski tok:

```text
EXTERNAL SOURCE
      ↓
SOURCE ADAPTER
      ↓
RAW LISTING DATA
      ↓
INGESTION
      ↓
NORMALIZATION
      ↓
CHANGE / HISTORY
      ↓
LISTING
      ↓
PROPERTY MATCHING
      ↓
CANONICAL PROPERTY
      ↓
LOCATION + FEATURES
      ↓
COMPARABLES
      ↓
VALUATION
      ↓
LIQUIDITY / FAST-SALE INPUTS
      ↓
SELLER / TEXT ANALYSIS
      ↓
RISK
      ↓
DEAL ENGINE
      ↓
OPPORTUNITY
      ↓
RECOMMENDED ACTION
      ↓
ALERT / DASHBOARD
      ↓
HUMAN FEEDBACK
      ↓
REANALYSIS / HISTORICAL OUTCOME
```

Nisu svi koraci implementirani od početka.

`docs/07-phase-plan.md` određuje kada se svaki deo uvodi.

## 86. Dependency cilj

Arhitektura treba da obezbedi sledeću vrstu nezavisnosti:

```text
source HTML changes
→ source adapter changes
→ valuation remains unchanged
```

```text
valuation algorithm changes
→ source scraping remains unchanged
```

```text
Telegram unavailable
→ listing history remains intact
```

```text
frontend redesigned
→ financial formulas remain unchanged
```

```text
new analytical version
→ historical source observations remain intact
```

To je potreban nivo modularnosti.

Nije cilj da svaki modul bude zaseban servis.

## 87. Canonical ownership drugih dokumenata

Za konkretne odluke koristiti:

```text
Product behavior
→ docs/01-product-specification.md

Database model and invariants
→ docs/03-data-model.md

Scraping algorithms and source behavior
→ docs/04-scraping-specification.md

Valuation / liquidity / risk / deal logic
→ docs/05-analysis-specification.md

API and frontend contracts
→ docs/06-api-ui-specification.md

Implementation order
→ docs/07-phase-plan.md

Testing
→ docs/08-testing-specification.md

Deployment / backups / runtime operations
→ docs/09-deployment-operations.md
```

Ovaj dokument ne treba da kopira njihove detalje.

## 88. Konačni arhitektonski princip

Glavni odnos sistema je:

```text
SOURCES
↓
TRUSTWORTHY HISTORICAL DATA
↓
ANALYSIS
↓
DECISION SUPPORT
```

Svaki sloj treba da može da evoluira bez nepotrebnog rewrite-a ostalih slojeva.

Ali tu fleksibilnost treba postići:

* jasnim odgovornostima;
* malim interface granicama;
* očuvanjem podataka;
* eksplicitnim application workflow-ima;

a ne preranim framework-ovima i distribuiranom infrastrukturom.

Kada postoje dve validne arhitekture, koristiti:

> **najjednostavniju koja pouzdano rešava trenutni problem i ne ugrožava istorijske podatke.**
