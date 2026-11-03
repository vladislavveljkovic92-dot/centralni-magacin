# Centralni magacin

Streamlit aplikacija i zajednički Python backend za magacin, radne naloge, godišnji budžet i preventivno održavanje. Jedna serverska instanca koristi jednu PostgreSQL bazu određenu isključivo promenljivom `DATABASE_URL`. Korisnici otvaraju istu HTTPS adresu u browseru; na njihovim računarima nema baze niti instalacije Pythona.

## Lokalni pregled pripremljen na ovom računaru

- Otvorite **http://localhost:8501**.
- Pristupni podaci su u lokalnom fajlu **credentials-local.txt**. Lozinka je nasumično generisana. Ovaj fajl i `.env` nisu za deljenje/publikovanje.
- Ako aplikacija nije pokrenuta, pokrenite `pokreni_pregled.ps1` ili `Magacin.py`. Lokalni PostgreSQL sluša isključivo `127.0.0.1:55432`; Streamlit pregled isključivo `127.0.0.1:8501`.
- Lokalni pregled je odvojena kopija podataka u bazi `magacin_preview`. Nije internet produkcija i nije povezan sa postojećim cloud nalozima.
- Stare baze nisu menjane. Konzistentne SQLite kopije su u `backups/20261103_115229/`.
- Originalni Tkinter programi su sačuvani kao tekst u `legacy/`. Oba prethodna `.py` ulaza sada otvaraju web aplikaciju, pa više ne upisuju u stare SQLite fajlove.

## Šta radi backend

- Magacin: kreiranje/izmena/arhiviranje dela; nabavka sa stvarnom cenom; povrat uz razlog; izdavanje više stavki na jedan radni nalog.
- Transakcije: agregiranje istih delova, atomska provera i umanjenje zalihe, rollback celog naloga ako bilo koja stavka nije dostupna; DB ograničenje `stock >= 0`.
- Zaštita od dupliranja: svaki zahtev dobija stabilan ID. Ponovljen zahtev, uključujući konkurentne pozive, vraća prethodni rezultat bez ponovnog upisa. Posle neizvesne mrežne greške ponovite isti zahtev u istoj formi; nemojte praviti novi nalog pre provere istorije.
- Nalozi: zatvaranje ili storno otvorenog naloga sa povratom robe i odgovarajućim kretanjem. Zatvoreni nalozi se ne storniraju ovim MVP tokom.
- Nabavke: storno po ID-u dela, uz proveru raspoložive zalihe; originalni zapis ostaje sa oznakom storna. Stare nabavke bez pouzdane veze sa delom se prikazuju, ali se ne storniraju automatski.
- Budžet: jedinstvena kombinacija godine i kategorije, stvarni trošak nabavke, precizni decimalni iznosi; poslovna vremenska zona Europe/Budapest.
- PM: linije, mašine, zadaci, periodika, rokovi, evidencija izvršenja i poništavanje uz očuvanje istorije. Rok danas ima status „Danas“, tek protekao rok „Kasni“.
- Pristup: scrypt heševi lozinki, serverske sesije (8 h), obavezna promena privremenih lozinki, provera uloga u backendu i trajno ograničenje pokušaja prijave. Promena/reset lozinke i deaktivacija opozivaju stare sesije.
- Nema automatskog kreiranja zamenske lokalne baze. Greška konekcije je vidljiva greška.
- Promene imaju revizijski trag. Brisanje istorije i fabrički reset nisu izloženi korisnicima.

## Postavljanje na ZASEBAN internet nalog

Pripremljen je `render.yaml` za novu aplikaciju i novu PostgreSQL bazu na Render-u; predloženi planovi su plaćeni i trošak treba pregledati pri kreiranju. Nijedan resurs nije kreiran na postojećim nalozima. Konfiguracija je strukturno proverena prema javnoj Render JSON šemi; nije izvršen deploy niti platformna validacija sa nalogom.

1. Na zasebnom Git/Render nalogu napravite privatni repozitorijum i dodajte samo izvorni kod. `dist/magacin-central-source.zip` sadrži paket izvornog koda bez baza i tajni. Ne dodajte `.env`, `.local`, `.venv`, `backups`, `credentials-local.txt` ni stare baze.
2. Povežite repozitorijum kao novi Blueprint. Proverite nazive i planove. Baza je zasebna, u Frankfurtu, sa `ipAllowList: []` (bez direktnog javnog pristupa). Web aplikacija se povezuje internom konekcijom.
3. Postavite jedinstvenu `ADMIN_PASSWORD` sa najmanje 12 znakova u secrets konfiguraciji. Ne koristite lokalnu lozinku ili stare podrazumevane lozinke.
4. `start_server.py` primenjuje Alembic migracije, kreira admina samo ako korisnici još ne postoje i pokreće Streamlit. Restart/deploy ne resetuje podatke niti lozinke. Početno pokretanje treba da bude jedna instanca; promene šeme izvršavati kontrolisano pre skaliranja.
5. Pre otvaranja za korisnike prenesite merodavne stare podatke postupkom ispod. Tokom konačnog prenosa zaustavite upise u staru aplikaciju. Lokalni testni unosi nisu produkcijski podaci.
6. Proverite HTTPS adresu iz dva browsera: prijava → ulaz → izdavanje → čitanje u drugoj sesiji → restart aplikacije → ponovno čitanje. Tek zatim podelite adresu korisnicima.
7. Na zasebnom produkcijskom nalogu uključite automatske bekape i odgovarajuće zadržavanje, uz odvojenu kopiju i probno vraćanje. Lokalna provera bekapa nije aktiviran cloud raspored.

Docker alternativa je u `compose.yaml`. Baza koristi trajni volume i nema objavljen SQL port; aplikacija je vezana za loopback iza budućeg HTTPS reverse proxy-ja. U `.env` postaviti zasebne `POSTGRES_PASSWORD`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`. Za lozinku baze koristiti URL-safe vrednost jer se ugrađuje u URL. `docker compose up --build -d`. Docker build ovde nije testiran jer Docker nije dostupan.

## Instalacija i administracija

Podržano/testirano okruženje: Python 3.13.18 i PostgreSQL 17. Koristite `requirements.lock.txt` za ponovljivo serversko okruženje.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
# U .env podesiti DATABASE_URL i nov administratorski pristup.
.venv\Scripts\python.exe manage.py migrate
# Za praznu instalaciju bez starih podataka:
.venv\Scripts\python.exe manage.py bootstrap
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address=127.0.0.1
```

Promenljive okruženja imaju prednost nad `.env`. Baza može biti kod drugog PostgreSQL provajdera; za javnu mrežnu konekciju obavezno koristiti TLS konfiguraciju provajdera. Baza se ne bira preko korisničkog interfejsa. Promena `DATABASE_URL` zahteva restart serverske aplikacije.

## Prenos starih podataka

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py import-legacy --source "C:\putanja\magacin.db"
.venv\Scripts\python.exe manage.py check
```

Import je jedna transakcija i otvara SQLite izvor samo za čitanje. Koristi konzistentan snapshot i proverava integritet. Prepoznaje ponovljen import identičnog sadržaja; odbija automatsko spajanje sa popunjenom poslovnom bazom. Dozvoljen je prethodno kreiran jedini bootstrap admin sa istim korisničkim imenom. Import ne menja njegovu lozinku.

Prenose se delovi sa trenutnim stanjem, transakcije, nalozi i stavke, budžeti/nabavke, PM hijerarhija i evidencija. Podaci dodatnih starih modula (kvarovi, rezervacije, kompleti i ostalo) ostaju u centralnoj `legacy_archive` arhivi i dostupni su administratoru; njihove zasebne radne forme nisu implementirane u ovoj verziji. Stare lozinke i reset PIN se ne prenose. Svi stari nalozi osim izabranog novog administratora su deaktivirani dok admin ne dodeli novi privremeni pristup.

`odrzavanje_akytec.db` je sačuvana pomoćna baza i ne spaja se automatski sa `magacin.db`. Ako drugi računar ima novije ili dodatne zapise, potrebno je pregledati i tu kopiju i odabrati/usaglasiti merodavne podatke pre produkcijskog importa. Import istorije čuva ono što postoji; ne može rekonstruisati ranije obrisane transakcije.

Za Render sa zatvorenom javnom bazom, import pokrenuti unutar serverskog okruženja iz privremeno i bezbedno prenetog izvora, ili preneti prethodno pripremljen PostgreSQL dump kontrolisanim administratorskim putem. Ne stavljati SQLite fajl u javni repozitorijum niti otvarati SQL port svim adresama.

## Backup i vraćanje

Na administrativnom računaru sa PostgreSQL klijentom iste ili novije glavne verzije:

```powershell
.venv\Scripts\python.exe backup_database.py --pg-bin .local\pgsql\bin
```

Nastaju custom-format `.dump` i SHA-256 fajl. Lozinka se prosleđuje pg_dump procesu kroz okruženje, bez kredencijala u komandnoj liniji. Bekapi sadrže poslovne podatke i heševe lozinki; čuvajte ih u zaštićenom odvojenom skladištu. Za probno vraćanje napravite NOVU praznu test bazu i koristite `pg_restore --no-owner --no-acl` sa PGHOST/PGUSER/PGPASSWORD/PGDATABASE podešenim na tu test bazu. Ne vraćati preko aktivne produkcijske baze. Lokalno je provereno vraćanje kompletnog dump-a u zasebnu test bazu i poređenje broja zapisa.

## Provere

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# TEST_DATABASE_URL mora pokazivati na zasebnu bazu sa imenom koje završava na _test ili _tests.
.venv\Scripts\python.exe -m pytest -q tests
```

Testovi koriste stvarni PostgreSQL, izolovanu šemu po testu i dve nezavisne konekcije/sesije za proveru konkurentnog rada. Testovi Streamlit formi proveravaju unos dela, nabavku, izdavanje, čitanje u drugoj sesiji, prikaz stranica i PM evidenciju. Promene iz testova ne ostaju u bazi za lokalni pregled.

Arhitektonske reference: [Streamlit](https://docs.streamlit.io/develop/concepts/architecture/architecture), [SQLAlchemy](https://docs.sqlalchemy.org/en/20/tutorial/data_update.html), [Render Blueprint](https://render.com/docs/blueprint-spec).

