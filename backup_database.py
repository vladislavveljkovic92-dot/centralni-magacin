"""Produce a PostgreSQL custom-format backup without credentials on the command line."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

from sqlalchemy.engine import make_url

from magacin_backend.db import ROOT, database_url
from magacin_backend.service import now


def pg_environment(url):
    u = make_url(url)
    if u.get_backend_name() not in ('postgresql', 'postgres'):
        raise RuntimeError('Backup zahteva PostgreSQL.')
    env = os.environ.copy()
    env.update(PGHOST=u.host or '', PGPORT=str(u.port or 5432), PGDATABASE=u.database or '',
               PGUSER=u.username or '', PGPASSWORD=u.password or '')
    for name in ('sslmode', 'sslrootcert', 'sslcert', 'sslkey', 'channel_binding', 'options'):
        if name in u.query:
            env['PG' + name.upper()] = str(u.query[name])
    return env


def pronadji_pg_dump(pg_bin=None):
    """pg_dump sa PUTANJE, ili iz standardne Windows instalacije PostgreSQL-a."""
    if pg_bin:
        executable = str(Path(pg_bin) / 'pg_dump')
    else:
        executable = shutil.which('pg_dump')
        if not executable:
            # Lokalni pg_bin u folderu projekta (prenosi se na novi računar).
            lokalni = ROOT / 'pg_bin' / ('pg_dump.exe' if os.name == 'nt' else 'pg_dump')
            if lokalni.exists():
                executable = str(lokalni)
        if not executable and os.name == 'nt':
            # Windows često ima PostgreSQL instaliran, ali bin nije na PATH-u.
            import glob
            kandidati = sorted(glob.glob(r'C:\Program Files\PostgreSQL\*\bin\pg_dump.exe'))
            executable = kandidati[-1] if kandidati else None
    if os.name == 'nt' and executable and not executable.endswith('.exe'):
        executable += '.exe'
    return executable


def rotiraj_backup_e(folder, keep, obrazac='central_????????T??????Z.dump'):
    """Zadržava poslednjih `keep` automatskih backupova; stariji se brišu
    zajedno sa svojim .sha256. Ručni backupi (USB, preview) se ne diraju."""
    if keep <= 0:
        return 0
    folder = Path(folder)
    fajlovi = sorted(folder.glob(obrazac), key=lambda p: p.stat().st_mtime, reverse=True)
    obrisano = 0
    for stari in fajlovi[keep:]:
        stari.unlink(missing_ok=True)
        stari.with_suffix(stari.suffix + '.sha256').unlink(missing_ok=True)
        obrisano += 1
    return obrisano


def create_backup(url, destination, pg_bin=None):
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError('Backup fajl već postoji; postojeći backup se ne prepisuje.')
    executable = pronadji_pg_dump(pg_bin)
    if not executable:
        raise RuntimeError('Instalirajte PostgreSQL klijentske alate ili navedite --pg-bin.')
    temp = destination.with_suffix(destination.suffix + '.partial')
    try:
        subprocess.run([executable, '--format=custom', '--no-owner', '--no-acl', '--file', str(temp)],
                       env=pg_environment(url), check=True, capture_output=True)
        temp.rename(destination)
    except subprocess.CalledProcessError:
        raise RuntimeError('pg_dump nije uspeo. Proverite pristup bazi i verziju PostgreSQL klijenta.') from None
    finally:
        if temp.exists():
            temp.unlink()
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + '.sha256').write_text(digest, encoding='ascii')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'backups' / f'central_{now():%Y%m%dT%H%M%SZ}.dump'))
    parser.add_argument('--pg-bin')
    parser.add_argument('--keep', type=int, default=10,
                        help='Koliko najnovijih automatskih backupova da se zadrži (0 = bez ograničenja).')
    args = parser.parse_args()
    putanja = create_backup(database_url(), args.output, args.pg_bin)
    obrisano = rotiraj_backup_e(putanja.parent, args.keep)
    print(putanja)
    if obrisano:
        print(f'Obrisano starijih backupova: {obrisano} (zadržano poslednjih {args.keep})')
