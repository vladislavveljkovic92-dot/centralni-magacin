import hashlib
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError

from magacin_backend import schema as s
from magacin_backend.db import engine_for, ROOT
from magacin_backend.legacy import import_legacy
from magacin_backend.service import Warehouse, BusinessError, uid, next_due, money, LOCAL_TZ


def create_part(service, token, stock=5, name='Test deo', pn=None):
    pid = service.save_part(token, uid(), pn or uid(), name, 'Mehanika', 2, '10.50')['id']
    if stock:
        service.receive(token, uid(), pid, stock, '10.50')
    return pid


def stock(service, token, pid):
    return next(r['stock'] for r in service.list_parts(token) if r['id'] == pid)


def count(service, table):
    with service.engine.connect() as c:
        return c.scalar(select(func.count()).select_from(table))


def test_missing_url_and_sqlite_fail_closed(monkeypatch):
    with pytest.raises(RuntimeError, match='PostgreSQL'):
        engine_for('sqlite:///accidental.db')
    monkeypatch.setattr('magacin_backend.db.load_dotenv', lambda *a, **k: None)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(RuntimeError, match='zamensku'):
        engine_for()
    assert not Path('accidental.db').exists()


def test_duplicate_cart_lines_cannot_overdraw(warehouse):
    svc, token = warehouse
    pid = create_part(svc, token)
    with pytest.raises(BusinessError, match='Nedovoljno'):
        svc.issue_order(token, uid(), [{'part_id': pid, 'quantity': 4}, {'part_id': pid, 'quantity': 4}])
    assert stock(svc, token, pid) == 5
    assert count(svc, s.orders) == 0
    assert count(svc, s.movements) == 1


def test_whole_order_rolls_back(warehouse):
    svc, token = warehouse
    p1, p2 = sorted([create_part(svc, token), create_part(svc, token, stock=1)])
    before = {p: stock(svc, token, p) for p in (p1, p2)}
    with pytest.raises(BusinessError):
        svc.issue_order(token, uid(), [{'part_id': p1, 'quantity': 1}, {'part_id': p2, 'quantity': 100}])
    assert {p: stock(svc, token, p) for p in (p1, p2)} == before
    assert count(svc, s.orders) == count(svc, s.order_items) == 0


def test_two_clients_share_database_and_cannot_overdraw(warehouse):
    svc, token = warehouse
    pid = create_part(svc, token)
    second = Warehouse(engine_for(svc.engine.url))
    other_token = second.login('admin', 'test-admin-password-2026')
    def issue(args):
        client, session = args
        try:
            return client.issue_order(session, uid(), [{'part_id': pid, 'quantity': 4}])
        except BusinessError:
            return None
    try:
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(issue, [(svc, token), (second, other_token)]))
        assert sum(r is not None for r in results) == 1
        assert stock(svc, token, pid) == stock(second, other_token, pid) == 1
        assert count(svc, s.orders) == 1
    finally:
        second.engine.dispose()


def test_repeated_concurrent_request_writes_once(warehouse):
    svc, token = warehouse
    pid = create_part(svc, token, stock=0)
    rid = uid()
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: svc.receive(token, rid, pid, 3, '2.50'), range(2)))
    assert results[0] == results[1]
    assert stock(svc, token, pid) == 3
    assert count(svc, s.purchases) == count(svc, s.movements) == 1
    with pytest.raises(BusinessError, match='drugu operaciju'):
        svc.receive(token, rid, pid, 4, '2.50')


def test_cancel_order_restores_once_and_preserves_history(warehouse):
    svc, token = warehouse
    pid = create_part(svc, token)
    order = svc.issue_order(token, uid(), [{'part_id': pid, 'quantity': 2}])
    rid = uid()
    svc.order_action(token, rid, order['id'], 'cancel', 'Pogrešan nalog')
    svc.order_action(token, rid, order['id'], 'cancel', 'Pogrešan nalog')
    assert stock(svc, token, pid) == 5
    assert count(svc, s.movements) == 3
    assert svc.read_table(token, 'orders')[0]['status'] == 'Storniran'
    with pytest.raises(BusinessError):
        svc.order_action(token, uid(), order['id'], 'cancel', 'Ponovo')


def test_purchase_storno_uses_id_and_rejects_consumed_stock(warehouse):
    svc, token = warehouse
    p1 = create_part(svc, token, stock=0, name='Isti naziv')
    p2 = create_part(svc, token, stock=7, name='Isti naziv')
    purchase = svc.receive(token, uid(), p1, 4, '3.20')
    svc.issue_order(token, uid(), [{'part_id': p1, 'quantity': 3}])
    with pytest.raises(BusinessError, match='već izdat'):
        svc.cancel_purchase(token, uid(), purchase['id'], 'Test')
    assert stock(svc, token, p1) == 1
    assert stock(svc, token, p2) == 7
    assert not next(r for r in svc.read_table(token, 'purchases') if r['id'] == purchase['id'])['cancelled']


def test_purchase_storno_updates_budget_and_keeps_original(warehouse):
    svc, token = warehouse
    pid = create_part(svc, token, stock=0)
    purchase = svc.receive(token, uid(), pid, 2, '1.10')
    svc.cancel_purchase(token, uid(), purchase['id'], 'Dupla narudžbina')
    assert stock(svc, token, pid) == 0
    assert count(svc, s.purchases) == 1
    assert count(svc, s.movements) == 2
    assert svc.read_table(token, 'purchases')[0]['cancelled']


def test_yearly_budget_and_decimal_money(warehouse):
    svc, token = warehouse
    pid = create_part(svc, token, stock=0)
    p1 = svc.receive(token, uid(), pid, 3, '0.10')
    p2 = svc.receive(token, uid(), pid, 2, '0.10')
    with svc.engine.begin() as c:
        c.execute(update(s.purchases).where(s.purchases.c.id == p1['id']).values(created_at=datetime(2025, 12, 31, 23, 59, tzinfo=LOCAL_TZ)))
        c.execute(update(s.purchases).where(s.purchases.c.id == p2['id']).values(created_at=datetime(2026, 1, 1, 0, 1, tzinfo=LOCAL_TZ)))
    svc.save_budget(token, uid(), 2025, 'Mehanika', '100')
    svc.save_budget(token, uid(), 2026, 'Mehanika', '200')
    assert svc.budget_report(token, 2025)[0]['spent'] == Decimal('.30')
    assert svc.budget_report(token, 2026)[0]['remaining'] == Decimal('199.80')
    with pytest.raises(BusinessError):
        money('NaN')


def test_roles_password_hashes_and_session_revocation(warehouse):
    svc, admin = warehouse
    svc.save_user(admin, uid(), 'tech', 'temporary-tech-pass-2026')
    token = svc.login('tech', 'temporary-tech-pass-2026')
    with pytest.raises(BusinessError, match='privremenu'):
        svc.list_parts(token)
    svc.change_password(token, 'temporary-tech-pass-2026', 'new-password-for-tech-2026')
    with pytest.raises(BusinessError, match='Sesija'):
        svc.actor(token)
    token = svc.login('tech', 'new-password-for-tech-2026')
    with pytest.raises(BusinessError, match='administrator'):
        svc.save_part(token, uid(), 'PN', 'Naziv', 'Kat', 0, 0)
    with pytest.raises(BusinessError):
        svc.read_table(token, 'users')
    svc.save_user(admin, uid(), 'tech', 'reset-password-tech-2026', active=False)
    with pytest.raises(BusinessError):
        svc.actor(token)
    with svc.engine.connect() as c:
        assert all(r.startswith('scrypt$') for r in c.scalars(select(s.users.c.password_hash)))


def test_login_throttle_is_shared(warehouse):
    svc, _ = warehouse
    for _ in range(5):
        with pytest.raises(BusinessError):
            svc.login('admin', 'wrong')
    other = Warehouse(svc.engine)
    with pytest.raises(BusinessError, match='zaključana'):
        other.login('admin', 'test-admin-password-2026')


def test_pm_due_dates_and_void_preserve_history(warehouse):
    svc, token = warehouse
    line = svc.save_maintenance(token, uid(), 'line', 'Linija')['id']
    machine = svc.save_maintenance(token, uid(), 'machine', 'Mašina', parent_id=line)['id']
    task = svc.save_maintenance(token, uid(), 'task', 'Provera', parent_id=machine, period='Mesečno')['id']
    svc.set_pm_start(token, uid(), date(2026, 1, 1))
    assert svc.maintenance_report(token)[0]['due'] == date(2026, 1, 1)
    entry = svc.complete_task(token, uid(), task)
    assert svc.maintenance_report(token)[0]['last_done'] is not None
    svc.void_maintenance(token, uid(), entry['id'], 'Greška')
    assert svc.maintenance_report(token)[0]['last_done'] is None
    assert count(svc, s.maintenance_logs) == 1
    assert next_due(date(2024, 1, 31), 'Mesečno') == date(2024, 2, 29)
    assert next_due(date(2024, 2, 29), 'Godišnje') == date(2025, 2, 28)


def test_legacy_import_readonly_complete_and_idempotent(warehouse):
    svc, token = warehouse
    source = ROOT / 'magacin.db'
    if not source.exists():
        pytest.skip('Legacy source is not distributed with the application.')
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    result = import_legacy(svc.engine, source, 'admin', 'test-admin-password-2026')
    assert not result['already_imported']
    assert count(svc, s.parts) == result['counts']['delovi']
    assert count(svc, s.movements) == result['counts']['transakcije']
    assert count(svc, s.maintenance_logs) == result['counts']['pm_evidencija']
    assert import_legacy(svc.engine, source, 'admin', 'test-admin-password-2026')['already_imported']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    archive = svc.read_table(token, 'archive')
    assert any(r['table_name'] == 'kvarovi_zastoji' for r in archive)
    assert all('password' not in r['payload'] for r in archive)
    assert all(r['payload'].get('kljuc') != 'reset_pin' for r in archive)
    with pytest.raises(BusinessError):
        svc.login('tehnicar', 'tehnicar')


def test_constraints_reject_negative_stock_directly(warehouse):
    svc, token = warehouse
    pid = create_part(svc, token)
    with pytest.raises(IntegrityError):
        with svc.engine.begin() as c:
            c.execute(update(s.parts).where(s.parts.c.id == pid).values(stock=-1))
    assert stock(svc, token, pid) == 5

