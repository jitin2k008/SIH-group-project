"""Initialize an empty database or verify the exact supplied legacy table layout."""
from alembic import op
from sqlalchemy import inspect
from migrations.legacy_schema import Base
revision = '0001_legacy'
down_revision = None
branch_labels = depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    expected = set(Base.metadata.tables)
    present = set(inspector.get_table_names()) & expected
    if present:
        if present != expected:
            raise RuntimeError('Partial legacy schema found. Restore/repair it before migration.')
        for table in Base.metadata.sorted_tables:
            actual = {c['name'] for c in inspector.get_columns(table.name)}
            if actual != set(table.columns.keys()):
                raise RuntimeError(f'{table.name} differs from uploaded schema. Review migration before proceeding.')
    else:
        Base.metadata.create_all(bind)

def downgrade():
    raise RuntimeError('Automatic downgrade is disabled to avoid deleting existing data; restore your backup.')
