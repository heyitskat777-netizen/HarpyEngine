"""Raw canonical writers and replacement routes cannot evade the draining barrier."""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine


@pytest.mark.parametrize("schema", ("metadata", "migrations"))
def test_canonical_barrier_all_writes_and_rowid_replace(tmp_path, monkeypatch, schema):
    url = f"sqlite:///{tmp_path / 'barrier.db'}"
    if schema == "migrations":
        monkeypatch.setenv("GIRLFRAME_DATABASE_URL", url)
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    engine = create_database_engine(Settings(database_url=url))
    if schema == "metadata":
        t.metadata.create_all(engine)
    table = t.m2["m2_state"]
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA recursive_triggers=OFF")
        for campaign in ("draining", "open"):
            connection.execute(t.campaigns.insert().values(id=campaign, guild_id=campaign))
            connection.execute(
                table.insert().values(campaign_id=campaign, revision=1, body_json="{}")
            )
        values = dict(
            campaign_id="draining",
            owner_id="11",
            incarnation="original",
            generation=1,
            phase="active",
        )
        connection.execute(t.actor_availability.insert().values(**values))
        connection.execute(
            table.update().where(table.c.campaign_id == "draining").values(revision=2)
        )
        connection.execute(
            t.actor_availability.insert().values(**dict(values, generation=2, phase="draining"))
        )
        before = connection.execute(sa.select(table).order_by(table.c.campaign_id)).all()
        for statement in (
            table.update().where(table.c.campaign_id == "draining").values(revision=3),
            table.delete().where(table.c.campaign_id == "draining"),
            table.insert()
            .prefix_with("OR REPLACE")
            .values(campaign_id="draining", revision=3, body_json="changed"),
            table.update().where(table.c.campaign_id == "draining").values(campaign_id="moved"),
        ):
            with pytest.raises(sa.exc.IntegrityError, match="Canonical writes blocked"):
                connection.execute(statement)
        rowid = connection.exec_driver_sql(
            "SELECT rowid FROM m2_state WHERE campaign_id='draining'"
        ).scalar_one()
        for sql in (
            "INSERT OR REPLACE INTO m2_state(rowid,campaign_id,revision,body_json) "
            "VALUES (?, 'open', 3, '{}')",
            "UPDATE OR REPLACE m2_state SET rowid=? WHERE campaign_id='open'",
        ):
            with pytest.raises(sa.exc.IntegrityError, match="Canonical writes blocked"):
                connection.exec_driver_sql(sql, (rowid,))
        assert connection.execute(sa.select(table).order_by(table.c.campaign_id)).all() == before
        connection.execute(table.update().where(table.c.campaign_id == "open").values(revision=2))
    engine.dispose()
