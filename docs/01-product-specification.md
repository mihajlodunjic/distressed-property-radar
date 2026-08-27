
# Distressed Property Radar — Product Specification

## 1. Svrha dokumenta

Ovaj dokument definiše **šta Distressed Property Radar mora da radi kao proizvod** i poslovno značenje njegovih glavnih rezultata.

Ovo je source of truth za:

- cilj proizvoda;
- korisnički workflow;
- ključne domain koncepte;
- značenje analitičkih outputa;
- investiciona pravila proizvoda;
- Action Queue i alert ponašanje;
- Watchlist i acquisition workflow;
- korisnički feedback i outcomes;
- V1 product scope;
- product success criteria.

Ovaj dokument ne definiše:

- tehničku arhitekturu;
- SQL šemu;
- scraping algoritme;
- konkretne analytical formule;
- API ugovore;
- detaljan UI;
- test implementaciju;
- deployment;
- redosled implementacije.

Za te oblasti koristiti njihove canonical specifikacije.


## 2. Osnovna ideja

Distressed Property Radar je privatni decision-support sistem za pronalaženje potencijalno potcenjenih nekretnina i drugih real-estate prilika.

Sistem treba da:

1. kontinuirano prati relevantno tržište;
2. prepoznaje nove i promenjene oglase;
3. povezuje oglase koji predstavljaju istu fizičku nekretninu;
4. čuva istoriju oglasa i property-ja;
5. procenjuje tržišnu vrednost;
6. procenjuje konzervativnu fast-sale vrednost;
7. analizira likvidnost;
8. analizira seller motivation i negotiability;
9. identifikuje rizike i nepoznate podatke;
10. računa ekonomiku potencijalne kupovine;
11. određuje Max Buy Price;
12. rangira potencijalne transakcije;
13. alarmira korisnika kada postoji razlog za brzu reakciju;
14. omogućava praćenje poziva, obilazaka, ponuda i ishoda;
15. vremenom koristi istorijske podatke i ljudski feedback za proveru i poboljšanje sistema.


## 3. Primarni cilj

Sistem treba da pomogne korisniku da odgovori na pitanje:

> **Koju nekretninu trenutno mogu da kupim dovoljno dobro da i uz konzervativnu izlaznu cenu imam atraktivan odnos očekivanog profita, rizika, potrebnog kapitala i vremena?**

Cilj nije:

> pronaći najjeftiniji oglas.

Cilj je:

> **pronaći najbolji potencijalni deal.**

Sistem zato ne optimizuje samo discount u odnosu na asking price.

Mora uzeti u obzir najmanje:

- realnu vrednost;
- fast-sale vrednost;
- očekivanu kupovnu cenu;
- sve relevantne troškove;
- profit;
- downside;
- likvidnost;
- rizik;
- confidence;
- seller behavior;
- vreme potrebno za realizaciju.


## 4. Primarni korisnik

V1 je privatni alat za jednog korisnika:

> investitora koji koristi sopstveni kapital i ručno donosi konačne odluke.

V1 ne zahteva:

- javnu registraciju;
- više korisnika;
- timske role;
- billing;
- subscriptions;
- tenant isolation;
- customer onboarding;
- javni SaaS pristup;
- agency CRM funkcionalnosti.

Proizvod može kasnije evoluirati, ali trenutna implementacija ne sme biti komplikovana hipotetičkim budućim SaaS zahtevima.


## 5. Šta proizvod nije

Distressed Property Radar nije:

- klasičan agregator oglasa;
- portal za prodaju nekretnina;
- chatbot;
- autonomni investicioni agent;
- pravni alat;
- poreski savetnik;
- zamena za profesionalnog procenitelja;
- zamena za advokata;
- zamena za građevinskog stručnjaka;
- generički property-management sistem.

Sistem daje:

> **decision support**

a ne profesionalno potvrđenu investicionu, pravnu ili tehničku odluku.

Finalna odluka ostaje ljudska.


## 6. Centralni domain model proizvoda

Sistem mora jasno razlikovati:

```text
SOURCE
↓
LISTING
↓
PROPERTY
↓
ANALYSIS
↓
POTENTIAL DEAL
↓
ACTION
````

### Listing

Listing je pojedinačna objava na jednom source-u.

Može:

* menjati cenu;
* menjati opis;
* menjati prodavca/agenciju;
* nestati;
* ponovo se pojaviti;
* biti zamenjen novim listingom.

### Property

Property predstavlja fizičku nekretninu.

Jedan property može imati:

* više listinga;
* više listinga na istom portalu;
* listing na više portala;
* više agencija;
* owner listing;
* različite asking prices;
* istoriju relisting-a.

### Potential Deal

Deal predstavlja hipotetičku investicionu transakciju nad property-jem.

Njegova ekonomika zavisi od:

* moguće kupovne cene;
* tržišne vrednosti;
* fast-sale vrednosti;
* troškova;
* rizika;
* potrebnog kapitala;
* vremena držanja;
* strategije korisnika.

Sistem primarno rangira:

> **potencijalne transakcije, ne oglase.**

## 7. Property tipovi

Domain model treba da može da razlikuje najmanje:

```text
APARTMENT
HOUSE
LAND
COMMERCIAL
OTHER
```

### V1

Prva potpuno podržana kategorija je:

```text
APARTMENT
```

### Ostali tipovi

Postojanje enum/domain tipa ne znači da je njegova specifična analitika implementirana.

Posebno:

> apartment valuation logika ne sme automatski biti korišćena za LAND.

Podrška drugih tipova uvodi se tek kada je definisana odgovarajućom specifikacijom i phase planom.

## 8. Početno tržište

Početni V1 scope:

```text
Country:
Serbia

Market:
Belgrade

Initial focus:
Novi Beograd
Zemun

Property type:
APARTMENT

Typical target size:
approximately 35–90 m²
```

Ograničeni početni market omogućava:

* bolju uporedivost;
* dovoljno oglasa za analizu;
* ručnu proveru rezultata;
* učenje mikro-lokacija;
* stabilniju početnu valuaciju;
* fokus na relativno likvidan segment.

## 9. Future market scope

Arhitektura proizvoda može kasnije podržati:

* ostatak Beograda;
* druge gradove Srbije;
* Crnu Goru;
* kuće;
* zemljište;
* komercijalne nekretnine;
* distressed/public-sale izvore;
* druge real-estate acquisition strategije.

To nije V1 requirement osim kada phase plan eksplicitno uvede određenu oblast.

## 10. Kategorije izvora podataka

Proizvod dugoročno razlikuje nekoliko vrsta tržišnih podataka.

### 10.1 Listing izvori

Na primer:

* veliki property portali;
* manji property portali;
* agencijski sajtovi;
* drugi javno dostupni listing izvori.

### 10.2 Transaction podaci

Podaci o realizovanim transakcijama imaju posebno značenje jer predstavljaju stvarno zaključene tržišne događaje.

Kada su kvalitetni i relevantni, oni predstavljaju bolji dokaz tržišne vrednosti od same asking cene aktivnog oglasa.

### 10.3 Distressed izvori

Kasnije mogu biti uključeni:

* javne prodaje;
* izvršenja;
* aukcije;
* stečajne prodaje;
* bankarske prodaje;
* drugi legitimno dostupni distressed izvori.

Takvi izvori mogu zahtevati drugačiji risk i due-diligence workflow.

## 11. Asking Price nije Market Value

Jedna od najvažnijih product invarijanti je:

```text
ASKING PRICE
!=
MARKET VALUE
!=
FAST-SALE VALUE
```

Cena koju prodavac traži nije dokaz koliko property realno vredi.

Prosek aktivnih oglasa takođe nije sam po sebi Fair Market Value.

Sistem mora jasno razdvojiti:

* trenutnu asking cenu;
* procenjenu normal-market vrednost;
* konzervativnu fast-sale vrednost;
* očekivanu purchase cenu.

## 12. Fair Market Value

Fair Market Value — FMV — predstavlja procenjenu vrednost property-ja u normalnoj tržišnoj transakciji uz razuman period prodaje.

FMV ne treba prikazivati samo kao jednu apsolutno sigurnu cifru.

Product output treba da podrži najmanje:

```text
Fair Value Low
Fair Value Base
Fair Value High
Valuation Confidence
```

Primer:

```text
Fair Value

Low:   €171,000
Base:  €178,000
High:  €185,000

Confidence:
82 / 100
```

Korisnik mora moći da razume zbog čega je valuacija takva.

## 13. Valuation Confidence

Valuation Confidence predstavlja:

> koliko je sistem siguran u konkretnu procenu vrednosti.

To nije isto što i Data Quality.

Na confidence mogu uticati stvari poput:

* broja kvalitetnih comps;
* kvaliteta comps;
* transaction vs listing podataka;
* sličnosti sa target property-jem;
* recency;
* preciznosti lokacije;
* dispersion-a;
* nedostajućih atributa.

Visoka FMV cifra sa niskim confidence-om ne sme biti predstavljena kao pouzdan output.

Primer:

```text
FMV:
€160k–220k

Confidence:
36 / 100
```

mora biti vizuelno i semantički slabiji signal od uske procene sa visokim confidence-om.

## 14. Comparable Properties

Korisnik mora moći da vidi podatke koji podržavaju valuaciju.

Sistem mora razlikovati najmanje:

```text
TRANSACTION COMPS
LISTING COMPS
```

gde su dostupni.

Za relevantan comp korisniku treba prikazati ključne informacije potrebne za procenu njegove uporedivosti, kao što su:

* lokacija;
* udaljenost;
* površina;
* sobnost;
* cena;
* cena po m²;
* datum;
* tip izvora;
* similarity/relevance.

Detaljna pravila izbora i weighting-a comps pripadaju Analysis Specification-u.

## 15. Fast-Sale Value

Fast-Sale Value predstavlja:

> konzervativnu cenu na kojoj property ima dovoljno dobar market appeal da se može očekivati relativno brža realizacija.

Fast-Sale Value nije isto što i FMV.

Primer:

```text
FMV Base:
€178k

Fast-Sale Base:
€165k
```

Za flipping/acquisition strategiju Fast-Sale Value je posebno važna zato što deal ne treba da zavisi od savršene izlazne prodaje.

V1 može koristiti rules-based ili drugi eksplicitno definisan conservative estimate.

Dugoročno, kada postoji dovoljno outcome podataka, sistem može modelovati stvari poput:

```text
P(sale <= 30 days | price)
P(sale <= 60 days | price)
P(sale <= 90 days | price)
```

Takav probabilistički model nije automatski V1 requirement.

## 16. Osnovna investiciona filozofija

Centralni princip:

> **Profit treba da nastane pri kupovini, ne iz nade da će buduća prodaja biti savršena.**

Sistem ne treba da favorizuje deal koji zahteva:

* značajan budući rast tržišta;
* veoma optimističan exit;
* idealno renoviranje;
* neobično emotivnog kupca;
* ignorisanje troškova;
* ignorisanje rizika;
* veoma dug period držanja.

Dobar kandidat treba da ima dovoljno dobru ekonomiku već na konzervativnim pretpostavkama.

## 17. Max Buy Price

Jedan od centralnih product outputa je:

```text
MAX BUY PRICE
```

Max Buy Price predstavlja najveću kupovnu cenu koja još zadovoljava trenutne investicione pretpostavke korisnika.

Konceptualno uzima u obzir:

```text
Conservative Exit Value
-
Purchase Costs
-
Sale Costs
-
Taxes
-
Financing
-
Holding Costs
-
Renovation
-
Risk Reserve
-
Desired Profit
=
Max Buy Price
```

Tačna matematika pripada Analysis Specification-u.

Korisniku treba jasno prikazati najmanje:

```text
Asking Price
Expected Purchase Price, where available
Max Buy Price
Difference to Max Buy
Required Negotiation
```

## 18. Expected Purchase Price

Asking Price nije nužno cena po kojoj se property može kupiti.

Kada postoje dovoljni seller/negotiability podaci, sistem može proceniti:

```text
Expected Purchase Price
```

Ova vrednost predstavlja procenu, ne garantovanu buduću cenu.

Deal analysis treba jasno razlikovati:

```text
Asking Price
Expected Purchase Price
Manual Purchase Scenario
Max Buy Price
```

## 19. Margin of Safety

Svaki ozbiljan potential deal mora biti posmatran kroz više scenarija.

Minimalno:

```text
DOWNSIDE
BASE
UPSIDE
```

Deal ne treba smatrati dobrim samo zato što je Base scenario profitabilan.

Downside mora biti dovoljno vidljiv da korisnik odmah razume šta se dešava ako:

* exit bude slabiji;
* troškovi budu viši;
* renovation bude skuplji;
* holding period bude duži;
* druga relevantna pretpostavka bude nepovoljnija.

Scenario assumptions moraju biti vidljive.

## 20. Ključni deal outputi

Za relevantan kandidat sistem treba da može da prikaže najmanje:

```text
Asking Price
Expected Purchase Price
Max Buy Price

Total Cost Basis
Expected Exit Price
Expected Net Profit
Downside Profit

ROI
Annualized ROI

Capital Required
Expected Holding Days
Capital Days
Profit / Capital-Day
```

Ne moraju svi outputi biti dostupni u svakoj fazi implementacije.

Phase plan određuje kada se uvode.

## 21. Capital Efficiency

Dva deala sa sličnim profitom nisu jednako kvalitetna ako jedan:

* koristi znatno više kapitala;
* drži kapital znatno duže.

Zato sistem ne treba da rangira samo po:

```text
Expected Profit
```

Već mora moći da uzme u obzir:

```text
capital required
holding period
capital days
profit / capital-day
```

Primer:

```text
Deal A
Profit: €20k
Capital: €145k
Holding: 40d

Deal B
Profit: €28k
Capital: €230k
Holding: 200d
```

Deal B nije automatski bolji samo zato što ima veći nominalni profit.

## 22. Seller Motivation

Sistem treba da identifikuje signale da je prodavac motivisan za realizaciju.

### Direktni signali

Mogu uključivati:

* hitna prodaja;
* brza realizacija;
* odlazak;
* selidba;
* prednost keš kupcu;
* potreban brz dogovor;
* vremenski ograničena cena;
* druga eksplicitna urgency poruka.

### Indirektni signali

Mogu uključivati:

* više price cut-ova;
* veliki price cut;
* dug property market age;
* relisting;
* promenu agencija/owner statusa;
* promenu teksta ka urgentnijem tonu;
* druge istorijske seller signale.

Seller motivation mora imati vidljivo evidence kada je dostupno.

## 23. Seller Motivation nije Value

Visoka seller motivation ne znači automatski dobar deal.

Na primer:

```text
Seller Motivation:
VERY HIGH

Asking:
€220k

FMV:
€180k
```

i dalje može biti loš kandidat.

Sistem zato mora odvojeno tretirati:

```text
Value
Seller Motivation
Negotiability
Liquidity
Risk
Confidence
```

## 24. Negotiability

Negotiability predstavlja procenu:

> koliko postoji realan prostor da trenutna asking cena bude smanjena kroz pregovor.

Može koristiti informacije kao što su:

* seller language;
* price-cut history;
* property market age;
* owner/agency status;
* prethodna komunikacija;
* call feedback;
* drugi relevantni seller signali.

Negotiability je procena, ne činjenica.

Kada nema dovoljno podataka:

```text
UNKNOWN
```

je validan rezultat.

## 25. Liquidity

Sistem mora odvojeno analizirati koliko je property:

> lako prodati dovoljnjoj bazi kupaca po razumnoj tržišnoj ceni.

Likvidnost nije isto što i valuation.

Na liquidity mogu uticati:

* mikro-lokacija;
* kvadratura;
* raspored;
* buyer pool;
* sprat;
* lift;
* parking;
* stanje;
* pravna/kreditna pogodnost;
* kvalitet zgrade;
* cenovni segment;
* drugi property atributi.

Product output treba da sadrži:

```text
Liquidity
Liquidity explanation
```

Tačna formula pripada Analysis Specification-u.

## 26. Risk

Veoma nizak asking price nije dovoljan razlog za pozitivan opportunity signal.

Sistem mora odvojeno identifikovati:

```text
HARD RISKS
SOFT RISKS
```

i jasno prikazati relevantne nepoznanice.

## 27. Hard Risk

Hard risk predstavlja problem koji može:

* potpuno onemogućiti transakciju;
* značajno promeniti njenu pravnu ili ekonomsku prirodu;
* zahtevati dodatnu proveru pre agresivne akcije.

Mogući product-level primeri:

* partial ownership;
* unknown ownership;
* ozbiljna pravna neizvesnost;
* aktivan spor;
* problematičan registration status;
* zauzet property u specifičnoj distressed situaciji;
* nedostatak kritične dokumentacije;
* posebna ograničenja prodaje.

Minimalni risk-gate statusi:

```text
PASS
VERIFY
BLOCK
```

Visok Opportunity Score ne sme poništiti `BLOCK`.

## 28. Soft Risk

Soft risks ne moraju automatski blokirati deal, ali mogu uticati na:

* cenu;
* likvidnost;
* renovation;
* holding period;
* confidence;
* margin of safety.

Primeri mogu uključivati:

* ground floor;
* visok sprat bez lifta;
* bučnu ulicu;
* loš parking;
* slabije prirodno svetlo;
* čudan raspored;
* veliko renoviranje;
* slabije stanje zgrade.

Tačna risk klasifikacija pripada Analysis Specification-u.

## 29. Claim vs Verified Fact

Sistem mora razlikovati:

```text
SOURCE CLAIM
```

od:

```text
VERIFIED FACT
```

Primer:

Listing kaže:

```text
"uknjižen 1/1"
```

To znači da postoji tvrdnja izvora.

Ne znači automatski da je pravni status profesionalno potvrđen.

Isto pravilo važi za druge podatke gde je provenance važan.

## 30. UNKNOWN

Nedostatak informacije mora ostati vidljiv.

Validni product outputi uključuju:

```text
Ownership:
UNKNOWN

Elevator:
UNKNOWN

Exact Location:
UNKNOWN
```

`UNKNOWN` ne sme biti automatski pretvoren u povoljnu ili nepovoljnu pretpostavku bez eksplicitnog analytical pravila.

Bolje je prikazati:

```text
UNKNOWN
```

nego lažnu sigurnost.

## 31. Data Quality

Sistem treba da ima zaseban indikator:

```text
Data Quality
```

koji opisuje koliko su kompletni i pouzdani input podaci potrebni za analizu.

Može zavisiti od dostupnosti stvari poput:

* lokacije;
* površine;
* sobnosti;
* sprata;
* lifta;
* parkinga;
* stanja;
* fotografija;
* godina/karakteristika zgrade;
* relevantnih pravnih tvrdnji.

Važno:

```text
Data Quality
!=
Valuation Confidence
```

Property može imati dosta poznatih atributa, a i dalje imati slab valuation confidence zbog loših comparables.

## 32. Istorija je ključni deo proizvoda

Distressed Property Radar nije samo snapshot trenutnog tržišta.

Njegova dugoročna vrednost zavisi od očuvanja:

* first seen;
* last seen;
* price history;
* description changes;
* seller/agency changes;
* removals;
* reappearances;
* relistings;
* cross-portal identity;
* analiza;
* ljudskog feedback-a;
* outcomes.

History se koristi za razumevanje:

* market age-a;
* seller behavior-a;
* negotiability-ja;
* price-cut ponašanja;
* evolucije property-ja;
* kvaliteta ranijih preporuka.

## 33. Listing History i Property History

Sistem mora razlikovati:

```text
LISTING HISTORY
```

od:

```text
PROPERTY HISTORY
```

### Listing History

Prati promene jednog konkretnog listinga.

### Property History

Kombinuje relevantne informacije kroz sve listing-e za istu fizičku nekretninu.

Primer:

```text
Day 0
Agency A
€180k

Day 21
Agency A
€175k

Day 43
description changed

Day 51
Agency A
€165k

Day 66
Owner listing
€158k
```

Ovo treba da ostane jedan property history čak i kada se listing identitet promenio.

## 34. Market Age

Sistem mora razlikovati:

```text
listing_age
```

i:

```text
property_market_age
```

Novi listing ID ne znači automatski da je property nov na tržištu.

Property market age je važniji seller-behavior signal kada postoji dovoljno podataka da se relisting pravilno poveže.

## 35. Duplicate i Relisting koncept

Sistem treba da pokušava da prepozna kada više listing-a predstavlja isti property.

Product-level odluke mogu uključivati:

```text
AUTO_MATCH
POSSIBLE_MATCH
NO_MATCH
```

`POSSIBLE_MATCH` mora biti moguće ručno potvrditi ili odbiti.

Relisting ne sme automatski resetovati property history.

Detaljan matching behavior pripada Data Model i Analysis/Architecture specifikacijama.

## 36. Glavni korisnički rezultat — Action Queue

Glavni workflow treba prvenstveno da odgovori na:

> **Šta trenutno treba da uradim?**

Minimalne action kategorije:

```text
URGENT_CALL
CALL
REVIEW
WATCH
IGNORE
```

Kasnije, kada acquisition workflow to zahteva, može postojati i:

```text
DUE_DILIGENCE
```

Action predstavlja preporučeni nivo korisničke pažnje.

Nije konačna BUY odluka.

## 37. `URGENT_CALL`

Koristiti samo kada postoje dovoljno jaki razlozi da brzina može biti važna.

Tipično zahteva kombinaciju:

* potencijalno dobre ekonomike;
* prihvatljivog valuation confidence-a;
* prihvatljive liquidity;
* odsustva hard `BLOCK`;
* dovoljno dobrog downside-a;
* realnog razloga za hitnu reakciju.

`URGENT_CALL` treba da bude redak output.

## 38. `CALL`

`CALL` znači:

> kandidat vredi direktnog kontakta sa prodavcem ili agentom.

Razlozi mogu uključivati:

* dobru ekonomiku uz dostižan pregovor;
* potrebu za proverom seller motivation;
* potrebu za dodatnim podacima;
* potencijalno realan put ka Max Buy ceni.

Poziv može služiti i prikupljanju novih informacija.

## 39. `REVIEW`

`REVIEW` znači:

> kandidat zaslužuje ručnu analizu, ali trenutno nema dovoljno razloga za direktan poziv.

Primeri razloga:

* potencijalni value anomaly;
* slabiji confidence;
* važan `UNKNOWN`;
* neobični comps;
* potreba za ručnim pregledom fotografija ili lokacije.

## 40. `WATCH`

`WATCH` znači:

> property trenutno nije dovoljno dobar za aktivnu akciju, ali promena tržišnih ili property podataka može ga učiniti interesantnim.

Tipičan primer:

```text
Asking:
€155k

Max Buy:
€137k
```

Property može biti kvalitetan, ali trenutna cena nije dovoljno dobra.

## 41. `IGNORE`

`IGNORE` znači:

> sistem trenutno ne nalazi dovoljno dobar razlog za dalju pažnju.

Razlozi mogu uključivati:

* očigledno lošu ekonomiku;
* cenu daleko iznad relevantnog Max Buy-a;
* property van trenutne strategije;
* veoma nisku relevantnost;
* hard blocker;
* druge eksplicitne product rules.

`IGNORE` ne znači da se istorijski podaci property-ja brišu.

## 42. Alert Philosophy

Cilj nije maksimalan broj alertova.

Primarni cilj je:

> **visoka alert precision.**

Bolje je:

```text
malo kvalitetnih alertova
```

nego:

```text
veliki broj prosečnih kandidata
```

Sistem ne sme stvarati alert fatigue.

Opportunity sistem treba da služi korisnikovoj pažnji kao oskudnom resursu.

## 43. Telegram Alerts

Telegram je primarni kanal za vremenski osetljive opportunity alertove.

Alert treba da omogući korisniku da brzo proceni:

> da li ovaj kandidat zahteva neposrednu pažnju?

Treba da sadrži samo najvažnije decision podatke, kao što su:

* location;
* osnovni property atributi;
* asking;
* FMV;
* Fast-Sale estimate;
* Max Buy;
* očekivani profit;
* downside;
* liquidity;
* valuation confidence;
* seller motivation;
* veliki risk signal;
* relevantna price-history informacija;
* property market age;
* recommended action;
* link ka detaljima.

Ne slati celu analizu u Telegram poruci.

## 44. Primer opportunity alert-a

Primer product outputa:

```text
URGENT CALL

Novi Beograd — Blok 45
72 m² | 3.0 | 5/8 | lift

ASKING
€134,000

FMV
€171k–182k

FAST-SALE BASE
€165k

MAX BUY
€138.5k

EXPECTED PROFIT
€19k

DOWNSIDE
+€5k

LIQUIDITY
87

VALUATION CONFIDENCE
81

SELLER MOTIVATION
HIGH

PRICE HISTORY
€154k → €145k → €134k

LEGAL
VERIFY

PROPERTY MARKET AGE
21d
```

Tačan presentation format pripada UI/API specifikaciji.

## 45. Watchlist

Korisnik mora moći da ručno prati property bez obzira na njegovu trenutnu automatic action kategoriju.

Watchlist može podržati trigger-e poput:

```text
alert if price <= target
```

ili:

```text
alert if next price drop >= X%
```

Watchlist ne sme da izgubi property history kada listing nestane ili se promeni.

## 46. Watch triggeri

Relevantni triggeri mogu uključivati:

* price <= target;
* price drop >= configured threshold;
* važnu description promenu;
* seller promenu;
* owner listing pojavljivanje;
* agency listing nestanak;
* novi duplicate;
* relisting;
* novu relevantnu analitičku informaciju.

Tačni automatski triggeri uvode se prema phase planu.

## 47. What Changed

Za postojeći kandidat korisnik mora brzo da vidi:

> **šta se promenilo od prethodnog relevantnog stanja ili analize?**

Primer:

```text
PRICE
€162k → €149k

DESCRIPTION
"cena nije fiksna"
→
"hitno zbog odlaska"

SELLER
Agency → Owner
```

Cilj je da korisnik ne mora svaki put ponovo da analizira ceo property od početka.

## 48. Re-analysis

Promena relevantnog inputa može zahtevati novu analizu.

Primeri:

* price change;
* važna description change;
* seller change;
* bolji location podatak;
* novi duplicate;
* novi transaction comp;
* call feedback;
* visit feedback;
* manual override.

Posle re-analysis kandidat može promeniti action, npr:

```text
IGNORE → WATCH
WATCH → REVIEW
WATCH → CALL
CALL → URGENT_CALL
```

Tačna invalidation pravila pripadaju Analysis Specification-u.

## 49. Personal Deal Pipeline

Kada kandidat pređe iz pasivnog tržišnog praćenja u stvarni acquisition proces, proizvod treba da podrži pipeline.

Predviđeni statusi:

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

Pipeline status i automatic recommended action nisu ista stvar.

Na primer property može biti:

```text
Pipeline:
CALLED

Current recommended action:
WATCH
```

ako se ekonomika promenila.

## 50. Call Feedback

Posle poziva korisnik treba brzo da unese strukturirane informacije kada su dostupne.

Relevantni podaci mogu uključivati:

* seller motivation;
* reason for sale;
* lowest indicated price;
* cash preference;
* preferred closing timing;
* viewing availability;
* ownership claim;
* mortgage claim;
* tenant status;
* druge relevantne tvrdnje;
* notes.

Call feedback predstavlja vredan human input.

Tvrdnja iz poziva i dalje nije automatski profesionalno verified fact.

## 51. Visit Feedback

Posle obilaska korisnik može evidentirati stvari poput:

* condition;
* renovation estimate;
* layout;
* light;
* noise;
* building quality;
* entrance;
* elevator;
* parking;
* visible defects;
* manual FMV estimate;
* manual Fast-Sale estimate;
* manual Max Buy;
* notes.

Takvi podaci mogu biti pouzdaniji od ranijih listing-based pretpostavki i treba da omoguće novu analizu.

## 52. Offer Tracking

Kada korisnik pošalje stvarnu ponudu, sistem treba da može da sačuva najmanje:

* amount;
* date;
* conditions;
* seller response;
* counteroffer;
* final outcome.

Ovi podaci su važni za buduću procenu:

* negotiability-ja;
* seller behavior-a;
* kvaliteta recommendation sistema.

## 53. Skip Feedback

Kada korisnik ručno odbaci ozbiljniji kandidat, treba omogućiti strukturirani razlog.

Minimalne kategorije mogu uključivati:

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

Dodatna beleška može biti slobodan tekst.

Strukturiran feedback je važan za kasniju evaluaciju sistema.

## 54. Outcome Tracking

Za ozbiljnije property-je sistem treba, gde je moguće, da sačuva kasniji outcome.

Primeri:

```text
STILL_ACTIVE
REMOVED_UNKNOWN
RELISTED
LIKELY_SOLD
CONFIRMED_SOLD
BOUGHT_BY_USER
LOST_TO_OTHER_BUYER
```

Posebno:

```text
listing removed
```

ne znači automatski:

```text
property sold
```

Outcome confidence/provenance mora ostati vidljiv kada nije potvrđen.

## 55. User Override

Korisnik mora moći da koristi sopstvenu procenu bez uništavanja originalnog sistemskog rezultata.

Primer:

```text
System FMV:
€180k

User FMV:
€170k
```

ili:

```text
System Renovation:
€4k

User Renovation:
€9k
```

Sistem treba zatim da može da izračuna manual scenario koristeći korisničke pretpostavke.

Originalna sistemska analiza mora ostati sačuvana.

## 56. Investment Profile

Korisnik treba da može da definiše investicione kriterijume koji određuju šta predstavlja dobar deal.

Relevantne kategorije uključuju:

* minimum expected profit;
* minimum downside result;
* minimum ROI;
* maximum holding period;
* minimum liquidity;
* minimum valuation confidence;
* risk-reserve assumptions;
* druge strategy thresholds predviđene Analysis Specification-om.

Investment Profile utiče na:

* Max Buy;
* opportunity qualification;
* action;
* ranking.

Codex ili analytical engine ne smeju samostalno smanjivati kriterijume samo zato što postoji malo prilika.

## 57. Explainability

Za svaki važan decision output korisnik mora moći da odgovori na:

> **WHY?**

### FMV

Treba moći videti:

* relevantne comps;
* transaction vs listing inpute;
* ključne adjustment-e;
* confidence razloge.

### Fast-Sale / Liquidity

Treba videti:

* ključne pozitivne faktore;
* ključne negativne faktore;
* relevantne pretpostavke.

### Seller Motivation

Treba videti evidence kao što su:

* price cuts;
* opis;
* property market age;
* seller history;
* call feedback.

### Risk

Treba videti:

* risk signal;
* severity/status;
* provenance;
* claim vs verified status.

### Max Buy / Deal

Treba videti:

* exit assumption;
* troškove;
* renovation;
* holding assumptions;
* risk reserve;
* profit target;
* scenario rezultat.

Sistem ne sme sakriti decision logiku iza jednog score-a.

## 58. Opportunity Score

Ako postoji aggregate Opportunity Score, on služi prvenstveno za:

> ranking i prioritizaciju.

Score nije zamena za osnovne ekonomske i risk podatke.

Korisnik i dalje mora moći da vidi:

```text
Asking
FMV
Fast-Sale
Expected Purchase Price
Max Buy
Profit
Downside
Liquidity
Confidence
Risk
Seller Motivation
```

Hard `BLOCK` ne sme postati mali negativni score koji se poništava drugim pozitivnim faktorima.

## 59. Konzervativnost

Kada postoji velika neizvesnost, sistem treba da bude konzervativan.

Preferirati:

```text
REVIEW
```

umesto lažno sigurnog:

```text
URGENT_CALL
```

Preferirati:

```text
UNKNOWN
```

umesto izmišljene vrednosti.

Preferirati:

```text
NO QUALIFYING DEALS
```

umesto slabog kandidata koji samo popunjava dashboard.

## 60. No Deal je validan rezultat

Sistem ne mora svakog dana da pronađe deal.

Potpuno ispravan output može danima ili nedeljama biti:

```text
NO QUALIFYING DEALS
```

Broj prilika nije cilj sam za sebe.

## 61. Ne optimizovati za frequency

Cilj nije:

```text
što više dealova
```

Cilj je:

```text
retki, dovoljno kvalitetni dealovi
```

Moguće je da sistem bude veoma vredan čak i ako identifikuje samo nekoliko izuzetno dobrih prilika godišnje.

## 62. Shadow Portfolio i istorijska evaluacija

Pre ozbiljnog oslanjanja na recommendation sistem korisno je podržati simulirane odluke.

Shadow deal može sačuvati stvari poput:

* simulated buy price;
* simulated cost basis;
* expected exit;
* expected holding;
* expected profit.

Kasnije se rezultat može porediti sa tržišnim razvojem.

Istorijska evaluacija treba prvenstveno da odgovori na:

> **Da li bi preporuke sistema bile ekonomski korisne?**

Ne samo:

> da li je pojedinačna klasifikacija bila statistički tačna?

## 63. Product KPI

Primarni product KPI:

```text
ALERT PRECISION
```

Odnosno:

> **Koliki procenat opportunity alertova zaista vredi korisnikove pažnje?**

Dodatne korisne metrike mogu uključivati:

```text
alerts / week

% alerts worth calling

% calls worth visiting

% visits worth offering

% offers accepted

valuation error

fast-sale prediction error

false-positive rate

false-negative discoveries

listing publication → detection latency

detection → alert latency
```

Nisu sve metrike nužno dostupne u V1.

## 64. V1 success criteria

V1 nije uspešan samo zato što može da scrape-uje jedan portal.

Prvi koristan sistem treba da demonstrira da:

1. stabilno nalazi nove relevantne oglase;
2. prati njihove ključne promene;
3. čuva listing history;
4. dovoljno dobro povezuje listing-e da property history ima smisla;
5. daje korisne comparable rezultate;
6. daje razumne i konzervativne valuation rezultate;
7. jasno prikazuje valuation confidence;
8. daje liquidity / fast-sale procenu potrebnu za deal analizu;
9. računa Max Buy i deal ekonomiku;
10. primenjuje risk gates;
11. šalje mali broj smislenih opportunity alertova;
12. korisnik može razumeti zašto je kandidat preporučen;
13. istorijski podaci nisu izgubljeni.

Detaljni acceptance kriterijumi po implementacionoj fazi pripadaju Phase Plan-u.

## 65. Minimalni useful milestone

Kada core acquisition engine prvi put postane upotrebljiv, korisnik treba da može:

```text
market listing appears
↓
system discovers it
↓
listing/property is updated
↓
history is preserved
↓
property is analyzed
↓
deal economics are calculated
↓
recommended action is produced
↓
relevant candidate triggers an alert
```

i zatim ručno proveriti:

> **Da li bih zbog ovog outputa stvarno reagovao?**

Real-world validation je važnija od nastavka gradnje velikog broja budućih funkcionalnosti.

## 66. Idealni Property Detail rezultat

Za ozbiljnog kandidata sistem treba da bude sposoban da korisniku objedini nešto približno ovome:

```text
PROPERTY

Location:
Novi Beograd / Blok 45

Size:
72 m²

Rooms:
3.0

Floor:
5/8

Elevator:
YES


ASKING
€134,000

FAIR VALUE
Low:  €171k
Base: €177k
High: €182k

VALUATION CONFIDENCE
81

DATA QUALITY
89


FAST-SALE VALUE

Downside:
€157k

Base:
€165k

Upside:
€172k


MAX BUY
€138.5k

EXPECTED ALL-IN COST
€146k

BASE PROFIT
€19k

DOWNSIDE PROFIT
€5k

EXPECTED HOLD
35–55 days


LIQUIDITY
87

SELLER MOTIVATION
HIGH

NEGOTIABILITY
HIGH

LEGAL
VERIFY


PRICE HISTORY
€154k → €145k → €134k

PROPERTY MARKET AGE
21 days


ACTION
URGENT_CALL
```

Korisnik zatim mora moći da otvori explanation i vidi osnovu ovih rezultata.

Tačan UI layout nije predmet ovog dokumenta.

## 67. Human feedback loop

Sistem dugoročno treba da poveže:

```text
system recommendation
↓
human review
↓
call
↓
visit
↓
offer
↓
outcome
```

Ovi podaci omogućavaju proveru pitanja kao što su:

* da li su alertovi stvarno korisni;
* da li seller motivation signal nešto znači;
* koliko je stvarni negotiation room;
* koliko su valuation rezultati dobri;
* koji tip kandidata postaje stvaran deal;
* gde sistem pravi false positive;
* šta sistem propušta.

Ne uvoditi ML samo zato što feedback podaci postoje.

Prvo koristiti podatke za realnu evaluaciju.

## 68. Dugoročni data advantage

Dugoročna vrednost sistema ne nastaje samo iz koda ili scraping-a.

Posebno vredan asset postaje istorijski dataset koji povezuje:

```text
listing history
price history
cross-source property identity
transaction data
micro-location knowledge
system analyses
manual reviews
calls
visits
offers
seller behavior
outcomes
```

Zbog toga je očuvanje istorijskih podataka product requirement, a ne samo tehnički detalj.

## 69. Future Product Direction

Sledeće oblasti predstavljaju buduće pravce, ne V1 requirements:

### Land

Land zahteva zasebnu analitiku i može uključiti podatke poput:

* parcel size;
* parcel number;
* cadastral municipality;
* land use;
* buildability;
* road access;
* frontage;
* shape;
* utilities;
* planning parameters;
* allowed buildable area;
* ownership.

Land analiza ne treba da bude samo apartment analiza primenjena na parcelu.

### Distressed Sources

Kasniji sistem može uključiti:

* auctions;
* executions;
* bank sales;
* bankruptcy sales;
* druge legitimno dostupne distressed prilike.

### Off-Market

Dugoročni sistem može proširiti cilj sa:

```text
find an attractive public listing
```

na:

```text
identify a potentially attractive acquisition situation before or outside a standard public listing
```

Ovo nije deo početnog apartment V1.

## 70. Scope discipline

Poznavanje budućeg pravca ne predstavlja zahtev da se on implementira unapred.

Posebno, V1 ne treba komplikovati zbog:

* Land analitike;
* multi-country podrške;
* off-market sourcing-a;
* javnih auction workflow-a;
* investor network-a;
* SaaS-a;
* enterprise funkcionalnosti;
* naprednog ML-a.

Phase Plan određuje kada određena product capability ulazi u aktivni implementation scope.

## 71. Konačni product principle

Distressed Property Radar treba da transformiše:

```text
veliki broj sirovih tržišnih oglasa i promena
```

u:

```text
veoma mali broj potencijalnih transakcija
```

koje zaslužuju ljudsku pažnju.

Sistem ne treba da donese konačnu BUY odluku.

Njegova svrha je:

> **da korisnik dovoljno brzo identifikuje retke situacije sa povoljnim odnosom kupovne cene, konzervativne realizabilne vrednosti, likvidnosti, rizika, potrebnog kapitala, vremena i očekivanog profita.**

Konceptualno:

```text
DATA
+
HISTORY
+
COMPARABLES
+
VALUATION
+
FAST-SALE ESTIMATION
+
LIQUIDITY
+
SELLER INTELLIGENCE
+
RISK
+
DEAL ECONOMICS
+
SPEED
+
HUMAN FEEDBACK

=

ACTIONABLE EDGE
