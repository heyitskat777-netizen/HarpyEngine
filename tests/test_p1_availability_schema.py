"""Historical migration and metadata enforce the same non-reversible epoch ledger."""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine


@pytest.mark.parametrize("schema", ("metadata", "migrations"))
def test_availability_epoch_history_rejects_replace_and_reactivation(tmp_path, monkeypatch, schema):
    url = f"sqlite:///{tmp_path / 'availability.db'}"
    if schema == "migrations":
        monkeypatch.setenv("GIRLFRAME_DATABASE_URL", url)
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    engine = create_database_engine(Settings(database_url=url))
    if schema == "metadata":
        t.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA recursive_triggers=OFF")
        connection.execute(t.campaigns.insert().values(id="synthetic", guild_id="11"))
        values = dict(
            campaign_id="synthetic",
            owner_id="11",
            incarnation="original",
            generation=1,
            phase="active",
        )
        connection.execute(t.actor_availability.insert().values(**values))
        connection.execute(
            t.actor_availability.insert().values(**dict(values, generation=2, phase="draining"))
        )
        for mutation in (
            t.actor_availability.insert().prefix_with("OR REPLACE").values(**values),
            t.actor_availability.update().values(phase="active"),
            t.actor_availability.delete(),
            t.actor_availability.insert().values(**dict(values, generation=3)),
        ):
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(mutation)
        with pytest.raises(sa.exc.OperationalError, match="rowid"):
            connection.exec_driver_sql("SELECT rowid FROM p1_actor_availability")
        assert connection.execute(
            sa.select(t.actor_availability.c.generation, t.actor_availability.c.phase).order_by(
                t.actor_availability.c.generation
            )
        ).all() == [(1, "active"), (2, "draining")]
    engine.dispose()
