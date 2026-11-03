"""Administrative CLI. Never prints database credentials or passwords."""
import argparse
import json
import os
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import select, func

from magacin_backend.db import ROOT, engine_for, identity
from magacin_backend.legacy import import_legacy
from magacin_backend.service import Warehouse, BusinessError
from magacin_backend import schema as s


def main():
    parser = argparse.ArgumentParser(description='Centralni magacin: administracija')
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('migrate')
    sub.add_parser('bootstrap')
    sub.add_parser('check')
    imp = sub.add_parser('import-legacy')
    imp.add_argument('--source', required=True, help='Putanja do merodavne SQLite baze; izvor se ne menja.')
    args = parser.parse_args()
    engine = engine_for()
    if args.cmd == 'migrate':
        command.upgrade(Config(str(ROOT / 'alembic.ini')), 'head')
        print('Migracije završene:', identity(engine))
    elif args.cmd in ('bootstrap', 'import-legacy'):
        username = os.getenv('ADMIN_USERNAME', 'admin')
        password = os.getenv('ADMIN_PASSWORD', '')
        if args.cmd == 'bootstrap':
            made = Warehouse(engine).bootstrap(username, password)
            print('Administrator kreiran.' if made else 'Korisnici već postoje; postojeća lozinka nije izmenjena.')
        else:
            result = import_legacy(engine, args.source, username, password)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        with engine.connect() as c:
            revision = c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one()
            counts = {t.name: c.scalar(select(func.count()).select_from(t)) for t in
                      (s.parts, s.movements, s.orders, s.purchases, s.users, s.tasks, s.maintenance_logs)}
        print(json.dumps({'database': identity(engine), 'revision': revision, 'counts': counts}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (BusinessError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

