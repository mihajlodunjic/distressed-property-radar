# Distressed Property Radar — API & UI Specification

## 1. Svrha dokumenta

Ovaj dokument definiše kako korisnik pristupa Distressed Property Radar sistemu i kako frontend komunicira sa backendom.

Source of truth je za:

- glavne frontend ekrane;
- korisničke tokove;
- API granice;
- response modele;
- filtering, sorting i pagination;
- Action Queue;
- Property Detail;
- Watchlist;
- acquisition pipeline i feedback;
- manual scenario/override interakcije;
- Source Health;
- partial-analysis UI;
- minimalnu autentikaciju privatnog alata.

Ne definiše:

- SQL šemu;
- scraping implementaciju;
- analytical formule;
- deployment;
- detaljan test matrix;
- implementation order.

Za te oblasti koristiti odgovarajuće canonical dokumente.

# 2. Osnovni UX princip

Frontend je interni decision-support alat.

Primarni zadatak:

> **u nekoliko sekundi pokazati šta zahteva pažnju, zašto i šta korisnik može sledeće da uradi.**

Prioritet:

    actionability
    >
    clarity
    >
    useful data density
    >
    speed
    >
    visual polish

Ne dodavati dekorativne elemente koji otežavaju brzo čitanje tržišnih i finansijskih podataka.

# 3. Desktop i Mobile

Primarni workflow je desktop.

Desktop prioriteti:

- tabele;
- filtering/sorting;
- comps;
- price history;
- deal calculator;
- detaljna analiza.

Mobile mora dovoljno dobro podržati:

- otvaranje Telegram alerta;
- ključni property summary;
- Recommended Action;
- Asking / Max Buy / Profit / Risk;
- Watch/Review/Skip;
- logovanje poziva;
- promenu pipeline statusa.

Telegram ostaje primarni real-time alert kanal.

# 4. Glavna navigacija

Ciljna navigacija:

    Action Queue
    Properties
    Watchlist
    Pipeline
    Map
    Sources
    Analytics
    Settings

Ne implementirati sve unapred.

`docs/07-phase-plan.md` određuje kada ekran ulazi u scope.

# 5. Action Queue

Action Queue je početni operativni ekran.

Odgovara na pitanje:

> **Šta treba da uradim sada?**

Glavne grupe:

    URGENT_CALL
    CALL
    REVIEW
    WATCH

`IGNORE` se po default-u ne prikazuje u glavnom queue-u.

Ako nema qualifying kandidata, prazan queue je validan rezultat.

# 6. Action Queue Summary

Na vrhu je dozvoljen kompaktan summary:

    URGENT CALL     2
    CALL            5
    REVIEW         12
    WATCH          38

Dodatno, kada je korisno:

- new since last visit;
- price changes;
- source warnings.

Ne praviti dashboard prepun vanity metrics.

# 7. Action Queue Table

Minimalne korisne kolone:

    Action
    Location
    Property
    Asking
    FMV
    Fast Sale
    Max Buy
    Expected Profit
    Downside
    Liquidity
    Confidence
    Market Age
    Last Change

Primer reda:

    URGENT
    Blok 45
    72 m² / 3.0 / 5/8
    €134k
    €171k–182k
    €165k
    €138.5k
    €19k
    +€5k
    87
    81
    21d
    Price -7.6%

Frontend ne računa ove canonical analytical vrednosti.

Dobija ih od backend-a.

# 8. Action Queue Sorting

Default:

    recommended_action priority
    ↓
    ranking_value
    ↓
    most recent important change

Korisnik može sortirati po relevantnim dostupnim poljima, npr:

- Expected Profit;
- ROI;
- Profit / Capital-Day;
- Max Buy Gap;
- Liquidity;
- Confidence;
- Market Age;
- Newest Listing;
- Largest Price Cut.

Backend whitelist-uje dozvoljena sort polja.

# 9. Action Queue Filters

Po potrebi podržati:

- Action;
- City;
- Municipality;
- Micro-location;
- Property Type;
- Price Range;
- Size Range;
- Expected Profit;
- Liquidity;
- Confidence;
- Risk Gate;
- Seller Type;
- Source;
- Market Age.

Filter state po mogućnosti čuvati u URL query parametrima kada to poboljšava navigation/back behavior.

# 10. Quick Actions

Iz liste treba omogućiti najčešće akcije bez obaveznog otvaranja Property Detail-a:

- Open;
- Watch / Unwatch;
- Mark Reviewed;
- Log Call;
- Skip.

Ne tražiti confirmation za trivijalne reverzibilne akcije.

# 11. Property Detail

Property Detail je centralni ekran dubinske analize.

Preporučene sekcije:

    1. Header / Key Decision
    2. Deal Summary
    3. Price & Listing History
    4. Property Data
    5. Listings / Sources
    6. Comparables
    7. Valuation
    8. Liquidity
    9. Seller Intelligence
    10. Risk
    11. Deal Calculator
    12. Activity / Pipeline
    13. Notes / Manual Data

Sekcija se prikazuje samo ako odgovarajuća backend funkcionalnost postoji.

# 12. Property Header

Odmah prikazati:

    Location
    Property basics
    Recommended Action
    Asking
    Max Buy
    Expected Profit
    Downside
    Risk Gate
    Confidence

Primer:

    Novi Beograd · Blok 45
    72 m² · 3.0 · 5/8 · lift

    URGENT CALL

    Asking:      €134,000
    Max Buy:     €138,500
    Base Profit: €19,000
    Downside:    +€5,000

    Risk: VERIFY
    Confidence: 81

# 13. Decision Reasons

Recommended Action mora odmah imati najvažnije reason codes/faktore.

Primer:

    + Asking below Max Buy
    + High liquidity
    + Recent 12% price cut
    + High seller motivation
    - Ownership not verified

Korisnik ne treba da prolazi kroz više sekcija samo da bi saznao zašto je property rangiran visoko.

# 14. Deal Summary

Prikazati dostupne:

    Asking
    Assumed Purchase Price
    FMV Low / Base / High
    Fast-Sale Low / Base / High
    Max Buy
    Total Cost Basis
    Expected Profit
    Downside Profit
    ROI
    Annualized ROI
    Holding Days
    Profit / Capital-Day

Ako rezultat nije poznat, prikazati:

    UNKNOWN

ili:

    Not calculated

Ne prikazivati `€0` kada podatak zapravo nije poznat.

# 15. Price & Listing History

Price history treba da pokaže relevantan timeline.

Primer:

    Aug 02   €165k
    Aug 11   €159k
    Aug 19   €149k
    Aug 25   €134k

Uz njega mogu stajati:

- total price drop;
- largest price drop;
- number of cuts;
- days since last cut.

Listing history treba da prikaže decision-relevant događaje, npr:

- listing discovered;
- price changed;
- seller/agency changed;
- description changed;
- listing removed;
- listing reappeared;
- relisting.

# 16. What Changed

Kada postoji novi relevantan događaj, Property Detail treba moći da prikaže sažetak delta-e.

Primer:

    Since your last review:

    Price:
    €149k → €134k

    Description:
    added "potrebna brza realizacija"

    Seller:
    Agency → Owner listing also active

Cilj je da korisnik ne mora ručno da poredi staro i novo stanje.

# 17. Property Data

Prikazati effective property podatke, npr:

    Size
    Rooms
    Floor
    Total Floors
    Elevator
    Building Type
    Construction Year
    Heating
    Parking
    Garage
    Terrace
    Condition
    Location Precision

Ako postoji konflikt ili važan provenance podatak, korisnik treba da ga može otvoriti.

Primer:

    Size: 72 m²

    Portal A: 72 m²
    Portal B: 74 m²
    Effective: 72 m²

Ne prikazivati kompletan provenance pored svakog polja ako nema konflikta ili potrebe.

# 18. Listings / Sources

Prikazati sve poznate listing-e povezane sa property-jem.

Minimalno:

    Source
    Seller / Agency
    Current or Last Price
    Status
    First Seen
    Last Seen
    Original URL

Primer:

    Portal A | Agency X | €149k | REMOVED
    Portal B | Owner    | €134k | ACTIVE
    Portal C | Agency Y | €145k | ACTIVE

Originalni listing se otvara u novom tabu.

Frontend ne pokušava da reprodukuje ceo eksterni portal.

# 19. Comparables

Transaction i Listing comps moraju biti jasno razdvojeni.

Tabela može sadržati:

    Type
    Location
    Distance
    Size
    Rooms
    Price
    €/m²
    Date
    Similarity
    Weight
    Included?
    Exclusion Reason

Target i comps mogu biti prikazani i na pomoćnoj mapi ako postoje geo podaci.

Tabela ostaje važniji analytical prikaz.

# 20. Valuation

Prikazati:

    FMV Low
    FMV Base
    FMV High
    Confidence
    Analysis Timestamp

Explainability treba da omogući pregled:

- transaction comps used;
- listing comps used;
- base €/m²;
- adjustments;
- excluded comps;
- confidence positives;
- confidence negatives;
- model version.

Frontend ne reprodukuje valuation formulu.

# 21. Liquidity

Prikazati:

    Liquidity Score
    Confidence

uz:

    positive factors
    negative factors
    unknown important factors

Ako analytical model kasnije podržava probabilistički output:

    P(sale <= 30d)
    P(sale <= 60d)
    P(sale <= 90d)

# 22. Seller Intelligence

Odvojeno prikazati:

    Seller Motivation
    Negotiability
    Cash Preference
    Reason for Sale

Za relevantne inferred signale prikazati:

    confidence
    evidence

LLM evidence i deterministički price-history/seller-history signali treba da budu jasno razlikovani.

# 23. Risk

Na vrhu:

    PASS
    VERIFY
    BLOCK

Ispod prikazati pojedinačne risk flags.

Svaki relevantan flag treba da može pokazati:

- code / label;
- severity;
- gate effect;
- source/provenance;
- confidence;
- evidence.

`BLOCK` mora biti mnogo uočljiviji od soft risk-a.

Ne koristiti samo boju kao signal; status uvek prikazati tekstom.

# 24. Deal Calculator

Deal Calculator omogućava manual scenario bez menjanja canonical automatic analysis.

Editable polja, kada ih backend podržava:

    Purchase Price
    Renovation
    Holding Days
    Exit Price
    Risk Reserve
    Cost Profile

Za relevantan input razlikovati:

    System Estimate
    Manual Scenario Value

Primer:

    Renovation
    System: €4,000
    Manual: €8,000

Manual vrednost ne overwrite-uje originalni system estimate.

# 25. Deal Recalculation

Canonical calculation radi backend.

Frontend šalje scenario input i dobija:

    Total Cost Basis
    Net Profit
    ROI
    Annualized ROI
    Max Buy
    Capital Days
    Downside / scenario outputs

Preview calculation ne mora biti persistentan.

Saved scenario je posebna write operacija.

# 26. Scenario Comparison

Kada su dostupni scenariji, omogućiti jasan prikaz:

                 Downside   Base   Upside
    Buy
    Exit
    Cost Basis
    Profit
    ROI
    Holding

Manual/custom scenario može biti dodatna kolona ili zaseban prikaz.

# 27. Pipeline / Activity

Recommended Action i Pipeline Status su različiti.

Pipeline status:

    NEW
    REVIEWED
    CALLED
    VISIT_SCHEDULED
    VISITED
    DUE_DILIGENCE
    OFFERED
    NEGOTIATING
    WON
    LOST
    SKIPPED
    SOLD

Property Detail treba da prikaže trenutni status i timeline ljudskih aktivnosti.

# 28. Log Call

Forma mora biti kratka i većina polja optional.

Moguća polja:

    Date/Time
    Seller Motivation
    Reason for Sale
    Lowest Indicated Price
    Cash Preferred
    Desired Closing Time
    Viewing Available
    Claimed Legal Information
    Tenant
    Notes

`claimed_*` informacije ne prikazivati kao verified facts.

# 29. Log Visit

Moguća structured polja:

    Condition
    Renovation Low/Base/High
    Layout
    Light
    Noise
    Building
    Entrance
    Parking
    Elevator Verified
    Visible Defects
    Manual FMV
    Manual Fast Sale
    Manual Max Buy
    Notes

Relevantan visit feedback može pokrenuti re-analysis.

# 30. Offers

Offer workflow treba da podrži najmanje:

    Amount
    Date
    Conditions
    Status
    Counteroffer
    Notes

Offer history mora ostati povezana sa property-jem.

# 31. Skip

`Skip` zahteva reason code.

Početni kodovi:

    OVERPRICED
    NO_MARGIN
    BAD_LEGAL
    LOW_LIQUIDITY
    BAD_LOCATION
    BAD_BUILDING
    HEAVY_RENOVATION
    SELLER_UNREALISTIC
    LOW_CONFIDENCE
    FAKE_LISTING
    OTHER

`OTHER` omogućava slobodnu belešku.

Application service treba u jednoj business operaciji da sačuva skip reason i relevantnu pipeline promenu.

# 32. Watch

Watch može imati optional trigger:

    ANY_PRICE_CHANGE
    PRICE_BELOW
    PRICE_DROP_PERCENT
    SELLER_CHANGE
    DESCRIPTION_CHANGE

Ako korisnik ne definiše poseban trigger, property ostaje na Watchlist-i sa default relevant-change behavior-om.

# 33. Watchlist

Minimalne kolone:

    Location
    Asking
    Max Buy
    Gap to Max Buy
    Last Price Cut
    Market Age
    Watch Trigger
    Last Change

Poželjni default ranking:

    smallest positive gap to Max Buy
    ↓
    most recent important change

# 34. Properties

`Properties` je kompletna pretraga canonical property-ja, uključujući po potrebi historical properties bez aktivnih listing-a.

Filteri mogu uključiti:

- active only;
- property type;
- location;
- size;
- rooms;
- asking;
- FMV;
- market age;
- pipeline status;
- Recommended Action;
- Risk Gate;
- Source.

Search minimalno može podržati:

- street/location text;
- internal property ID;
- external listing ID;
- agency.

Ne uvoditi full-text infrastrukturu dok jednostavan indexed search rešava potrebu.

# 35. Map

Map je pomoćni exploration ekran.

Može prikazati relevantne:

    URGENT_CALL
    CALL
    REVIEW
    WATCH

properties.

Ne mora po default-u prikazivati hiljade `IGNORE` property-ja.

Osnovni filters treba da budu usklađeni sa Properties ekranom.

Klik na pin otvara compact property preview.

# 36. Pipeline Screen

V1 može koristiti običnu tabelu grupisanu/filterovanu po pipeline statusu.

Kanban je optional kasnije.

Ne graditi kompleksan drag-and-drop CRM ako tabela rešava workflow.

# 37. Sources Screen

Minimalno prikazati:

    Source
    Status
    Last Success
    Last Discovery
    Recent Errors
    Listings Discovered
    Parse Health
    Enabled

Source health:

    HEALTHY
    DEGRADED
    FAILED
    DISABLED

Source Detail može prikazati:

- recent job runs;
- HTTP error summary;
- parse error summary;
- recent listing counts;
- configured intervals.

Manual actions kao `Run Discovery`, `Run Reconciliation` i `Enable/Disable` prikazati samo ako backend capability postoji.

# 38. Global Source Warning

Jedan failed/degraded source ne blokira ceo dashboard.

Globalno može stajati kompaktno:

    1 source degraded

Ako source problemi znače da tržišni podaci mogu biti nepotpuni, to mora biti jasno razlikovano od normalnog empty state-a.

# 39. Analytics Screen

Analytics nije V0 prioritet.

Kasnije može prikazivati:

- Listings / day;
- New Properties / day;
- Price Cuts;
- Alerts;
- Alert Precision;
- Calls;
- Visits;
- Offers;
- Deals;
- Skip Reasons;
- Valuation Errors.

Najvažniji product KPI je kvalitet opportunity selekcije, ne samo broj scraped listing-a.

Funnel može biti:

    Alerts
    → Calls
    → Visits
    → Offers
    → Deals

# 40. Settings

Glavne kategorije:

    Investment Profile
    Cost Profile
    Notification Settings
    Source Settings
    Analysis Settings

Ne praviti generic admin platform.

# 41. Investment Profile UI

Kada je funkcionalnost dostupna, korisnik može menjati npr:

    Minimum Expected Profit
    Minimum Downside Profit
    Minimum ROI
    Maximum Holding Days
    Minimum Liquidity
    Minimum Valuation Confidence
    Desired Profit
    Default Risk Reserve

Izmena profila ne rewrite-uje historical analysis.

Relevantni current properties se po potrebi ponovo evaluiraju.

# 42. Cost Profile UI

Prikazivati relevantne assumptions kao:

    Purchase Costs
    Sale Costs
    Taxes
    Lawyer
    Agency
    Holding
    Financing
    Other

Ako formula nije jednostavno editabilna kroz UI, dozvoljen je read-only prikaz dok ne postoji bezbedan editor.

# 43. Analysis Status UX

Frontend mora prikazivati partial analytical stanje.

Primer:

    Valuation: SUCCESS
    LLM: PENDING
    Risk: STALE
    Deal: SUCCESS

Ne koristiti jedan globalni spinner za sve analytical module.

Relevantni statusi uključuju:

    NOT_RUN
    PENDING
    SUCCESS
    FAILED
    STALE
    INSUFFICIENT_DATA

# 44. Manual Reanalysis

Property može imati:

    Reanalyze

ako backend capability postoji.

Akcija treba da queue-uje background analysis.

API odgovor:

    status = QUEUED

Frontend ne drži request otvoren dok traje kompletan analytical pipeline.

# 45. Loading / Empty / Error States

Razlikovati:

    loading
    no data
    analysis pending
    analysis failed
    insufficient data
    stale data
    source failure

Ako nema qualifying kandidata:

    No qualifying opportunities.

To nije error.

Ako nema kandidata zato što tržišni source-ovi ne rade:

    Market data may be incomplete.
    2 sources failed.

To jeste operational warning.

# 46. UNKNOWN

`UNKNOWN` je legitimno domain stanje.

Ne prikazivati ga kao tehničku grešku.

Ne zamenjivati ga:

    0
    false
    -

ako to menja semantiku.

# 47. Freshness

Property Detail treba da može prikazati najmanje:

    Last Listing Update
    Last Analysis

Ako je current analysis stale:

    STALE

mora biti jasno vidljivo.

Korisnik mora razlikovati staru analizu od sveže analize.

# 48. Formatting

Money format mora biti konzistentan.

Primer:

    €134,000
    €2,845/m²

Ako backend confidence koristi `0.0–1.0`, frontend ga može prikazati kao:

    81%

ili:

    81

ali konzistentno kroz aplikaciju.

Ne prikazivati isti score nekad kao `0.81`, a nekad kao `81`.

# 49. Frontend Routes

Ciljni routes mogu biti:

    /
      → Action Queue

    /properties
    /properties/:id

    /watchlist
    /pipeline
    /map

    /sources
    /sources/:id

    /analytics
    /settings

Ne kreirati route za funkcionalnost koja još nije implementirana samo kao prazan placeholder.

# 50. Telegram Deep Link

Opportunity alert treba da vodi direktno na odgovarajući property route, npr:

    /properties/{id}

Korisnik posle alerta ne treba ručno da traži isti property.

# 51. Frontend State Management

Ne uvoditi kompleksan global state framework bez potrebe.

Preferirati:

    server-state query/cache library
    +
    local component/form state

Ako se koristi TanStack Query ili ekvivalent, server state treba prvenstveno rešavati kroz njegov cache/refetch model.

# 52. Real-Time Updates

V0 ne zahteva WebSocket ili SSE.

Dovoljni su:

- query invalidation;
- polling;
- manual refresh.

Action Queue može, ako je potrebno, raditi lightweight refetch približno na 30–60 sekundi.

Telegram već rešava kritični real-time notification use case.

WebSocket/SSE uvoditi tek ako postoji stvarna potreba za:

- live analysis status;
- instant in-app alerts;
- drugim dokazanim real-time workflow-om.

# 53. API Principle

API je interni application API za frontend.

Preferirati REST.

Ne uvoditi GraphQL bez stvarnog razloga.

Routes treba da budu tanki:

    request validation
    → application service
    → response serialization

Business formulas ne pripadaju API route-u.

# 54. API Prefix

Koristiti jedan konzistentan prefix, preporučeno:

    /api/v1

Ne održavati više API verzija dok ne postoji stvarna compatibility potreba.

# 55. Success & Error Responses

Success response može biti običan JSON resource.

Ne uvoditi obavezni wrapper poput:

    {
      "success": true,
      "data": ...
    }

bez stvarne potrebe.

Error response treba da bude konzistentan, npr:

    {
      "code": "PROPERTY_NOT_FOUND",
      "message": "Property not found",
      "details": null
    }

Validation errors mogu koristiti konzistentan FastAPI/Pydantic format.

# 56. Pagination

List endpoint-i moraju biti paginirani.

V1:

    page
    page_size

Početni default može biti oko:

    page_size = 50

Maximum tipično:

    100–200

zavisno od endpoint-a.

Ne vraćati desetine hiljada property-ja jednim requestom.

Cursor pagination uvoditi tek ako offset/page pristup postane stvarni problem.

# 57. Sorting

Standardni query oblik:

    sort
    direction

Primer:

    ?sort=expected_profit&direction=desc

Backend koristi whitelist dozvoljenih sort vrednosti.

Ne prosleđivati proizvoljno ime korisničkog polja direktno u SQL.

# 58. Filtering

`GET /api/v1/properties` može postepeno podržati:

    action
    pipeline_status
    property_type
    city
    municipality
    micro_location
    min_price
    max_price
    min_size
    max_size
    min_profit
    min_liquidity
    min_confidence
    risk_gate
    source_id
    active_only

Implementirati samo filtere potrebne trenutnoj fazi/UI-u.

# 59. Action Queue API

Preporučeni endpoint:

    GET /api/v1/action-queue

Treba da vraća read model dovoljan za listu bez dodatnih requestova po svakom redu.

Minimalni item koncept:

    property_id
    recommended_action

    location
    size_m2
    rooms

    asking_price
    currency

    fair_value_low/base/high
    fast_sale_base
    max_buy_price

    expected_profit
    downside_profit

    liquidity_score
    valuation_confidence
    risk_gate

    property_market_age_days

    last_change

Ne zahtevati da frontend spaja veliki broj domain endpoint-a da bi prikazao jednu tabelu.

# 60. Properties API

Osnovno:

    GET /api/v1/properties
    GET /api/v1/properties/{property_id}

List koristi pagination/filtering/sorting.

Detail vraća dovoljno current summary podataka za početno renderovanje Property Detail ekrana.

Veće sekcije mogu biti lazy-loaded kroz subresources.

# 61. Property Subresources

Uvoditi kada su stvarno potrebni:

    GET /api/v1/properties/{id}/analysis
    GET /api/v1/properties/{id}/listings
    GET /api/v1/properties/{id}/history
    GET /api/v1/properties/{id}/comparables
    GET /api/v1/properties/{id}/valuations
    GET /api/v1/properties/{id}/risk
    GET /api/v1/properties/{id}/deal
    GET /api/v1/properties/{id}/activity

Ne kreirati sve unapred ako jedan jednostavan detail endpoint rešava current phase.

# 62. Current Analysis API

Kada postoji:

    GET /api/v1/properties/{id}/analysis

treba da vrati current relevantne:

    data_quality
    valuation
    liquidity
    fast_sale
    seller_intelligence
    risk
    deal
    opportunity
    module statuses

Partial result je validan response.

# 63. History API

    GET /api/v1/properties/{id}/history

Backend vraća unified chronological timeline.

Mogući item types:

    LISTING_DISCOVERED
    PRICE_CHANGED
    DESCRIPTION_CHANGED
    SELLER_CHANGED
    LISTING_REMOVED
    LISTING_REAPPEARED
    CALL
    VISIT
    OFFER
    PIPELINE_CHANGED

Backend radi merge/sort događaja.

Frontend ne treba da poziva više tabela/API-ja i sam rekonstruiše domain timeline.

# 64. Watch API

Konceptualno:

    POST   /api/v1/properties/{id}/watch
    DELETE /api/v1/properties/{id}/watch
    GET    /api/v1/watchlist

Optional trigger payload može biti:

    {
      "rule_type": "PRICE_BELOW",
      "threshold_numeric": 142000
    }

# 65. Review API

    POST /api/v1/properties/{id}/review

Mogući payload:

    {
      "decision": "INTERESTING",
      "manual_fmv": 170000,
      "manual_fast_sale_value": 160000,
      "notes": "..."
    }

Optional fields ostaju optional osim kada domain pravilo zahteva drugačije.

# 66. Pipeline API

    PATCH /api/v1/properties/{id}/pipeline-status

Primer:

    {
      "status": "CALLED"
    }

Promena mora ići kroz application service.

Ako timeline capability postoji, istorijski evidentirati transition.

# 67. Call API

    POST /api/v1/properties/{id}/interactions/call

Mogući payload:

    {
      "occurred_at": "...",
      "seller_motivation": "HIGH",
      "reason_for_sale": "MOVING_ABROAD",
      "lowest_indicated_price": 140000,
      "cash_preferred": true,
      "desired_closing_days": 7,
      "viewing_available": true,
      "claimed_registered": true,
      "notes": "..."
    }

Relevantan feedback treba da može pokrenuti downstream re-analysis.

# 68. Visit API

    POST /api/v1/properties/{id}/interactions/visit

Payload prati structured visit model iz Data Model Specification-a.

Successful write može queue-ovati relevantnu re-analysis.

# 69. Offers API

Konceptualno:

    POST  /api/v1/properties/{id}/offers
    PATCH /api/v1/offers/{offer_id}

PATCH služi za relevantne promene kao:

- status;
- seller response;
- counteroffer;
- notes.

# 70. Skip API

    POST /api/v1/properties/{id}/skip

Primer:

    {
      "reason_code": "NO_MARGIN",
      "notes": "..."
    }

Jedan application command treba da:

- sačuva skip record;
- promeni relevantni pipeline state;
- evidentira history gde postoji.

Frontend ne treba da orkestrira više zavisnih write requestova za jednu business akciju.

# 71. Reanalysis API

    POST /api/v1/properties/{id}/reanalyze

Response:

    {
      "status": "QUEUED"
    }

Ne držati HTTP connection otvoren do kraja LLM/analytical pipeline-a.

# 72. Deal Calculator API

Preview:

    POST /api/v1/deal-calculator

Mogući payload:

    {
      "property_id": "...",
      "purchase_price": 135000,
      "renovation_cost": 8000,
      "exit_price": 160000,
      "holding_days": 60,
      "risk_reserve": 4000,
      "cost_profile_id": "..."
    }

Response vraća canonical calculation rezultat, npr:

    total_cost_basis
    net_profit
    roi
    annualized_roi
    max_buy_price
    capital_days

Preview ne mora biti persistentan.

# 73. Saved Scenario API

Ako korisnik eksplicitno čuva manual scenario:

    POST /api/v1/properties/{id}/deal-scenarios

Saved scenario i preview calculation nisu ista operacija.

# 74. Comparables API

    GET /api/v1/properties/{id}/comparables

Optional filter:

    type=transaction|listing|all

Relevantan response item treba da omogući najmanje:

    type
    included
    similarity
    weight
    exclusion_reason

plus podatke potrebne za comparable prikaz.

# 75. Sources API

Minimalni read API:

    GET /api/v1/sources
    GET /api/v1/sources/{id}

Kada postoji odgovarajuća backend capability:

    PATCH /api/v1/sources/{id}
    POST  /api/v1/sources/{id}/run-discovery
    POST  /api/v1/sources/{id}/run-reconciliation

Ne izlagati manual operation endpoint ako underlying workflow nije bezbedno implementiran.

# 76. Jobs API

Za basic debugging/operations može postojati:

    GET /api/v1/jobs
    GET /api/v1/jobs/{id}

Filteri po potrebi:

    source
    job_type
    status
    date range

Nije potreban kompleksan job-management UI.

# 77. Alerts API

    GET /api/v1/alerts

Filteri po potrebi:

    status
    priority
    property_id
    date range

Alert history je važna za kasnije merenje alert precision-a.

# 78. Matching API — Kasnije

Kada UI za `POSSIBLE_MATCH` postane deo scope-a:

    GET  /api/v1/matching/candidates
    POST /api/v1/matching/candidates/{id}/accept
    POST /api/v1/matching/candidates/{id}/reject

UI treba da prikaže dovoljno podataka za odluku:

- images;
- location;
- size;
- rooms;
- price;
- source;
- similarity breakdown.

Manual matching odluka ima prednost nad automatic matcher-om.

# 79. API Performance

Action Queue i Properties list ne smeju praviti N+1 query pattern za svaki analytical atribut.

Backend treba da koristi odgovarajući read model/query.

Takođe nije prihvatljivo da frontend radi desetine requestova po list item-u.

# 80. Detail Payload Size

Osnovni Property Detail response ne treba da sadrži:

- raw HTML;
- sve full-resolution slike;
- kompletnu istoriju svih analytical versions;
- ogromne raw payload-e.

Velike/retko korišćene sekcije lazy-load-ovati kroz subresources kada je potrebno.

# 81. Images

Ako listing image URL postoji, frontend ga može koristiti za gallery/thumbnails.

Ne proxy-ovati sve images kroz backend bez razloga.

Image storage/fallback strategija nije deo ovog dokumenta.

# 82. Authentication

Aplikacija je privatna.

Nema javne registracije.

Minimalna production invarijanta:

> neautorizovan korisnik ne može pristupiti dashboard-u niti API-ju.

API/UI pretpostavljaju single-user auth.

Ne graditi:

- multi-tenant auth;
- role matrix;
- javne korisničke naloge;

bez promene product scope-a.

Tačan production auth mehanizam pripada Deployment/Operations specifikaciji.

# 83. Session / CSRF

Ako se koristi cookie session auth:

- koristiti odgovarajuću same-site/cookie zaštitu;
- write endpoint-e zaštititi od CSRF-a prema izabranom auth modelu.

Ako se koristi bearer token:

- token ne hardkodovati u frontend source code.

# 84. Write Validation

Svaki write endpoint validira relevantne:

- enum vrednosti;
- currency;
- money bounds;
- percentages;
- dates;
- referenced property/entity existence;
- domain constraints.

Primer nevalidnog inputa:

    holding_days = -30

Backend, ne UI, ostaje poslednja validation granica.

# 85. Manual Data i Concurrency

Ako background analysis radi dok korisnik unosi manual podatak:

- manual write mora biti sačuvan;
- automatic result ne sme overwrite-ovati manual/verified podatak;
- analysis koristi odgovarajući latest effective state;
- ako se relevantan input promeni tokom run-a, rezultat se može označiti stale i re-queue-ovati.

# 86. No Raw SQL Interface

Frontend šalje domain filtere i commands.

Ne postoji generic API poput:

    /query?sql=...

Niti frontend određuje database table/column expression direktno.

# 87. Confirmations

Confirmation koristiti samo za ozbiljne/destructive operacije poput:

- property merge/split;
- brisanje important manual podatka;
- druge destructive admin akcije.

Ne koristiti confirmation za:

    Mark Reviewed
    Watch
    običnu promenu filtera

bez posebnog razloga.

# 88. Manual Data Audit UX

Za relevantne manual podatke prikazati najmanje:

    updated_at

i gde je korisno:

    system value
    manual value

Single-user proizvodu nije potreban kompleksan enterprise audit viewer.

# 89. V0 UI Scope

Prvi usable UI može imati samo:

    Action Queue
    Property Detail
    Source Health
    Basic Settings

Property Detail može početi sa:

    Basic Property Data
    Listings
    Price History
    Current Analysis
    Deal Summary
    Watch / Review / Skip

Comparables, CRM, Pipeline, Map i Analytics se dodaju kada odgovarajući backend capability postoji.

# 90. V0 API Scope

Minimalni početni API, kada ga phase plan uvede:

    GET  /api/v1/health

    GET  /api/v1/action-queue

    GET  /api/v1/properties
    GET  /api/v1/properties/{id}
    GET  /api/v1/properties/{id}/history

    POST /api/v1/properties/{id}/watch
    POST /api/v1/properties/{id}/review
    POST /api/v1/properties/{id}/skip

    GET  /api/v1/sources

Tačan endpoint se implementira samo kada ga current phase zahteva.

# 91. API Acceptance Criteria

API sloj je kvalitetan kada:

1. Action Queue može biti prikazan jednim efikasnim list request-om;
2. Property Detail može dobiti relevantne current podatke bez nepotrebnog N+1 request pattern-a;
3. write operacije idu kroz application services;
4. input validation je konzistentna;
5. list endpoint-i imaju pagination;
6. sorting/filtering koriste whitelist domain vrednosti;
7. `UNKNOWN`, `STALE`, `FAILED` i `INSUFFICIENT_DATA` ostaju različiti;
8. partial analysis je validno predstavljen;
9. background re-analysis nije dug blocking request;
10. API route ne implementira canonical business formule;
11. manual podatak ne može biti prepisan background analysis-om;
12. authorization štiti privatni API.

# 92. UI Acceptance Criteria

Korisnik bez baze, terminala ili manual spreadsheet-a treba da može da:

1. vidi najvažnije kandidate;
2. razume zašto su preporučeni;
3. otvori originalni listing;
4. vidi relevantnu listing/price istoriju;
5. vidi FMV i confidence;
6. vidi liquidity/Fast-Sale kada postoje;
7. vidi comps kada su implementirani;
8. vidi Risk Gate i flags;
9. vidi deal economics i Max Buy;
10. promeni manual scenario i dobije novu calculation;
11. stavi property na Watch;
12. Review/Skip kandidat;
13. unese call/visit feedback kada CRM postoji;
14. prati pipeline kada je implementiran;
15. vidi source degradation/failure;
16. razlikuje fresh, stale, partial i unavailable analysis.

# 93. Ključne API/UI Invarijante

1. Frontend ne računa canonical FMV, Fast-Sale, Max Buy, Risk Gate ili Opportunity Action.

2. Recommended Action nije Pipeline Status.

3. Property nije Listing; Property Detail može imati više listing-a.

4. Transaction comps i Listing comps moraju biti jasno razlikovani.

5. `UNKNOWN` nije `0`.

6. `INSUFFICIENT_DATA` nije tehnički `FAILED`.

7. `STALE` analysis ne prikazuje se kao fresh.

8. `BLOCK` se ne skriva iza visokog score-a.

9. Manual scenario ne overwrite-uje automatic historical analysis.

10. Manual/verified podatak ne sme biti prepisan background result-om.

11. Source failure nije isto što i `No qualifying opportunities`.

12. Empty Action Queue je validan product state.

13. Frontend ne spaja veliki broj database/domain struktura ako backend može vratiti prikladan read model.

14. List endpoints moraju biti paginirani.

15. Sort/filter parametri moraju biti whitelist-ovani.

16. Business write koji zahteva više persistence promena rešava application service, ne više nevezanih frontend requestova.

17. Long-running analysis se queue-uje; ne drži HTTP request otvorenim.

18. API/UI se implementiraju samo za capability koji postoji u current phase-u.

# 94. Canonical Ownership

Data entities i persistence:

    docs/03-data-model.md

Scraping i source behavior:

    docs/04-scraping-specification.md

Valuation, liquidity, risk, deal i opportunity semantics:

    docs/05-analysis-specification.md

Implementation order:

    docs/07-phase-plan.md

Testing:

    docs/08-testing-specification.md

Production auth, runtime i operations:

    docs/09-deployment-operations.md

Ovaj dokument poseduje:

> **način na koji backend capability postaje bezbedan API i brz, razumljiv korisnički workflow.**

# 95. Konačni UI princip

Za ozbiljan kandidat korisnik treba bez nepotrebnog kliktanja da dobije odgovore redom:

    Šta je ovo?
    ↓
    Koliko seller traži?
    ↓
    Koliko property verovatno vredi?
    ↓
    Koliki je konzervativan Fast-Sale exit?
    ↓
    Koliko maksimalno smem da platim?
    ↓
    Kolika je očekivana i downside zarada?
    ↓
    Koji rizici i uncertainties postoje?
    ↓
    Zašto je sistem zainteresovan?
    ↓
    Šta sada treba da uradim?

Ako Action Queue i Property Detail brzo i pouzdano odgovaraju na ova pitanja, UI ispunjava svoju glavnu svrhu.