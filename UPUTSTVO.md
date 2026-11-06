# Uputstvo za korišćenje magacina (kratko)

Ovo uputstvo je za svakodnevnu upotrebu. Ne treba programersko znanje.

## Gde se nalazi magacin

Aplikacija radi na internetu (Streamlit hosting):

```
https://vladislavveljkovic92-dot-centralni-magacin-streamlit-app-a82wgy.streamlit.app/
```

Korisnici otvaraju tu adresu u browseru (Chrome, Edge...) i prijavljuju se svojim korisničkim imenom i lozinkom. Na njihovom računaru ne treba ništa da se instalira.

## Ako polja za prijavu ne reaguju

Ovo je poznati problem hostinga (Streamlit), ne kvar programa:

1. Osvežite stranicu (taster **F5** ili dugme "Osveži stranicu" ispod polja).
2. Ako i dalje ne radi, zatvorite tab pa otvorite adresu iznova.
3. Popunjavanje ide tek kada se cela stranica učita (vidi se naslov "Magacin — prijava").

## Dnevna provera sistema

Na ovom računaru postoji zakazana provera koja se pokreće **svakog dana u 09:00**.
Rezultat se upisuje u datoteku `logovi\provera.log`.

Možete je pokrenuti i ručno — dvaput kliknite na **`Provera.bat`**.
Provera ispituje:

- da li baza podataka radi i koliko ima zapisa,
- da li se web stranica otvara na internetu,
- da li se programski fajlovi (JS) ispravno učitavaju,
- da li je backup baze svež (mlađi od 7 dana).

### Šta znače oznake u rezultatu

| Oznaka | Značenje |
|---|---|
| `OK` | Sve radi ispravno. |
| `INFO` | Bezbedna informacija, ne traži akciju. |
| `UPOZORENJE` | Radi, ali treba obratiti pažnju (npr. star backup). |
| `PROBLEM` | Nešto ne radi. Pošalji celu datoteku `logovi\provera.log` vlasniku sistema. |

Ako na kraju piše `SVE OK` — nema razloga za brigu.

## Kada nešto ne radi

Pošalji (putem poruke ili mejla):

1. Datoteku **`logovi\provera.log`** (ona već sadrži istoriju provera sa datumima).
2. Screenshot greške sa ekrana.
3. Tačan datum i vreme kada se desilo.

Na osnovu toga se najbrže utvrdi uzrok: da li je baza, hosting ili sam program.

## Backup podataka

Backup se pravi ovom komandom (iz foldera magacina):

```powershell
.venv\Scripts\python.exe backup_database.py --pg-bin "C:\Program Files\PostgreSQL\17\bin"
```

Nastaju fajlovi u folderu `backups\` (`.dump` + `.sha256` za proveru ispravnosti).
Dnevna provera sama upozorava ako je backup stariji od 7 dana.

## Pokretanje aplikacije lokalno (opciono)

```powershell
.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address=127.0.0.1
```

Zatim otvorite **http://localhost:8501**. Localni pregled je odvojena kopija podataka.

## Provera posle izmene koda (za održavanje)

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q tests
```

Testovi traže `TEST_DATABASE_URL` (navedena je u `.env`) i traju oko 5 minuta.
Svih 18 testova mora proći pre nego što se izmene proslede na GitHub.

## Uloge i opasne operacije

Postoje dve uloge:

| Uloga | Šta može |
|---|---|
| `tehnicar` | Pregled zaliha i izdavanje, unos novih delova u Zalihe. |
| `admin` | Sve što tehničar + izmena delova, brisanje delova, korisnici, revizijski trag, fabrički reset. |

### Trajno brisanje dela (samo admin)

U delu **Zalihe** postoji proširenje **"Trajno brisanje dela"** (crvena zona).
Deo se može obrisati **samo ako nema nikakvu istoriju** (kretanja zalihâ, nalozi,
nabavke) i ako mu je stanje nula. U suprotnom program traži da se deo arhivira.
Brisanje traži potvrdu u checkboxu i nepovratno je.

### Fabrički reset (samo admin)

U delu **Administracija** postoji proširenje **"Fabrički reset baze"** (crvena zona).
Reset traži **šifru 300120** i potvrdu u checkboxu, pa trajno briše:

- sve delove, istoriju kretanja, radne naloze i nabavke,
- budžet i podatke preventivnog održavanja,
- arhivu i revizijski trag,
- **sve korisnike osim administratorskih** (tehnici moraju ponovo da se naprave).

Administratorski nalozi i njihove sesije ostaju — admin ne biva odjavljen.
Nije ga moguće poništiti, zato se prvo napravi backup (vidi gore).

## Zakazana provera — promena i uklanjanje

Zadatak se zove **"Magacin provera"** i vidi se u Windows "Task Scheduler"-u
(Pretraga → "Schedule Tasks"). Promena sata: desni klik na zadatak → Properties → Trigger.
Uklanjanje: desni klik → Delete.
