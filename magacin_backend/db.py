import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def database_url():
    load_dotenv(ROOT / '.env', override=False)
    value = os.environ.get('DATABASE_URL', '').strip()
    if not value:
        raise RuntimeError('DATABASE_URL nije podešen. Aplikacija neće kreirati zamensku lokalnu bazu.')
    return value


def engine_for(url=None):
    value = url or database_url()
    parsed = make_url(value)
    if parsed.drivername in ('postgres', 'postgresql'):
        parsed = parsed.set(drivername='postgresql+psycopg')
    if parsed.get_backend_name() != 'postgresql':
        raise RuntimeError('Ova aplikacija koristi isključivo centralnu PostgreSQL bazu.')
    return create_engine(parsed, pool_pre_ping=True, pool_size=5, max_overflow=5,
                         connect_args={'connect_timeout': 10}, hide_parameters=True)


def identity(engine):
    u = engine.url
    return f'{u.host}:{u.port or 5432}/{u.database}'

