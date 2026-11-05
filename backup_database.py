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


def create_backup(url, destination, pg_bin=None):
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError('Backup fajl već postoji; postojeći backup se ne prepisuje.')
    executable = str(Path(pg_bin) / 'pg_dump') if pg_bin else shutil.which('pg_dump')
    if os.name == 'nt' and executable and not executable.endswith('.exe'):
        executable += '.exe'
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
    args = parser.parse_args()
    print(create_backup(database_url(), args.output, args.pg_bin))
