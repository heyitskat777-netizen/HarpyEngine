"""Explicit application migrations; runtime startup never invokes this module."""

from alembic import context

from girlframe.config import load_settings
from girlframe.database import tables  # noqa: F401 -- register migration metadata
from girlframe.database.base import Base
from girlframe.database.connection import create_database_engine

target_metadata = Base.metadata
settings = load_settings()

if context.is_offline_mode():
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, render_as_batch=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
