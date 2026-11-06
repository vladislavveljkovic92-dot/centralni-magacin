"""Transactional business operations. All writes use this layer, never UI SQL."""
import calendar
import hashlib
import hmac
import json
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, insert, update, func
from sqlalchemy.exc import IntegrityError

from . import schema as s

LOCAL_TZ = ZoneInfo('Europe/Budapest')
PERIODS = ['Dnevno', 'Nedeljno', 'Mesečno', 'Kvartalno', 'Polugodišnje', 'Godišnje']
# Šifra potvrde za fabrički reset (vidi Warehouse.factory_reset).
RESET_CODE = '300120'


class BusinessError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password, stored):
    try:
        method, salt, expected = stored.split('$')
        if method != 'scrypt':
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def valid_password(value):
    if len(value) < 12:
        raise BusinessError('Lozinka mora imati najmanje 12 znakova.')


def required(value, label, limit=2000):
    value = str(value).strip()
    if not value or len(value) > limit:
        raise BusinessError(f'{label}: unesite vrednost do {limit} znakova.')
    return value


def quantity(value):
    if isinstance(value, bool):
        raise BusinessError('Količina mora biti pozitivan ceo broj.')
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d != d.to_integral_value() or d <= 0 or d > 2_000_000_000:
            raise ValueError
        return int(d)
    except (ValueError, InvalidOperation):
        raise BusinessError('Količina mora biti pozitivan ceo broj.') from None


def money(value):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or d > Decimal('999999999999.99'):
            raise ValueError
        return d.quantize(Decimal('.01'))
    except (ValueError, InvalidOperation):
        raise BusinessError('Novčani iznos mora biti konačan broj, veći ili jednak nuli.') from None


def next_due(last_day, period):
    if period == 'Dnevno':
        return last_day + timedelta(days=1)
    if period == 'Nedeljno':
        return last_day + timedelta(days=7)
    months = {'Mesečno': 1, 'Kvartalno': 3, 'Polugodišnje': 6, 'Godišnje': 12}.get(period)
    if not months:
        raise BusinessError('Nepoznata periodika održavanja.')
    y, m = divmod(last_day.year * 12 + last_day.month - 1 + months, 12)
    return date(y, m + 1, min(last_day.day, calendar.monthrange(y, m + 1)[1]))


class Warehouse:
    def __init__(self, engine):
        self.engine = engine

    def _actor(self, conn, token, admin=False, allow_change=False):
        digest = hashlib.sha256((token or '').encode()).hexdigest()
        row = conn.execute(select(s.users).join(s.sessions, s.users.c.id == s.sessions.c.user_id).where(
            s.sessions.c.token_hash == digest, s.sessions.c.expires_at > now(),
            s.sessions.c.auth_version == s.users.c.auth_version, s.users.c.active.is_(True))).mappings().first()
        if not row:
            raise BusinessError('Sesija je istekla. Prijavite se ponovo.')
        if row['must_change'] and not allow_change:
            raise BusinessError('Prvo promenite privremenu lozinku.')
        if admin and row['role'] != 'admin':
            raise BusinessError('Ovu operaciju može izvršiti samo administrator.')
        return dict(row)

    def actor(self, token):
        with self.engine.connect() as conn:
            user = self._actor(conn, token, allow_change=True)
            return {k: user[k] for k in ('id', 'username', 'role', 'must_change')}

    def login(self, username, password):
        username = username.strip()[:100]
        blocked = False
        token = None
        with self.engine.begin() as c:
            # Persistent, atomic per-account throttle works across app processes.
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            c.execute(pg_insert(s.attempts).values(username=username, failures=0).on_conflict_do_nothing())
            attempt = c.execute(select(s.attempts).where(s.attempts.c.username == username).with_for_update()).mappings().one()
            if attempt['locked_until'] and attempt['locked_until'] > now():
                blocked = True
            else:
                user = c.execute(select(s.users).where(s.users.c.username == username)).mappings().first()
                stored = user['password_hash'] if user else password_hash('dummy-password-for-timing')
                ok = verify_password(password, stored)
                if user and user['active'] and ok:
                    token = secrets.token_urlsafe(32)
                    c.execute(insert(s.sessions).values(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                        user_id=user['id'], auth_version=user['auth_version'], expires_at=now() + timedelta(hours=8)))
                    c.execute(update(s.attempts).where(s.attempts.c.username == username).values(failures=0, locked_until=None))
                else:
                    failures = (0 if attempt['locked_until'] else attempt['failures']) + 1
                    c.execute(update(s.attempts).where(s.attempts.c.username == username).values(
                        failures=failures, locked_until=now() + timedelta(minutes=15) if failures >= 5 else None))
        if not token:
            raise BusinessError('Prijava nije uspela. Posle 5 neuspešnih pokušaja sačekajte 15 minuta.'
                                if not blocked else 'Prijava je privremeno zaključana. Sačekajte 15 minuta.')
        return token

    def logout(self, token):
        with self.engine.begin() as c:
            c.execute(s.sessions.delete().where(s.sessions.c.token_hash == hashlib.sha256(token.encode()).hexdigest()))

    def bootstrap(self, username, password):
        valid_password(password)
        with self.engine.begin() as c:
            c.exec_driver_sql('SELECT pg_advisory_xact_lock(7142301)')
            if c.scalar(select(func.count()).select_from(s.users)):
                return False
            c.execute(insert(s.users).values(id=uid(), username=required(username, 'Korisnik', 100),
                password_hash=password_hash(password), role='admin', active=True, must_change=False, auth_version=1))
            return True

    def _audit(self, c, actor, action, entity, details=None):
        c.execute(insert(s.audit).values(id=uid(), actor=actor['username'], action=action,
            entity_id=str(entity), details=json.loads(json.dumps(details or {}, default=str)), created_at=now()))

    def _write(self, token, request_id, action, payload, callback, admin=False):
        request_id = required(request_id, 'ID zahteva', 36)
        fingerprint = hashlib.sha256(json.dumps([action, payload], sort_keys=True, default=str).encode()).hexdigest()
        try:
            with self.engine.begin() as c:
                actor = self._actor(c, token, admin)
                fingerprint = hashlib.sha256((fingerprint + actor['id']).encode()).hexdigest()
                c.execute(insert(s.operations).values(id=request_id, fingerprint=fingerprint, result={}))
                result = callback(c, actor)
                c.execute(update(s.operations).where(s.operations.c.id == request_id).values(result=result))
                self._audit(c, actor, action, result.get('id', request_id), payload)
                return result
        except IntegrityError:
            with self.engine.connect() as c:
                self._actor(c, token, admin)
                existing = c.execute(select(s.operations).where(s.operations.c.id == request_id)).mappings().first()
                if existing and hmac.compare_digest(existing['fingerprint'], fingerprint):
                    return existing['result']
                if existing:
                    raise BusinessError('Zahtev je već korišćen za drugu operaciju. Osvežite formu.') from None
            raise BusinessError('Podaci su u konfliktu sa postojećim zapisom ili pravilima baze. Ništa nije upisano.') from None

    def change_password(self, token, old, new):
        valid_password(new)
        if old == new:
            raise BusinessError('Nova lozinka mora biti različita od stare.')
        with self.engine.begin() as c:
            user = self._actor(c, token, allow_change=True)
            if not verify_password(old, user['password_hash']):
                raise BusinessError('Trenutna lozinka nije tačna.')
            c.execute(update(s.users).where(s.users.c.id == user['id']).values(
                password_hash=password_hash(new), must_change=False, auth_version=s.users.c.auth_version + 1))
            self._audit(c, user, 'password_change', user['id'])

    def save_user(self, token, request_id, username, password, role='tehnicar', active=True):
        username = required(username, 'Korisnik', 100)
        valid_password(password)
        if role not in ('admin', 'tehnicar'):
            raise BusinessError('Nepoznata uloga.')
        # Do not put credentials or password hashes in the audit payload.
        def perform(c, actor):
            user = c.execute(select(s.users).where(s.users.c.username == username).with_for_update()).mappings().first()
            if user and user['id'] == actor['id']:
                raise BusinessError('Svoju lozinku menjate kroz opciju Promena lozinke.')
            values = dict(password_hash=password_hash(password), role=role, active=active, must_change=True)
            if user:
                c.execute(update(s.users).where(s.users.c.id == user['id']).values(**values, auth_version=s.users.c.auth_version + 1))
                return {'id': user['id']}
            user_id = uid()
            c.execute(insert(s.users).values(id=user_id, username=username, auth_version=1, **values))
            return {'id': user_id}
        return self._write(token, request_id, 'save_user', {'username': username, 'role': role, 'active': active}, perform, admin=True)

    def list_parts(self, token, include_inactive=False):
        with self.engine.connect() as c:
            self._actor(c, token)
            q = select(s.parts).order_by(s.parts.c.category, s.parts.c.name)
            if not include_inactive:
                q = q.where(s.parts.c.active.is_(True))
            return [dict(r) for r in c.execute(q).mappings()]

    def save_part(self, token, request_id, part_number, name, category, minimum, price,
                  supplier='', part_id=None, active=True):
        try:
            minimum_value = Decimal(str(minimum))
            if not minimum_value.is_finite() or minimum_value != minimum_value.to_integral_value() or not 0 <= minimum_value <= 2_000_000_000:
                raise ValueError
            minimum = int(minimum_value)
        except (InvalidOperation, ValueError):
            raise BusinessError('Minimalna zaliha mora biti nenegativan ceo broj.') from None
        data = dict(part_number=required(part_number, 'Part number', 150), name=required(name, 'Naziv'),
            category=required(category, 'Kategorija', 100), minimum=minimum, price=money(price),
            supplier=str(supplier).strip(), active=active)
        def perform(c, actor):
            pid = part_id or uid()
            if part_id:
                changed = c.execute(update(s.parts).where(s.parts.c.id == pid).values(**data)).rowcount
                if not changed:
                    raise BusinessError('Deo ne postoji.')
            else:
                c.execute(insert(s.parts).values(id=pid, stock=0, purpose='', image_path='', **data))
            return {'id': pid}
        # Novi deo sme da doda i tehnicar; izmena postojećeg zahteva admina.
        return self._write(token, request_id, 'save_part', {**data, 'part_id': part_id}, perform,
                           admin=(part_id is not None))

    def delete_part(self, token, request_id, part_id):
        """Trajno brisanje dela — dozvoljeno samo ako deo nema nikakvu istoriju."""
        def perform(c, actor):
            row = c.execute(select(s.parts).where(s.parts.c.id == part_id).with_for_update()).mappings().first()
            if not row:
                raise BusinessError('Deo ne postoji.')
            movements = c.scalar(select(func.count()).select_from(s.movements)
                                 .where(s.movements.c.part_id == part_id))
            items = c.scalar(select(func.count()).select_from(s.order_items)
                             .where(s.order_items.c.part_id == part_id))
            purchases = c.scalar(select(func.count()).select_from(s.purchases)
                                 .where(s.purchases.c.part_id == part_id))
            if movements or items or purchases:
                raise BusinessError('Deo ima istoriju (kretanja zalihâ, nalozi ili nabavke) '
                                    'i ne može se trajno obrisati. Koristite arhiviranje.')
            if row['stock']:
                raise BusinessError('Deo ima zalihšu na stanju i ne može se trajno obrisati.')
            c.execute(s.parts.delete().where(s.parts.c.id == part_id))
            return {'id': part_id}
        return self._write(token, request_id, 'delete_part', {'part_id': part_id}, perform, admin=True)

    def factory_reset(self, token, request_id, code):
        """Fabrički reset: briše sve poslovne podatke i sve korisnike osim admina."""
        def perform(c, actor):
            if str(code or '').strip() != RESET_CODE:
                raise BusinessError('Pogrešna šifra za fabrički reset.')
            # Redosled po stranim ključevima: prvo ono što na nešto referencira.
            for table in (s.movements, s.order_items, s.purchases, s.orders,
                          s.maintenance_logs, s.tasks, s.machines, s.lines,
                          s.parts, s.budgets, s.audit, s.archive, s.imports,
                          s.operations, s.attempts):
                c.execute(table.delete())
            # Korisnici: ostaju samo admini (i njihove sesije, da admin ne bude odjavljen).
            admin_ids = select(s.users.c.id).where(s.users.c.role == 'admin')
            c.execute(s.sessions.delete().where(s.sessions.c.user_id.not_in(admin_ids)))
            c.execute(s.users.delete().where(s.users.c.role != 'admin'))
            return {'id': 'factory_reset'}
        return self._write(token, request_id, 'factory_reset', {}, perform, admin=True)

    def _part(self, c, part_id, lock=False):
        q = select(s.parts).where(s.parts.c.id == part_id, s.parts.c.active.is_(True))
        if lock:
            q = q.with_for_update()
        row = c.execute(q).mappings().first()
        if not row:
            raise BusinessError('Deo ne postoji ili je arhiviran.')
        return row

    def _movement(self, c, actor, part_id, qty, kind, note='', order_id=None, purchase_id=None):
        c.execute(insert(s.movements).values(id=uid(), part_id=part_id, quantity=qty, kind=kind,
            note=note, actor=actor['username'], created_at=now(), order_id=order_id, purchase_id=purchase_id))

    def receive(self, token, request_id, part_id, qty, unit_price, supplier='', note=''):
        qty, price = quantity(qty), money(unit_price)
        def perform(c, actor):
            part = self._part(c, part_id, lock=True)
            purchase_id = uid()
            c.execute(insert(s.purchases).values(id=purchase_id, part_id=part_id, item_name=part['name'],
                category=part['category'], quantity=qty, unit_price=price, total=price * qty,
                supplier=supplier or part['supplier'], created_at=now(), actor=actor['username'], cancelled=False))
            c.execute(update(s.parts).where(s.parts.c.id == part_id).values(stock=s.parts.c.stock + qty))
            self._movement(c, actor, part_id, qty, 'ULAZ', note, purchase_id=purchase_id)
            return {'id': purchase_id}
        return self._write(token, request_id, 'receive', {'part': part_id, 'quantity': qty,
            'price': str(price), 'supplier': supplier, 'note': note}, perform)

    def return_stock(self, token, request_id, part_id, qty, note):
        qty, note = quantity(qty), required(note, 'Razlog povrata')
        def perform(c, actor):
            self._part(c, part_id, lock=True)
            c.execute(update(s.parts).where(s.parts.c.id == part_id).values(stock=s.parts.c.stock + qty))
            self._movement(c, actor, part_id, qty, 'POVRAT', note)
            return {'id': part_id}
        return self._write(token, request_id, 'return', {'part': part_id, 'quantity': qty, 'note': note}, perform)

    def issue_order(self, token, request_id, items, note=''):
        # Aggregate duplicates BEFORE checking stock. Lock in stable order.
        totals = {}
        for item in items:
            pid = str(item['part_id'])
            totals[pid] = totals.get(pid, 0) + quantity(item['quantity'])
        if not totals:
            raise BusinessError('Nalog nema stavke.')
        def perform(c, actor):
            order_id = uid()
            number = f'RN-{now():%Y%m%d}-{order_id}'
            c.execute(insert(s.orders).values(id=order_id, number=number, status='Otvoren',
                created_at=now(), actor=actor['username'], note=note))
            for pid, qty in sorted(totals.items()):
                part = self._part(c, pid)
                result = c.execute(update(s.parts).where(s.parts.c.id == pid, s.parts.c.active.is_(True),
                    s.parts.c.stock >= qty).values(stock=s.parts.c.stock - qty))
                if result.rowcount != 1:
                    raise BusinessError(f'Nedovoljno zalihe za {part["name"]}. Nalog nije izdat.')
                c.execute(insert(s.order_items).values(id=uid(), order_id=order_id, part_id=pid, quantity=qty))
                self._movement(c, actor, pid, qty, 'IZLAZ', note, order_id=order_id)
            return {'id': order_id, 'number': number}
        return self._write(token, request_id, 'issue_order', {'items': totals, 'note': note}, perform)

    def order_action(self, token, request_id, order_id, action, reason=''):
        if action not in ('close', 'cancel'):
            raise BusinessError('Nepoznata operacija.')
        if action == 'cancel':
            required(reason, 'Razlog storna')
        def perform(c, actor):
            order = c.execute(select(s.orders).where(s.orders.c.id == order_id).with_for_update()).mappings().first()
            if not order or order['status'] != 'Otvoren':
                raise BusinessError('Nalog nije otvoren ili je već obrađen.')
            if action == 'cancel':
                items = c.execute(select(s.order_items).where(s.order_items.c.order_id == order_id)
                    .order_by(s.order_items.c.part_id)).mappings()
                for item in items:
                    c.execute(update(s.parts).where(s.parts.c.id == item['part_id']).values(stock=s.parts.c.stock + item['quantity']))
                    self._movement(c, actor, item['part_id'], item['quantity'], 'STORNO_IZLAZA', reason, order_id=order_id)
            c.execute(update(s.orders).where(s.orders.c.id == order_id).values(status='Zatvoren' if action == 'close' else 'Storniran'))
            return {'id': order_id}
        return self._write(token, request_id, 'order_' + action, {'order': order_id, 'reason': reason}, perform, admin=True)

    def cancel_purchase(self, token, request_id, purchase_id, reason):
        reason = required(reason, 'Razlog storna')
        def perform(c, actor):
            purchase = c.execute(select(s.purchases).where(s.purchases.c.id == purchase_id).with_for_update()).mappings().first()
            if not purchase or purchase['cancelled']:
                raise BusinessError('Nabavka ne postoji ili je već stornirana.')
            if not purchase['part_id']:
                raise BusinessError('Stara nabavka nema pouzdanu vezu sa delom. Potrebno je prethodno usaglašavanje podataka.')
            result = c.execute(update(s.parts).where(s.parts.c.id == purchase['part_id'],
                s.parts.c.stock >= purchase['quantity']).values(stock=s.parts.c.stock - purchase['quantity']))
            if result.rowcount != 1:
                raise BusinessError('Storno nije moguć: deo nabavljene robe je već izdat.')
            c.execute(update(s.purchases).where(s.purchases.c.id == purchase_id).values(cancelled=True))
            self._movement(c, actor, purchase['part_id'], purchase['quantity'], 'STORNO_ULAZA', reason, purchase_id=purchase_id)
            return {'id': purchase_id}
        return self._write(token, request_id, 'cancel_purchase', {'purchase': purchase_id, 'reason': reason}, perform, admin=True)

    def save_budget(self, token, request_id, year, category, approved):
        year = int(year)
        if not 2000 <= year <= 2200:
            raise BusinessError('Neispravna godina.')
        category, approved = required(category, 'Kategorija', 100), money(approved)
        def perform(c, actor):
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            values = dict(id=uid(), year=year, category=category, approved=approved)
            c.execute(pg_insert(s.budgets).values(**values).on_conflict_do_update(
                index_elements=['year', 'category'], set_={'approved': approved}))
            return {'id': f'{year}/{category}'}
        return self._write(token, request_id, 'save_budget', {'year': year, 'category': category, 'approved': str(approved)}, perform, admin=True)

    def budget_report(self, token, year):
        with self.engine.connect() as c:
            self._actor(c, token)
            approved = {r.category: r.approved for r in c.execute(select(s.budgets).where(s.budgets.c.year == int(year)))}
            # Local business year, even around UTC New Year boundaries.
            start = datetime(int(year), 1, 1, tzinfo=LOCAL_TZ)
            end = datetime(int(year) + 1, 1, 1, tzinfo=LOCAL_TZ)
            spent = dict(c.execute(select(s.purchases.c.category, func.sum(s.purchases.c.total)).where(
                s.purchases.c.cancelled.is_(False), s.purchases.c.created_at >= start,
                s.purchases.c.created_at < end).group_by(s.purchases.c.category)).all())
            return [dict(category=cat, approved=approved.get(cat, Decimal(0)), spent=spent.get(cat, Decimal(0)),
                         remaining=approved.get(cat, Decimal(0)) - spent.get(cat, Decimal(0)))
                    for cat in sorted(approved.keys() | spent.keys())]

    def read_table(self, token, name):
        tables = {'orders': s.orders, 'order_items': s.order_items, 'purchases': s.purchases, 'history': s.movements,
                  'users': s.users, 'audit': s.audit, 'lines': s.lines, 'machines': s.machines,
                  'tasks': s.tasks, 'maintenance': s.maintenance_logs, 'archive': s.archive}
        if name not in tables:
            raise BusinessError('Nepoznat pregled.')
        with self.engine.connect() as c:
            self._actor(c, token, admin=name in ('users', 'audit', 'archive'))
            t = tables[name]
            cols = [col for col in t.c if col.name not in ('password_hash', 'auth_version')]
            q = select(*cols)
            if 'created_at' in t.c:
                q = q.order_by(t.c.created_at.desc())
            return [dict(r) for r in c.execute(q).mappings()]

    def save_maintenance(self, token, request_id, kind, name, parent_id=None, period=None,
                         entity_id=None, active=True):
        tables = {'line': s.lines, 'machine': s.machines, 'task': s.tasks}
        if kind not in tables:
            raise BusinessError('Nepoznata PM stavka.')
        values = {'description' if kind == 'task' else 'name': required(name, 'Naziv / opis'), 'active': active}
        if kind == 'task':
            if period not in PERIODS:
                raise BusinessError('Izaberite periodiku.')
            values.update(machine_id=parent_id, period=period)
        elif kind == 'machine':
            values['line_id'] = parent_id
        def perform(c, actor):
            t = tables[kind]
            eid = entity_id or uid()
            if entity_id:
                if not c.execute(update(t).where(t.c.id == eid).values(**values)).rowcount:
                    raise BusinessError('PM stavka ne postoji.')
            else:
                c.execute(insert(t).values(id=eid, position=0, **values))
            return {'id': eid}
        return self._write(token, request_id, 'save_maintenance', {'kind': kind, 'id': entity_id, **values}, perform, admin=True)

    def set_pm_start(self, token, request_id, start):
        if not isinstance(start, date):
            raise BusinessError('Neispravan datum.')
        def perform(c, actor):
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            c.execute(pg_insert(s.settings).values(key='pm_pocetak', value=start.isoformat()).on_conflict_do_update(
                index_elements=['key'], set_={'value': start.isoformat()}))
            return {'id': 'pm_pocetak'}
        return self._write(token, request_id, 'set_pm_start', {'start': start.isoformat()}, perform, admin=True)

    def complete_task(self, token, request_id, task_id, note=''):
        def perform(c, actor):
            task = c.execute(select(s.tasks.c.id).select_from(s.tasks.join(s.machines).join(s.lines)).where(
                s.tasks.c.id == task_id, s.tasks.c.active.is_(True), s.machines.c.active.is_(True),
                s.lines.c.active.is_(True))).first()
            if not task:
                raise BusinessError('Zadatak ili nadređena mašina/linija nije aktivna.')
            lid = uid()
            c.execute(insert(s.maintenance_logs).values(id=lid, task_id=task_id, created_at=now(),
                actor=actor['username'], status='Urađeno', note=note, voided=False))
            return {'id': lid}
        return self._write(token, request_id, 'complete_task', {'task': task_id, 'note': note}, perform)

    def void_maintenance(self, token, request_id, log_id, reason):
        reason = required(reason, 'Razlog poništavanja')
        def perform(c, actor):
            if c.execute(update(s.maintenance_logs).where(s.maintenance_logs.c.id == log_id,
                s.maintenance_logs.c.voided.is_(False)).values(voided=True)).rowcount != 1:
                raise BusinessError('Evidencija ne postoji ili je već poništena.')
            return {'id': log_id}
        return self._write(token, request_id, 'void_maintenance', {'log': log_id, 'reason': reason}, perform, admin=True)

    def maintenance_report(self, token):
        with self.engine.connect() as c:
            self._actor(c, token)
            start = c.scalar(select(s.settings.c.value).where(s.settings.c.key == 'pm_pocetak'))
            start = date.fromisoformat(start) if start else now().astimezone(LOCAL_TZ).date()
            logs = c.execute(select(s.maintenance_logs).where(s.maintenance_logs.c.voided.is_(False),
                s.maintenance_logs.c.status == 'Urađeno').order_by(s.maintenance_logs.c.created_at.desc())).mappings()
            latest = {}
            for log in logs:
                latest.setdefault(log['task_id'], log)
            query = select(s.tasks.c.id, s.lines.c.name.label('line'), s.machines.c.name.label('machine'),
                s.tasks.c.description, s.tasks.c.period).select_from(s.tasks.join(s.machines).join(s.lines)).where(
                s.tasks.c.active.is_(True), s.machines.c.active.is_(True), s.lines.c.active.is_(True))
            result = []
            today = now().astimezone(LOCAL_TZ).date()
            for r in c.execute(query).mappings():
                log = latest.get(r['id'])
                last = log['created_at'].astimezone(LOCAL_TZ).date() if log else None
                due = next_due(last, r['period']) if last else start
                status = 'Kasni' if today > due else ('Danas' if today == due else 'U roku')
                result.append({**dict(r), 'due': due, 'last_done': last, 'actor': log['actor'] if log else '', 'status': status})
            return result
