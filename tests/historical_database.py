"""Disposable historical-schema test fixtures; never downgrade a head database."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from girlframe.config import Settings
from girlframe.database.connection import create_database_engine


@contextmanager
def historical_database(
    source_engine: sa.Engine,
    config: Config,
    revision: str,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[sa.Engine]:
    """Copy genuine synthetic rows into a fresh actual historical common schema."""
    assert not database.exists()
    url = "sqlite:///" + str(database)
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", url)
    command.upgrade(config, revision)
    engine = create_database_engine(Settings(database_url=url))
    try:
        metadata = sa.MetaData()
        names = set(sa.inspect(engine).get_table_names()) - {"alembic_version"}
        metadata.reflect(bind=engine, only=sorted(names))
        with source_engine.connect() as source, engine.begin() as target:
            for table in metadata.sorted_tables:
                # The historical reflection selects only columns present then.
                rows = [dict(row) for row in source.execute(sa.select(table)).mappings()]
                if rows:
                    target.execute(table.insert(), rows)
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == revision
            assert connection.execute(sa.text("PRAGMA foreign_key_check")).all() == []
        yield engine
    finally:
        engine.dispose()
