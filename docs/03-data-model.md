**Putanja:** `/docs/03-data-model.md`

````md
# Distressed Property Radar — Data Model Specification

## 1. Svrha dokumenta

Ovaj dokument definiše kanonski model podataka Distressed Property Radar sistema.

Source of truth je za:

- entitete i njihove odgovornosti;
- veze između entiteta;
- listing/property identitet;
- current state i istoriju;
- provenance;
- manual i verified podatke;
- istorijske analytical rezultate;
- versioning relevantne logike;
- database constraints i integrity invarijante.

Ne definiše scraping algoritme, analytical formule, API/UI, deployment, test matrix ili implementation order.

Nazivi tabela i polja su preporučeni canonical model. Manje tehničke izmene su dozvoljene ako ih PostgreSQL/SQLAlchemy opravdavaju, ali se semantika i invarijante ne smeju menjati.


# 2. Osnovne invarijante

## 2.1. Listing nije Property

`Property` je fizička nekretnina.

`Listing` je jedan oglas za tu nekretninu na jednom source-u.

Jedan `Property` može imati više listing-a:

```text
Property A
├── Portal X / listing 123
├── Portal X / listing 987
├── Portal Y / listing 555
└── Agency Z / listing abc
````

Jedan listing može imati najviše jednu current canonical property vezu.

## 2.2. Current state nije history

`listings` može čuvati trenutno stanje radi brzog čitanja.

Istorijske promene čuvaju se kroz `listing_events` i druge istorijske entitete.

Ne praviti puni snapshot listing-a pri svakom crawl-u ako nema relevantne promene.

## 2.3. Removal nije delete

Nestanak sa portala menja lifecycle state.

`REMOVED` listing se ne hard-delete-uje.

Takođe:

```text
listing REMOVED
!=
property SOLD
```

## 2.4. Poreklo podataka

Sistem mora razlikovati najmanje:

```text
SCRAPED
DERIVED
LLM
MANUAL
VERIFIED_MANUAL
TRANSACTION_DATA
IMPORT
```

Automatski proces ne sme tiho prepisati pouzdaniji manual/verified podatak.

## 2.5. `null` znači UNKNOWN

Ako podatak nije poznat, koristiti `null`.

Primer:

```text
elevator = null
```

znači da nije poznato da li lift postoji.

Nije isto što i:

```text
elevator = false
```

Ne koristiti `0`, `false` ili prazan string kao zamenu za nepoznatu vrednost ako time menjamo semantiku.

## 2.6. Analytical history se ne overwrite-uje

Nova valuacija, risk assessment, deal analysis ili opportunity assessment predstavlja novi istorijski rezultat.

Stari rezultat ostaje vezan za:

* property;
* vreme/as-of;
* relevantne input reference;
* model/rules/formula version.

# 3. PostgreSQL pravila

## IDs

Za interne entitete preferirati UUID.

Eksterni source ID čuvati zasebno kao string.

## Timestamp

Koristiti `TIMESTAMPTZ`.

Čuvati u UTC.

Primeri:

```text
created_at
updated_at
first_seen_at
last_seen_at
detected_at
analyzed_at
occurred_at
```

## Novac

Koristiti `NUMERIC`, nikada floating-point.

Tipičan iznos:

```text
NUMERIC(14,2)
```

Currency čuvati odvojeno.

## Površina

Koristiti decimalni numerički tip, npr:

```text
NUMERIC(10,2)
```

## Probability / confidence

Gde ima smisla, interno koristiti `0.0–1.0`.

UI može prikazivati `0–100`.

Ne mešati formate za isto persistence polje.

## JSONB

Koristiti za podatke promenljive strukture kao što su:

* explanation;
* evidence;
* provider payload;
* LLM structured output;
* configuration;
* scenario assumptions.

Ne skrivati osnovna često query-ovana polja u JSONB.

# 4. Glavni enum-i

## `PropertyType`

```text
APARTMENT
HOUSE
LAND
COMMERCIAL
OTHER
```

V1 analytical scope je `APARTMENT`.

## `CurrencyCode`

```text
EUR
RSD
```

## `ListingStatus`

```text
ACTIVE
NOT_SEEN
REMOVED
UNKNOWN
```

`NOT_SEEN` je privremeno stanje pre potvrđenog removal-a.

## `SellerType`

```text
OWNER
AGENCY
INVESTOR
BANK
COURT_OR_ENFORCEMENT
OTHER
UNKNOWN
```

## `MatchDecision`

```text
AUTO_MATCH
MANUAL_MATCH
POSSIBLE_MATCH
REJECTED_MATCH
```

## `PropertyPipelineStatus`

```text
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
```

Pipeline state je korisnikov acquisition workflow, ne analytical recommendation.

## `RecommendedAction`

```text
IGNORE
WATCH
REVIEW
CALL
URGENT_CALL
DUE_DILIGENCE
```

## `RiskGateStatus`

```text
PASS
VERIFY
BLOCK
```

## `DataSourceKind`

```text
SCRAPED
DERIVED
LLM
MANUAL
VERIFIED_MANUAL
TRANSACTION_DATA
IMPORT
```

# 5. `sources`

Predstavlja eksterni ili importovani source podataka.

Polja:

```text
id
name
code
source_type
base_url
is_enabled

supports_discovery
supports_market_scan
supports_detail_fetch
supports_transaction_data

created_at
updated_at
```

`code` je stabilan machine-readable identifikator, npr:

```text
portal_a
rgz_transactions
manual
```

Deaktiviranje source-a ne briše istorijske podatke.

# 6. `source_runtime_state`

Current operational state jednog source-a.

Polja:

```text
source_id

last_attempt_at
last_success_at
last_discovery_success_at
last_market_scan_success_at

last_error_at
last_error_type
last_error_message

recent_http_error_count
recent_parse_error_count

last_discovered_count

updated_at
```

Služi za current health/observability.

Nije kompletan historical error log.

# 7. `properties`

Canonical fizička nekretnina.

## Identitet

```text
id
property_type
```

## Lokacija

Početni model može imati:

```text
country_code
city
municipality
neighborhood
micro_location
street

latitude
longitude

location_precision
location_confidence
```

Nepoznate vrednosti ostaju `null`.

## Osnovni fizički atributi

Za početni apartment/house model:

```text
size_m2

rooms
bedrooms

floor
total_floors

elevator

construction_year
building_type
heating_type

parking
garage
terrace

condition_category
```

## Derived/current market summary

Radi brzine može sadržati:

```text
first_seen_at
last_seen_at

active_listing_count
estimated_market_age_days
relist_count
```

Ova polja su cache/derived.

Istorijski source of truth ostaje u listing i history podacima.

## Pipeline

```text
pipeline_status
pipeline_status_updated_at
```

## Metadata

```text
created_at
updated_at
```

# 8. Property-type extensions

Ne dodavati veliki broj LAND-specific polja u `properties`.

Kada drugi property type stvarno dobije sopstvenu analitiku, koristiti extension tabelu gde je opravdano.

Za početni APARTMENT V1 nije potrebno praviti `apartment_details` ako su postojeća zajednička polja praktična.

`LAND` schema se ne implementira dok je phase plan ne zahteva.

# 9. `listings`

Jedan oglas na jednom source-u.

## Identitet

```text
id

source_id
external_listing_id

property_id
```

`property_id` može privremeno biti `null` tokom ingestion/matching procesa.

## Uniqueness

Obavezno:

```text
UNIQUE(source_id, external_listing_id)
```

Ako source nema stabilan external ID, njegov adapter mora imati eksplicitnu alternativnu identity strategiju.

Ne koristiti title, cenu ili telefon kao globalni listing identitet.

## URL

```text
url
canonical_url
```

## Current listing data

```text
title
description

asking_price
currency

size_m2
price_per_m2

city_raw
location_raw

rooms
bedrooms

floor
total_floors

elevator

construction_year
building_type
heating_type

parking
garage
terrace

condition_raw
legal_status_raw
```

Ovo su listing-level podaci i ne moraju biti isti kao canonical property values.

## Seller

```text
seller_type
seller_name
agency_name

seller_phone
seller_contact_raw
```

Kontakt čuvati samo ako je stvarno potreban i legitimno dostupan.

Telefon nije property identitet.

## Lifecycle

```text
status

published_at

first_seen_at
last_seen_at

removed_at

last_detail_fetch_at
last_card_seen_at
```

`published_at` može biti `null`.

## Change detection

```text
card_state_hash
detail_state_hash
llm_input_hash
```

## Scheduling

Ako je potrebno:

```text
crawl_priority
next_check_at
```

## Metadata

```text
created_at
updated_at
```

# 10. `listing_raw_records`

Opcioni raw source payload za debugging i reprocessing.

Polja:

```text
id
listing_id

record_type

raw_payload
content_type
content_hash

captured_at
```

`record_type`:

```text
CARD
DETAIL
```

Ne čuvati novu identičnu kopiju bez razloga.

Raw payload retention nije isto što i canonical history retention.

# 11. `listing_events`

Centralni istorijski zapis relevantnih listing promena.

Polja:

```text
id
listing_id

event_type
detected_at

old_value_json
new_value_json

source_record_id

created_at
```

Minimalni event-i:

```text
DISCOVERED
PRICE_CHANGED
TITLE_CHANGED
DESCRIPTION_CHANGED
SELLER_CHANGED
STATUS_CHANGED
REMOVED
REAPPEARED
DETAIL_CHANGED
```

Za često query-ovane event-e mogu postojati specifična polja.

Primer za cenu:

```text
old_price
new_price
```

Ne kreirati event samo zato što se promenio `last_seen_at`.

Retry istog inputa ne sme napraviti duplicate event.

# 12. Price History

V0 price history izvodi se iz `listing_events`.

Ne uvoditi zasebnu `listing_price_history` tabelu dok postoji stvaran performance ili analytical razlog.

# 13. `property_listing_links`

Čuva provenance i istoriju matching veze listing → property.

Polja:

```text
id

property_id
listing_id

decision
match_confidence

matching_method
matching_version

reason_json

created_at
confirmed_at
```

`listings.property_id` može predstavljati current canonical vezu.

`property_listing_links` objašnjava kako je veza nastala.

## Matching invarijante

* jedan listing ne može imati dve current canonical property veze;
* manual confirmation ima prednost nad automatic matching-om;
* automatic reprocessing ne sme sam raskinuti potvrđenu manual vezu;
* promena matching modela ne briše staru matching istoriju.

# 14. `property_match_candidates`

Neizvesni matching kandidati.

Polja:

```text
id

listing_id
candidate_property_id

similarity_score

location_score
size_score
rooms_score
image_score
text_score
other_score

matching_version

status

created_at
resolved_at
```

Status:

```text
PENDING
ACCEPTED
REJECTED
EXPIRED
```

Individualni score može biti `null` ako taj signal nije korišćen.

# 15. `images`

Listing image metadata.

Polja:

```text
id
listing_id

source_url
position

width
height

content_hash
perceptual_hash

first_seen_at
last_seen_at

is_active
```

Ne čuvati originalni image binary u PostgreSQL-u.

# 16. Lokacije

V0 može koristiti direktna location polja u `properties`.

Ako bude potrebna normalizovana taksonomija, može se uvesti `locations`:

```text
id

type
name
normalized_name

parent_id

geometry

external_reference

created_at
updated_at
```

Tipovi mogu biti:

```text
COUNTRY
CITY
MUNICIPALITY
NEIGHBORHOOD
MICROZONE
STREET
```

`geometry` može koristiti PostGIS.

## `property_location_assignments`

Uvodi se tek ako sistem mora da čuva više location interpretacija/provenance-a.

```text
id
property_id
location_id

source_kind
confidence
is_current

created_at
```

Ne implementirati obe strukture unapred.

# 17. `property_features`

Current derived/cache feature-i.

Mogu uključivati:

```text
property_id

price_per_m2

listing_age_days
property_market_age_days

active_listing_count
known_listing_count

relist_count

current_lowest_asking_price
current_highest_asking_price

total_price_drop_pct
price_drop_7d_pct
price_drop_30d_pct

price_cut_count
days_since_last_price_cut
largest_price_cut_pct

owner_listing_present
agency_listing_count

computed_at
feature_version
```

Ovo nije historical source of truth.

Feature-i moraju biti ponovo izračunljivi iz relevantnih canonical podataka.

# 18. `transaction_records`

Eksterno dostupni podaci o realizovanim transakcijama.

Moguća polja:

```text
id

source_id
external_transaction_id

transaction_date
property_type

price
currency

size_m2
price_per_m2

location / geometry

rooms
floor
building_type

raw_reference
data_quality

created_at
updated_at
```

Tačan skup zavisi od source-a.

Transaction record se ne povezuje automatski sa property-jem bez dovoljno dobrog matching-a.

# 19. `transaction_property_matches`

Veza između transaction record-a i canonical property-ja.

```text
id

transaction_record_id
property_id

match_confidence
matching_method
matching_version

status

created_at
confirmed_at
```

Status:

```text
POSSIBLE
CONFIRMED
REJECTED
```

# 20. `comparable_sets`

Konkretan skup comparables korišćen u jednoj analizi.

```text
id

property_id

as_of

comparable_engine_version
search_parameters_json

created_at
```

`as_of` je obavezan za historical evaluation/backtesting.

# 21. `comparable_items`

Jedan član comparable seta.

```text
id

comparable_set_id
comparable_type
```

Tip:

```text
TRANSACTION
LISTING
PROPERTY_HISTORY
```

Reference:

```text
transaction_record_id
listing_id
property_id
```

Popunjava se samo odgovarajuća referenca.

Snapshot analytical podaci:

```text
similarity_score

distance_m
age_days_at_analysis

price
price_per_m2

weight

included_in_valuation
exclusion_reason
```

Snapshot vrednosti moraju predstavljati stanje relevantno u vreme te analize.

# 22. `valuations`

Svaka valuacija je immutable historical result.

```text
id

property_id
comparable_set_id

as_of

fair_value_low
fair_value_base
fair_value_high

currency

confidence
data_quality_at_analysis

model_type
model_version

input_summary_json
explanation_json

created_at
```

Ne update-ovati jedan valuation red zauvek.

# 23. `liquidity_assessments`

Istorijski liquidity rezultat.

```text
id

property_id
as_of

liquidity_score
confidence

probability_sale_30d
probability_sale_60d
probability_sale_90d

positive_factors_json
negative_factors_json

model_version

created_at
```

Probability polja ostaju `null` dok model to ne podržava.

# 24. `fast_sale_estimates`

Uvesti kao zaseban entitet samo ako Fast-Sale postoji kao zaseban analytical model.

```text
id

property_id
as_of

value_low
value_base
value_high

target_days
target_probability

confidence
model_version

created_at
```

Ne duplirati isti rezultat na više mesta.

# 25. `llm_analyses`

Istorijski LLM extraction/analysis run.

```text
id

listing_id
property_id

input_hash

provider
model
prompt_version

status

seller_motivation_level
seller_motivation_confidence

cash_preferred
cash_preference_confidence

negotiability_level
negotiability_confidence

reason_for_sale

condition_category
condition_confidence

structured_output_json
evidence_json

created_at
completed_at

error_message
```

`property_id` može biti `null` ako analiza nastane pre matchovanja.

Status:

```text
PENDING
SUCCESS
FAILED
INVALID_OUTPUT
```

Ako su isti:

```text
listing_id
input_hash
prompt_version
model
```

application layer ne treba nepotrebno da ponavlja uspešnu analizu.

# 26. `risk_assessments`

Istorijski risk rezultat.

```text
id

property_id
as_of

hard_gate_status

risk_score
confidence

rules_version

created_at
```

`risk_score` može biti `null`.

`hard_gate_status` ima zasebno značenje.

# 27. `risk_flags`

Jedan risk signal.

```text
id

risk_assessment_id

code

severity
gate_effect

source_kind
source_reference

confidence

description
evidence_json
```

Katalog konkretnih risk code-ova pripada Analysis Specification-u.

# 28. `cost_profiles`

Centralizovana konfiguracija troškova za deal engine.

Moguća struktura:

```text
id

name
code

currency
is_active

purchase_tax_rule_json
notary_rule_json
lawyer_rule_json
agency_rule_json
sale_cost_rule_json
holding_cost_rule_json
financing_rule_json
other_cost_rule_json

version

created_at
updated_at
```

Ako su početna pravila jednostavna, model može biti jednostavniji.

Važna invarijanta:

> finansijske pretpostavke nisu rasute kao hardcoded konstante kroz codebase.

# 29. `investment_profiles`

Korisnikovi investment kriterijumi.

```text
id

name
is_default

min_expected_profit
min_downside_profit

min_roi

max_expected_holding_days

min_liquidity_score
min_valuation_confidence

default_risk_reserve
desired_profit

created_at
updated_at
```

Kasnije, samo ako je potrebno:

```text
property_type
location scope
capital_limit
```

# 30. `deal_analyses`

Istorijski rezultat deal kalkulacije.

```text
id

property_id

valuation_id
liquidity_assessment_id
risk_assessment_id

cost_profile_id
investment_profile_id

as_of

assumed_purchase_price

purchase_costs
renovation_cost
sale_costs
taxes
financing_costs
holding_costs
risk_reserve
other_costs

total_cost_basis

expected_exit_price
max_buy_price

expected_profit
downside_profit
upside_profit

roi
annualized_roi

expected_holding_days

capital_days
profit_per_capital_day

formula_version

created_at
```

Formule pripadaju Analysis Specification-u.

# 31. `deal_scenarios`

Ako downside/base/upside imaju dovoljno različite inpute, koristiti child tabelu.

```text
id

deal_analysis_id

scenario_type

purchase_price
exit_price

cost_basis

profit
roi

holding_days

assumptions_json
```

`scenario_type`:

```text
DOWNSIDE
BASE
UPSIDE
```

Preferirati ovo umesto velikog broja `downside_*`, `base_*`, `upside_*` kolona.

# 32. `opportunity_assessments`

Istorijski decision-support rezultat.

```text
id

property_id
deal_analysis_id

as_of

recommended_action

opportunity_score
ranking_value

reason_codes_json
explanation_json

rules_version

created_at
```

`opportunity_score` može biti `null`.

Obavezno:

```text
recommended_action
!=
property.pipeline_status
```

# 33. `watch_rules`

Korisnički watch trigger.

```text
id

property_id

is_active

rule_type

threshold_numeric
rule_config_json

created_at
triggered_at
last_evaluated_at
```

Primer `rule_type`:

```text
PRICE_BELOW
PRICE_DROP_PERCENT
ANY_PRICE_CHANGE
DESCRIPTION_CHANGE
SELLER_CHANGE
NEW_OWNER_LISTING
```

# 34. `alerts`

Alert decision/delivery zapis.

```text
id

property_id
opportunity_assessment_id

channel

alert_type
priority

reason_code
dedupe_key

payload_json

status

created_at
sent_at
failed_at

provider_message_id
error_message
```

Status:

```text
PENDING
SENT
FAILED
SUPPRESSED
```

Alert decision i provider delivery rezultat nisu ista stvar.

`dedupe_key` treba da omogući sprečavanje identičnih ponovljenih alertova.

Tačno dedupe pravilo pripada application/alert logici.

# 35. `property_reviews`

Ručna korisnička evaluacija.

```text
id

property_id

reviewed_at

decision

manual_fmv
manual_fast_sale_value
manual_max_buy_price

notes

created_at
updated_at
```

`decision`:

```text
INTERESTING
NOT_INTERESTING
UNSURE
```

# 36. `interactions`

Acquisition događaji.

```text
id

property_id

interaction_type
occurred_at

notes

created_at
```

Tip:

```text
CALL
MESSAGE
VISIT
DUE_DILIGENCE
OFFER
COUNTEROFFER
OTHER
```

Strukturirani tipovi mogu dobiti child tabelu kada je potrebna.

# 37. `call_feedback`

Extension za `CALL`.

```text
interaction_id

seller_motivation
reason_for_sale

lowest_indicated_price

cash_preferred
desired_closing_days

viewing_available

claimed_registered
claimed_owner_1_1
claimed_mortgage

tenant_present

structured_notes_json
```

Sve nepoznato ostaje `null`.

`claimed_*` predstavlja tvrdnju, ne verified fact.

# 38. `visit_feedback`

Extension za `VISIT`.

```text
interaction_id

condition_category

estimated_renovation_low
estimated_renovation_base
estimated_renovation_high

layout_score
light_score
noise_score
building_score
entrance_score
parking_score

elevator_verified

visible_defects_json

manual_fmv
manual_fast_sale_value
manual_max_buy_price

notes
```

# 39. `offers`

Stvarna korisnička ponuda.

```text
id

property_id

offered_at

amount
currency

offer_type
conditions_json

status

seller_response_at
counteroffer_amount

notes

created_at
updated_at
```

Status:

```text
OPEN
ACCEPTED
REJECTED
COUNTERED
WITHDRAWN
EXPIRED
```

# 40. `skip_records`

Strukturiran razlog ručnog odbacivanja kandidata.

```text
id

property_id

reason_code
notes

skipped_at
```

Reason codes:

```text
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
```

# 41. `property_outcomes`

Kasnije poznat outcome property-ja.

```text
id

property_id

outcome_type
outcome_date

sale_price
currency

confidence

source_kind
source_reference

notes

created_at
```

Tip:

```text
STILL_ACTIVE
REMOVED_UNKNOWN
RELISTED
LIKELY_SOLD
CONFIRMED_SOLD
BOUGHT_BY_USER
LOST_TO_OTHER_BUYER
SALE_CANCELLED
OTHER
```

Obavezno razlikovati:

```text
LIKELY_SOLD
!=
CONFIRMED_SOLD

REMOVED_UNKNOWN
!=
CONFIRMED_SOLD
```

# 42. `shadow_deals`

Simulirana investiciona odluka za validation/backtesting.

```text
id

property_id

created_at

simulated_buy_date
simulated_buy_price

assumed_total_cost_basis

expected_exit_price
expected_holding_days
expected_profit

linked_deal_analysis_id

status
```

Status:

```text
OPEN
CLOSED
ABANDONED
```

Kasnije, ako postoji pouzdan ground truth:

```text
actual_observed_outcome
actual_observed_price
actual_observed_date
```

Originalne assumptions shadow deal-a ostaju istorijski sačuvane.

# 43. Model Versioning

Analytical istorijski rezultat mora sadržati relevantnu version oznaku direktno ili preko reference.

Primeri komponenti:

```text
MATCHING
VALUATION
LIQUIDITY
RISK
LLM_PROMPT
DEAL_FORMULA
OPPORTUNITY_RULES
```

Opcioni registry:

```text
model_versions
```

sa:

```text
id
component
version
description
activated_at
deactivated_at
config_hash
created_at
```

Ne versionirati svaki code commit.

Versionirati semantic logiku čija promena utiče na interpretaciju istorijskih rezultata.

# 44. Provenance

Za decision-relevant podatak sistem mora, gde je bitno, moći da kaže odakle dolazi.

Primer:

```text
risk flag
source_kind = LLM
source_reference = llm_analysis_id
```

Primer:

```text
elevator
source_kind = VERIFIED_MANUAL
source_reference = visit_feedback_id
```

Ne graditi generički EAV/provenance sistem za svako polje.

# 45. Manual Override

Originalni scraped podatak se ne menja da bi se simulirala ručna korekcija.

Primer:

```text
listing.floor = 5
```

Korisnik utvrdi da je stvarna vrednost:

```text
4
```

Scraped vrednost ostaje istorijska činjenica.

Effective property data može koristiti manual override.

## `property_overrides`

Uvesti tek kada manual override workflow postane potreban:

```text
id

property_id

field_name
value_json

source_kind

reason

created_at
updated_at
```

`source_kind`:

```text
MANUAL
VERIFIED_MANUAL
```

# 46. Effective Property Data

Analytical moduli treba da koriste jasno definisan effective property representation.

Konceptualni precedence:

```text
VERIFIED_MANUAL
>
MANUAL OVERRIDE
>
reliable structured source data
>
derived inference
>
LLM inference
>
UNKNOWN
```

Tačno pravilo može zavisiti od polja.

Na primer, LLM ne sme pobediti pouzdan structured source field za površinu.

# 47. Canonical Property Values

`properties` može sadržati current effective/canonical vrednosti radi performansi.

Ali za bitne podatke mora biti moguće utvrditi poreklo.

Nije potreban potpuni event-sourcing sistem.

Potrebna je samo dovoljna provenance i originalna history.

# 48. `property_analysis_state`

Current operational analytical state.

Ne koristiti jedan generički `analysis_status`.

Predlog:

```text
property_id

features_status
matching_status

valuation_status
liquidity_status
llm_status
risk_status
deal_status
opportunity_status

last_analysis_started_at
last_analysis_completed_at

last_error

updated_at
```

Statusi:

```text
NOT_RUN
PENDING
RUNNING
SUCCESS
FAILED
STALE
```

Historical analysis ostaje u odgovarajućim analytical tabelama.

# 49. Stale Results

Kada relevantan input promeni validnost trenutnog analytical output-a:

```text
current state = STALE
```

Stari istorijski rezultat se ne briše.

Primer:

```text
price changed
→ current deal analysis stale
→ old deal_analysis row remains
→ new deal analysis is calculated
```

# 50. `job_runs`

Operational summary važnog background run-a.

```text
id

job_type
source_id

started_at
finished_at

status

items_discovered
items_processed
items_changed
items_failed

error_summary

created_at
```

Ne koristiti za svaki sitan internal function call.

# 51. Per-request Crawl Telemetry

Ne uvoditi persistent `crawl_attempts` tabelu po default-u.

Detaljni request telemetry primarno pripada logovima.

Persistent request record uvodi se samo ako se pojavi konkretna operativna potreba.

# 52. Current Result References

Ako dashboard query performance to kasnije zahteva, `properties` može imati:

```text
current_valuation_id
current_liquidity_assessment_id
current_risk_assessment_id
current_deal_analysis_id
current_opportunity_assessment_id
```

Ovo su cache/reference polja.

Istorijske analytical tabele ostaju source of truth.

# 53. Data Quality

Ako Data Quality postane samostalan reusable rezultat, može se uvesti:

```text
data_quality_assessments
```

sa:

```text
id

property_id
as_of

score

missing_critical_fields_json
positive_factors_json

rules_version

created_at
```

Ako ga u početku koristi samo valuation, može ostati deo valuation result/input-a.

Ne duplirati isti canonical score na više mesta.

# 54. Multi-Currency

Originalni iznos i currency uvek ostaju sačuvani.

Primer:

```text
asking_price = 21000000
currency = RSD
```

Ako se radi FX conversion, derived rezultat treba da zna:

```text
converted_amount
conversion_currency
fx_rate
fx_rate_date
```

Ne prepisivati originalni iznos.

Ne uvoditi FX subsystem dok nije potreban.

# 55. Property Merge

Ako se utvrdi da dva property entiteta predstavljaju istu fizičku nekretninu, merge mora sačuvati:

* listing-e;
* listing history;
* matching history;
* analytical history;
* reviews;
* interactions;
* offers;
* outcomes;
* provenance samog merge-a.

Može postojati:

```text
property_merges
```

sa:

```text
id

source_property_id
target_property_id

reason

performed_by
performed_at
```

Source property se ne hard-delete-uje.

# 56. Property Split

Ako je automatic matching spojio različite nekretnine, manual split mora biti moguć.

Zbog toga:

* originalni listing identiteti ostaju sačuvani;
* listing history ostaje vezana za originalne listing-e;
* derived aggregates se mogu ponovo izračunati;
* historical analysis se ne falsifikuje naknadnim rewrite-om.

# 57. Relisting

Novi listing ID ne znači automatski novi property.

Ako matching pronađe postojeći property:

```text
new listing
→ existing property
```

novi listing ostaje poseban red.

`relist_count` je derived property podatak.

# 58. Property Market Age

`property_market_age_days` treba da bude izračunljiv iz property/listing istorije.

Može biti cache-ovan u `property_features`.

Ne koristiti current listing age kao zamenu za property market age.

# 59. Indeksi

Tačne indekse određuju realni query pattern-i i migrations.

Minimalno treba podržati sledeće efikasne pristupe.

## Listings

```text
UNIQUE(source_id, external_listing_id)

property_id

status

next_check_at

(source_id, status)

last_seen_at
```

## Listing Events

```text
(listing_id, detected_at)

(event_type, detected_at)
```

## Properties

Relevantni filteri:

```text
property_type
pipeline_status
city
municipality
micro_location
```

Ako postoji PostGIS geometry, koristiti spatial index.

## Matching

```text
listing_id
candidate_property_id
status
```

## Analytical history

Za:

```text
valuations
liquidity_assessments
risk_assessments
deal_analyses
opportunity_assessments
```

podržati efikasno:

```text
property_id + created_at/as_of DESC
```

## Alerts

```text
status
created_at
property_id
dedupe_key
```

# 60. Soft Delete / History

U normalnom radu ne hard-delete-ovati ključne istorijske entitete:

```text
properties
listings
listing_events
matching history

valuations
risk assessments
deal analyses
opportunity assessments

alerts
interactions
offers
outcomes
```

Lifecycle/state rešavati statusima gde je moguće.

# 61. Retention

Dugoročno čuvati:

```text
properties
listings
listing_events
matching history
canonical normalized data
important analytical history
manual feedback
interactions
offers
outcomes
```

Potencijalno kraći retention mogu imati:

```text
raw HTML
duplicate raw payloads
temporary fetch payloads
large transient error payloads
```

Tačna retention politika pripada Deployment/Operations dokumentu.

# 62. Schema Migrations

Sve schema promene moraju koristiti migrations.

Semantička promena podatka zahteva novi jasan model/polje, ne samo rename.

Primer:

```text
registered
```

ne sme tiho promeniti značenje iz:

```text
seller claims registered
```

u:

```text
verified registered
```

To su različite činjenice.

# 63. Minimalni Initial Subset

Ovaj dokument opisuje ciljnu semantiku.

Ne kreirati sve tabele prvog dana.

Početni ingestion/data foundation može koristiti samo:

```text
sources
source_runtime_state

properties
listings
listing_events

property_listing_links

property_features

job_runs
```

ili još manji podskup ako phase plan tako zahteva.

Kasnije faze uvode analytical i feedback entitete kada postanu potrebni.

# 64. Zabranjeno Prerano Modelovanje

Ne praviti desetine praznih tabela zato što su opisane u ovom dokumentu.

Pravilo:

> tabela se uvodi kada njena funkcionalnost ulazi u aktivni implementation scope.

Ovaj dokument određuje buduću semantiku kako kasnija evolucija ne bi zahtevala pogrešan redesign.

# 65. Ključne Database Invarijante

1. `(source_id, external_listing_id)` jedinstveno identifikuje source listing kada source ima stabilan ID.

2. `Property != Listing`.

3. Više listing-a može pripadati istom property-ju.

4. Jedan listing ne može imati dve current canonical property veze.

5. Listing removal ne briše listing niti njegovu istoriju.

6. `REMOVED listing != SOLD property`.

7. `null` se ne interpretira kao `false` ili `0`.

8. Verified manual podatak ne sme biti tiho prepisan automatskim podatkom.

9. Scraped claim nije isto što i verified fact.

10. Finansijski iznosi ne koriste floating-point.

11. Historical analytical result ostaje vezan za vreme i version logike.

12. Current analytical reference nije zamena za analytical history.

13. Merge/split ne sme uništiti originalni listing identitet i history.

14. Derived/cache podatak mora biti ponovo izračunljiv iz relevantnih canonical inputa.

15. Backtesting mora moći da razlikuje podatke dostupne u vreme analize od podataka koji su postali poznati kasnije.

# 66. Relationship Overview

```text
SOURCE
│
├── SOURCE_RUNTIME_STATE
│
├── LISTING
│   ├── LISTING_RAW_RECORDS
│   ├── LISTING_EVENTS
│   ├── IMAGES
│   └── LLM_ANALYSES
│
└── TRANSACTION_RECORDS
    └── TRANSACTION_PROPERTY_MATCHES


PROPERTY
│
├── LISTINGS
│   └── PROPERTY_LISTING_LINKS
│
├── PROPERTY_MATCH_CANDIDATES
├── PROPERTY_FEATURES
├── LOCATION / LOCATION_ASSIGNMENTS
│
├── COMPARABLE_SETS
│   └── COMPARABLE_ITEMS
│
├── VALUATIONS
├── LIQUIDITY_ASSESSMENTS
├── FAST_SALE_ESTIMATES
│
├── RISK_ASSESSMENTS
│   └── RISK_FLAGS
│
├── DEAL_ANALYSES
│   └── DEAL_SCENARIOS
│
├── OPPORTUNITY_ASSESSMENTS
├── WATCH_RULES
├── ALERTS
│
├── PROPERTY_REVIEWS
├── PROPERTY_OVERRIDES
│
├── INTERACTIONS
│   ├── CALL_FEEDBACK
│   └── VISIT_FEEDBACK
│
├── OFFERS
├── SKIP_RECORDS
├── PROPERTY_OUTCOMES
├── SHADOW_DEALS
│
└── PROPERTY_MERGES
```

# 67. Analytical Relationship

Konceptualno:

```text
PROPERTY
↓
COMPARABLE SET
↓
VALUATION
↓
LIQUIDITY / FAST-SALE
↓
RISK
↓
DEAL ANALYSIS
↓
OPPORTUNITY ASSESSMENT
↓
ALERT
```

Ne mora svaki entitet imati foreign key ka svakom prethodnom entitetu.

Ali mora biti moguće utvrditi koje relevantne analytical inpute/resultate je kasnija recommendation koristila.

# 68. Historical Relationship

```text
SOURCE
↓
LISTING
↓
LISTING EVENTS
↓
PROPERTY MATCHING
↓
PROPERTY
↓
ANALYTICAL HISTORY
↓
HUMAN FEEDBACK
↓
OUTCOME
```

Current `properties` red nije dovoljan za rekonstrukciju istorije.

# 69. Canonical Ownership

Za pitanja o persistence semantici koristi ovaj dokument.

Za:

```text
kada PRICE_CHANGED nastaje?
```

koristi:

```text
docs/04-scraping-specification.md
```

Za:

```text
kako se biraju comps ili računa FMV/Max Buy?
```

koristi:

```text
docs/05-analysis-specification.md
```

Za:

```text
kako API izlaže podatak?
```

koristi:

```text
docs/06-api-ui-specification.md
```

Za:

```text
kada se određena tabela implementira?
```

koristi:

```text
docs/07-phase-plan.md
```

# 70. Konačni Model Princip

Baza ne treba samo da odgovori:

> Kako listing izgleda sada?

Mora dugoročno omogućiti odgovor:

> **Šta smo u određenom trenutku znali o ovoj fizičkoj nekretnini, odakle su podaci došli, kako su se njeni listing-i menjali, kako ju je sistem tada analizirao, šta je korisnik uradio i šta se kasnije dogodilo?**

Zato od početka treba pravilno razlikovati:

```text
CURRENT STATE
HISTORY
PROVENANCE
ANALYTICAL VERSION
HUMAN FEEDBACK
OUTCOME
```

Ako se sačuva samo trenutno stanje listing-a, gubi se najveći deo dugoročne vrednosti sistema.

