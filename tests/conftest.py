import os
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url

from magacin_backend import schema as s
from magacin_backend.db import engine_for
from magacin_backend.service import Warehouse


@pytest.fixture
def warehouse():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL mora pokazivati na zasebnu PostgreSQL test bazu.')
    parsed = make_url(url)
    if not (parsed.database or '').endswith(('_test', '_tests')):
        pytest.fail('Testovi zahtevaju ime baze koje se završava na _test ili _tests.')
    admin = engine_for(url)
    schema = 'test_' + uuid4().hex
    with admin.begin() as c:
        c.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped = parsed.update_query_dict({'options': '-c search_path=' + schema})
    engine = engine_for(scoped)
    s.metadata.create_all(engine)
    with engine.begin() as c:
        c.exec_driver_sql('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)')
        c.exec_driver_sql("INSERT INTO alembic_version VALUES ('001')")
    service = Warehouse(engine)
    service.bootstrap('admin', 'test-admin-password-2026')
    token = service.login('admin', 'test-admin-password-2026')
    try:
        yield service, token
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()

