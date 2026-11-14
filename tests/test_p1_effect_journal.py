"""Synthetic preparation tests; no claim of dispatch/drain integration coverage."""

import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import ValidationError

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.p1_effect_journal import (
    Destination,
    Incidence,
    JournalError,
    Preparation,
    ResourceBinding,
    Source,
    prepare,
    reserve,
)

ROOT = Path(__file__).resolve().parents[1]


def preparation() -> Preparation:
    return Preparation(
        source=Source(
            kind="action", id="synthetic-action", revision=1, event_seq=1, step_key="public-result"
        ),
        operation="public_post",
        actors=(
            Incidence(
                actor=ActorRef(kind="pilot", entity="11", incarnation="original"),
                generation=1,
                relation="subject",
            ),
        ),
        resource=ResourceBinding(
            destination=Destination(
                kind="guild_channel", guild_id="22", channel_id="33", bot_id="44"
            ),
            revision=1,
            owner_generation=1,
            scene_id="original-scene",
            cast_revision=1,
            source_generation=1,
        ),
        payload='{"content":"Synthetic saved result"}',
    )


def seed(connection: sa.Connection, campaign: str = "test", guild: str = "22") -> None:
    connection.execute(t.campaigns.insert().values(id=campaign, guild_id=guild))
    evidence = preparation().model_dump(mode="json")
    evidence["resource"]["destination"]["guild_id"] = guild
    connection.execute(
        t.events.insert().values(
            campaign_id=campaign,
            seq=1,
            command_key="synthetic",
            actor_id="11",
            kind="test",
            payload_json=json.dumps({"external_effect_preparations": [evidence]}),
            id=f"{campaign}-event",
            created_utc="2026-11-10T00:00:00Z",
        )
    )


def test_prepare_retains_identity_replays_and_rolls_back_with_source(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'journal.db'}"))
    t.metadata.create_all(engine)
    original = preparation()
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        seed(connection)
        identity = prepare(connection, "test", original)
        assert prepare(connection, "test", original) == identity
        with pytest.raises(JournalError, match="does not attest"):
            prepare(connection, "test", original.model_copy(update={"payload": "changed"}))
        row = connection.execute(sa.select(t.external_effects["effects"])).mappings().one()
        assert row["state"] == "prepared"
        assert "original-scene" in row["body_json"]
        assert "original" in row["body_json"]
        with pytest.raises(JournalError, match="Dispatch unavailable"):
            reserve(campaign_id="test", effect_id=identity, expected_revision=1)
        connection.rollback()
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(t.external_effects["effects"]))
            == 0
        )
        assert connection.scalar(sa.select(sa.func.count()).select_from(t.events)) == 0
    engine.dispose()


def test_prepare_requires_transaction_incidence_and_physical_ownership(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'scope.db'}"))
    t.metadata.create_all(engine)
    with engine.connect() as connection:
        with pytest.raises(JournalError, match="source transaction"):
            prepare(connection, "test", preparation())
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        seed(connection)
        seed(connection, "other", "55")
        prepare(connection, "test", preparation())
        data = preparation().model_dump()
        data["resource"]["destination"]["guild_id"] = "55"
        with pytest.raises(JournalError, match="ownership conflicts"):
            prepare(connection, "other", Preparation.model_validate(data))
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(t.external_effects["effects"]))
            == 1
        )
        connection.commit()
    data = preparation().model_dump()
    data["actors"] = ()
    with pytest.raises(ValidationError):
        Preparation.model_validate(data)
    engine.dispose()


def test_migration_preserves_old_source_evidence_and_refuses_journal_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "0016")
    engine = create_database_engine(Settings(database_url=url))
    with engine.begin() as connection:
        seed(connection)
        connection.execute(
            t.p1_source_pauses.insert().values(
                campaign_id="test",
                id="legacy",
                kind="source",
                channel_id="33",
                scene_id="old",
                event_id="test-event",
                state="restoring",
                snapshot_json='{"exact":"baseline"}',
            )
        )
    command.upgrade(config, "0018")
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        assert connection.scalar(sa.select(t.p1_source_pauses.c.snapshot_json)) == (
            '{"exact":"baseline"}'
        )
        assert connection.scalar(sa.select(t.p1_source_pauses.c.state)) == "restoring"
        prepare(connection, "test", preparation())
        connection.commit()
    with pytest.raises(RuntimeError, match="preparation evidence"):
        command.downgrade(config, "0016")
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(t.external_effects["effects"]))
            == 1
        )
    engine.dispose()


def test_source_evidence_must_attest_exact_actor_resource_and_payload(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'proof.db'}"))
    t.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        seed(connection)
        for field in ("source", "actors", "resource", "payload"):
            data = preparation().model_dump()
            if field == "source":
                data[field]["id"] = "unrelated-source"
            elif field == "actors":
                data[field][0]["actor"]["incarnation"] = "different-body"
            elif field == "resource":
                data[field]["destination"]["channel_id"] = "99"
            else:
                data[field] = "different private payload"
            with pytest.raises(JournalError, match="does not attest"):
                prepare(connection, "test", Preparation.model_validate(data))
        connection.execute(t.events.update().values(payload_json="{}"))
        with pytest.raises(JournalError, match="does not attest"):
            prepare(connection, "test", preparation())
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(t.external_effects["effects"]))
            == 0
        )
        connection.rollback()
    engine.dispose()


def test_journal_and_referenced_event_are_append_only(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'frozen.db'}"))
    t.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        seed(connection)
        identity = prepare(connection, "test", preparation())
        connection.commit()
        for table in (*t.external_effects.values(), t.events):
            column = next(iter(table.c))
            with pytest.raises(sa.exc.IntegrityError, match="immutable"):
                connection.execute(table.update().values({column.name: column}))
            with pytest.raises(sa.exc.IntegrityError, match="immutable"):
                connection.execute(table.delete())
            row = dict(connection.execute(sa.select(table)).mappings().one())
            with pytest.raises(sa.exc.IntegrityError, match="immutable"):
                connection.execute(table.insert().prefix_with("OR REPLACE").values(**row))
        actor = dict(connection.execute(sa.select(t.external_effects["actors"])).mappings().one())
        actor["actor_token"] = "unrelated"
        actor["availability_generation"] = 99
        with pytest.raises(sa.exc.IntegrityError, match="immutable|does not match|token conflicts"):
            connection.execute(t.external_effects["actors"].insert().values(**actor))
        link = dict(connection.execute(sa.select(t.external_effects["links"])).mappings().one())
        link["resource_key"] = "discord:channel:999"
        with pytest.raises(sa.exc.IntegrityError, match="immutable|does not match|token conflicts"):
            connection.execute(t.external_effects["links"].insert().values(**link))
        assert prepare(connection, "test", preparation()) == identity
        connection.rollback()
    engine.dispose()


def test_historical_migrations_do_not_import_live_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from girlframe.database import p1_effect_schema

    def changed_schema(_metadata: sa.MetaData) -> dict[str, sa.Table]:
        raise AssertionError("Historical migrations must not invoke live definitions")

    monkeypatch.setattr(p1_effect_schema, "define", changed_schema)
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", f"sqlite:///{tmp_path / 'history.db'}")
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "0018")
    command.downgrade(config, "0016")


def test_explicit_rowid_replace_cannot_discard_evidence(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'rowid.db'}"))
    t.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA recursive_triggers=OFF")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        seed(connection)
        prepare(connection, "test", preparation())
        # A second synthetic parent permits valid actor/link insertion with distinct
        # declared keys. The only conflict must be the occupied physical rowid.
        effects = t.external_effects["effects"]
        second = dict(connection.execute(sa.select(effects)).mappings().one())
        second.update(id="second-parent", source_id="second-source")
        connection.execute(effects.insert().values(**second))
        for table in (*t.external_effects.values(), t.events):
            before = list(
                connection.exec_driver_sql(
                    f"SELECT rowid, * FROM {table.name} ORDER BY rowid"
                ).mappings()
            )
            replacement = dict(before[0])
            if table.name == "external_effects":
                replacement.update(id="third-parent", source_id="third-source")
            elif table.name in ("external_effect_actors", "external_effect_resources"):
                replacement["effect_id"] = "second-parent"
            elif table.name == "external_resources":
                replacement["resource_key"] = "discord:channel:999"
            else:
                replacement.update(id="replacement-event", seq=2, command_key="replacement")
            columns = ", ".join(replacement)
            parameters = ", ".join(f":{key}" for key in replacement)
            with pytest.raises(sa.exc.IntegrityError, match="immutable"):
                connection.execute(
                    sa.text(
                        f"INSERT OR REPLACE INTO {table.name} ({columns}) VALUES ({parameters})"
                    ),
                    replacement,
                )
            assert (
                list(
                    connection.exec_driver_sql(
                        f"SELECT rowid, * FROM {table.name} ORDER BY rowid"
                    ).mappings()
                )
                == before
            )
        connection.rollback()
    engine.dispose()


def test_actor_identity_is_unique_independent_of_json_whitespace(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'semantic.db'}"))
    t.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        seed(connection)
        identity = prepare(connection, "test", preparation())
        actors = t.external_effects["actors"]
        original = dict(connection.execute(sa.select(actors)).mappings().one())
        contradictory = dict(original)
        contradictory.update(
            actor_token="forged-token",
            actor_json=json.dumps(json.loads(original["actor_json"]), indent=2),
        )
        with pytest.raises(sa.exc.IntegrityError, match="immutable|token conflicts"):
            connection.execute(actors.insert().values(**contradictory))
        assert prepare(connection, "test", preparation()) == identity
        assert connection.scalar(sa.select(sa.func.count()).select_from(actors)) == 1
        connection.rollback()
    engine.dispose()


def test_legacy_redundant_metadata_is_not_blessed_on_replay(tmp_path: Path) -> None:
    engine = create_database_engine(Settings(database_url=f"sqlite:///{tmp_path / 'metadata.db'}"))
    t.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        seed(connection)
        prepare(connection, "test", preparation())
        # Emulate an unguarded 0017 database, not an authorized production mutation.
        connection.exec_driver_sql("DROP TRIGGER external_effects_no_update")
        effects = t.external_effects["effects"]
        original = dict(connection.execute(sa.select(effects)).mappings().one())
        event = dict(connection.execute(sa.select(t.events)).mappings().one())
        event.update(id="second-event", seq=2, command_key="second-event")
        connection.execute(t.events.insert().values(**event))
        for column, changed in (
            ("event_seq", 2),
            ("operation", "control_post"),
            ("payload_digest", "changed"),
        ):
            with connection.begin_nested() as savepoint:
                connection.execute(effects.update().values({column: changed}))
                with pytest.raises(JournalError, match="metadata is inconsistent"):
                    prepare(connection, "test", preparation())
                savepoint.rollback()
        assert dict(connection.execute(sa.select(effects)).mappings().one()) == original
        connection.rollback()
    engine.dispose()


@pytest.mark.parametrize("schema", ("metadata", "migration"))
def test_multirow_event_replacement_cannot_recycle_source_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    schema: str,
) -> None:
    url = f"sqlite:///{tmp_path / 'multirow.db'}"
    if schema == "migration":
        monkeypatch.setenv("GIRLFRAME_DATABASE_URL", url)
        command.upgrade(Config(str(ROOT / "alembic.ini")), "0018")
    engine = create_database_engine(Settings(database_url=url))
    if schema == "metadata":
        t.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA recursive_triggers=OFF")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        seed(connection)
        identity = prepare(connection, "test", preparation())
        before = list(connection.execute(sa.select(t.events)).mappings())
        # First row conflicts only on the command/index unique key, deleting the
        # referenced seq implicitly. Second row restores that seq with new evidence
        # before SQLite's statement-end FK check. No explicit rowid is supplied.
        replacement = dict(before[0])
        replacement.update(seq=2, id="new-command-slot", payload_json="{}")
        recycled = dict(before[0])
        recycled.update(id="recycled-source", command_key="recycled", payload_json="{}")
        with pytest.raises(sa.exc.IntegrityError, match="immutable"):
            connection.execute(
                t.events.insert().prefix_with("OR REPLACE").values([replacement, recycled])
            )
        assert list(connection.execute(sa.select(t.events)).mappings()) == before
        assert prepare(connection, "test", preparation()) == identity
        connection.rollback()
    engine.dispose()
