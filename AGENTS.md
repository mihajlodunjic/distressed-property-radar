
# Distressed Property Radar — Codex Repository Rules

## 1. Svrha

Ovaj fajl sadrži samo **repository-wide pravila rada** koja Codex mora da poštuje u svakoj implementacionoj sesiji.

Ovaj fajl nije poslovna, arhitektonska, database, scraping, analytical, API/UI, testing ili deployment specifikacija.

Detaljna pravila pripadaju dokumentima u `/docs`.

Osnovni princip:

> **AGENTS.md definiše kako Codex radi. Specifikacije definišu šta sistem radi.**

Pre implementacije bilo kog task-a Codex mora prvo pročitati:

1. `/AGENTS.md`;
2. `/docs/11-project-status.md`;
3. relevantni deo `/docs/07-phase-plan.md`;
4. samo relevantne sekcije ostalih specifikacija;
5. postojeći kod i testove koje task može da promeni.


## 2. Prioriteti projekta

Prioritet je:

```text
correctness
>
data integrity
>
reliability
>
maintainability
>
performance
>
visual polish
````

Sistem je prvenstveno privatni decision-support alat za jednog korisnika.

Ne projektovati ga kao enterprise SaaS niti uvoditi infrastrukturu za hipotetički budući scale dok trenutni zahtev to ne opravda.

## 3. Source of truth

Dokumentacija je podeljena po odgovornosti.

| Dokument                            | Odgovornost                                                  |
| ----------------------------------- | ------------------------------------------------------------ |
| `AGENTS.md`                         | repository-wide Codex pravila                                |
| `docs/01-product-specification.md`  | šta proizvod mora da radi                                    |
| `docs/02-system-architecture.md`    | arhitektonske granice i organizacija sistema                 |
| `docs/03-data-model.md`             | entiteti, persistence i data-integrity pravila               |
| `docs/04-scraping-specification.md` | prikupljanje i praćenje eksternih podataka                   |
| `docs/05-analysis-specification.md` | valuation, liquidity, seller/risk, deal i opportunity logika |
| `docs/06-api-ui-specification.md`   | API i korisnički interfejs                                   |
| `docs/07-phase-plan.md`             | redosled implementacije i scope faza                         |
| `docs/08-testing-specification.md`  | canonical testing zahtevi                                    |
| `docs/09-deployment-operations.md`  | runtime, deployment i produkcione operacije                  |
| `docs/11-project-status.md`         | trenutno stanje projekta i sledeći task                      |

`README.md` je pregled projekta i nije detaljan source of truth.

`docs/10-codex-execution-guide.md` je pomoćni workflow/playbook. Ne treba ga čitati pri svakom task-u ako `AGENTS.md` i `project-status.md` već daju dovoljno instrukcija.

## 4. Ownership pravilo

Kada se ista oblast pominje u više dokumenata, koristi dokument koji je **source of truth za tu oblast**.

Primeri:

```text
database semantics
→ docs/03-data-model.md

scraping behavior
→ docs/04-scraping-specification.md

valuation formula
→ docs/05-analysis-specification.md

API contract
→ docs/06-api-ui-specification.md

implementation order
→ docs/07-phase-plan.md

test expectation
→ docs/08-testing-specification.md

production deployment
→ docs/09-deployment-operations.md
```

`docs/07-phase-plan.md` prvenstveno određuje:

> **KADA se nešto implementira.**

Domain specifikacije određuju:

> **ŠTA i KAKO mora da se ponaša.**

`docs/11-project-status.md` ne sme da promeni značenje kanonske specifikacije.

## 5. Konflikt dokumentacije

Ako dve relevantne specifikacije deluju kontradiktorno:

1. utvrdi koji dokument poseduje tu odgovornost;
2. ne izmišljaj kompromis;
3. ne radi veliki redesign;
4. ne menjaj specifikaciju samo da bi odgovarala postojećem kodu;
5. sačuvaj podatke i postojeće pouzdano ponašanje dok se problem ne razreši.

Ako je konflikt mali i postoji jedno očigledno bezbedno tumačenje, koristi najmanju implementaciju koja poštuje canonical ownership.

Ako konflikt može promeniti poslovno značenje, integritet podataka ili finansijski rezultat, ne nagađati.

## 6. Context efficiency

Ne učitavati kompletnu dokumentaciju za svaki task.

Za velike specifikacije:

1. pronađi relevantne heading-e;
2. pročitaj relevantnu sekciju i potreban neposredni kontekst;
3. učitaj dodatne sekcije samo ako se tokom implementacije pojavi stvarna zavisnost.

Ceo dokument čitati samo kada task zaista obuhvata veliki deo njegovog domena.

`docs/11-project-status.md` treba, gde je moguće, da navede tačne dokumente ili sekcije potrebne za trenutni task.

Cilj je:

> **minimalan relevantan kontekst bez gubitka važnih zahteva.**

## 7. Pregled postojećeg sistema pre izmene

Pre menjanja koda:

1. pregledaj relevantnu strukturu repozitorijuma;
2. pregledaj `docs/11-project-status.md`;
3. pročitaj trenutni phase/task;
4. pročitaj potrebne canonical sekcije;
5. pregledaj postojeću implementaciju;
6. pregledaj postojeće testove;
7. proveri trenutni git diff/status kada je relevantno.

Ne pretpostavljaj da nešto ne postoji pre nego što proveriš repository.

Ne kreiraj paralelnu implementaciju ako odgovarajući modul već postoji.

## 8. Jedan aktivni scope

Implementirati samo trenutni task.

Ne implementirati:

* naredne faze;
* „nice to have“ funkcionalnosti;
* buduću infrastrukturu;
* nepovezane refaktore;
* dodatne ekrane;
* dodatne modele;
* dodatne integracije;

samo zato što bi mogli biti korisni kasnije.

Ako trenutni task zahteva mali prerequisite, dozvoljena je najmanja izmena potrebna da trenutni task bude ispravno implementiran.

Mali prerequisite nije dozvola za implementaciju cele buduće funkcionalnosti.

## 9. Faze

Faze iz `docs/07-phase-plan.md` implementiraju se redom.

Ne prelaziti na sledeću fazu dok trenutni relevantni scope nema:

```text
implementation complete
+
relevant tests passing
+
migrations valid, if changed
+
affected startup/runtime verified
+
acceptance criteria satisfied
```

Ako phase plan zahteva ručnu real-world validaciju pre nastavka, ne predstavljati fazu kao potpuno validiranu dok ta validacija nije urađena.

## 10. Preferirati najjednostavnije pouzdano rešenje

Kada postoji više validnih implementacija, preferirati onu koja ima:

* manje delova;
* manje dependency-ja;
* manje infrastrukture;
* manje implicitnog ponašanja;
* jasnije granice;
* lakše testiranje;
* lakše debugovanje.

Ne uvoditi kompleksniji sistem samo zato što je tehnički sofisticiraniji.

Primer principa:

```text
existing dependency > new dependency
simple function > unnecessary class hierarchy
PostgreSQL capability > new infrastructure
HTTP access > browser automation, when both reliably solve the same task
existing module > parallel duplicate module
```

## 11. Ne generalizovati prerano

Ne graditi framework za hipotetičke buduće slučajeve.

Prvi realni slučaj treba rešiti jasno i pouzdano.

Generalizaciju uvoditi kada:

* postoji drugi stvarni slučaj;
* postoji jasno ponavljanje;
* trenutna struktura stvarno postaje problem;
* canonical architecture zahteva zajednički contract.

Izbegavati „platform for everything“ dizajn.

## 12. Modularni monolit

Dok canonical architecture ne kaže drugačije, sistem ostaje modularni monolit.

Ne uvoditi bez stvarne potrebe i odgovarajuće promene specifikacije:

* mikroservise;
* Kubernetes;
* Kafka;
* service mesh;
* više baza po modulu;
* distribuiranu infrastrukturu;
* kompleksne queue sisteme.

Background proces može biti poseban runtime proces bez pretvaranja logičkog modula u mikroservis.

## 13. Granice modula

Svaki modul treba da ima jasnu odgovornost.

Izbegavati:

* circular dependencies;
* dupliranje poslovne logike;
* direktno zaobilaženje postojećeg service/domain sloja;
* velike generičke `utils` module;
* paralelne implementacije iste funkcionalnosti.

Ako jedno poslovno pravilo koristi više delova sistema, treba da postoji jedno canonical mesto gde je implementirano.

## 14. Novi fajlovi i apstrakcije

Novi fajl, klasu, servis ili abstraction napraviti samo ako imaju jasnu odgovornost potrebnu trenutnom task-u.

Ne praviti placeholder fajlove za buduće faze.

Ne praviti dokumente poput:

```text
PROJECT_NOTES.md
IMPLEMENTATION_NOTES.md
SPEC_COPY.md
TODO_DETAILS.md
HANDOFF_FINAL_V2.md
```

ako informacija već pripada postojećoj dokumentaciji.

Ne generisati dodatnu dokumentaciju bez potrebe.

## 15. Existing code first

Pre kreiranja novog modula proveriti da li postoji odgovarajuće mesto u trenutnoj implementaciji.

Preferirati:

```text
extend existing correct module
```

umesto:

```text
create parallel replacement
```

osim ako postojeća struktura stvarno mora biti zamenjena.

Ne praviti `*_v2`, `*_new`, `*_final` implementacije samo da bi se izbeglo razumevanje postojećeg koda.

## 16. Refactoring

Refaktorisati samo kada postoji konkretan razlog:

* realno dupliranje;
* bug;
* data-integrity rizik;
* ozbiljna testability prepreka;
* trenutni task ne može čisto da se implementira;
* canonical architecture zahteva promenu.

Ne refaktorisati nepovezan kod zato što postoji lepši pattern.

Refactor mora ostati proporcionalan trenutnom problemu.

## 17. Dependency pravilo

Pre dodavanja novog dependency-ja proveriti:

1. da li standardna biblioteka rešava problem;
2. da li postojeći dependency već rešava problem;
3. da li novi paket rešava dovoljno važan problem;
4. da li je paket pouzdano održavan;
5. da li uvodi nepotrebnu kompleksnost.

Ne dodavati dependency za nekoliko trivijalnih helper funkcija.

## 18. Kritične data-integrity invarijante

Bez obzira na trenutni task, Codex mora da čuva sledeće principe.

### 18.1. Istorijski podaci se ne uništavaju

Ne brisati ili resetovati istorijske podatke samo zato što se:

* promenio model;
* promenila analiza;
* pronašao duplicate;
* promenio parser;
* implementira nova faza.

Ako postoji migration ili data-repair potreba, rešiti je eksplicitno.

### 18.2. Automatski rezultat ne prepisuje pouzdaniji ručni podatak

Scraping, derived logika ili LLM rezultat ne smeju bez eksplicitnog canonical pravila da prepišu verified/manual podatke.

### 18.3. `UNKNOWN` je validno stanje

Nepoznata vrednost se ne pretvara automatski u:

```text
false
0
""
```

ako to menja značenje podatka.

Ne izmišljati vrednost da bi model bio kompletan.

### 18.4. Claim nije verification

Tvrdnja iz oglasa, inference ili LLM extraction nije automatski potvrđena činjenica.

Ne podizati nivo pouzdanosti podatka bez odgovarajućeg dokaza.

### 18.5. Listing nije Property

Ne spajati semantiku:

```text
physical property
listing
listing history
```

samo zato što trenutno postoji jedan oglas za jednu nekretninu.

Detaljna pravila su u data-model specifikaciji.

## 19. Destruktivne database operacije

Sve schema promene moraju koristiti migration mehanizam projekta.

Bez eksplicitnog zahteva i odgovarajuće bezbednosne procedure ne:

* dropovati produkcione tabele;
* resetovati production bazu;
* masovno brisati istorijske podatke;
* menjati značenje postojećeg polja bez migracije;
* koristiti production podatke kao test workspace.

Ako migration može ugroziti postojeće podatke, zaštita podataka ima prioritet nad brzinom implementacije.

## 20. Secrets i konfiguracija

Nikada ne commitovati stvarne:

* API ključeve;
* database password-e;
* Telegram token;
* provider secrets;
* credentials.

Koristiti projektni configuration sistem i environment variables.

`.env.example` ne sme sadržati stvarne secrets.

Poslovno promenljive vrednosti ne hardkodovati duboko kroz više modula ako architecture predviđa centralnu konfiguraciju.

## 21. Greške

Ne gutati greške bez razloga.

Zabranjen obrazac:

```python
try:
    ...
except Exception:
    pass
```

Greška mora biti:

* obrađena;
* logovana;
* pretvorena u eksplicitan failure state;
* ili propagirana sloju koji zna kako da je obradi.

Fallback ponašanje mora biti namerno i testabilno.

## 22. Testovi su deo task-a

Implementacija nije završena samo zato što radi u jednom ručnom primeru.

Za trenutni task koristiti relevantne zahteve iz:

```text
docs/08-testing-specification.md
```

Dodati ili izmeniti samo testove potrebne za ponašanje koje se menja.

Ne menjati očekivanje testa samo da bi test postao zelen ako je implementacija pogrešna.

Ne mockovati samu funkcionalnost koju test treba da proveri.

## 23. Verification

Tokom implementacije koristiti ciljane testove za brzu proveru.

Pre završetka task-a pokrenuti sve relevantne provere koje projekat podržava:

* relevant tests;
* formatting;
* lint;
* type checks;
* migration verification;
* startup/runtime verification kada je pogođen.

Ne izmišljati komande.

Koristiti komande i alate koje repository stvarno definiše.

## 24. Ne tvrditi da je nešto provereno ako nije

Razlikovati:

```text
PASS
FAIL
NOT RUN
```

Ako test ili provera nisu mogli da se pokrenu, navesti konkretan razlog.

`NOT RUN` nije `PASS`.

## 25. Definition of Done

Task se može označiti završenim samo kada:

1. implementacija zadovoljava trenutni scope;
2. relevantna canonical specifikacija je ispunjena;
3. nisu implementirane nepovezane buduće funkcionalnosti;
4. relevantni testovi prolaze;
5. migrations su proverene ako su menjane;
6. pogođeni startup/runtime je proverljiv;
7. nema privremenog/debug koda;
8. finalni diff je pregledan;
9. `docs/11-project-status.md` je ažuriran ako je task stvarno završen.

Ako nešto od ključnog acceptance criteria nije ispunjeno, task ostaje incomplete.

## 26. Git i postojeće korisničke izmene

Ne uklanjati ili prepisivati postojeće korisničke izmene samo zato što nisu deo trenutnog task-a.

Pre većih izmena pregledati relevantni diff/status.

Ne raditi široko formatiranje ili rewrite nepovezanih fajlova.

Ne praviti commit ili push osim kada je to eksplicitno traženo ili trenutni workflow projekta izričito nalaže.

## 27. Bug van trenutnog scope-a

Ako se pronađe nepovezan bug:

* ne širiti automatski scope;
* zabeležiti ga kao poznat problem ili predloženi sledeći task.

Dozvoljeno ga je popraviti u trenutnom task-u samo ako:

* direktno blokira implementaciju;
* ugrožava data integrity;
* predstavlja ozbiljan security problem;
* predstavlja vrlo mali očigledan prerequisite.

Objasniti zašto je odstupanje bilo potrebno.

## 28. Kada ne nagađati

Codex treba sam da izabere jednostavniju tehničku opciju kada više opcija imaju isto poslovno značenje.

Ne treba tražiti korisničku odluku za sitne interne detalje.

Ali ne nagađati kada nepoznanica može promeniti:

* identitet podataka;
* finansijski rezultat;
* poslovnu semantiku;
* istorijske podatke;
* security;
* canonical API behavior.

U takvom slučaju prvo jasno identifikovati problem.

## 29. `docs/11-project-status.md`

`project-status` je jedini kratki continuation checkpoint između Codex sesija.

Treba da sadrži samo informacije potrebne da naredna sesija nastavi rad:

```text
Current phase
Current task
Task state
Required context
Completed relevant work
Important implementation facts
Blockers
Important issues
Next task
```

Ne koristiti ga kao:

* drugi phase plan;
* drugi architecture dokument;
* veliki changelog;
* kopiju specifikacija;
* istoriju svakog test run-a.

Git istorija služi za detaljan changelog.

## 30. Ažuriranje project status-a

`docs/11-project-status.md` ažurirati tek nakon što se zna stvarno stanje task-a.

Ako je task završen:

```text
COMPLETED
```

Ako je delimično završen:

```text
IN_PROGRESS
```

Ako je blokiran:

```text
BLOCKED
```

Ne označavati task kao completed ako relevantni acceptance criteria nisu ispunjeni.

`Required Context` za sledeći task treba, kada je praktično, da navede samo potrebne dokumente ili konkretne sekcije.

## 31. Završni Codex report

Završni odgovor nakon task-a treba da bude kratak.

Koristiti format:

```text
Implemented:
- ...

Verified:
- ...

Not verified / blockers:
- ...

Next:
- ...
```

Ne prepričavati svaku promenjenu liniju.

Ako task nije završen, to jasno reći.

## 32. Glavni continuation workflow

Za normalnu novu Codex sesiju dovoljan je workflow:

```text
1. Read AGENTS.md.
2. Read docs/11-project-status.md.
3. Identify the current task.
4. Read the relevant phase section.
5. Read only the specification sections required by that task.
6. Inspect the existing implementation and tests.
7. Implement only the current scope.
8. Run the relevant checks.
9. Inspect the diff.
10. Update project-status only with the verified state.
```

Repository treba da nosi trajno znanje o projektu.

Prompt treba prvenstveno da nosi:

> **šta treba uraditi sada.**

## 33. Konačni princip

Za svaki task birati:

> **najmanju pouzdanu implementaciju koja tačno ispunjava trenutni zahtev, čuva podatke i ostavlja jasan put za narednu fazu.**

Ne graditi generičku platformu za svaki budući slučaj.

Graditi Distressed Property Radar.

