from alembic import context
from database import engine, Base
import models

if context.is_offline_mode():
    raise RuntimeError('This migration needs an online PostgreSQL connection for legacy-schema checks')
with engine.connect() as connection:
    if connection.dialect.name != 'postgresql':
        raise RuntimeError('Migrations require PostgreSQL; SQLite is only supported by unit tests')
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
