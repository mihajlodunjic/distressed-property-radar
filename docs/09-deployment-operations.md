# Distressed Property Radar — Deployment & Operations Specification

## 1. Svrha dokumenta

Ovaj dokument definiše kako se Distressed Property Radar:

- pokreće;
- deployuje;
- štiti;
- nadzire;
- bekapuje;
- oporavlja;
- održava u production-u.

Source of truth je za:

- development i production runtime;
- Docker Compose topologiju;
- server sizing;
- environment variables i secrets;
- persistent storage;
- database migrations;
- backup i restore;
- API/worker procese;
- scheduler ownership;
- restart/recovery behavior;
- production access;
- TLS i reverse proxy;
- logging;
- resource monitoring;
- disk/retention;
- deployment i rollback;
- incident response;
- disaster recovery;
- production readiness.

Ne definiše:

- business funkcionalnosti;
- SQL/data-model semantiku;
- scraper parsing i lifecycle pravila;
- analytical formule;
- API contract;
- detaljan test matrix;
- implementation order.

Za njih koristiti ostale canonical dokumente.


# 2. Osnovni Production Princip

V1 koristi:

    1 VPS
    +
    Docker Compose

dok realna merenja ne pokažu da je potrebna složenija infrastruktura.

Ne uvoditi unapred:

- Kubernetes;
- Docker Swarm;
- service mesh;
- autoscaling;
- multi-server application cluster;
- distributed queue cluster;
- komplikovani CI/CD deployment sistem.

Ovo je privatni alat.

Operational complexity mora ostati mala.


# 3. Početni Server

Komotan početni V1 VPS:

    8 vCPU
    16 GB RAM
    160–250 GB NVMe SSD

Može podržati:

- PostgreSQL/PostGIS;
- FastAPI;
- React frontend;
- HTTP crawlers;
- scheduler/workers;
- standardne analytical jobs;
- Telegram;
- ograničen Playwright workload.

Za rani V0, ako browser scraping skoro ne postoji:

    4 vCPU
    8 GB RAM
    80–160 GB SSD

može biti dovoljno.

Ne skalirati unapred.

Ako browser workload prvi postane problem, prvo razmotriti:

    lower browser concurrency
    →
    more RAM / stronger VPS

pre distribuirane arhitekture.


# 4. Production Topologija V1

Početni Compose stack:

    reverse-proxy
    frontend
    api
    worker
    postgres

Opcionalno:

    playwright-worker

samo ako browser scraping stvarno postoji.

Konceptualno:

    Internet
       │
       ▼
    Reverse Proxy
       │
       ├── Frontend
       │
       └── FastAPI
               │
               ▼
           PostgreSQL

    Worker ───────► PostgreSQL

    Optional:
    Playwright Worker ─► application services / PostgreSQL


# 5. Container Odgovornosti

## `postgres`

Sadrži:

    PostgreSQL
    PostGIS
    persistent database volume

Database data mora preživeti container recreation.


## `api`

Pokreće FastAPI.

Ne treba da pokreće glavni crawler scheduler kao hidden background thread ako postoji dedicated worker.


## `worker`

Pokreće trenutno implementirane background poslove, npr:

- discovery;
- market scan;
- reconciliation;
- analytics;
- notifications;
- maintenance.

Jedan listing/job failure ne sme rušiti ceo worker ako aplikacija može bezbedno da ga izoluje.


## `playwright-worker`

Postoji samo kada browser workload opravda odvajanje.

Razlog:

- RAM izolacija;
- Chromium process control;
- zaštita API/discovery workload-a.


## `frontend`

Servira production build direktno ili preko reverse proxy-ja, prema izabranoj implementaciji.


## `reverse-proxy`

Odgovoran najmanje za:

- TLS termination;
- routing;
- basic access controls;
- request-size limits;
- compression gde ima smisla.


# 6. Redis / Celery

Nisu deo V1 deployment-a.

Uvesti tek kada application architecture stvarno zahteva queue capability koji trenutni PostgreSQL/job model ne može razumno da podrži.

Signal za razmatranje može biti:

- persistent job backlog;
- više worker servera;
- složene priority/retry potrebe;
- analysis značajno blokira crawling;
- Postgres-based claiming postaje problem.

Do tada:

> ne pokretati Redis samo zato što projekat ima background jobs.


# 7. Reverse Proxy

Koristiti jedno jednostavno rešenje.

Prihvatljivo:

    Caddy

ili:

    Nginx

Ako nema posebnog razloga, Caddy je dobar V1 izbor zbog jednostavnog HTTPS setup-a.

Ne uvoditi oba.


# 8. HTTPS

Ako se aplikaciji pristupa preko javne mreže:

    HTTPS

je obavezan.

HTTP je dozvoljen:

- unutar Docker network-a;
- lokalno u development-u;
- unutar namerno privatnog trusted network-a.


# 9. Private Access

Dashboard i API nisu javna aplikacija.

Mora postojati single-user access protection.

Prihvatljivi V1 pristupi uključuju:

- application-level login;
- private VPN/Tailscale-style access;
- drugi jednostavan kontrolisan private-access model.

Ne ostaviti bez zaštite:

    dashboard
    API
    database


# 10. Same-Origin Production

Kada je praktično, preferirati:

    https://radar.example.com/

za frontend i:

    https://radar.example.com/api/...

za backend.

Time se pojednostavljuju:

- cookies;
- auth;
- CORS;
- TLS;
- Telegram deep links.


# 11. CORS

Dozvoliti samo stvarne frontend origin-e.

Ne koristiti široko:

    Access-Control-Allow-Origin: *

za credentialed private API bez razloga.

Ako frontend i backend koriste isti origin, preferirati da se CORS problem gotovo potpuno izbegne.


# 12. PostgreSQL Exposure

Production PostgreSQL port ne sme biti javno dostupan internetu.

Dozvoljeno:

    Docker internal network

i siguran administratorski pristup kroz:

- SSH tunnel;
- `docker exec`;
- drugi private tunnel.

Ne otvarati:

    0.0.0.0:5432

„privremeno“ radi GUI alata.


# 13. Firewall

Javno otvoriti samo ono što je potrebno.

Tipično:

    22   SSH
    80   HTTP redirect / certificate challenge
    443  HTTPS

Prilagoditi stvarnom server setup-u.

Database i internal worker portovi nisu public.


# 14. SSH

Koristiti SSH keys.

Nakon potvrđenog administratorskog pristupa preferirati:

    password authentication disabled
    root password login disabled

Ne menjati SSH security settings automatski na način koji može zaključati korisnika van servera.


# 15. Production Direktorijum

Koristiti jednu stabilnu lokaciju, npr:

    /opt/distressed-property-radar/

ili:

    /srv/distressed-property-radar/

Ne menjati lokaciju kroz deployment-e bez razloga.

Primer:

    /opt/distressed-property-radar/
      docker-compose.yml
      .env
      backend/
      frontend/
      backups/

PostgreSQL volume nije Git-tracked application folder.


# 16. Environment Fajlovi

Repository sadrži:

    .env.example

bez pravih secrets.

Production host sadrži:

    .env

koji nije commitovan.

Tačni nazivi environment variables moraju odgovarati stvarnom settings modelu.

Tipične kategorije:

    APP_ENV
    APP_BASE_URL

    DATABASE_URL

    LOG_LEVEL

    SECRET_KEY

    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

    LLM_API_KEY
    LLM_MODEL

    source-specific settings

Promenljiva se dodaje tek kada capability koji je koristi postoji.


# 17. Secrets

Nikada ne commitovati:

- DB password;
- Telegram token;
- LLM key;
- session/auth secret;
- source credentials;
- cookies;
- private access token-e.

Ako secret završi u Git istoriji:

    remove from code
    +
    rotate/revoke secret

Samo brisanje iz poslednjeg commit-a nije dovoljno.


# 18. `.env.example`

Sadrži:

    VARIABLE_NAME=

ili bezbedan development primer.

Ne sadrži production vrednosti.

Nestandardne promenljive mogu imati kratko objašnjenje.


# 19. Development Environment

Infrastructure dependencies treba da budu reproduktivne kroz Docker Compose.

Minimum:

    PostgreSQL + PostGIS

Backend/frontend mogu u development-u raditi:

- lokalno;
- ili u container-ima.

Ne zahtevati production-like kompleksnost za lokalni development.


# 20. Environment Separation

Razlikovati najmanje:

    development
    test
    production

Lokalni development ne sme po default-u koristiti production `DATABASE_URL`.

Test suite ne koristi production DB.


# 21. Persistent Database Storage

PostgreSQL mora koristiti persistent Docker volume ili pouzdan bind mount.

Container recreation ne sme izgubiti database.

Potrebno je proveriti:

    docker compose down
    docker compose up

bez `-v`

i potvrditi da data ostaje.


# 22. Zabranjena Obična Deployment Komanda

Ne koristiti:

    docker compose down -v

na production-u tokom normalnog deployment-a.

Može ukloniti persistent volumes.


# 23. Database User

Application treba da koristi dedicated database user.

Ne koristiti PostgreSQL superuser za normalni runtime bez potrebe.

U V1 migration i application user mogu biti isti ako to značajno pojednostavljuje deployment, ali privilegije treba držati samo koliko je potrebno.


# 24. Database Connection Pool

API i worker koriste ograničen connection pool.

Ne praviti novu PostgreSQL konekciju za svaki listing.

Ne koristiti ogroman pool na single-VPS setup-u sa malim brojem procesa.

Pool sizing podešavati prema realnom process/workload broju.


# 25. Database Migrations

Schema promene koriste canonical migration alat:

    Alembic

Deployment koji menja schema mora izvršiti:

    alembic upgrade head

ili stvarni ekvivalent definisan repository-jem.

Migration se izvršava jednom.

Ne dozvoliti da svaki API/worker container paralelno pokušava migration pri startup-u.


# 26. Migration Redosled

Za normalan deployment:

    target code ready
    ↓
    backup if migration is risky
    ↓
    migration
    ↓
    application containers using new schema

Ako migration ne uspe:

> deployment ne nastavlja automatski sa kodom koji očekuje novu schema.


# 27. Rizična Migration

Pre migration-a koja:

- uklanja data;
- transformiše veliki broj redova;
- menja critical relations;
- menja semantic meaning;
- uvodi rizičan backfill;

napraviti backup.

Preferirati backward-compatible schema changes gde je praktično.


# 28. Expand-and-Contract

Za rizične izmene u već vrednoj production bazi preferirati:

    1. add new schema
    2. deploy compatible code
    3. backfill/migrate data
    4. switch reads/writes
    5. remove old schema later

umesto:

    rename/drop everything in one deployment


# 29. Backup je Obavezan

Historical listing/property dataset je jedan od najvrednijih asset-a projekta.

Production crawler ne treba dugoročno da radi bez automatizovanog backup-a.


# 30. V1 Backup Strategija

Minimum:

    daily logical PostgreSQL backup

koristeći:

    pg_dump

Preferirati compressed custom format:

    pg_dump -Fc

Konkretne commands se dokumentuju tek kada realna Compose/service imena postoje.


# 31. Backup Retention

Početna razumna politika:

    daily   → 14 days
    weekly  → 8 weeks
    monthly → 6–12 months

Vrednosti mogu biti promenjene prema storage trošku i vrednosti dataseta.

Ne čuvati samo jedan poslednji backup.

Korupcija se može otkriti sa zakašnjenjem.


# 32. Off-Server Backup

Backup samo na istom VPS disku nije dovoljan.

Bar jedna backup kopija treba da postoji fizički/logički odvojeno, npr:

    S3-compatible object storage

ili drugi pouzdan off-server storage.

Provider nije architectural dependency.


# 33. Backup Security

Backup storage nije public.

Koristiti:

- private bucket/access;
- provider encryption at rest;
- dodatnu encryption strategiju kada risk model to opravdava.

Backup credentials su secrets.


# 34. Backup Failure

Automatski backup mora imati vidljiv status.

Minimum:

    backup success/failure log

Kasnije poželjno:

    operational Telegram warning

za failed backup.


# 35. Restore mora biti Testiran

Backup koji nikada nije restore-ovan nije dovoljan dokaz recovery sposobnosti.

Periodično:

    create empty test DB
    ↓
    restore backup
    ↓
    run basic integrity checks

Ne testirati restore preko production baze.


# 36. V1 Recovery Point Objective

Sa daily backup strategijom početni RPO je približno:

    <= 24 hours

Ako historical dataset postane dovoljno vredan, razmotriti:

- češće backup-e;
- WAL archiving;
- point-in-time recovery.

Ne uvoditi PITR pre stvarne potrebe.


# 37. Disaster Recovery

Potpuni gubitak VPS-a mora biti rešiv približno ovako:

    1. provision new VPS
    2. install runtime requirements
    3. clone repository
    4. recreate .env / secrets
    5. start infrastructure
    6. restore PostgreSQL backup
    7. run required migrations
    8. start API/workers
    9. verify application
    10. verify source health
    11. resume crawling

Ako repository + secrets + off-server backup nisu dovoljni da se ovo uradi, recovery strategija nije kompletna.


# 38. Data Ownership

Najvažniji production asset-i su:

    PostgreSQL data
    historical listing events
    analytical history
    manual feedback
    outcomes
    backups

Application containers treba da budu disposable.

Application runtime treba da može ponovo nastati iz:

    Git repository
    configuration
    secrets
    persistent data / backup


# 39. Raw Payload Retention

Raw HTML/JSON je transient/diagnostic storage.

Ne dozvoliti nekontrolisan rast.

Cleanup sme brisati samo podatke kojima retention policy to dozvoljava.

Nikada cleanup-ovati kao raw podatke:

- normalized listing-e;
- listing events;
- property history;
- analytical history;
- manual feedback.

Pre prvog production cleanup-a imati:

- dry-run; ili
- pouzdan test.


# 40. Images

Originalne listing images ne skladištiti masovno na VPS po default-u.

Ako kasnije postoji potreba za trajnim čuvanjem:

    object storage

je prirodniji izbor.

VPS disk prvenstveno koristi:

- application;
- database;
- ograničene temporary files;
- kratkoročni backup cache.


# 41. Disk Monitoring

Početne smernice:

    ~70% disk → warning
    ~85% disk → critical

Pragovi mogu biti configurable.

Ne čekati 100%.

Pun disk može ugroziti:

- PostgreSQL;
- Docker;
- backup;
- logging;
- worker processing.


# 42. Disk Full Incident

Ako disk brzo raste:

1. smanjiti/zaustaviti bezbedno workload koji generiše rast ako je potrebno;
2. proveriti Docker logs;
3. proveriti raw payload storage;
4. proveriti backup cache;
5. proveriti DB growth;
6. pronaći uzrok pre brisanja.

Nikada ručno ne brisati fajlove iz:

    PGDATA

radi oslobađanja prostora.


# 43. Docker Log Rotation

Container logs moraju imati bounded rotation.

Koristiti Docker logging konfiguraciju sa konceptima poput:

    max-size
    max-file

ili ekvivalent.


# 44. Application Logs

Preferirati:

    stdout
    stderr

koje prikuplja container runtime.

Ne pisati nekontrolisane log fajlove u ephemeral container filesystem.


# 45. Log Level

Production default:

    INFO

`DEBUG` uključivati privremeno.

Ne ostavljati globalni DEBUG dugoročno ako:

- proizvodi mnogo logova;
- otkriva nepotrebne podatke;
- otežava signal/noise.


# 46. Centralized Logging

Nije V1 requirement.

Razmotriti tek ako:

- postoji više servera;
- incident investigation postane težak;
- local log retention više nije dovoljna.


# 47. Container Restart Policy

Production servisi treba da koriste razumnu restart policy, npr:

    unless-stopped

ili odgovarajući ekvivalent.

Posle server reboot-a treba automatski da se vrate relevantni:

- postgres;
- api;
- worker;
- reverse proxy;
- frontend.


# 48. Restart nije Job Retry

Container restart nije normalan način rešavanja individualne business greške.

Ako jedan listing ima parser error:

- evidentirati error;
- nastaviti batch gde je bezbedno.

Ne crashovati worker namerno samo da bi Docker restartovao proces.


# 49. Scheduler Ownership

Za V1 mora postojati tačno jedan aktivni scheduler ako schedule nije multi-instance coordinated.

Najjednostavnije:

    worker
    = scheduler owner

API nema scheduler.

Ne dozvoliti:

    API scheduler
    +
    worker scheduler

koji pokreću iste jobs duplo.


# 50. Worker Startup

Pri startup-u worker:

1. uspostavlja DB connection;
2. inicijalizuje scheduler/job loop;
3. učitava enabled configuration;
4. nastavlja processing.

Restart ne sme duplirati već završene business događaje.

Ovo se oslanja na application idempotency.


# 51. Graceful Worker Shutdown

Pri normalnom shutdown/deploy signal-u, gde je praktično:

1. prestati sa uzimanjem novih jobs;
2. kratkim aktivnim jobs dozvoliti završetak;
3. ili ih bezbedno prekinuti tako da mogu biti retry-ovani.

Crash ne sme ostaviti trajni lažni:

    RUNNING forever

state.


# 52. Stale Job Recovery

Ako job ostane `RUNNING` duže od realnog maksimuma zbog crash-a:

- označiti ga `FAILED` / `STALE`; ili
- vratiti ga u retryable stanje,

prema job modelu.

Ordinary worker crash ne treba da zahteva ručni SQL fix za svaki job.


# 53. Long-Running Jobs

Dugi maintenance/market scan ne sme trajno blokirati latency-sensitive discovery.

Ako se to pojavi kao realan problem, prvi korak je odvajanje execution capacity-ja, npr:

    discovery-worker
    maintenance-worker

pre uvođenja potpuno nove distributed infrastructure.


# 54. Playwright Isolation

Ako Chromium značajno utiče na RAM:

- koristiti zaseban worker/container;
- ograničiti concurrency;
- zatvarati page/context/browser resources;
- pratiti broj Chromium procesa.

Browser resources moraju se zatvoriti i na exception path-u.


# 55. OOM Incident

Ako server ostaje bez memorije, proveriti:

- Playwright concurrency;
- leaked Chromium processes;
- worker count;
- PostgreSQL memory;
- druge runaway processes.

Tipični prvi potezi:

    reduce browser concurrency
    clean leaked browser processes
    restart affected worker
    increase RAM if justified

Swap nije trajno rešenje.


# 56. Swap

Mali swap može ublažiti kratki memory spike.

Ako normalni workload redovno tera server duboko u swap:

> smanjiti workload ili povećati RAM.


# 57. Health Endpoint

API treba da ima osnovni:

    GET /health

koji potvrđuje da application process radi.

Po potrebi može proveriti osnovnu DB connectivity.

Ne treba svaki health request da:

- crawl-uje portals;
- zove LLM;
- šalje Telegram;
- izvršava veliki analytical query.

Source health se prati posebno.


# 58. Liveness / Readiness

Ne moraju postojati od prvog dana.

Uvesti odvojene:

    liveness
    readiness

tek kada deployment tooling ili runtime to stvarno koristi.


# 59. External Uptime Monitoring

Poželjno je imati jednostavan eksterni monitor za:

    HTTPS /health

Ne graditi sopstveni monitoring servis.

Koristiti jednostavan postojeći uptime monitoring provider kada za tim postoji production potreba.


# 60. Source Health

Operational UI/logovi moraju moći da odgovore najmanje:

    is source enabled?
    current status?
    last successful crawl?
    last discovery?
    last market scan?
    recent errors?

Source Health semantika pripada scraping specifikaciji.

Ovaj dokument određuje da mora biti vidljiva u operations workflow-u.


# 61. Operational Alerts

Telegram se može koristiti i za operativne probleme, npr:

    source FAILED
    backup failed
    disk critical
    crawler has not succeeded for N hours

Operational alert mora biti jasno odvojen od property Opportunity Alert-a.


# 62. Operational Alert Dedupe

Ako problem traje satima, ne slati istu poruku svakih nekoliko minuta.

Potrebni su:

- dedupe;
- cooldown;
- eventualni periodic reminder.

Primer:

    initial failure alert
    ↓
    optional reminder after several hours


# 63. V1 Observability Minimum

Bez Prometheus/Grafana stack-a mora biti moguće odgovoriti na:

    Da li API radi?
    Da li worker radi?
    Da li PostgreSQL radi?
    Da li svaki source radi?
    Kada je bio poslednji discovery?
    Koliko recent jobs je palo?
    Da li backup radi?
    Koliko diska je slobodno?

Ako se na ovo može odgovoriti kroz:

- health;
- Source Health;
- job summaries;
- logs;
- hosting metrics;

V1 observability je dovoljna.


# 64. Server Metrics

Pratiti najmanje:

    CPU
    RAM
    swap
    disk usage
    load
    disk I/O when relevant

Ne mora sve biti u application dashboard-u.

Hosting provider metrics su dovoljni za rani V1.


# 65. Database Metrics

Povremeno pratiti:

    total database size
    largest tables
    connection count
    slow queries
    index usage when relevant

Posebno rast:

    listings
    listing_events
    raw records
    analytical history


# 66. PostgreSQL Maintenance

Autovacuum ostaje uključen.

Ne uvoditi rutinski:

    VACUUM FULL

bez stvarne dijagnostike.

Ako query postane spor:

    EXPLAIN
    EXPLAIN ANALYZE

pa tek onda menjati indekse/query.


# 67. Database Size Inspection

Poželjna je jednostavna operations komanda ili query za:

- total DB size;
- largest tables;
- raw records;
- listing events;
- analytical history.

Ne treba poseban frontend ekran samo radi ovoga.


# 68. Release Identity

Production application treba da može da loguje/prikaže:

    Git commit SHA

ili jednostavnu application version vrednost.

Mora biti lako odgovoriti:

> Koji code version trenutno radi?


# 69. Startup Log

Pri startup-u korisno logovati:

    environment
    application version
    worker/process type
    database reachable

Ne logovati:

- passwords;
- tokens;
- API keys;
- cookies.


# 70. Standardni Deployment Workflow

Deployment treba da bude predvidljiv.

Minimalni redosled:

    1. identify desired commit/version
    2. confirm environment changes
    3. obtain/build target images
    4. run relevant pre-deploy verification
    5. backup DB if migration is risky
    6. run migrations
    7. start/update containers
    8. check container state
    9. check /health
    10. verify private access
    11. verify worker startup
    12. inspect startup logs
    13. verify scheduler ownership
    14. verify source/job status

Konkretne shell commands treba dokumentovati tek kada stvarni repository/runtime postoji.


# 71. Simple Deployment Mechanism

Za rani V1 prihvatljiv je disciplinovan:

    git pull
    docker compose build
    docker compose up -d

workflow.

Kasnije se može preći na image registry/CI deployment.

Ne graditi kompleksan CI/CD sistem pre potrebe.


# 72. Zero-Downtime

Nije V1 requirement.

Kratak maintenance downtime je prihvatljiv za privatni alat.

Ne uvoditi:

- load balancer;
- blue/green;
- rolling multi-node deploy;

samo radi nekoliko minuta potencijalnog downtime-a.

Prioritet:

    SAFE DEPLOYMENT


# 73. Deploy ne Restartuje Celo Tržište

Normalan application restart/deploy ne treba automatski da izazove:

    full market detail refresh
    full historical rebuild

Scheduler nastavlja iz persistent application state-a.

Maintenance rescan se pokreće samo eksplicitno kada je potreban.


# 74. Production Smoke nakon Deploy-a

Minimum:

- `GET /health`;
- private login/access radi;
- worker radi;
- schema je na expected migration version;
- nema repeated startup exception-a;
- scheduler/job state deluje normalno.

Ako UI već postoji:

- Action Queue ili glavni ekran se učitava.

Ako scraper postoji:

- koristiti mali safe source check; ili
- proveriti prvi normalni scheduled discovery.

Ne koristiti full-market scan kao deployment smoke test.


# 75. Application Rollback

Pre deployment-a mora biti poznat prethodni stabilan:

    commit
    tag
    image version

Ako novi code ima ozbiljan problem, application rollback može biti:

    return to previous version
    rebuild/restart

ako database schema ostaje kompatibilna.


# 76. Database Rollback nije isto što i Application Rollback

Ne pretpostavljati:

    old application
    =
    old database

Ako nova migration ostane backward-compatible, moguće je vratiti samo application.

Ako nije:

- potrebna je posebna migration/recovery odluka;
- ne izvršavati nasumični downgrade bez razumevanja data posledica.


# 77. Emergency Database Restore

Database restore je poslednja opcija za slučajeve poput:

- stvarne data corruption;
- destructive migration failure;
- accidental mass deletion.

Pre production restore-a:

1. zaustaviti relevantne write procese;
2. ako je moguće sačuvati backup trenutnog oštećenog stanja;
3. identifikovati restore point;
4. preferirati probni restore u odvojenu bazu;
5. proveriti integrity;
6. tek zatim izvršiti production recovery.

Ne raditi restore samo zato što jedan scraper nije radio nekoliko dana.


# 78. Source Parser Incident

Ako portal promeni markup i parser postane nepouzdan:

    source → DEGRADED/FAILED
    ↓
    stop unsafe removal inference
    ↓
    preserve history
    ↓
    other sources continue
    ↓
    capture minimal failing fixture
    ↓
    fix parser
    ↓
    run tests
    ↓
    deploy
    ↓
    controlled reconciliation

Ne:

    reset database
    delete listings
    re-scrape everything from scratch


# 79. Source Outage

Za timeout/5xx:

- koristiti configured bounded retry;
- evidentirati failure;
- ne zaključivati removal;
- sledeći scheduled run pokušava ponovo.

Source outage nije listing lifecycle evidence.


# 80. Rate-Limit Incident

Za `429` ili drugi jasan rate-limit signal:

    reduce pressure
    backoff
    record degradation

Ne:

- povećavati concurrency;
- agresivno retry-ovati;
- uvoditi bypass samo da bi scan nastavio istom brzinom.


# 81. LLM Provider Outage

Očekivani behavior:

    scraping continues
    history continues
    independent analytics continue
    LLM status fails/pends
    downstream output is partial/conservative

Nakon provider recovery-ja retry-ovati relevantne failed analyses prema normalnim application pravilima.


# 82. LLM Usage Monitoring

Pratiti približno:

    calls/day
    failed calls

Kasnije po potrebi:

    token usage
    estimated cost

Cilj nije billing platform.

Cilj je primetiti runaway analysis loop.


# 83. LLM Runaway Protection

Input hashing/idempotency treba da spreči beskonačno ponavljanje identične analize.

Dodatno je korisno imati upozorenje ako se LLM request volume naglo promeni za red veličine bez očekivanog razloga.


# 84. Telegram Outage

Ako Telegram ne radi:

    alert record remains PENDING/FAILED
    crawler continues
    analytics continue

Nakon recovery-ja retry-ovati delivery.

Ne kreirati novi Opportunity samo zato što prvobitna notification delivery nije uspela.


# 85. Database Outage

Ako PostgreSQL nije dostupan:

- API/worker treba da failuju vidljivo;
- ne održavati alternativni lokalni business state koji se kasnije teško reconcile-uje.

Nakon recovery-ja:

    reconnect/restart
    →
    continue idempotently

Database outage ne sme proizvesti duplicate business history pri recovery-ju.


# 86. Long Crawler Downtime

Ako crawler nije radio više sati/dana:

    normal discovery
    +
    controlled reconciliation

nakon povratka.

Ne pretpostaviti da je period downtime-a kontinuirano posmatran.


# 87. Observation Gap

Ako source nije uspešno posmatran između:

    T1
    ...
    T2

i promena je tek na T2 otkrivena:

    detected_at = T2

može biti poznat,

ali stvarni trenutak source promene unutar gap-a nije poznat.

Sistem ne treba da izmišlja precizniji timestamp.


# 88. Dependency Updates

Ne upgrade-ovati production dependencies na `latest` pri svakom deployment-u.

Koristiti project lock/pinning strategiju.

Dependency update je normalna code promena:

    update
    → test
    → deploy


# 89. OS Security Updates

Production VPS periodično dobija security updates.

Ako update zahteva reboot:

    backup / verify backup
    ↓
    maintenance
    ↓
    reboot
    ↓
    verify containers
    ↓
    verify worker
    ↓
    verify source health


# 90. Time i Timezone

Server/container/database interno preferiraju:

    UTC

Server clock mora biti sinhronizovan kroz NTP ili ekvivalent.

UI radi lokalnu prezentaciju vremena.

Scheduler/cron pravila ne smeju zavisiti od skrivene pretpostavke da OS koristi `Europe/Belgrade`.


# 91. Docker Cleanup

Docker images/build cache mogu vremenom popuniti disk.

Periodično cleanup-ovati samo razumljivo unused data.

Ne koristiti agresivan prune nad volumes bez provere.

Nikada ne brisati persistent DB volume zato što container runtime kaže da izgleda „unused“ bez razumevanja sadržaja.


# 92. Backup Cleanup

Retention cleanup:

- targetira samo backup fajlove koje sistem kontroliše;
- koristi poznate paths/patterns;
- poštuje retention policy.

Ne koristiti široke wildcards nad nepoznatim directory-jima.


# 93. Production Seed

Production bootstrap ne sme da kreira development/demo properties ili listing-e.

Može kreirati samo eksplicitno potrebne configuration entities, npr:

    first source config
    default investment profile
    default cost profile

kada phase/model to zahteva.


# 94. Default Cost / Investment Profile

Default configuration mora biti jasno označena kao početna pretpostavka koju korisnik proverava.

Ne predstavljati:

- poreske stope;
- pravne assumptions;
- investment thresholds;

kao trajno nepromenjive činjenice.


# 95. API Request Protection

Pošto je sistem private/single-user, nije potreban kompleksan public SaaS rate limiter.

Reverse proxy može koristiti razumna osnovna ograničenja.

Ne uvoditi public API abuse infrastructure bez potrebe.


# 96. Debug Endpoint-i

Production ne sme imati nezaštićen endpoint koji:

- vraća environment;
- vraća secrets;
- izvršava arbitrary SQL;
- scrape-uje proizvoljan user-supplied URL;
- izvršava arbitrary shell command;
- pokreće bulk destructive operation bez jasne zaštite.

Admin actions moraju predstavljati poznate application operations.


# 97. Data Export

CSV/backup/manual export ne ostavljati u public web directory-ju.

Privremeni export:

- ima kontrolisanu lokaciju;
- ima ograničen lifetime;
- cleanup-uje se.


# 98. Feature Flags / Development Bypass

Production ne sme slučajno koristiti:

    mock scraper
    fake LLM
    fake Telegram
    auth bypass

Development-only behavior mora biti eksplicitno environment-gated.

U production-u unsafe bypass treba da failuje zatvoreno.


# 99. Credentials Rotation

Source, LLM i Telegram credentials treba menjati kroz configuration/secrets bez izmene business koda.

Opšti flow:

    revoke/rotate secret
    ↓
    update environment
    ↓
    restart relevant service
    ↓
    run small safe verification

Za leaked secret:

> stari secret se obavezno revoke-uje.


# 100. Source Request Monitoring

Po source-u kroz job summaries/logs pratiti relevantne:

    requests
    pages
    details fetched
    errors
    duration

Ako workload naglo poraste, npr. 20× requestova za isti market rezultat:

> istražiti uzrok pre kupovine jačeg servera.


# 101. First Production Launch Checklist

Pre dugotrajnog production crawling-a potvrditi:

    environment configured
    database persistent
    migrations at head

    private access works
    TLS works
    database not publicly exposed

    source config correct
    target market/filter correct
    source request limits configured

    exactly one scheduler owner
    worker starts correctly

    automatic backup works
    off-server destination works
    restore has been tested

    disk monitoring exists
    log growth bounded
    source health visible

    Telegram configured if required
    LLM configured if required

    no production auth/debug bypass


# 102. Prvi Production Crawling Period

Prvih nekoliko dana nadgledati sistem češće.

Posmatrati:

    request volume
    new listing count
    duplicate rate
    parse errors
    lifecycle/removal behavior
    DB growth
    RAM
    CPU
    disk

Crawl interval povećavati tek na osnovu realnih rezultata.


# 103. Crawl Interval Tuning

Balansirati:

    detection latency
    source request volume
    source stability
    real listing publication frequency

Najkraći mogući interval nije automatski najbolji interval.

Scraping semantics i konkretnu adaptive polling logiku definiše `04-scraping-specification.md`.


# 104. Maintenance Window

Privatni V1 nema formalni high-availability SLA.

Maintenance se može raditi u razumnom korisničkom periodu.

Ipak posebno pažljivo planirati:

- parser changes;
- risky migrations;
- backup/restore operations;
- work koji može prekinuti historical collection.


# 105. Future Object Storage

Object storage uvoditi kada postoji stvaran use case:

- off-server backups;
- long-lived image storage;
- large raw archive.

Ne uvoditi kompleksnu object-storage strukturu pre potrebe.


# 106. Future Database Separation

Razmotriti zaseban DB server ili managed PostgreSQL kada:

- DB značajno konkuriše crawler workload-u;
- availability zahtevi porastu;
- dataset postane dovoljno vredan;
- backup/recovery zahtjevi opravdaju trošak.

Ne pre.


# 107. Future Worker Separation

HTTP crawler, Playwright i analytics mogu se razdvojiti na posebne workers/servere kada realna merenja pokažu:

    browser RAM spikes
    discovery latency degradation
    job backlog
    independent scaling need

Domain/source adapter logic ostaje ista.


# 108. Future Queue Topology

Ako kasnije Redis/Celery ili ekvivalent postane opravdan, deployment može evoluirati ka:

    api
    scheduler
    http-worker
    browser-worker
    analysis-worker
    queue
    postgres

Ovo nije V1 requirement.


# 109. Future Observability Stack

Prometheus/Grafana ili sličan stack uvoditi kada:

- postoji više servera;
- incident analysis traži historical metrics;
- basic provider/UI/log monitoring više nije dovoljan;
- operational pain opravda dodatnu infrastrukturu.

Ne uvoditi zato što je to „standard production stack“.


# 110. Incident Prioriteti

## P0 — Data Integrity Risk

Primer:

    mass deletion
    false mass removal
    duplicate event explosion
    wrong merge corruption
    destructive migration issue
    database corruption

Akcija:

> po potrebi odmah zaustaviti relevantne write procese i sačuvati stanje.


## P1 — Core Collection Unavailable

Primer:

    worker dead
    all important sources failed
    database unavailable

Visok prioritet jer historical dataset prestaje da raste.


## P2 — Analysis / Notification Degraded

Primer:

    LLM unavailable
    valuation job failure
    Telegram failure

Collection/history može nastaviti gde dependency chain to dozvoljava.


## P3 — Presentation Issue

Primer:

    chart broken
    minor UI formatting

Niži prioritet dok su data i core workflow bezbedni.


# 111. P0 Incident Workflow

Za incident koji može korumpirati historical data:

    detect
    ↓
    stop unsafe writes if necessary
    ↓
    preserve evidence/current DB state
    ↓
    reproduce
    ↓
    add regression protection
    ↓
    fix
    ↓
    assess already-affected production data
    ↓
    repair/recover
    ↓
    resume

Ne nastavljati feature development dok je aktivan poznat data-integrity incident.


# 112. Zabranjene Operational Prečice

Ne raditi:

    reset production database

zato što migration ne radi.

Ne raditi:

    delete all listings and re-scrape

zato što parser ima bug.

Ne raditi:

    docker compose down -v

kao ordinary deployment.

Ne ručno brisati:

    PGDATA files

radi disk prostora.

Ne menjati bulk production data kroz ad-hoc SQL ako postoji bezbednija migration/application procedura.

Ne raditi production restore samo zato što crawler ima observation gap.


# 113. Operational Commands

Kada stvarna implementacija postoji, README ili kratki operations deo treba da dokumentuje stvarne komande za:

    local startup
    production startup
    deployment
    migrations
    backup
    restore
    logs
    worker restart
    status/health

Trenutne V1 komande koje postoje u repozitorijumu:

```powershell
# local infrastructure
docker compose up -d postgres
docker compose ps

# migrations, from backend/
.\.venv\Scripts\alembic.exe upgrade head

# API startup, from backend/
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000

# health/readiness
curl.exe -i http://127.0.0.1:8000/health
curl.exe -i http://127.0.0.1:8000/ready

# private operations status, from backend API
curl.exe -i http://127.0.0.1:8000/api/v1/operations/status

# worker one-shot smoke without live source access, from backend/
.\.venv\Scripts\python.exe -m app.operations.worker --once --skip-crawl

# worker loop, from backend/
.\.venv\Scripts\python.exe -m app.operations.worker --send-alerts

# 4zida controlled crawl, from backend/
.\.venv\Scripts\python.exe -m app.ingestion.four_zida_discovery --mode fast-discovery --max-pages-per-market 1

# database backup, from backend/
.\.venv\Scripts\python.exe -m app.operations.backup create

# restore verification must use an empty non-production database
.\.venv\Scripts\python.exe -m app.operations.backup verify-restore .\backups\dpr-postgres-YYYYMMDDTHHMMSSZ.dump --database-url "<restore-test-database-url>"
```

Production deployment i restore komande moraju koristiti production `.env`/secrets i ne smeju
restore test izvrsavati preko production baze.

Ne izmišljati komande pre nego što service/file names stvarno postoje.


# 114. Production Readiness

Sistem je spreman za dugotrajan V1 crawling tek kada najmanje važi:

- Docker startup je reproduktivan;
- PostgreSQL storage je persistent;
- migrations su pouzdane;
- production API/dashboard nije javno nezaštićen;
- HTTPS/private access radi;
- PostgreSQL nije public;
- scheduler ima jednog vlasnika;
- worker restart je bezbedan;
- ingestion/change handling je idempotentno;
- source health je vidljiv;
- automatic backup radi;
- backup postoji van VPS-a;
- restore je makar jednom proveren;
- secrets nisu u repository-ju;
- disk/log growth je bounded;
- source rate/concurrency config postoji;
- failed crawl ne proizvodi false market lifecycle promene.

Testing dokaze za ove tačke definiše `docs/08-testing-specification.md`.


# 115. Canonical Ownership

Architecture:

    docs/02-system-architecture.md

Persistence i historical data:

    docs/03-data-model.md

Scraping/source behavior:

    docs/04-scraping-specification.md

Analysis behavior:

    docs/05-analysis-specification.md

API/UI behavior:

    docs/06-api-ui-specification.md

Implementation order:

    docs/07-phase-plan.md

Automated verification:

    docs/08-testing-specification.md

Ovaj dokument poseduje:

> **runtime, deployment, storage, security, monitoring, backup, recovery i operational behavior produkcionog sistema.**


# 116. Najvažniji Operational Princip

Ako sistem mora da bira između:

    nastaviti processing
    uz rizik korupcije istorije

i:

    privremeno usporiti / zaustaviti deo pipeline-a
    dok se stanje ne razjasni

izabrati:

> **integritet istorijskih podataka.**

Privremeno missing data je vidljiv problem.

Pogrešan podatak koji izgleda pouzdano može trajno pokvariti:

- history;
- matching;
- valuation;
- backtesting;
- investment decision.


# 117. Konačni Deployment Princip

Production infrastruktura treba da bude:

    jednostavna
    reproduktivna
    dosadna
    merljiva
    laka za oporavak

Najvažnije je da:

    crawler može dugo da radi
    historical data ostaje bezbedan
    backup stvarno može da se restore-uje
    failure jednog modula ne uništava ostale
    deploy ne ugrožava bazu
    recovery ne zahteva improvizaciju

Za Distressed Property Radar pouzdan single-VPS sistem koji godinu dana bezbedno gradi tržišnu istoriju vredi više od sofisticirane infrastrukture koja je teška za održavanje.
