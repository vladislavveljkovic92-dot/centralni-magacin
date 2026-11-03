"""One-time, transactional import. The legacy source is opened read-only."""
import hashlib
import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import insert, select, func

from . import schema as s
from .service import BusinessError, LOCAL_TZ, money, now, password_hash, uid, valid_password, PERIODS


def timestamp(value):
    if not value:
        raise BusinessError('Stari zapis nema datum; potrebna je provera izvora.')
    result = datetime.fromisoformat(str(value))
    return result if result.tzinfo else result.replace(tzinfo=LOCAL_TZ)


def import_legacy(engine, source, admin_username, admin_password):
    valid_password(admin_password)
    source = Path(source).resolve(strict=True)
    # SQLite backup includes committed WAL contents, unlike a plain file copy.
    with tempfile.TemporaryDirectory() as td:
        old = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
        snapshot = sqlite3.connect(str(Path(td) / 'snapshot.db'))
        try:
            old.backup(snapshot)
            snapshot.row_factory = sqlite3.Row
            check = snapshot.execute('PRAGMA integrity_check').fetchone()[0]
            if check != 'ok':
                raise BusinessError('Izvorna baza nije prošla proveru integriteta.')
            names = [r[0] for r in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            data = {name: [dict(r) for r in snapshot.execute('SELECT * FROM "' + name.replace('"', '""') + '" ORDER BY rowid')] for name in names}
        finally:
            old.close()
            snapshot.close()
    if not {'delovi', 'transakcije', 'korisnici'}.issubset(data):
        raise BusinessError('Izaberite glavnu magacinsku bazu, ne praznu ili pomoćnu bazu.')
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
    counts = {name: len(rows) for name, rows in data.items()}
    with engine.begin() as c:
        # Prevent two import/bootstrap processes from racing on an empty target.
        c.exec_driver_sql('SELECT pg_advisory_xact_lock(7142301)')
        if c.scalar(select(s.imports.c.source_hash).where(s.imports.c.source_hash == fingerprint)):
            return {'already_imported': True, 'counts': counts}
        if any(c.scalar(select(func.count()).select_from(table)) for table in
               (s.parts, s.movements, s.orders, s.purchases, s.budgets, s.lines, s.machines, s.tasks, s.maintenance_logs)):
            raise BusinessError('Ciljna baza već sadrži poslovne podatke. Automatsko spajanje nije dozvoljeno.')
        existing_users = c.execute(select(s.users)).mappings().all()
        if existing_users and (len(existing_users) != 1 or existing_users[0]['username'] != admin_username
                               or existing_users[0]['role'] != 'admin'):
            raise BusinessError('Pre importa je dozvoljen samo početni administratorski nalog.')

        def rows(name):
            return data.get(name, [])

        found_admin = False
        for r in rows('korisnici'):
            chosen = r['username'] == admin_username
            found_admin |= chosen
            if chosen and existing_users:
                continue
            # Old passwords are never activated or copied to the new database.
            c.execute(insert(s.users).values(id=str(r['id']), username=r['username'],
                password_hash=password_hash(admin_password if chosen else uid() + uid()),
                role='admin' if chosen or r.get('uloga') == 'admin' else 'tehnicar',
                active=chosen, must_change=not chosen, auth_version=1))
        if not found_admin and not existing_users:
            c.execute(insert(s.users).values(id=uid(), username=admin_username, password_hash=password_hash(admin_password),
                role='admin', active=True, must_change=False, auth_version=1))
        for r in rows('delovi'):
            c.execute(insert(s.parts).values(id=str(r['id']), part_number=r['part_number'], name=r['naziv'],
                category=r.get('kategorija') or 'Univerzalno', stock=r.get('stanje') or 0,
                minimum=r.get('min_stanje') or 0, maximum=r.get('max_stanje'), price=money(r.get('cena') or 0),
                supplier=r.get('dobavljac') or '', purpose=r.get('namena') or '', image_path=r.get('slika_putanja') or '', active=True))
        for r in rows('radni_nalozi'):
            c.execute(insert(s.orders).values(id=str(r['id']), number=r['rn_broj'], status=r['status'],
                created_at=timestamp(r['datum']), actor=r.get('korisnik') or 'legacy', note=r.get('napomena') or ''))
        for r in rows('rn_stavke'):
            c.execute(insert(s.order_items).values(id=str(r['id']), order_id=str(r['rn_id']), part_id=str(r['part_id']), quantity=r['kolicina']))
        for r in rows('transakcije'):
            c.execute(insert(s.movements).values(id=str(r['id']), part_id=str(r['part_id']), quantity=r['kolicina'],
                kind=r['tip'], actor=r.get('korisnik') or 'legacy', created_at=timestamp(r['datum']), note=r.get('napomena') or ''))
        for r in rows('budzet_odobren'):
            c.execute(insert(s.budgets).values(id=str(r['id']), year=r['godina'], category=r['kategorija'], approved=money(r['odobrena_suma'])))
        for r in rows('budzet_potrosen'):
            # Name-based legacy links are ambiguous; never guess a stock identity.
            c.execute(insert(s.purchases).values(id=str(r['id']), part_id=None, item_name=r['stavka'], category=r['kategorija'],
                quantity=r['kolicina'], unit_price=money(r['cena_po_komadu']), total=money(r['ukupno']),
                supplier=r.get('dobavljac') or '', created_at=timestamp(r['datum']), actor=r.get('korisnik') or 'legacy', cancelled=False))
        for r in rows('pm_linije'):
            c.execute(insert(s.lines).values(id=str(r['id']), name=r['naziv'], description=r.get('opis') or '',
                icon=r.get('ikona') or '🏭', position=r.get('redosled') or 0, active=True))
        for r in rows('pm_masine'):
            c.execute(insert(s.machines).values(id=str(r['id']), line_id=str(r['linija_id']), name=r['naziv'], position=r.get('redosled') or 0, active=True))
        for r in rows('pm_zadaci'):
            period = next((p for p in PERIODS if p.casefold() == str(r['tip_odrzavanja']).strip().casefold()), None)
            if not period:
                raise BusinessError(f'Nepoznata PM periodika za zadatak {r["id"]}; import je poništen.')
            c.execute(insert(s.tasks).values(id=str(r['id']), machine_id=str(r['masina_id']), description=r['opis_zadatka'],
                period=period, position=r.get('redosled') or 0, active=True))
        for r in rows('pm_evidencija'):
            c.execute(insert(s.maintenance_logs).values(id=str(r['id']), task_id=str(r['zadatak_id']),
                status=r.get('status') or 'Urađeno', actor=r.get('korisnik') or 'legacy', created_at=timestamp(r['datum']), note=r.get('napomena') or '', voided=False))
        for r in rows('podesavanja'):
            if r['kljuc'] == 'pm_pocetak':
                c.execute(insert(s.settings).values(key=r['kljuc'], value=r['vrednost']))
        # Preserve ALL remaining source information in an inspectable central archive.
        # Credentials and obsolete reset PINs are explicitly excluded.
        for name, records in data.items():
            for r in records:
                if name == 'podesavanja' and 'pin' in str(r.get('kljuc', '')).lower():
                    continue
                clean = {k: v for k, v in r.items() if k.lower() not in ('password', 'password_hash')}
                c.execute(insert(s.archive).values(id=uid(), table_name=name, payload=clean))
        c.execute(insert(s.imports).values(source_hash=fingerprint, created_at=now(), counts=counts))
    return {'already_imported': False, 'counts': counts}

