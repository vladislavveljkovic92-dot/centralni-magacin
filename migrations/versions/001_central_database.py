"""Initial central database, independent from the untouched legacy SQLite files."""
from alembic import op
from magacin_backend.schema import metadata

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(bind=op.get_bind())


def downgrade():
    raise RuntimeError('Automatsko brisanje poslovne baze nije podržano; koristite provereni backup.')

