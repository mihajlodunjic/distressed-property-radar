
# Distressed Property Radar — Scraping Specification

## 1. Svrha dokumenta

Ovaj dokument definiše kako Distressed Property Radar prikuplja, osvežava i prati podatke sa eksternih listing source-ova.

Source of truth je za:

- source adapter ponašanje;
- discovery novih listing-a;
- active market scan;
- detail fetch;
- incremental crawling;
- change detection;
- listing lifecycle observation;
- removal i reappearance;
- pagination i filtere;
- rate limiting i retry;
- HTTP/browser granicu;
- adaptive polling;
- source health;
- raw payload i parser reprocessing;
- scraper failure isolation.

Ne definiše:

- database model;
- property matching algoritam;
- valuation, liquidity, risk ili deal formule;
- API/UI;
- deployment;
- kompletan test matrix;
- implementation order.

Za te oblasti koristiti njihove canonical dokumente.


# 2. Osnovni cilj

Scraping sistem mora istovremeno da obezbedi:

1. dovoljno brzo otkrivanje novih listing-a;
2. pouzdanu istoriju postojećih listing-a;
3. razuman broj requestova;
4. zaštitu od pogrešnih zaključaka kada source ili parser ne rade.

Scraping nije samo:

> pronađi nove oglase.

Mora takođe pratiti:

- `first_seen`;
- `last_seen`;
- cenu;
- naslov;
- opis;
- seller/agency;
- disappearance;
- reappearance.


# 3. Incremental Crawling

Default nije:

```text
periodic job
→ fetch every known detail page
→ parse everything again
````

Koristiti:

```text
listing/search pages
→ parse cards
→ compare lightweight state
→ detail fetch only when justified
```

Glavni princip:

```text
NEW
→ detail if needed
→ persist

CHANGED
→ detail if needed
→ diff
→ persist event

UNCHANGED
→ refresh observation state
→ stop
```

Detail fetch svih known listing-a nije standardni crawl režim.

# 4. Tri scraping režima

Gde source to podržava, razlikovati:

```text
FAST_DISCOVERY
ACTIVE_MARKET_SCAN
DEEP_RECONCILIATION
```

## `FAST_DISCOVERY`

Cilj:

> pronaći nove listing-e što pre.

## `ACTIVE_MARKET_SCAN`

Cilj:

> jeftino pratiti relevantne promene aktivnog tržišta.

## `DEEP_RECONCILIATION`

Cilj:

> periodično proveriti nepotpuna, neizvesna ili potencijalno zastarela stanja.

# 5. Fast Discovery

Ako source podržava pouzdano sortiranje po najnovijem, crawler proverava samo početni deo feed-a.

Primer poznatog vrha:

```text
9832
9831
9830
9829
```

Novi scan:

```text
9837 NEW
9836 NEW
9835 NEW
9834 NEW
9833 NEW
9832 KNOWN
9831 KNOWN
```

Novi listing-i se obrađuju.

Crawler ne nastavlja do poslednje stranice ako je dovoljno pouzdano stigao do poznatog dela feed-a.

# 6. Discovery Boundary

Ne zaustavljati discovery na prvom poznatom listing-u.

Portal može imati:

* sponsored listing-e;
* pinned listing-e;
* stare listing-e među novima;
* nestabilan sort;
* reorder između requestova.

Source konfiguracija treba da podrži granicu poput:

```text
known_listing_stop_threshold
```

Primer:

```text
10 consecutive known listings
```

Tačna vrednost je source-specific.

# 7. Nepouzdan `newest` sort

Ako source navodno sortira po najnovijem, ali se pokaže da redosled nije pouzdan, source može imati:

```text
supports_reliable_newest_sort = false
```

Tada:

* koristiti veći discovery window;
* ne koristiti agresivan early stop;
* osloniti se više na periodic market scan/reconciliation.

# 8. Discovery interval

Interval je konfigurabilan po source-u.

Početne smernice mogu biti:

```text
FAST:   2–5 min
NORMAL: 5–15 min
SLOW:   15+ min
```

To nisu univerzalne obavezne vrednosti.

Interval zavisi od:

* market activity-ja;
* source stabilnosti;
* rate limits;
* troška requestova;
* vrednosti nižeg latency-ja.

# 9. Active Market Scan

Active Market Scan koristi lightweight listing/card podatke gde god je moguće.

Primarno otkriva:

* price changes;
* nove listing ID-eve;
* relevantne card promene;
* listing-e koji više nisu viđeni.

Ako search page već daje:

```text
external_listing_id
price
title
location
basic attributes
```

nije potreban detail fetch za svaki listing.

# 10. Detail Fetch

Detail page se fetchuje kada postoji konkretan razlog.

Minimalni razlozi:

```text
NEW listing
material card change
missing required initial data
explicit manual refresh
reconciliation verification
priority refresh when card data is insufficient
```

Ne raditi detail fetch samo zato što je listing još aktivan.

# 11. Unchanged Listing

Ako je listing pouzdano viđen i relevantni card state je nepromenjen:

```text
update last_seen / observation metadata
do not create business event
do not fetch detail unless independently required
do not trigger unnecessary downstream analysis
```

# 12. Deep Reconciliation

Deep Reconciliation je sporiji periodični proces.

Koristi se za:

* proveru `NOT_SEEN` listing-a;
* potvrdu removal-a;
* missed listing-e;
* nepotpune podatke;
* source recovery;
* reconciliation posle downtime-a;
* sumnjive lifecycle state-ove;
* povremene detail provere gde je potrebno.

Ne koristiti ga kao zamenu za Fast Discovery.

# 13. Listing Lifecycle

Canonical lifecycle:

```text
ACTIVE
↓
not observed
↓
NOT_SEEN
↓
removal confirmation
↓
REMOVED
```

Ako se isti source listing ponovo pojavi:

```text
NOT_SEEN / REMOVED
↓
REAPPEARED
↓
ACTIVE
```

Jedan missed observation nije dovoljan za `REMOVED`.

# 14. `NOT_SEEN`

Listing može privremeno nestati iz rezultata zbog:

* source error-a;
* parser error-a;
* partial scan-a;
* pagination promene;
* sort/reorder promene;
* rate limit-a;
* filter problema;
* stvarnog removal-a.

Zato:

```text
not seen once
!=
removed
```

# 15. Scan Completeness

Market scan mora razlikovati:

```text
COMPLETE
PARTIAL
FAILED
```

Primer:

```text
expected ~100 pages
processed 20
request failed
```

je:

```text
PARTIAL
```

Listing-i sa neobrađenih strana ne smeju biti tretirani kao missing.

# 16. Removal Confirmation

Svaki source ima eksplicitnu removal policy.

Primer:

```text
not seen in 2 COMPLETE scans
AND
detail page confirms inactive
```

ili:

```text
not seen longer than configured grace period
```

Tačno pravilo je source-specific.

`404`/`410` na detail URL-u može biti signal, ali ne mora biti dovoljan sam po sebi.

# 17. Confirmed Removal

Kada je removal dovoljno pouzdano potvrđen:

```text
status = REMOVED
removed_at = ...
```

i kreira se odgovarajući historical event.

Listing se ne briše.

# 18. Reappearance

Ako isti `(source_id, external_listing_id)` ponovo postane prisutan:

```text
status = ACTIVE
```

i kreira se:

```text
REAPPEARED
```

event.

Prethodna istorija ostaje sačuvana.

# 19. Relisting

Novi `external_listing_id` ne znači automatski novi fizički property.

Scraping sloj radi:

```text
discover new listing
→ normalize/persist
→ property matching
```

Matching sloj odlučuje da li listing pripada postojećem property-ju.

Scraper ne rešava property identity.

# 20. Source Adapter

Svaki source ima izolovan adapter.

Primer:

```text
sources/
  portal_x/
    adapter.py
    parser.py
```

Adapter zna:

* URL strukturu;
* query parametre;
* pagination;
* sort;
* filtere;
* listing-page fetch;
* detail fetch;
* source-specific parsing;
* external listing ID;
* canonical URL pravila.

Ne mora svaki source imati identičnu internu strukturu ako nema potrebe.

# 21. Source Adapter ne radi business analysis

Adapter ne sme:

* računati FMV;
* birati comparables;
* raditi property matching;
* računati Max Buy;
* određivati Opportunity Score;
* odlučivati Telegram alert.

Njegov output je source data.

# 22. Adapter Contract

Konceptualno adapter može izlagati:

```python
class ListingSourceAdapter:
    async def discover_latest(...):
        ...

    async def scan_market(...):
        ...

    async def fetch_detail(...):
        ...
```

Exact method signatures mogu biti source/application-specific.

Bitna granica je:

```text
source-specific representation
→ standardized raw DTO
```

# 23. `RawListingCard`

Minimalni raw card DTO:

```text
external_listing_id
url

title_raw
price_raw
location_raw
size_raw

source_published_at_raw

additional_card_data
```

Osim identiteta, polja mogu biti `null`.

# 24. `RawListingDetail`

Predviđeni raw detail DTO:

```text
external_listing_id
url

title_raw
description_raw

price_raw
currency_raw

size_raw
location_raw

rooms_raw
floor_raw

seller_raw
agency_raw

property_attributes_raw

image_urls

source_published_at_raw

raw_payload_reference
```

Ne zahtevati da svaki source podržava svako polje.

# 25. Raw DTO nije Domain Model

Adapter treba da očuva source značenje.

Primer:

```text
floor_raw = "III/5"
```

Normalizer može kasnije dobiti:

```text
floor = 3
total_floors = 5
```

Ne ugrađivati svu shared normalization logiku u svaki parser.

# 26. External Listing ID

Preferirati stabilan ID samog source-a.

Primer:

```text
/oglas/123456
```

→

```text
external_listing_id = "123456"
```

Canonical listing identity:

```text
(source_id, external_listing_id)
```

# 27. Source bez stabilnog ID-a

Ako source nema stabilan external ID, adapter mora imati dokumentovanu determinističku alternativu.

Ne koristiti samo:

```text
title
price
title + price
phone
```

jer se ti podaci mogu promeniti.

# 28. Canonical URL

Adapter treba da ukloni tracking/query noise kada je moguće.

Na primer:

```text
utm_source
tracking_token
page_ref
```

ne smeju sami napraviti drugi listing.

Originalni URL može ostati sačuvan odvojeno.

# 29. Duplicate Cards

Source može prikazati isti listing više puta:

* sponsored;
* pinned;
* regular result;
* više sekcija iste strane.

Unutar jednog batch-a deduplicirati po canonical source listing identity-ju pre ingestion-a.

# 30. HTTP pre Browsera

Za source prvo proveriti da li se potrebni podaci mogu dobiti preko:

* server-rendered HTML-a;
* JSON-a;
* endpoint-a koji sama stranica koristi.

Ako mogu, koristiti HTTP.

Playwright nije default.

# 31. HTTP Client

Preferirati shared:

```text
httpx.AsyncClient
```

po worker/source kontekstu sa:

* connection pooling;
* timeout-ima;
* controlled concurrency;
* potrebnim legitimnim headers-ima.

Ne kreirati novi client za svaki request.

# 32. Timeout

Svaki source treba da ima konfigurabilne:

```text
connect timeout
read timeout
request/total timeout
```

Request ne sme beskonačno blokirati worker.

# 33. Concurrency

Source mora imati:

```text
max_concurrency
```

Početna konzervativna smernica:

```text
2–5
```

paralelnih requestova po source-u.

Povećavati tek kada postoji stvarna potreba i source to pouzdano podnosi.

# 34. Rate Limiting

Podržati source-level:

```text
minimum_delay_between_requests
```

ili ekvivalentan rate limiter.

Ne optimizovati za maksimalan request throughput.

Cilj je stabilan i dovoljno brz ingestion.

# 35. Jitter

Mali random scheduling jitter je dozvoljen da više source job-ova ne udara istovremeno.

Jitter ne sme značajno pokvariti discovery latency.

# 36. Retry

Retry koristiti za verovatno privremene probleme:

```text
network error
timeout
temporary DNS issue
selected 5xx
429
```

Početna smernica:

```text
2–3 attempts
```

sa bounded/exponential backoff-om.

Tačne vrednosti su konfigurabilne.

# 37. Ne retry-ovati Parser Failure kao Network Failure

Ako response uspe, ali parser više ne nalazi očekivani sadržaj:

```text
missing selector
missing listing container
HTML structure changed
```

klasifikovati parser/source problem.

Ne ponavljati request mnogo puta očekujući da će isti HTML rešiti parser kvar.

# 38. HTTP Status Handling

Minimalno razlikovati:

```text
2xx
3xx
404/410
429
other 4xx
5xx
```

## `429`

Tretirati kao rate-limit signal:

* backoff;
* smanjenje request rate-a;
* health degradation ako se ponavlja.

Ne koristiti agresivne bypass mehanizme.

# 39. Error Classification

Minimalne kategorije:

```text
NETWORK_ERROR
TIMEOUT
RATE_LIMIT
HTTP_CLIENT_ERROR
HTTP_SERVER_ERROR
PARSE_ERROR
SOURCE_STRUCTURE_CHANGED
INVALID_CONTENT
BROWSER_ERROR
UNKNOWN_ERROR
```

Klasifikacija treba da omogući razlikovanje:

```text
temporary failure
```

od:

```text
source/parser fundamentally broken
```

# 40. Browser Scraping

Playwright koristiti samo kada HTTP ne može pouzdano dobiti required podatke.

Browser scraping ostaje source-specific.

Ne uvoditi generic browser fallback za svaki HTTP problem.

# 41. Infinite Scroll

Ako source koristi infinite scroll:

1. proveriti network requests;
2. pronaći strukturirani endpoint ako postoji;
3. koristiti HTTP kada je pouzdano moguće;
4. koristiti Playwright ako nema odgovarajućeg HTTP pristupa.

# 42. Browser Concurrency

Browser workload treba da bude ograničen.

Početna smernica:

```text
2–5 concurrent pages/contexts
```

Ne pokretati novi browser binary po listing-u.

# 43. Browser Resource Blocking

Ako ne utiče na funkcionalnost, mogu se blokirati nepotrebni:

* video;
* fonts;
* analytics;
* veliki dekorativni resursi.

Ne blokirati ono što je potrebno za extraction ili rad stranice.

# 44. Browser Fallback

Zabranjen generic pattern:

```text
HTTP request failed
→ launch Playwright
```

za svaki failure.

Browser fallback mora biti eksplicitno dozvoljen za konkretan source/use case.

# 45. Pagination

Adapter mora znati source-specific:

```text
page numbering
page size
next page behavior
last page detection
sort behavior
```

Ne pretpostavljati `?page=2`.

# 46. Filters

Koristiti source filtere kada smanjuju nepotreban workload.

Za trenutni scope to može biti:

```text
city = Beograd
property_type = apartment
transaction_type = sale
```

Ne crawl-ovati celu nacionalnu bazu ako trenutni proizvod koristi manji market.

# 47. Filter Config

Market scope ne hardkodovati u HTML parser.

Adapter/query config može sadržati:

```text
city
municipality
property_type
min_size
max_size
```

Product/Phase dokument određuje current scope.

# 48. Više Query Kombinacija

Ako jedan query ne pokriva target market:

```text
query 1 → Novi Beograd
query 2 → Zemun
```

svaki query može imati sopstveni crawl state gde je potrebno.

# 49. Crawl Cursor

Optional source/query state:

```text
last_successful_page
last_known_top_listing_id
last_scan_at
```

Cursor je optimizacija.

Ne sme trajno sprečiti ponovno otkrivanje listing-a zbog reorder-a, sponsored rezultata ili relisting-a.

# 50. Card State Hash

Za lightweight comparison napraviti stabilan representation od relevantnih card polja.

Primer:

```text
external_listing_id
normalized price
normalized title
relevant card status
```

Od toga može nastati:

```text
card_state_hash
```

# 51. Ne uključivati Volatile Noise u Hash

Ne uključivati bez razloga:

```text
view count
page order
random token
render timestamp
advertisement marker
```

Jer bi tada svaki crawl izgledao kao business change.

# 52. Detail State Hash

Relevantni detail state može uključiti:

```text
title
description
price
size
rooms
floor
seller/agency
important attributes
```

Whitespace-only text promene ne treba tretirati kao semantic description change.

# 53. Field-Level Diff

Hash mismatch znači:

> proveri stvarnu razliku.

Ne znači automatski:

> napravi generic change event.

Primer:

```text
PRICE
175000 → 159000

DESCRIPTION
changed

AGENCY
unchanged
```

Kreirati samo event-e koji odgovaraju stvarnim promenama.

# 54. Price Change

`PRICE_CHANGED` nastaje kada se canonical parsed cena stvarno promeni.

Primer:

```text
180000 → 170000
```

produkuje jedan event.

Ponovna obrada `170000` ne proizvodi novi event.

# 55. Invalid / Non-Numeric Price

Source može prikazati:

```text
"dogovor"
"na upit"
"1 €"
```

Raw vrednost ostaje sačuvana.

Normalizer odlučuje da li postoji validna numeric cena.

Posebno:

```text
"dogovor"
```

ne sme postati:

```text
0
```

# 56. Currency

Adapter izdvaja raw currency kada postoji.

Normalizer je mapira u canonical currency kao što su:

```text
EUR
RSD
```

Ako source ima nedvosmislen source-wide currency rule, može se dokumentovano koristiti.

Ne zaključivati currency iz magnitude cene.

# 57. Description

Originalni opis treba očuvati dovoljno verno za:

* history;
* diff;
* seller analysis;
* eventualnu LLM extraction.

Za comparison se može normalizovati:

* trim;
* newlines;
* redundant whitespace.

Ali semantic content ne sme nestati.

Promena:

```text
"cena nije fiksna"
```

u:

```text
"hitna prodaja"
```

mora biti vidljiva.

# 58. Seller Change

Relevantna seller/agency promena treba da bude detektabilna.

Primer:

```text
Agency A → Owner
```

Scraper beleži promenu.

Downstream analysis odlučuje šta ona znači.

# 59. Source Published Date

Source može prikazati:

```text
today
2 hours ago
12.08.2026
```

Čuvati raw representation kada je korisna.

`published_at` postaviti samo kada timestamp može dovoljno pouzdano da se izvede.

Ako ne:

```text
published_at = null
```

# 60. `first_seen_at`

`first_seen_at` je:

> trenutak kada je naš sistem prvi put pronašao listing.

Nije isto što i source publication date.

# 61. `last_seen_at`

`last_seen_at` ažurirati samo kada je listing zaista viđen tokom relevantnog uspešnog scan-a.

Ne ažurirati ga na osnovu failed ili nerelevantnog partial crawl-a.

# 62. Adaptive Polling

Known listing-i ne moraju svi imati isti refresh interval.

Minimalne klase:

```text
HIGH
NORMAL
LOW
```

Ovo je crawl priority, ne investment score.

## `HIGH`

Primeri:

* Watchlist;
* cena blizu target-a;
* veliki recent price cut;
* novi relevantan listing;
* current action `CALL` / `URGENT_CALL`.

Moguća smernica:

```text
15–30 min
```

## `NORMAL`

Običan relevantan active listing.

Smernica:

```text
3–6 h
```

## `LOW`

Primeri:

* daleko iznad target-a;
* veoma star bez promena;
* slab relevance;
* current action `IGNORE`.

Smernica:

```text
12–24 h
```

Intervali nisu hardcoded business pravila.

# 63. Discovery i Adaptive Polling su odvojeni

Čak i ako je većina starih listing-a `LOW`:

```text
Fast Discovery
```

može i dalje raditi često.

Razlikovati:

```text
find new
```

od:

```text
refresh known
```

# 64. Scheduling Metadata

Known-listing refresh može koristiti:

```text
crawl_priority
next_check_at
last_checked_at
```

Tačna job/query implementacija pripada application layer-u.

# 65. Crawl Priority Recalculation

Priority može biti promenjen posle:

* price change-a;
* Watch rule-a;
* Opportunity re-analysis;
* manual user action-a;
* dugog perioda bez promena.

Scraper ne duplira investment logic.

Dobija priority ili jednostavno crawl-policy stanje.

# 66. Batch Processing

Jedan malformed card ne sme oboriti ceo batch.

Primer:

```text
20 cards
19 valid
1 parse failure
```

19 validnih se procesira.

Failure se evidentira.

# 67. Required Fields

Minimalni validni card treba da ima dovoljno podataka za stabilan listing identity.

Preferirano:

```text
external_listing_id
url
```

Detail takođe mora imati identitet i dovoljno sadržaja da listing može smisleno biti sačuvan.

Ostala polja mogu biti `null`.

# 68. Partial Parse

Ako card ima validan ID i URL, ali nema cenu:

```text
do not automatically discard listing
```

Moguće je uraditi detail fetch.

Istovremeno parser health beleži abnormalni missing field.

# 69. Source Health

Minimalni statusi:

```text
HEALTHY
DEGRADED
FAILED
DISABLED
```

## `HEALTHY`

* crawl uspeva;
* ključni parse rate je normalan;
* nema abnormalnih HTTP grešaka;
* discovery vraća očekivane podatke.

## `DEGRADED`

Primer:

* veliki rast parse error-a;
* mnogo missing price vrednosti;
* timeout spike;
* deo query-ja više ne radi.

Bezbedan scraping može nastaviti.

## `FAILED`

Primer:

* source nedostupan;
* parser više ne može pouzdano da nađe listing;
* struktura se fundamentalno promenila;
* normalan access više ne daje pouzdano market stanje.

Kod `FAILED`:

```text
do not infer mass removals
```

## `DISABLED`

Ako je source deaktiviran, ne pokretati nove crawl job-ove.

Istorija ostaje.

# 70. Parser Health

Gde je praktično pratiti presence/success rate ključnih polja:

```text
external_listing_id
url
price
title
```

Primer:

```text
price parse rate:
96% → 18%
```

treba tretirati kao source/parser anomaly.

# 71. Zero-Result Anomaly

Ako source koji normalno ima mnogo listing-a vrati:

```text
0 cards
```

ne tretirati rezultat automatski kao prazno tržište.

Proveriti:

* response;
* parser;
* query;
* health;
* source structure.

Ne praviti removal odluke dok rezultat nije dovoljno pouzdan.

# 72. Parser Error Evidence

Kod parse greške zabeležiti najmanje:

```text
source
operation
url
external_listing_id if known
parser stage / field
error class
error message
timestamp
raw payload reference if available
```

Ne logovati kompletan ogroman HTML payload u standardni log.

# 73. Source Configuration

Source config može sadržati:

```text
enabled
base_url

discovery_interval
market_scan_interval
reconciliation_interval

known_listing_stop_threshold
supports_reliable_newest_sort

max_concurrency
min_request_delay
timeouts
retry_count

uses_browser
browser_fallback_enabled

removal_policy

market query/filter config
```

Ne moraju sva polja biti user-editable.

# 74. Raw Payload

Za novi ili značajno promenjen detail može se sačuvati raw HTML/JSON.

Minimalni metadata:

```text
content_hash
captured_at
content_type
```

Ne čuvati novu identičnu kopiju ako nije potrebna.

# 75. Raw Payload Retention

Raw HTML/JSON može imati ograničen retention.

Početna smernica:

```text
30–90 days
```

ili duže uz kompresiju ako storage to dozvoljava.

Canonical listing/history podaci ostaju dugoročno.

Production retention policy pripada Deployment/Operations dokumentu.

# 76. Parser Version

Source parser može imati semantic version oznaku, npr:

```text
portal_x_parser_v3
```

Povećati version kada se značajno promeni interpretacija source podataka.

Ne versionirati svaki minor refactor.

# 77. Reprocessing

Ako parser bude popravljen:

```text
historical raw payload
↓
new parser
↓
new normalized interpretation
```

treba ga moći ponovo obraditi bez live fetch-a dok raw payload postoji.

# 78. Source Change vs Parser Reinterpretation

Ako historical raw payload kaže:

```text
"5/8"
```

a stari parser nije pravilno izvukao podatak, novi parser može dobiti:

```text
floor = 5
total_floors = 8
```

To nije nova promena na source-u.

Ne kreirati lažni listing change event.

Razlikovati:

```text
SOURCE_CHANGE
```

od:

```text
PARSER_REINTERPRETATION
```

# 79. Full Detail Refresh

Kompletan refresh starih detail podataka može postojati kao maintenance job.

Razlozi:

* parser migration;
* incomplete historical data;
* source recovery;
* data-quality repair.

Ne koristiti ga kao čest standardni market scan.

# 80. Images

Scraper treba da izvuče image URL-ove gde su dostupni.

Za početak je dovoljno:

```text
source_url
position
```

Ne download-ovati automatski sve full-resolution slike.

# 81. Lazy Image Hashing

Ako property matching zahteva image similarity:

```text
matching uncertain
↓
download selected image(s)
↓
compute perceptual hash
```

Ne raditi image processing za svaki listing unapred.

Prvih nekoliko slika može biti dovoljno dok evaluacija ne pokaže drugačije.

# 82. Request Budget

Korisno je pratiti aggregate podatke:

```text
requests/hour
requests/day
detail_fetches/day
browser_pages/day
```

Ne treba persistent DB row po svakom uspešnom request-u.

Ovo može dolaziti iz job metrics/logova.

# 83. Full Market Scan Pacing

Veliki scan ne slati kao ogroman burst.

Umesto toga:

```text
progressive processing
+
source rate limit
```

Cilj je dovoljno čest i pouzdan scan, ne minimalno moguće vreme izvršavanja.

# 84. Credentials i Sessions

Ako source legitimno zahteva session/credential koji korisnik poseduje:

* koristiti config/secrets;
* ne hardkodovati credentials;
* ne commitovati cookies;
* ne commitovati token-e.

Persistent session je dozvoljen kada je prirodan deo legitimnog source access-a.

# 85. Access Restrictions

Ako source ograniči automated access:

1. smanjiti rate gde je potrebno;
2. poštovati `429`;
3. evidentirati degradation/failure;
4. zaustaviti agresivan retry;
5. zadržati druge source-ove funkcionalnim.

Ne implementirati samoinicijativno:

```text
CAPTCHA bypass
stealth/fingerprint evasion
mass proxy rotation for protection bypass
mass account rotation
```

# 86. Source Access Review

Za production source korisno je dokumentovati:

```text
source code
access method
automated-access review status
notes
```

Source mora moći brzo da se deaktivira bez gubitka istorije.

# 87. Failure Isolation

Obavezno:

```text
one listing failure
!=
batch failure
```

```text
one source failure
!=
all sources failure
```

```text
analysis failure
!=
ingestion failure
```

```text
Telegram failure
!=
scraping failure
```

Validno prikupljen listing treba sačuvati pre nego što eventualni downstream analytical problem može da ga izgubi.

# 88. Downstream Signals

Novi listing treba da proizvede jasan downstream signal.

Relevantne promene poput:

```text
PRICE_CHANGED
DESCRIPTION_CHANGED
SELLER_CHANGED
REAPPEARED
```

treba da mogu pokrenuti potrebnu re-analysis.

Scraper ne određuje investicionu važnost promene.

# 89. Job Metrics

Discovery/scan/reconciliation job treba da proizvede summary poput:

```text
source

started_at
finished_at

pages_requested

cards_seen
cards_parsed

new_listings
changed_listings

details_fetched

not_seen_count

parse_errors
http_errors

status
```

Ovo je dovoljan početni scraper observability.

# 90. Logging

Uspešan request ne treba da loguje kompletan sadržaj stranice.

Koristan log:

```text
source=portal_x
operation=detail_fetch
external_listing_id=123
status=success
duration_ms=...
```

Kod failure-a uključiti relevantne:

```text
source
operation
url
status_code
error_class
attempt
```

bez secrets.

# 91. Scraper Operational Alert

Scraper alert je različit od property opportunity alert-a.

Primer:

```text
SCRAPER WARNING

Portal X

Price parse success:
97% → 18%

Possible markup change.
```

Mogu koristiti isti notification provider, ali su različite kategorije.

# 92. Source Recovery

Nakon source/parser recovery-ja:

1. potvrditi health;
2. pokrenuti reconciliation ako je potreban;
3. ne pretpostavljati removal listing-a tokom downtime-a;
4. zadržati istorijski trag da observation period nije bio pouzdan.

# 93. Manual Listing Refresh

Kasniji admin workflow može podržati:

```text
refresh this listing
```

Tok:

```text
fetch current detail
→ parse
→ normalize
→ compare
→ persist only real source changes
→ trigger required downstream work
```

Manual refresh ne proizvodi event ako se source state nije stvarno promenio.

# 94. Manual Discovery

Za debugging može postojati:

```text
run discovery now
```

Ne graditi javni generic scraping console bez potrebe.

# 95. Testability Requirements

Detaljni scraper test matrix pripada `docs/08-testing-specification.md`.

Ovaj dokument zahteva da implementacija omogućava najmanje:

* parser test bez mreže;
* fixture-based card/detail parsing;
* discovery test sa mock HTTP response-ovima;
* idempotency test;
* price-change test;
* removal transition test;
* reappearance test;
* source failure test.

# 96. Parser Fixtures

Svaki production source treba da ima representative fixture-e.

Minimalno:

```text
listing/search page
listing detail page
```

Dodavati edge-case fixture-e kada se pojave.

Primeri:

```text
normal listing
missing price
owner listing
agency listing
inactive/removed representation
```

# 97. Idempotency Requirement

Isti source payload procesiran dva puta mora rezultovati:

```text
one listing
zero duplicate business events
```

Dozvoljen je update observation metadata poput `last_seen_at` kada je semantički opravdan.

# 98. Live Smoke Tests

Live source smoke test može biti:

* manual;
* scheduled;
* operational.

Unit/CI suite ne treba da zavisi od third-party portala.

# 99. Source Adapter Acceptance Criteria

Source je spreman kada current-scope funkcionalnost pouzdano pokriva najmanje:

1. stable listing identity;
2. discovery;
3. pagination;
4. detail fetch gde je potreban;
5. parsing ključnih dostupnih polja;
6. standardized raw DTO;
7. fixture-based parser tests;
8. configurable rate limit;
9. bounded retry;
10. parser error razlikuje se od empty result-a;
11. source health se može proceniti;
12. ingestion je idempotentan;
13. source failure je izolovan;
14. removal policy je eksplicitna;
15. historical listing data se ne briše.

# 100. V0 Scraping Scope

Prvi scraping V0 treba da bude mali:

```text
1 source
1 property type
1 target market
```

Minimalno:

```text
discovery
card parsing
detail fetch where needed
normalization handoff
listing persistence
price tracking
basic lifecycle
source health
```

# 101. Dodavanje novog Source-a

Drugi source se dodaje kroz novi:

```text
Source Adapter
```

Ne copy/paste-ovati kompletan:

```text
ingestion
normalization
matching
history
analysis
```

pipeline.

# 102. Šta V0 ne zahteva

Ne uvoditi unapred:

* proxies;
* distributed scraper workers;
* Redis;
* Celery;
* browser farm;
* download svih images;
* computer vision;
* veliki broj portala;
* sve gradove;
* Crnu Goru;
* auction scraping;
* real-time scraping dashboard.

# 103. Zabranjene prečice

Ne koristiti:

```text
all scraping → Playwright
```

ako HTTP radi.

Ne koristiti:

```text
full detail refresh of all listings every few minutes
```

bez potrebe.

Ne koristiti random `sleep()` svuda kao zamenu za pravi limiter.

Posebno ne koristiti:

```python
try:
    ...
except Exception:
    return []
```

ako bi parser failure tada izgledao kao empty market.

# 104. Ključne Scraping Invarijante

1. `(source_id, external_listing_id)` identifikuje listing kada source ima stabilan external ID.

2. Jedan failed crawl nije dokaz da je tržište prazno.

3. Jedan missed observation nije confirmed removal.

4. `REMOVED` nije `DELETE`.

5. Novi external listing ID nije automatski novi physical property.

6. Isti unchanged payload ne proizvodi duplicate business events.

7. Detail fetch se ne radi bez razloga kada card state već daje dovoljno pouzdan signal.

8. Parser failure se ne predstavlja kao validan zero-result market state.

9. Nepoznat source podatak ostaje `null`/UNKNOWN umesto izmišljene vrednosti.

10. Source failure je izolovan od drugih source-ova.

11. Downstream analysis/notification failure ne sme izgubiti validno prikupljen listing.

12. Parser reinterpretation nije source change.

13. `first_seen_at` nije `published_at`.

14. `last_seen_at` se ažurira samo na osnovu validnog observation-a.

15. Removal inference se ne radi iz `PARTIAL`/`FAILED` scan-a ako listing nije stvarno obuhvaćen.

# 105. End-to-End Flow

```text
SCHEDULE
↓
SOURCE QUERY
↓
FETCH LISTING PAGE
↓
PARSE CARDS
↓
VALIDATE IDENTITY
↓
DEDUPLICATE
↓
COMPARE WITH KNOWN STATE
↓

┌─────────────┬─────────────┬─────────────┐
│ NEW         │ CHANGED     │ UNCHANGED   │
│             │             │             │
▼             ▼             ▼
DETAIL?       DETAIL?       UPDATE
│             │             LAST_SEEN
▼             ▼             │
NORMALIZE     NORMALIZE     STOP
│             │
▼             ▼
PERSIST       FIELD DIFF
│             │
│             ▼
│             EVENTS
│             │
└───────┬─────┘
        ▼
DOWNSTREAM SIGNAL
```

Odvojeno:

```text
DEEP RECONCILIATION
↓
check NOT_SEEN / incomplete states
↓
confirm removal or reappearance where justified
↓
repair state
```

# 106. Canonical Ownership

Database persistence i field definitions:

```text
docs/03-data-model.md
```

Property matching, valuation i ostala analiza:

```text
docs/05-analysis-specification.md
```

API/UI behavior:

```text
docs/06-api-ui-specification.md
```

Detailed tests:

```text
docs/08-testing-specification.md
```

Production scheduling, monitoring, recovery i deployment:

```text
docs/09-deployment-operations.md
```

Ovaj dokument poseduje:

> način na koji se external listing source pouzdano pretvara u incremental historical market data.

# 107. Konačni princip

Scraping sistem ne optimizuje za:

> što veći broj requestova.

Optimizuje za:

```text
FAST ENOUGH DISCOVERY
+
CHEAP MARKET REFRESH
+
CORRECT CHANGE DETECTION
+
CONSERVATIVE REMOVAL
+
SOURCE FAILURE ISOLATION
+
HISTORICAL PRESERVATION
```

Najvažnije pravilo:

> **Privremeni source, network ili parser problem nikada ne sme da izgleda kao stvarna tržišna promena i time pokvari istorijske podatke.**

