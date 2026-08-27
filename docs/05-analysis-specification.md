# Distressed Property Radar — Analysis Specification

## 1. Svrha dokumenta

Ovaj dokument definiše kako Distressed Property Radar analizira već prikupljene, normalizovane i povezane podatke.

Source of truth je za:

- Effective Property Data;
- Data Quality;
- Comparable Engine;
- Fair Market Value;
- Valuation Confidence;
- Liquidity;
- Fast-Sale Value;
- LLM extraction;
- Seller Motivation;
- Negotiability;
- Risk Engine;
- renovation assumptions;
- Deal Engine;
- Max Buy Price;
- downside/base/upside scenarije;
- Opportunity Assessment;
- Recommended Action;
- analytical invalidation i re-analysis;
- explainability;
- analytical versioning i backtesting.

Ne definiše:

- scraping;
- SQL šemu;
- API/UI;
- deployment;
- detaljan test matrix;
- implementation order.

Za te oblasti koristiti odgovarajuće canonical dokumente.

# 2. Osnovni analytical princip

Sistem ne odgovara samo:

> Koliko property vredi?

Mora odvojeno odgovoriti na:

1. koliko kvalitetne podatke imamo;
2. koje nekretnine su stvarno comparable;
3. koliki je FMV;
4. koliko smo sigurni u FMV;
5. koliko je property likvidan;
6. kolika je konzervativna Fast-Sale vrednost;
7. koliko je seller verovatno motivisan;
8. koliko je asking verovatno pregovarljiv;
9. koji rizici postoje;
10. koliko maksimalno smemo da platimo;
11. kako deal izgleda u downside/base/upside scenariju;
12. da li property sada zaslužuje ljudsku pažnju.

Rezultati moraju ostati dovoljno odvojeni da jedan visok score ne sakrije loš fundamentalni signal.

Centralni princip:

> **Hard blocker se ne kompenzuje visokim opportunity score-om.**

# 3. Analytical flow

Osnovni dependency flow:

    Effective Property Data
    ↓
    Data Quality
    ↓
    Comparable Selection
    ↓
    Fair Value
    ↓
    Valuation Confidence
    ↓
    Liquidity
    ↓
    Fast-Sale Estimate
    ↓
    Seller / LLM Signals
    ↓
    Risk
    ↓
    Deal Engine
    ↓
    Opportunity Assessment
    ↓
    Recommended Action

Nezavisni koraci mogu raditi paralelno.

Na primer, LLM extraction ne mora čekati valuation ako ne koristi njen rezultat.

# 4. Effective Property Data

Analitički moduli ne koriste proizvoljno prvi listing jednog property-ja.

Moraju dobiti strukturiran trenutni skup najboljih poznatih podataka:

`EffectivePropertyData`.

Konceptualni precedence:

    VERIFIED_MANUAL
    >
    MANUAL_OVERRIDE
    >
    reliable structured source value
    >
    cross-source consensus
    >
    derived inference
    >
    LLM inference
    >
    UNKNOWN

Tačan precedence zavisi od atributa.

LLM inference, na primer, ne sme pobediti pouzdano strukturirano `size_m2` polje.

## Conflict handling

Ako dva source-a daju:

    Listing A: 72 m²
    Listing B: 74 m²

ne uzimati proizvoljno prvi.

Resolver treba da razmotri:

- manual/verified podatke;
- kvalitet source-a;
- cross-source consensus;
- provenance;
- confidence.

Ako konflikt ne može pouzdano da se reši, dozvoljen rezultat je npr:

    value = 72
    confidence = 0.65
    conflict = true

ili `UNKNOWN` kada ni jedna vrednost nije dovoljno pouzdana.

# 5. Data Quality

Data Quality meri:

> koliko su ulazni podaci kompletni i korisni za analizu.

Ne meri:

> koliko je valuacija verovatno tačna.

To je `Valuation Confidence`.

Za APARTMENT V1 važni inputi uključuju:

- location;
- `size_m2`;
- rooms;
- floor;
- total floors;
- elevator;
- building type;
- condition;
- heating;
- parking;
- construction year;
- description;
- images;
- seller information;
- legal claims.

## V1 Data Quality heuristika

Početne težine:

    Location precision        20
    Size                      15
    Rooms                     10
    Floor                      8
    Elevator                   7
    Building type              7
    Condition                 10
    Heating                    4
    Parking                    4
    Construction year          3
    Description quality        5
    Images                     4
    Legal claims               3
    -----------------------------
    Total                    100

Ove težine mere informativnost, ne tržišnu vrednost atributa.

Moraju biti konfigurabilne/versioned.

## Critical missing data

Data Quality mora odvojeno vratiti `missing_critical_fields`.

Primer:

    Data Quality = 47
    missing_critical_fields:
    - usable micro-location
    - condition

`size_m2 = UNKNOWN` može onemogućiti normalnu apartment valuation.

Vrlo neprecizna lokacija može imati isti efekat.

Visok zbirni Data Quality score ne sme sakriti critical missing field.

# 6. Comparable Engine

Cilj Comparable Engine-a je da pronađe tržišne podatke dovoljno slične target property-ju da imaju smisla za valuation.

Ne koristiti prosečnu cenu cele opštine kao glavni comp metod.

## Comparable tipovi

Razlikovati:

    TRANSACTION
    LISTING
    PROPERTY_HISTORY

Konceptualni prioritet:

    reliable recent transaction
    >
    reliable older transaction
    >
    recent high-similarity listing
    >
    broad market aggregate

Broad aggregate je fallback/context, ne idealan comp.

Aktivni listing predstavlja asking konkurenciju.

Ne predstavlja realizovanu transaction cenu.

# 7. Comparable Candidate Generation

Za APARTMENT V1 početni kandidat može zahtevati približno:

    property_type = APARTMENT
    same relevant city/market
    distance <= configured radius
    size difference <= 25%

Ovo je široki candidate filter.

Nakon njega se radi detailed similarity ranking.

# 8. Adaptive Comparable Radius

Ne koristiti jedan radijus za svaki property.

Početni search može biti:

    300 m

Ako nema dovoljno kvalitetnih comps:

    300 m
    → 500 m
    → 800 m
    → 1,200 m

Širenjem radijusa smanjuje se location similarity.

Ne širiti beskonačno samo da bi se dostigao minimalni broj comps.

Ako nema kvalitetnih comps:

> `LOW CONFIDENCE` ili `INSUFFICIENT_DATA` je validan rezultat.

# 9. Size Filtering

Početni idealni size raspon:

    target ±15%

Fallback:

    target ±25%

Za ekstremnije kvadrature dozvoljena su segment-specific pravila ili apsolutna tolerancija.

Na primer, ista procentualna tolerancija ne mora imati jednako tržišno značenje za 30 m² i 120 m².

# 10. Comparable Similarity

V1 koristi deterministički weighted similarity score.

Početni okvir:

    Location             25%
    Size                 20%
    Condition            15%
    Rooms                10%
    Building type        10%
    Floor/elevator        8%
    Construction age      5%
    Parking               3%
    Heating               2%
    Other                 2%
    -------------------------
    Total               100%

Težine moraju biti configurable/versioned.

## Location similarity

Koristiti prvenstveno:

- physical distance;
- microzone;
- street/building informacije kada postoje.

Konceptualno:

    same building / extremely close → very high
    same microzone                  → high
    same neighborhood               → medium
    same municipality only          → low

## Size similarity

    size_diff_pct =
    abs(comp_size - target_size) / target_size

Početno mapiranje:

    <= 5%   → 1.00
    <= 10%  → 0.90
    <= 15%  → 0.75
    <= 20%  → 0.55
    <= 25%  → 0.30
    > 25%   → reject/fallback

Granice su konfigurabilne.

## Rooms similarity

Početno:

    same rooms       → 1.0
    difference 0.5   → 0.8
    difference 1.0   → 0.5
    larger difference → low/reject

Ako rooms nisu pouzdano normalizovane, ne davati ovom signalu lažnu težinu.

## Condition

Početne kategorije:

    NEW_OR_LUXURY
    RENOVATED
    GOOD
    DATED_HABITABLE
    NEEDS_RENOVATION
    MAJOR_RENOVATION
    UNKNOWN

`UNKNOWN` nije automatski prosečno stanje.

Treba prvenstveno da smanji confidence.

# 11. Comparable Recency

## Transaction

Stariji transaction comp dobija niži recency weight.

Početni okvir:

    0–90 days    → full weight
    91–180       → slight penalty
    181–365      → stronger penalty
    >365         → low weight / fallback

Kasnije se može koristiti market-index adjustment.

## Listing

Listing comp treba jasno označiti kao `LISTING`.

Ne tretirati asking cenu kao transaction cenu.

Dok nema kvalitetnog lokalnog asking-vs-transaction dataset-a, listing comps prvenstveno služe kao:

> current market asking context / ceiling

i treba da imaju niži `source_quality_weight`.

Ne koristiti univerzalno pravilo poput:

    every asking price - 10%

za svako tržište i segment.

# 12. Comparable Outliers

Preferirati robust metode:

- weighted median;
- IQR;
- MAD.

Ne koristiti običan mean kao jedini valuation estimator.

Odbačeni comp mora imati reason.

Primeri:

    PRICE_OUTLIER
    LOW_SIMILARITY
    TOO_OLD
    LOCATION_TOO_FAR

Outlier se ne uklanja tiho.

# 13. Comparable Count Quality

Početna smernica:

    >= 8   high-quality comps → ideal
    4–7                       → acceptable
    1–3                       → weak
    0                         → none

Broj nije dovoljan sam po sebi.

Osam slabih listing comps nije isto što i osam veoma sličnih recent transactions.

Comp count utiče na Valuation Confidence.

# 14. Fair Market Value

V1 mora biti transparentan i reproducibilan.

Osnovni flow:

    ranked comps
    ↓
    reject invalid/outliers
    ↓
    robust weighted €/m² estimate
    ↓
    target size
    ↓
    explicit target adjustments
    ↓
    FMV LOW / BASE / HIGH

## Weighted comp value

Comp weight može biti:

    similarity_weight
    × source_quality_weight
    × recency_weight

Primer početnog source quality odnosa:

    transaction comp ≈ 1.0
    listing comp     ≈ 0.4–0.7

Tačne vrednosti su konfigurabilne.

Central estimate može koristiti weighted median ili drugi transparentan robust weighted estimator.

# 15. Target Property Adjustments

V1 treba da koristi mali broj razumljivih korekcija, npr:

- condition;
- floor/elevator;
- parking;
- building type;
- očigledni micro-location subfactor.

Ne praviti desetine ručnih adjustment-a bez podataka koji ih opravdavaju.

Početni safeguard može biti:

    max positive combined adjustment = +15%
    max negative combined adjustment = -25%

Granice su konfigurabilne.

Ako je za property potrebna korekcija izvan razumnog opsega, verovatnije je da comparable set nije dovoljno sličan.

# 16. FMV Output

Obavezno:

    fair_value_low
    fair_value_base
    fair_value_high

Ne vraćati samo jednu preciznu vrednost.

Range treba da zavisi od:

- dispersion;
- comp count;
- comp similarity;
- Data Quality;
- transaction/listing mix;
- recency;
- adjustment uncertainty.

High-confidence valuation ima uži range.

Low-confidence valuation ima širi range.

Ne koristiti automatski fiksnih ±5% za svaki property.

# 17. Valuation Confidence

Valuation Confidence je odvojen od Data Quality.

Početni framework:

    Comparable Count Quality     20%
    Comparable Similarity        25%
    Transaction Data Share       20%
    Data Quality                 15%
    Price Dispersion             10%
    Recency                      10%
    --------------------------------
    Total                       100%

Ovo je početna heuristika koja kasnije mora biti kalibrisana.

## Strong penalties

Primeri:

- location poznata samo na municipality nivou;
- samo 1–2 comps;
- svi comps stari;
- svi comps su asking listings;
- unknown condition;
- veoma visok €/m² dispersion.

## Categories

    0–39    LOW
    40–59   LIMITED
    60–74   MODERATE
    75–89   HIGH
    90–100  VERY_HIGH

Opportunity rules mogu zahtevati minimalni confidence za ozbiljnije akcije.

# 18. Valuation Failure

Ako nema dovoljno smislenih inputa:

    status = INSUFFICIENT_DATA
    fair_value_low = null
    fair_value_base = null
    fair_value_high = null

Ne izmišljati FMV.

Property i dalje može završiti u `REVIEW` ako postoji drugi signal.

`INSUFFICIENT_DATA` nije tehnički failure.

# 19. Liquidity

Liquidity procenjuje:

> koliko je verovatno da standardan kupac relativno brzo kupi property kada je cena tržišno atraktivna.

Ne meri:

> koliko je stan vizuelno lep.

V1 faktori mogu uključiti:

- micro-location demand;
- size segment;
- rooms/layout proxy;
- floor;
- elevator;
- condition;
- legal/mortgageability signals;
- parking;
- building type;
- asking/FMV relation;
- inventory sličnih property-ja.

`UNKNOWN` signal prvenstveno smanjuje confidence, ne automatski liquidity score.

# 20. Liquidity Score

V1 može koristiti objašnjivi rules-based:

    liquidity_score = 0–100

uz:

    confidence
    positive_factors
    negative_factors
    unknown_important_factors

Primer:

    Liquidity = 84

    Positive:
    - high-demand microzone
    - common size segment
    - elevator
    - normal floor

    Negative:
    - weak parking

Size segmenti mogu imati različitu baznu likvidnost.

Takva pravila moraju biti market/config driven, ne univerzalna istina.

# 21. Fast-Sale Value

Fast-Sale Value je odvojena procena od FMV.

Dok nema dovoljno outcome podataka za probabilistički model, V1 ga konzervativno izvodi iz:

    FMV
    + Liquidity
    + market dispersion
    + Valuation Confidence

## Početna heuristic smernica

    HIGH liquidity:
    FMV base - 4% do 8%

    MEDIUM liquidity:
    FMV base - 7% do 12%

    LOW liquidity:
    FMV base - 10% do 18%

Ovo nisu trajne tržišne konstante.

Moraju biti configurable i kasnije kalibrisane.

Ako je Valuation Confidence slab, koristiti konzervativniji discount/range.

## Output

Minimalno:

    value_low
    value_base
    value_high
    target_days
    confidence

Fast-Sale `low` je posebno važan za downside scenario.

# 22. Budući Probabilistički Fast-Sale Model

Kada postoji dovoljno historical outcome podataka, poželjan model je:

    P(sale <= 30d | price)
    P(sale <= 60d | price)
    P(sale <= 90d | price)

Fast-Sale Price tada može biti:

> najveća cena za koju je `P(sale <= target_days) >= target_probability`.

Ne implementirati probabilistički model dok dataset ne opravda njegovu pouzdanost.

# 23. LLM Analysis

LLM služi za structured extraction iz nestrukturisanog source teksta.

LLM ne određuje:

- FMV;
- Max Buy Price;
- ROI;
- finalne finansijske formule;
- potvrđeno pravno vlasništvo.

Koristiti samo relevantan input, npr:

    title
    description
    selected seller metadata
    selected price-history summary

Ne slati kompletan property objekat bez potrebe.

# 24. LLM Output

Minimalna semantika treba da obuhvati:

    seller_motivation:
      level: LOW | MEDIUM | HIGH | UNKNOWN
      confidence
      evidence[]

    negotiability:
      level: LOW | MEDIUM | HIGH | UNKNOWN
      confidence
      evidence[]

    cash_preference:
      value: true | false | null
      confidence
      evidence[]

    reason_for_sale:
      value
      confidence
      evidence[]

    condition:
      value
      confidence
      evidence[]

    legal_claims[]
    risk_signals[]

Output mora biti schema-validated.

Invalid output ne postaje domain truth.

# 25. Evidence

Za važne LLM-derived signale čuvati kratak supporting evidence.

Primer:

> „Za kupca koji može brzo da realizuje moguć dodatni dogovor.“

Ne čuvati ceo description kao `evidence` samo zato što je model koristio ceo tekst.

Evidence predstavlja razlog zbog kog je signal izveden.

# 26. Reason for Sale

Početne kategorije:

    MOVING
    MOVING_ABROAD
    NEEDS_LIQUIDITY
    INHERITANCE
    DIVORCE
    BUSINESS_LIQUIDITY
    BOUGHT_ANOTHER_PROPERTY
    VACANT_PROPERTY
    INVESTOR_EXIT
    TIME_DEADLINE
    OTHER
    UNKNOWN

Ako razlog nije naveden ili dovoljno pouzdano impliciran:

    UNKNOWN

LLM ne sme da ga izmisli.

# 27. Seller Motivation

LLM nije jedini signal.

Seller Motivation Engine može kombinovati:

- language/LLM signals;
- price cuts;
- property market age;
- relisting;
- seller/agency changes;
- manual call feedback.

Početni V1 framework može biti:

    Language / LLM signals       35%
    Price history                30%
    Market age                   15%
    Relisting / seller changes   10%
    Manual feedback              10%

Ako postoji pouzdan manual feedback, on može imati prioritet nad automatskim signalima.

Težine su versioned/configurable.

Output može sadržati:

    level
    score
    confidence
    reasons

Numeric score je pomoćno ranking sredstvo.

Ne treba glumiti precizno poznatu seller psihologiju.

# 28. Negotiability

Negotiability znači:

> procenu koliko je verovatno da asking nije seller-ov realni minimum.

Inputi mogu uključiti:

- seller language;
- broj i veličinu price cuts;
- market age;
- owner vs agency;
- seller motivation;
- manual `lowest_indicated_price`.

Output:

    LOW
    MEDIUM
    HIGH
    UNKNOWN

plus confidence.

# 29. Expected Negotiated Price

LLM ne sme proizvoljno da izmisli:

> seller će prihvatiti €132k.

Automatska V1 procena može biti:

    asking_price
    -
    deterministic negotiation adjustment

ako za takvu heuristiku postoje eksplicitna pravila.

Mnogo pouzdaniji input je manual:

    seller_floor_from_call

Kada postoji manual indicated floor, on treba jasno da utiče na negotiation analysis prema provenance/precedence pravilima.

# 30. Risk Engine

Risk Engine ne potvrđuje da je property bezbedan za kupovinu.

Odgovara:

> Koji poznati ili potencijalni problemi zahtevaju oprez, proveru ili blokadu?

Može koristiti:

- structured listing fields;
- source claims;
- LLM extraction;
- property/listing history;
- call feedback;
- visit feedback;
- verified facts.

# 31. Risk Gate

Finalni gate:

    PASS
    VERIFY
    BLOCK

`PASS` znači:

> sistem trenutno nema poznat hard blocker.

Ne znači:

> profesionalni legal due diligence je završen.

`VERIFY` znači da je važan podatak nepoznat, konfliktan ili zahteva proveru.

`BLOCK` znači da current analytical rules smatraju poznati rizik neprihvatljivim za normalno napredovanje deal-a.

# 32. Hard Risk Signals

Početni code-ovi mogu uključiti:

    PARTIAL_OWNERSHIP
    OWNERSHIP_UNKNOWN
    UNREGISTERED_OR_UNCLEAR
    ACTIVE_DISPUTE
    LEGALIZATION_UNCLEAR
    OCCUPIED_PROPERTY
    AUCTION_SPECIAL_CONDITIONS
    CRITICAL_DOCUMENTATION_UNKNOWN
    PROPERTY_TYPE_MISMATCH
    SUSPICIOUS_LISTING

Neće svi biti automatski detektabilni u APARTMENT V1.

Nepoznat pravni podatak ne treba pretvarati u lažni `PASS`.

# 33. Soft Risks

Primeri:

    GROUND_FLOOR
    BASEMENT_OR_SEMI_BASEMENT
    TOP_FLOOR_RISK
    HIGH_FLOOR_NO_ELEVATOR
    BUSY_STREET
    POOR_PARKING
    MAJOR_RENOVATION
    POOR_BUILDING
    LOW_LIGHT
    ODD_LAYOUT

Soft risk može uticati na:

- valuation;
- liquidity;
- renovation;
- confidence;
- deal economics.

Ne mora automatski blokirati property.

# 34. Risk Flag

Svaki signal treba da može imati:

    code
    severity
    gate_effect
    source/provenance
    confidence
    evidence

Severity:

    INFO
    LOW
    MEDIUM
    HIGH
    CRITICAL

`severity` i `gate_effect` nisu ista stvar.

Primer:

    code = PARTIAL_OWNERSHIP
    severity = CRITICAL
    gate_effect = BLOCK

# 35. Risk Conflict Resolution

Ako listing kaže:

    uknjižen

a verified manual podatak kaže:

    nije uknjižen

current risk koristi pouzdaniji verified podatak.

Originalna source tvrdnja ostaje u istoriji.

Claim i verified fact nisu ista stvar.

# 36. Renovation

V1 ne zahteva Computer Vision.

Renovation input može biti:

- manual estimate;
- rules-based category estimate;
- `UNKNOWN`.

Početne kategorije:

    NONE
    COSMETIC
    MODERATE
    FULL
    UNKNOWN

Koristiti range gde je preciznost slaba.

Na primer, market/config može definisati okvir poput:

    COSMETIC: 2k–4k
    MODERATE: 7k–15k

ali konkretni defaults moraju biti konfigurabilni i kasnije kalibrisani.

Nepoznat značajan renovation cost ne treba automatski postati `0`.

# 37. Deal Engine

Deal Engine je deterministički.

LLM se ne koristi za finansijsku matematiku.

Koristiti `Decimal` / database `NUMERIC` semantiku.

Minimalni inputi:

    assumed_purchase_price
    purchase_costs
    renovation
    sale_costs
    taxes
    financing_costs
    holding_costs
    risk_reserve
    other_costs
    exit_price
    holding_days

Razlikovati:

    asking_price
    assumed_purchase_price

Jedan property može imati više purchase-price scenarija.

# 38. Cost Profiles

Tax/cost assumptions ne smeju biti rasute kao konstante kroz codebase.

Deal calculation koristi versioned/configured Cost Profile.

Cost Profile određuje:

- purchase-side costs;
- taxes;
- notary/lawyer;
- agency;
- holding;
- financing;
- sale-side costs;
- druge relevantne stavke.

Ne pretpostavljati da svi porezi pripadaju istoj fazi transakcije.

# 39. Total Cost Basis

Konceptualno:

    TOTAL COST BASIS
    =
    Purchase Price
    + Purchase-Side Costs
    + Renovation
    + Financing Costs
    + Holding Costs
    + Other Acquisition/Holding Costs

Sale-side costs ne treba duplirati u acquisition cost basis-u ako se već oduzimaju od sale proceeds.

Tačna klasifikacija mora biti stabilna u `deal_formula_version`.

# 40. Net Sale Proceeds

    NET SALE PROCEEDS
    =
    Sale Price
    - Sale Costs
    - Sale-Side Taxes
    - Other Exit Costs

# 41. Net Profit

    NET PROFIT
    =
    Net Sale Proceeds
    -
    Total Cost Basis

Sve cost kategorije moraju biti uključene tačno jednom.

# 42. ROI

    ROI
    =
    Net Profit
    /
    Capital Invested

`Capital Invested` mora imati eksplicitnu definiciju u formula version-u.

Za jednostavan cash V1 može približno odgovarati cash-u uloženom do prodaje.

Ne menjati imenilac kroz različite delove sistema.

# 43. Annualized ROI

Ako se koristi `annualized_roi`, formula mora biti eksplicitno definisana i versioned.

Ne mešati:

    linear annualization

i:

    compound annualization

u različitim rezultatima.

Ako je izabrana compound formula, ne koristiti usput:

    ROI × 365 / holding_days

kao drugu definiciju iste metrike.

# 44. Capital Days

Početna V1 aproksimacija:

    capital_days
    =
    capital_invested
    ×
    holding_days

Kasnije je moguće uvesti precizniji cash-flow based model.

# 45. Profit per Capital-Day

    profit_per_capital_day
    =
    net_profit
    /
    capital_days

Koristi se prvenstveno za poređenje kapitalne efikasnosti deal-ova.

Jedinica mora biti jasna.

# 46. Risk Reserve

Risk Reserve je eksplicitna stavka.

Ne skrivati je unutar `other_costs`.

Može biti:

- fixed amount;
- procenat purchase price-a;
- druga transparentna formula iz Investment Profile-a.

# 47. Required Profit

Investment Profile može definisati:

- minimum fixed net profit;
- minimum ROI;
- oba.

Max Buy mora zadovoljiti stroži relevantni uslov.

# 48. Max Buy Price

Max Buy predstavlja najveću purchase cenu pri kojoj deal još zadovoljava definisane konzervativne investment uslove.

Konceptualno:

    MAX BUY
    =
    Conservative Exit Value
    - non-purchase costs
    - risk reserve
    - required profit

Ako određeni costs zavise od purchase price-a, formula nije običan subtraction.

Primer:

    purchase_cost = rate × BuyPrice

tada se rešava jednačina:

    ConservativeExit
    - FixedCosts
    - PercentageBuyCosts(BuyPrice)
    - RequiredProfit
    =
    BuyPrice

Koristiti:

- analytical solution; ili
- deterministic numeric solver.

Ne koristiti LLM solver.

# 49. Max Buy Constraints

Max Buy calculation mora koristiti konzervativan exit, prvenstveno Fast-Sale scenario prema current Investment Profile-u.

Ne računati Max Buy direktno iz optimističnog FMV High samo zato što daje bolji rezultat.

Ako su relevantni i minimum profit i minimum ROI, solver mora proveriti oba.

# 50. Required Negotiation

    required_negotiation_amount
    =
    asking_price
    -
    max_buy_price

Ako je rezultat `<= 0`, asking je već unutar Max Buy granice.

Za `asking_price > 0`:

    required_negotiation_pct
    =
    required_negotiation_amount
    /
    asking_price

Ova metrika je posebno korisna za određivanje koliko je potencijalni deal praktično dostižan.

# 51. Deal Scenarios

Obavezno najmanje:

    DOWNSIDE
    BASE
    UPSIDE

Svaki scenario čuva svoje assumptions.

## Downside

Treba da bude konzervativan, ali realističan.

Može koristiti:

- `fast_sale_low`;
- viši renovation cost;
- više holding costs;
- duži holding period;
- druge razumne downside pretpostavke.

Katastrofalni stress scenario, ako kasnije postoji, treba da bude poseban.

## Base

Tipično koristi:

- expected purchase price;
- `fast_sale_base`;
- base renovation;
- expected holding period.

## Upside

Može koristiti:

- `fast_sale_high` ili realističan near-FMV exit;
- niži renovation;
- kraći holding.

Upside ne sme biti glavni razlog za `CALL` ili `URGENT_CALL`.

# 52. Scenario Explainability

Za svaki scenario mora biti moguće odgovoriti:

> Zašto je profit baš ovaj?

Čuvati relevantne assumptions, uključujući:

- purchase price;
- exit;
- renovation;
- holding;
- costs;
- risk reserve.

Manual scenario override ne menja originalni automatski scenario.

To je novi/manual calculation context.

# 53. Opportunity Assessment

Opportunity Engine prvo proverava fundamentalne uslove.

Tek zatim radi ranking.

Redosled:

    hard gates
    ↓
    minimum required data
    ↓
    confidence requirements
    ↓
    economic thresholds
    ↓
    ranking
    ↓
    recommended action

Score ne sme da pretvori nevalidan deal u validan.

# 54. Minimum za Serious Financial Recommendation

Za finansijski zasnovan `URGENT_CALL` minimalno treba imati:

- usable asking price;
- usable size;
- usable location;
- valid valuation;
- Fast-Sale estimate;
- Cost Profile;
- Risk status;
- dovoljno relevantnog confidence-a.

Ako nešto od ovoga nedostaje, `CALL` eventualno može biti opravdan drugim razlogom, npr. prikupljanjem podataka.

Ali:

> `URGENT_CALL` zasnovan na flip ekonomici nije dozvoljen bez potrebne finansijske osnove.

# 55. Opportunity Hard Conditions

Pre `URGENT_CALL` očekuju se konfigurisani uslovi poput:

    Risk Gate != BLOCK
    FMV available
    Fast-Sale available
    Deal Analysis available
    Valuation Confidence >= minimum
    Liquidity >= minimum
    Expected Profit >= minimum
    Downside Profit >= minimum

Tačni threshold-i dolaze iz Investment Profile-a.

# 56. `VERIFY` Risk

`VERIFY` ne mora automatski sprečiti `CALL`.

Poziv može biti upravo način da se prikupi missing information.

Ali `VERIFY` može sprečiti da property bude predstavljen kao potpuno finansijski/pravni clear kandidat za sledeću ozbiljnu fazu.

# 57. Recommended Actions

V1 actions moraju biti rules-based i explainable.

## `IGNORE`

Primeri:

- jasno nema marginu;
- veoma daleko iznad Max Buy;
- van Investment Profile-a;
- hard `BLOCK` bez razloga za dalju proveru;
- toliko malo podataka da ne postoji ni drugi relevantan signal.

## `WATCH`

Primeri:

- property je fundamentalno interesantan;
- trenutna cena je previsoka;
- postoji istorija price cuts;
- gap do Max Buy je potencijalno dostižan;
- čekamo novi trigger.

## `REVIEW`

Primeri:

- potencijalni value anomaly;
- ograničen confidence;
- unresolved critical data;
- neobičan comparable dispersion;
- analiza zahteva ljudsku procenu pre akcije.

## `CALL`

Primeri:

- economics postaju dobri uz razuman negotiation;
- confidence je dovoljan;
- nema hard BLOCK;
- seller podatak vredi proveriti;
- poziv može ukloniti ključnu uncertainty.

## `URGENT_CALL`

Početni princip:

    asking <= Max Buy
    OR asking is sufficiently close to Max Buy

uz:

    expected profit >= target
    downside acceptable
    liquidity sufficiently strong
    valuation confidence sufficient
    risk != BLOCK

i:

- time-sensitive signal; ili
- neuobičajeno jak deal.

Time-sensitive signal može biti:

- new listing;
- veliki recent price cut;
- visok seller motivation;
- Watch threshold crossed.

## `DUE_DILIGENCE`

Ne znači:

> BUY.

Znači:

> economics i dostupni podaci opravdavaju ulaganje dodatnog vremena/novca u ozbiljnu proveru.

# 58. Opportunity Score

Opportunity Score može postojati samo kao pomoć za ranking.

Može koristiti normalizovane komponente poput:

- Expected Return Quality;
- Downside Safety;
- Liquidity;
- Valuation Confidence;
- Seller Opportunity;
- Negotiation Feasibility;
- Risk Adjustment.

Ne tretirati score kao business truth.

# 59. Economic Priority

Seller urgency nema veliku vrednost ako economics ne funkcioniše.

Primer:

    Seller Motivation = HIGH
    Net Profit = negative

ne sme završiti kao:

    URGENT_CALL

samo zato što seller deluje hitno.

Centralni princip:

> distress bez diskonta nije investiciona prilika.

# 60. Hard Gate nije Score Penalty

Zabranjen model:

    Value score      95
    Urgency score    90
    Legal blocker   -20
    -------------------
    Still excellent

Hard `BLOCK` se obrađuje pre score-a.

Ne može biti „nadjačan“ drugim komponentama.

# 61. Ranking Value

Action Queue ranking treba da favorizuje direktnu ekonomiku.

Mogući inputi:

- expected net profit;
- downside profit;
- ROI;
- annualized ROI;
- profit per capital-day;
- required negotiation %;
- liquidity;
- confidence.

Tačna ranking formula može evoluirati.

Recommended Action i Ranking Value ostaju odvojeni.

# 62. Watch Threshold Crossing

Ako:

    Max Buy = €140k

a Watch trigger:

    asking <= €143k

i cena padne:

    €150k → €142k

sistem prvo radi relevantnu re-analysis.

Tek potom odlučuje o alert-u.

Ne slati „deal“ alert samo zato što je stari threshold crossed ako je nova economics analiza loša.

# 63. Re-analysis

Relevantan input change označava odgovarajuće current analytical rezultate kao `STALE` i pokreće samo potreban downstream calculation.

Historical rezultat se ne briše.

Minimalni triggeri:

- new listing/property;
- price change;
- description change;
- seller change;
- manual call feedback;
- manual visit feedback;
- manual override;
- new relevant comparable data;
- location correction;
- property merge/split.

# 64. Price Change Invalidation

Price change obavezno invalidira:

    deal analysis
    opportunity assessment

Može promeniti i:

    seller motivation
    negotiability

jer postaje novi price-history signal.

Ne mora invalidirati FMV ako valuation model namerno ne koristi target asking price.

# 65. Description Change Invalidation

Description change invalidira najmanje:

    LLM analysis
    seller analysis
    relevant risk analysis
    opportunity

Ako novi extraction promeni property atribut kao:

    condition

onda invalidirati i module koji taj atribut koriste, npr:

    valuation
    liquidity
    fast-sale
    deal
    opportunity

# 66. Location Change Invalidation

Location correction invalidira najmanje:

    comparable set
    valuation
    valuation confidence
    liquidity
    fast-sale
    deal
    opportunity

# 67. Property Merge/Split Invalidation

Posle property merge/split-a ponovo proceniti relevantne:

    features
    comps
    valuation
    liquidity
    seller history
    risk
    deal
    opportunity

Historical results ostaju sačuvani kao rezultati tadašnjeg state-a.

# 68. New Comparable Data

Nova transaction informacija ne treba automatski da pokrene valuation svakog property-ja u bazi.

Koristiti selektivnu invalidaciju, npr:

    affected microzone
    +
    active/relevant properties

V1 može prvenstveno re-analyze:

- Action Queue;
- Watch;
- active acquisition candidates.

# 69. Analysis Status

Svaki analytical modul treba da razlikuje najmanje:

    NOT_RUN
    PENDING
    SUCCESS
    FAILED
    STALE
    INSUFFICIENT_DATA

`INSUFFICIENT_DATA` nije isto što i `FAILED`.

Primer validnog partial state-a:

    Valuation: SUCCESS
    LLM: FAILED
    Risk: VERIFY
    Deal: SUCCESS
    Opportunity: REVIEW

Property se može prikazati i kada svi enrichment moduli nisu uspeli.

# 70. Failure Fallbacks

## LLM unavailable

Koristiti deterministic seller/history signale.

LLM rezultat označiti kao unavailable/failed.

Ne blokirati ostatak sistema ako nije neophodan.

## Valuation unavailable

Ne računati lažni Max Buy zasnovan na izmišljenom FMV-u.

Financial opportunity mora biti ograničen.

## Liquidity unavailable

Ne pretpostavljati prosečnu liquidity.

Opportunity mora biti konzervativniji ili ostati `REVIEW`.

## Significant cost unknown

Ne koristiti automatski:

    0

Koristiti:

- configured conservative default; ili
- `UNKNOWN` koji sprečava finalnu ekonomsku preporuku.

# 71. Explainability Contract

Svaki ozbiljan analytical result treba da ima najmanje:

    result
    status/confidence
    analytical version
    relevant input/reference
    reason/explanation

Korisnik mora moći da razume kako je sistem došao do odluke bez čitanja source code-a.

# 72. Comparable Explanation

Prikazivo/sačuvano explanation metadata treba da omogući:

- broj transaction comps;
- broj listing comps;
- top comps;
- excluded comps;
- similarity;
- distance;
- recency;
- weight;
- exclusion reason.

# 73. Valuation Explanation

Treba moći prikazati:

- comparable set;
- robust base €/m²;
- target adjustments;
- FMV low/base/high;
- razlog širine range-a;
- confidence faktore;
- relevantnu model version.

# 74. Liquidity Explanation

Minimalno:

    positive_factors
    negative_factors
    unknown_important_factors
    confidence

# 75. Seller Explanation

Treba kombinovati relevantne:

- LLM evidence;
- price-cut history;
- market age;
- relisting;
- seller changes;
- manual seller feedback.

# 76. Risk Explanation

Svaki relevantan flag treba da ima:

    code
    severity
    gate_effect
    source
    confidence
    evidence

# 77. Deal Explanation

Mora omogućiti pregled:

- assumed purchase price;
- svake relevantne cost kategorije;
- exit assumption;
- holding assumption;
- risk reserve;
- required profit;
- Max Buy calculation;
- scenario outputs.

Ne prikazivati samo finalni profit bez inputa.

# 78. Opportunity Explanation

Recommended Action mora imati reason codes.

Primer pozitivnih:

    ASKING_BELOW_MAX_BUY
    HIGH_LIQUIDITY
    HIGH_CONFIDENCE
    RECENT_LARGE_PRICE_CUT
    HIGH_SELLER_MOTIVATION

Primer negativnih:

    LOW_CONFIDENCE
    NO_DOWNSIDE_MARGIN
    REQUIRED_NEGOTIATION_TOO_LARGE
    LEGAL_VERIFY_REQUIRED

Reason codes treba da budu stabilniji od slobodnog explanation teksta.

# 79. Versioning

Versionirati najmanje logiku čija promena menja značenje istorijskih rezultata:

    data_quality_rules
    comparable_engine
    valuation_model
    liquidity_model
    fast_sale_model
    llm_prompt
    seller_motivation_rules
    risk_rules
    deal_formula
    opportunity_rules

Ne mora svaki component od prvog dana imati poseban registry.

Version string u analytical result-u je dovoljan dok postoji samo jednostavan model.

# 80. Historical `as_of`

Svaki istorijski analytical run mora imati jasno:

    as_of

Historical calculation sme koristiti samo podatke koji su bili dostupni:

    timestamp <= as_of

Ovo je centralna backtesting invarijanta.

# 81. Look-Ahead Bias

Historical valuation ne sme koristiti:

- buduću transaction cenu;
- budući listing price cut;
- budući description;
- budući seller signal;
- budući manual call;
- budući visit;
- budući outcome.

Podatak koji je danas poznat nije automatski validan input za analizu prošlosti.

# 82. Backtesting

Ne evaluirati sistem samo kroz valuation MAE.

Glavni cilj proizvoda je kvalitet investment decision-support-a.

Pratiti gde je ground truth dostupan:

- alert precision;
- koliko top-ranked kandidata je vredelo pozvati;
- simulated/shadow profitability;
- downside frequency;
- false-positive reasons;
- missed opportunities.

# 83. Valuation Metrics

Kada postoji pouzdana confirmed transaction vrednost, pratiti:

    MAE
    MAPE
    median absolute percentage error
    bias

Segmentirati gde dataset dozvoljava, npr:

- microzone;
- size segment;
- condition;
- confidence bucket.

Model koji dobro radi u proseku može loše raditi na konkretnom segmentu.

# 84. Confidence Calibration

Confidence mora biti evaluiran empirijski.

Ako `HIGH` confidence valuacije često greše veoma mnogo:

> confidence model nije kalibrisan.

Confidence nije dekorativni UI score.

Treba da predviđa stvarnu pouzdanost analytical rezultata.

# 85. Seller Model Feedback

Structured call feedback treba koristiti za proveru prethodnih automation signala:

    seller motivation
    negotiability
    reason for sale

Primer:

    predicted negotiability = HIGH
    seller call = no negotiation possible

postaje koristan calibration podatak.

# 86. False Positives

Structured `SKIPPED` reasons treba koristiti za kasniju analizu grešaka.

Primer:

    30% high-ranked candidates skipped
    because HEAVY_RENOVATION

signalizira da:

- condition;
- renovation;
- risk;
- ili opportunity logic

verovatno nije dovoljno dobra.

# 87. False Negatives / Missed Opportunities

Ako korisnik pronađe dobar deal koji sistem nije izdvojio, treba kasnije omogućiti structured:

    MISSED_OPPORTUNITY

uz razlog kada je poznat.

False negatives su jednako važni kao false positives.

# 88. Model Evolution

Poželjni redosled:

    transparent heuristics
    ↓
    calibrated heuristics
    ↓
    statistical models
    ↓
    ML

Ne uvoditi ML zato što „ima podataka“.

Mora pokazati bolji out-of-sample rezultat od jednostavnijeg sistema.

# 89. Budući ML Valuation

Kada postoji dovoljan kvalitetan ground-truth dataset, mogu se razmotriti features poput:

    lat/lng
    microzone
    size
    rooms
    floor
    building age
    elevator
    parking
    condition
    heating
    transaction date
    market regime

Mogući tabular modeli uključuju npr. gradient-boosting pristupe.

Konkretna biblioteka/model nije V1 requirement.

Čak i ako ML postane glavni estimator, korisniku i dalje prikazivati relevantne comps i market context.

# 90. Budući Computer Vision

Vision može kasnije pomoći kod inference-a poput:

- condition;
- kitchen/bathroom age;
- visible defects/moisture;
- renovation category;
- light proxy.

Vision rezultat je inference.

Nije verified fact.

Ako slike nisu dovoljno informativne, output mora moći biti:

    UNKNOWN
    LOW_CONFIDENCE

Ne implementirati CV u APARTMENT V1 dok nije opravdan phase plan-om i dataset-om.

# 91. Property-Type Boundary

Ova specifikacija je za trenutni APARTMENT analytical pipeline.

Budući `LAND`, `HOUSE` ili drugi tip ne sme automatski koristiti apartment valuation/liquidity/risk formule.

Zajednički framework može biti deljen, ali property-type-specific analytical logic mora ostati odvojena.

Za `LAND`, kada bude podržan, potrebni su zasebni:

- comparable rules;
- buildability analysis;
- valuation;
- liquidity;
- risk;
- deal assumptions.

Ne implementirati ih unapred.

# 92. Conservative Defaults

Kada značajan input nije poznat:

1. koristiti pouzdan configured conservative default ako je semantički opravdan; ili
2. vratiti `UNKNOWN` / `INSUFFICIENT_DATA`.

Ne koristiti optimističnu pretpostavku samo da bi calculation mogao da se završi.

Posebno ne koristiti `0` za:

- renovation;
- taxes;
- relevantne fees;
- risk reserve;

ako ne postoji razlog da su zaista nula.

# 93. No-Deal Behavior

Potpuno validan rezultat sistema je:

    NO QUALIFYING OPPORTUNITIES

Ne:

- spuštati threshold zato što nema kandidata;
- povećavati scores;
- menjati confidence;
- forsirati alert.

Sistem optimizuje precision i risk-adjusted opportunities, ne broj alertova.

# 94. Analytical V1 Acceptance

Za dovoljno popunjen APARTMENT property sistem treba reproducibilno da može proizvesti:

    Data Quality

    Comparable Set

    FMV Low / Base / High

    Valuation Confidence

    Liquidity

    Fast-Sale Low / Base / High

    Seller Motivation / Negotiability

    Risk Gate + Risk Flags

    Deal Economics

    Max Buy Price

    Required Negotiation

    Downside / Base / Upside

    Recommended Action

    Explainability

bez manuelnog računanja van sistema.

Tačni implementation acceptance testovi pripadaju `docs/08-testing-specification.md`.

# 95. Prioriteti kvaliteta

Kada postoje tradeoff-i, prioritet je:

    1. Comparable quality
    2. Conservative valuation
    3. Correct financial math
    4. Explainability
    5. Hard risk handling
    6. Liquidity / Fast-Sale quality
    7. Seller intelligence
    8. Opportunity ranking sophistication

Fancy Opportunity Score je manje važan od kvalitetnih inputa i tačne ekonomike.

# 96. Canonical Ownership

Persistence entiteta i analytical history:

    docs/03-data-model.md

Listing/source changes:

    docs/04-scraping-specification.md

API i UI representation:

    docs/06-api-ui-specification.md

Implementation order:

    docs/07-phase-plan.md

Detailed testing:

    docs/08-testing-specification.md

Ovaj dokument poseduje:

> analytical značenje, formule, thresholds/framework i dependency/invalidation pravila.

# 97. Ključne Analytical Invarijante

1. `Asking Price != FMV`.

2. `FMV != Fast-Sale Value`.

3. `Asking Price != Expected Purchase Price`.

4. `Fast-Sale Value` mora biti konzervativniji exit concept od normalnog FMV-a.

5. Max Buy koristi definisanu konzervativnu exit ekonomiku i sve relevantne troškove.

6. LLM ne računa finansijske formule.

7. `Decimal/NUMERIC`, ne floating-point, koristi se za finansijsku matematiku.

8. Hard `BLOCK` se proverava pre Opportunity Score-a.

9. Seller urgency ne može pretvoriti lošu ekonomiku u dobar deal.

10. `UNKNOWN` se ne pretvara u optimističan default.

11. Data Quality i Valuation Confidence nisu ista metrika.

12. Listing comp i transaction comp nisu ista vrsta tržišnog dokaza.

13. FMV vraća range, ne samo jednu tačku.

14. Insufficient data je validan analytical rezultat.

15. Manual/verified podatak ima odgovarajući precedence nad slabijim automatic inference-om.

16. Historical analytical result se ne overwrite-uje novim result-om.

17. Historical backtesting ne koristi future data.

18. Opportunity Score je ranking pomoć, ne investiciona istina.

19. Upside scenario ne sme biti glavni razlog za hitnu akciju.

20. `NO QUALIFYING OPPORTUNITIES` je potpuno validan rezultat.

# 98. Konačni analytical princip

Sistem ne treba da pokušava da dokaže da je property dobar deal.

Treba da pokušava da obori investicionu tezu:

    Izgleda jeftino.
    ↓
    Da li su comps stvarno uporedivi?
    ↓
    Da li je FMV dovoljno pouzdan?
    ↓
    Da li je Fast-Sale exit dovoljno konzervativan?
    ↓
    Da li je property dovoljno likvidan?
    ↓
    Da li postoje hard ili soft rizici?
    ↓
    Da li su uračunati svi značajni troškovi?
    ↓
    Da li downside i dalje funkcioniše?
    ↓
    Da li je potrebni negotiation realističan?
    ↓
    Tek onda:
    CALL / DUE_DILIGENCE

Najvažniji output nije:

> `Opportunity Score = 94`

nego:

> **jasno objašnjen razlog zbog kog potencijalni deal i dalje funkcioniše pod konzervativnim i proverljivim pretpostavkama.**