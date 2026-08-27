# Distressed Property Radar — Codex Execution Guide

## 1. Svrha dokumenta

Ovaj dokument je kratak praktični playbook za korišćenje Codex-a tokom razvoja Distressed Property Radar-a.

Njegova svrha je da korisniku objasni:

- kako započeti Codex sesiju;
- kako izabrati jedan task;
- koji kontekst Codex treba da pročita;
- kako završiti i verifikovati task;
- kako nastaviti projekat kroz mnogo sesija;
- kako postupati kod audita, hotfix-a i real-market validacije.

Ovaj dokument nije repository-wide policy.

Repository-wide pravila pripadaju:

    AGENTS.md

Trenutno stanje pripada:

    docs/11-project-status.md

Implementacioni redosled pripada:

    docs/07-phase-plan.md

Canonical behavior pripada odgovarajućim specifikacijama.

Codex ne mora da čita ovaj dokument pri svakom task-u osim ako mu je to eksplicitno potrebno.


# 2. Glavni princip

Repository treba da nosi:

    architecture
    requirements
    current state
    implementation
    tests

Prompt treba prvenstveno da nosi:

    šta sada treba uraditi

Ne ponavljati ceo projekat u svakom promptu.


# 3. Standardni Context Redosled

Za običan implementation task Codex treba da pročita:

    1. AGENTS.md

    2. docs/11-project-status.md

    3. relevantnu fazu iz:
       docs/07-phase-plan.md

    4. samo relevantne delove canonical specifikacija

    5. postojeći kod i testove pogođenog modula

Ne učitavati sve `/docs` fajlove bez potrebe.


# 4. Context Mapa

Koristiti samo ono što task zahteva.

## Product behavior

    docs/01-product-specification.md

## Architecture / module boundaries

    docs/02-system-architecture.md

## Persistence / entities / integrity

    docs/03-data-model.md

## Scraping / source behavior

    docs/04-scraping-specification.md

## Analysis / valuation / risk / deal / opportunity

    docs/05-analysis-specification.md

## API / UI

    docs/06-api-ui-specification.md

## Implementation order

    docs/07-phase-plan.md

## Tests

    docs/08-testing-specification.md

## Deployment / operations

    docs/09-deployment-operations.md

Primer:

Za price parser obično nisu potrebni:

    06-api-ui-specification.md
    09-deployment-operations.md


# 5. Jedan Task

Codex najbolje radi kada dobije jednu proverljivu celinu.

Dobro:

    Implement Phase 3 price-change detection.

Loše:

    Work on the scraper.

Još gore:

    Finish the project.

Dobar task ima jasno:

    input
    behavior
    output
    acceptance criteria


# 6. Veličina Task-a

Preferirati:

    jedan modul

ili:

    jedan mali vertikalni workflow

Primer dobre vertikale:

    Raw Listing
    → normalization
    → persistence
    → DISCOVERED event
    → idempotency tests

Ne spajati bez potrebe:

    scraper
    +
    property matching
    +
    valuation
    +
    dashboard


# 7. Kada Podeliti Task

Podeliti kada postoje velike nezavisne odgovornosti.

Umesto:

    Implement first source.

bolje:

    investigate source
    adapter skeleton
    card parser
    detail parser
    ingestion
    continuous discovery
    lifecycle monitoring

Ne postoji obaveza da jedan Codex run završi celu phase.


# 8. Investigation Task

Investigation bez izmene application code-a je validan task.

Posebno je koristan za:

- novi portal;
- nepoznat API;
- nejasan external ID;
- novu third-party integraciju;
- performance problem;
- production incident.

Rezultat investigation task-a treba da bude konkretna implementaciona preporuka.

Ne izmišljati source behavior ako stvarno stanje nije provereno.


# 9. Pre Izmene Koda

Codex prvo treba da pregleda postojeću implementaciju.

Cilj je da utvrdi:

- koji modul već poseduje odgovornost;
- koji testovi već postoje;
- da li postoje partial/WIP izmene;
- da li je nova datoteka zaista potrebna;
- da li task zahteva migration;
- da li postoje pre-existing failures.

Ne kreirati paralelni `*_v2` modul ako postojeći modul treba proširiti.


# 10. Novi Fajlovi

Ne diktirati Codex-u unapred veliki broj fajlova bez potrebe.

Codex treba da napravi najmanji smislen skup fajlova potreban trenutnom task-u.

Svaki novi fajl mora imati jasnu trenutnu odgovornost.

Ne praviti future placeholders.


# 11. Scope Discipline

Unutar jasno definisanog task-a Codex može samostalno da:

- pregleda kod;
- menja povezane fajlove;
- doda migration kada je stvarno potrebna;
- napiše testove;
- popravi failure koji je sam izazvao;
- izvrši potrebne lokalne podkorake.

Ne treba tražiti potvrdu posle svakog fajla.

Ali ne sme sam nastaviti u sledeću phase.


# 12. Mali Prerequisite

Mali prerequisite je dozvoljen ako je direktno potreban task-u.

Primer:

Current task zahteva novi enum member.

Codex sme da ga doda.

To ne daje dozvolu da implementira ceo budući modul koji će taj enum jednog dana koristiti.


# 13. Kada Zaustaviti Implementaciju

Codex treba da zaustavi scope expansion kada nepoznanica može promeniti:

- business meaning;
- data integrity;
- external identity;
- financial semantics;
- security;
- destructive migration behavior.

Primer:

Source nema očigledan stabilan listing ID.

Ne koristiti proizvoljno:

    hash(title + price)

samo da bi task mogao da se završi.

Prvo istražiti bezbednu identity strategiju.


# 14. Problem Van Scope-a

Codex sme da popravi problem van originalnog task-a samo ako je:

- critical data-integrity bug;
- security problem;
- direktan blocker trenutnog task-a.

Primer:

Task je price history, a otkriveno je da nedostajući listing uniqueness constraint pravi duplikate.

To treba popraviti.

Ne dirati nepovezan frontend styling dok se radi scraper.


# 15. Refactoring

Veliki refactor ne mešati sa feature task-om.

Ako je potreban:

    stabilize behavior
    ↓
    add regression coverage
    ↓
    separate refactor task

Refactor task ne treba sam da dodaje novu product funkcionalnost.


# 16. Dirty Repository

Ako postoje uncommitted izmene, Codex prvo utvrđuje:

- šta pripada current task-u;
- šta je prethodni WIP;
- šta je korisnikova nezavisna izmena.

Ne resetovati, checkout-ovati ili odbacivati korisničke izmene bez eksplicitne instrukcije.


# 17. Pre-Existing Test Failure

Ako test pada pre novih izmena:

1. proveriti da li je failure pre-existing;
2. ako direktno blokira current task i mali je, popraviti ga;
3. ako nije povezan, ostaviti ga i jasno prijaviti.

Ne pretvarati jedan task u „fix entire repository“.


# 18. Testiranje Tokom Rada

Tokom implementacije prvo pokretati ciljane testove pogođenog modula.

Pre završetka task-a pokrenuti:

- relevantne nove testove;
- dovoljan regression subset;
- configured lint/format/type checks;
- migration/startup proveru ako su pogođeni.

Na kraju cele phase pokrenuti širi suite prema `08-testing-specification.md`.


# 19. Ne Menjati Test da Bi Postao Zelen

Ako nova implementacija obori postojeći test:

prvo pitati:

> Da li se canonical requirement stvarno promenio?

Ako nije:

> popraviti implementation.

Ne menjati očekivanje samo zato što novi kod radi drugačije.


# 20. Ne Mockovati Predmet Testa

Ako se testira:

    database uniqueness

koristiti stvarni constraint.

Ako se testira:

    parser

koristiti stvarni parser nad fixture-om.

Ako se testira:

    Deal Engine

pozvati stvarnu calculation logiku.


# 21. Diff Review

Pre završetka task-a Codex treba da pregleda finalni diff.

Posebno tražiti:

- scope creep;
- accidental debug code;
- secrets;
- duplicate abstractions;
- unrelated formatting;
- unnecessary dependency;
- generated artifact koji ne pripada repository-ju;
- placeholder future code;
- slučajno obrisane korisničke izmene.


# 22. Project Status

`docs/11-project-status.md` je jedini continuation checkpoint.

Ne praviti:

    handoff-1.md
    handoff-final.md
    progress-notes-2.md

Status se ažurira tek kada je stvarno poznato trenutno stanje.


# 23. Kada Task Nije Završen

Ako nedostaje required behavior ili relevantni testovi ne prolaze:

    task != COMPLETED

`project-status.md` treba da zadrži current task i jasno opiše:

- šta jeste završeno;
- šta nije;
- blocker;
- sledeći konkretan korak.

Ne koristiti „done“ za partial implementation.


# 24. Project Status nije Changelog

Git istorija je changelog koda.

`project-status.md` treba da bude kratak.

Ne dodavati dnevnik svake izmene, rename-a i testa iz prethodnih meseci.


# 25. Specification vs Implementation

Ako code slučajno ne odgovara canonical specification-u:

> po default-u popraviti code.

Ne menjati spec samo da bi opravdala trenutnu implementaciju.


# 26. Kada Menjati Specification

Spec menjati ako se pojavi nova stvarna činjenica koja menja canonical behavior.

Primer:

    originalna pretpostavka:
    stable ID is in detail URL

    realno stanje:
    stable ID exists only in source JSON payload

Ako je promena samo source-specific tehnički detalj, možda nije potrebna promena globalne specifikacije.

Ako menja sistemsku invarijantu, prvo ažurirati canonical spec.


# 27. Source-Specific Dokumentacija

Ako konkretan source postane dovoljno složen, dozvoljeno je:

    docs/sources/<source-code>.md

Sadrži samo source-specific činjenice kao:

- URL/query behavior;
- pagination;
- ID extraction;
- browser requirement;
- poznata ograničenja.

Ne kopirati u njega globalna scraping pravila.


# 28. Data Repair

Code fix i data repair nisu ista stvar.

Ako bug već upiše loše production podatke:

    1. zaustavi buduću štetu
    2. popravi code
    3. identifikuj već pogođene podatke
    4. zasebno izvrši controlled repair

Repair treba, gde je moguće, da ima:

- precise affected-row selection;
- dry-run/report;
- backup;
- idempotency;
- post-repair validation.

Schema change koristi migration.

Jednokratni business-data repair ne mora biti migration.


# 29. Analytical Versioning

Ako code promena menja analytical rezultat za isti input, proveriti da li treba promeniti:

    model_version
    rules_version
    formula_version
    prompt_version

Primeri:

- valuation formula changed;
- Risk rules changed;
- Opportunity thresholds semantics changed;
- LLM prompt meaning changed.

Ne menjati semantic version zbog:

- private rename-a;
- formatting-a;
- log change-a;
- behavior-preserving performance optimizacije;
- test refactor-a.


# 30. Persistent History Nakon Phase 3

Kada crawler već ima vrednu production istoriju, ingestion task mora posebno da štiti:

- existing listings;
- listing events;
- property history;
- migrations;
- idempotency.

Production database se ne resetuje kao obična development prečica.


# 31. Historical Analysis Nakon Phase 16

Historical/backtesting task mora koristiti:

    as_of

i eksplicitno zaštititi:

> future data must not be visible.

Relevantni task treba da dobije look-ahead regression testove.


# 32. Manual Market Validation

Codex može pomoći da pripremi:

- representative sample;
- queries;
- tables;
- metrics;
- comparison UI.

Ali korisnik i dalje treba da proceni stvari poput:

    Da li su ovi comps stvarno smisleni?

    Da li bih zbog ovog alerta zaista pozvao prodavca?

Test suite ne može zameniti ovu proveru.


# 33. Calibration

Ne zadavati:

    Make valuation more accurate.

Zadati konkretno opažen problem.

Primer:

    low-floor units are systematically overvalued
    microzone X leaks comps from Y
    listing-only confidence is too high

Zatim tražiti:

- malu relevantnu korekciju;
- regression test;
- odgovarajući model/rules version update.


# 34. Investment Strategy

Codex ne treba sam da smanji:

- minimum profit;
- minimum liquidity;
- downside threshold;
- confidence threshold;

samo zato što sistem proizvodi malo alertova.

To su product/investment odluke.

`NO QUALIFYING OPPORTUNITIES` je validan rezultat.


# 35. Optimizacija

Ne koristiti prompt:

    Make everything faster.

Bolje:

    Market scan takes 4h.
    Target interval is 3h.
    Measure the bottleneck and implement the smallest safe optimization.

Performance optimization treba da bude zasnovana na merenju.


# 36. AI

Ne tražiti:

    Add AI wherever useful.

LLM/AI se koristi samo gde canonical product/analysis specifikacija to predviđa ili gde novi dokazani problem opravda promenu specifikacije.


# 37. Završni Codex Report

Posle task-a finalni report treba da bude kratak:

    Implemented:
    - ...

    Verified:
    - ...

    Not verified / blockers:
    - ...

    Exact next task:
    - ...

Ne ispisivati ceo diff kao esej.

Ako nešto nije provereno:

    Not verified

ne:

    Everything should work.


# 38. Daily Workflow

Većina rada treba da izgleda:

    1. Open Codex
    2. Ask for one next task
    3. Codex reads minimal required context
    4. Codex inspects existing implementation
    5. Codex implements
    6. Codex tests
    7. Codex reviews diff
    8. Codex updates project-status if complete
    9. User reviews result
    10. Commit if desired
    11. Repeat


# 39. Milestone Workflow

Na kraju važne phase:

    complete remaining phase tasks
    ↓
    run full relevant test suite
    ↓
    run phase audit
    ↓
    fix missing acceptance criteria
    ↓
    perform required real-world validation
    ↓
    update project-status
    ↓
    begin next phase


# 40. Git

Repository-wide Git pravila pripadaju `AGENTS.md`.

Praktično:

- mali smisleni commits su poželjni;
- ne commitovati failing task kao finalan rezultat;
- commit i push nisu ista operacija;
- kompleksan GitFlow nije potreban za solo V1;
- rizičan veliki migration/refactor može opravdati poseban branch.

Codex ne treba automatski da commit/push-uje ako to nije eksplicitno traženo.


# 41. Prompt Template — Normalni Continuation

Najčešći prompt:

    Continue Distressed Property Radar.

    Read AGENTS.md and docs/11-project-status.md first.

    Implement only the current next task recorded there.

    Then read the relevant PHASE section in docs/07-phase-plan.md and only the additional specification sections needed for that task.

    Inspect the existing implementation and tests before editing.

    Do not implement later phases or unrelated improvements.

    Add/update the relevant tests, run all checks appropriate for the task, and inspect the final diff.

    Update docs/11-project-status.md only after successful verification.

    Report:
    Implemented:
    Verified:
    Not verified / blockers:
    Exact next task:


# 42. Prompt Template — Start Nove Phase

    Start PHASE [X] of Distressed Property Radar.

    Read:
    - AGENTS.md
    - docs/11-project-status.md
    - PHASE [X] in docs/07-phase-plan.md
    - only the specification sections relevant to the first task

    First inspect the repository and verify that the prerequisites from the previous phase actually exist.

    Implement only the first logical task of PHASE [X], not the entire phase unless it is genuinely small.

    Keep the implementation minimal and consistent with the existing architecture.

    Add the required tests and run the relevant verification.

    Update project-status only after successful completion.

    Report the exact recommended next task.


# 43. Prompt Template — Phase Audit

    Audit PHASE [X] of Distressed Property Radar.

    Read:
    - AGENTS.md
    - docs/11-project-status.md
    - PHASE [X] acceptance criteria in docs/07-phase-plan.md
    - only the canonical specifications relevant to this phase
    - current implementation and tests

    Do not implement future-phase functionality.

    Compare the repository against every PHASE [X] acceptance criterion.

    Fix only:
    - clear omissions;
    - bugs;
    - data-integrity risks;
    - missing regression tests;
    - accidental duplicate implementation introduced by this phase.

    Run the full relevant test suite.

    If PHASE [X] is complete, update project-status.

    Otherwise leave it incomplete and list the exact remaining tasks.


# 44. Prompt Template — Production Hotfix

    Production hotfix for Distressed Property Radar.

    Problem:
    [precise observed issue]

    Impact:
    [data/process potentially at risk]

    Read AGENTS.md and only the specifications for the affected subsystem.

    Priority:
    1. prevent further data corruption or incorrect critical behavior;
    2. preserve historical data;
    3. reproduce the issue with a regression test where possible;
    4. implement the smallest safe root-cause fix;
    5. determine whether existing production data requires repair.

    Do not add features, redesign architecture, or refactor unrelated code.

    Run the relevant regression suite.

    Report:
    - root cause;
    - fix;
    - verification;
    - production data impact;
    - whether a separate repair task is required.


# 45. Promptovi koje treba izbegavati

Ne koristiti široke promptove kao:

    Finish the whole project.

    Implement the next 8 phases.

    Add everything that is missing.

    Improve everything.

    Modernize the architecture.

    Optimize the entire backend.

    Add AI wherever possible.

    Refactor the whole repository.

Takvi promptovi brišu scope granice i povećavaju rizik.


# 46. Preferirani Task Prompt

Ako korisnik želi konkretniji task od generic continuation prompt-a, dovoljno je:

    Implement Phase 3 price-change detection.

    Read AGENTS.md, docs/11-project-status.md and the relevant sections of:
    - docs/04-scraping-specification.md
    - docs/08-testing-specification.md

    Use the existing first-source ingestion pipeline.

    Do not implement removal/reappearance yet.

    Add idempotency and price-event regression tests.

    Update project-status only if this task is fully verified.

Nema potrebe da se ponavlja kompletan project context.


# 47. Konačni Princip

Najefikasniji Codex workflow je:

    SPECIFY ONCE
    ↓
    STORE KNOWLEDGE IN REPOSITORY
    ↓
    KEEP CURRENT STATE SHORT
    ↓
    CHOOSE ONE TASK
    ↓
    READ ONLY RELEVANT CONTEXT
    ↓
    INSPECT EXISTING CODE
    ↓
    IMPLEMENT MINIMUM COMPLETE SOLUTION
    ↓
    TEST
    ↓
    REVIEW DIFF
    ↓
    UPDATE PROJECT STATUS
    ↓
    NEXT TASK

Najvažnije pravilo:

> **Repository nosi znanje o projektu; prompt nosi samo trenutnu nameru.**

Ako se to poštuje, projekat može da se razvija kroz veliki broj Codex sesija bez stalnog ponavljanja celog konteksta i bez nekontrolisanog širenja dokumentacije i implementacije.