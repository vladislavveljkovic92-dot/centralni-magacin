from sqlalchemy import (MetaData, Table, Column, String, Integer, Boolean, Text,
                        Numeric, DateTime, Date, ForeignKey, UniqueConstraint,
                        CheckConstraint, JSON, Index)

metadata = MetaData(naming_convention={
    'ix': 'ix_%(table_name)s_%(column_0_name)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
})


def pk():
    return Column('id', String(36), primary_key=True)


users = Table('app_users', metadata, pk(),
    Column('username', String(100), nullable=False, unique=True),
    Column('password_hash', Text, nullable=False),
    Column('role', String(20), nullable=False),
    Column('active', Boolean, nullable=False, default=True),
    Column('must_change', Boolean, nullable=False, default=False),
    Column('auth_version', Integer, nullable=False, default=1),
    CheckConstraint("role IN ('admin','tehnicar')", name='role'))
sessions = Table('app_sessions', metadata,
    Column('token_hash', String(64), primary_key=True),
    Column('user_id', ForeignKey('app_users.id'), nullable=False),
    Column('auth_version', Integer, nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=False))
attempts = Table('login_attempts', metadata,
    Column('username', String(100), primary_key=True),
    Column('failures', Integer, nullable=False),
    Column('locked_until', DateTime(timezone=True)))
parts = Table('inventory_parts', metadata, pk(),
    Column('part_number', String(150), nullable=False, unique=True),
    Column('name', Text, nullable=False),
    Column('category', String(100), nullable=False),
    Column('stock', Integer, nullable=False, default=0),
    Column('minimum', Integer, nullable=False, default=0),
    Column('maximum', Integer),
    Column('price', Numeric(16, 2), nullable=False, default=0),
    Column('supplier', Text, nullable=False, default=''),
    Column('purpose', Text, nullable=False, default=''),
    Column('image_path', Text, nullable=False, default=''),
    Column('active', Boolean, nullable=False, default=True),
    CheckConstraint('stock >= 0', name='stock_nonnegative'),
    CheckConstraint('minimum >= 0', name='minimum_nonnegative'),
    CheckConstraint('price >= 0', name='price_nonnegative'))
orders = Table('work_orders', metadata, pk(),
    Column('number', String(100), nullable=False, unique=True),
    Column('status', String(20), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('actor', String(100), nullable=False),
    Column('note', Text, nullable=False, default=''),
    CheckConstraint("status IN ('Otvoren','Zatvoren','Storniran')", name='status'))
order_items = Table('work_order_items', metadata, pk(),
    Column('order_id', ForeignKey('work_orders.id'), nullable=False, index=True),
    Column('part_id', ForeignKey('inventory_parts.id'), nullable=False),
    Column('quantity', Integer, nullable=False),
    CheckConstraint('quantity > 0', name='positive_quantity'))
purchases = Table('purchases', metadata, pk(),
    Column('part_id', ForeignKey('inventory_parts.id')),
    Column('item_name', Text, nullable=False),
    Column('category', String(100), nullable=False),
    Column('quantity', Integer, nullable=False),
    Column('unit_price', Numeric(16, 2), nullable=False),
    Column('total', Numeric(18, 2), nullable=False),
    Column('supplier', Text, nullable=False, default=''),
    Column('created_at', DateTime(timezone=True), nullable=False, index=True),
    Column('actor', String(100), nullable=False),
    Column('cancelled', Boolean, nullable=False, default=False),
    CheckConstraint('quantity > 0', name='positive_quantity'),
    CheckConstraint('unit_price >= 0 AND total >= 0', name='positive_amount'))
movements = Table('stock_movements', metadata, pk(),
    Column('part_id', ForeignKey('inventory_parts.id'), nullable=False, index=True),
    Column('quantity', Integer, nullable=False),
    Column('kind', String(40), nullable=False),
    Column('actor', String(100), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False, index=True),
    Column('note', Text, nullable=False, default=''),
    Column('order_id', ForeignKey('work_orders.id')),
    Column('purchase_id', ForeignKey('purchases.id')),
    CheckConstraint('quantity > 0', name='positive_quantity'))
budgets = Table('annual_budgets', metadata, pk(),
    Column('year', Integer, nullable=False),
    Column('category', String(100), nullable=False),
    Column('approved', Numeric(18, 2), nullable=False),
    UniqueConstraint('year', 'category'),
    CheckConstraint('approved >= 0', name='positive_amount'))
lines = Table('maintenance_lines', metadata, pk(),
    Column('name', Text, nullable=False, unique=True),
    Column('description', Text, nullable=False, default=''),
    Column('icon', String(40), nullable=False, default='🏭'),
    Column('position', Integer, nullable=False, default=0),
    Column('active', Boolean, nullable=False, default=True))
machines = Table('maintenance_machines', metadata, pk(),
    Column('line_id', ForeignKey('maintenance_lines.id'), nullable=False, index=True),
    Column('name', Text, nullable=False),
    Column('position', Integer, nullable=False, default=0),
    Column('active', Boolean, nullable=False, default=True))
tasks = Table('maintenance_tasks', metadata, pk(),
    Column('machine_id', ForeignKey('maintenance_machines.id'), nullable=False, index=True),
    Column('description', Text, nullable=False),
    Column('period', String(30), nullable=False),
    Column('position', Integer, nullable=False, default=0),
    Column('active', Boolean, nullable=False, default=True))
maintenance_logs = Table('maintenance_logs', metadata, pk(),
    Column('task_id', ForeignKey('maintenance_tasks.id'), nullable=False, index=True),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('actor', String(100), nullable=False),
    Column('status', String(30), nullable=False, default='Urađeno'),
    Column('note', Text, nullable=False, default=''),
    Column('voided', Boolean, nullable=False, default=False))
settings = Table('app_settings', metadata,
    Column('key', String(100), primary_key=True), Column('value', Text, nullable=False))
operations = Table('app_operations', metadata,
    Column('id', String(36), primary_key=True),
    Column('fingerprint', String(64), nullable=False),
    Column('result', JSON, nullable=False))
audit = Table('audit_events', metadata, pk(),
    Column('actor', String(100), nullable=False),
    Column('action', String(100), nullable=False),
    Column('entity_id', String(100), nullable=False),
    Column('details', JSON, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False))
imports = Table('legacy_imports', metadata,
    Column('source_hash', String(64), primary_key=True),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('counts', JSON, nullable=False))
archive = Table('legacy_archive', metadata, pk(),
    Column('table_name', String(100), nullable=False),
    Column('payload', JSON, nullable=False))

