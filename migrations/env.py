from alembic import context
from magacin_backend.db import engine_for
from magacin_backend.schema import metadata

if context.is_offline_mode():
    raise RuntimeError('Migracije zahtevaju vezu sa odabranom centralnom bazom.')
engine = engine_for()
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

