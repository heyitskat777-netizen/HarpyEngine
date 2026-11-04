import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import setup_game, state

from girlframe.database import tables as t
from girlframe.services.m3_work import bind_scene_context, related
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def scene(game, channel=900):
    with game.store.engine.connect() as c:
        return game.scene(c, channel)["id"]


def source(game, c, key="synthetic-source"):
    return game.event(c, 2, key, "synthetic.required_decision_source")


def append(store, c, event, **fields):
    parent = dict(campaign_id=store.campaign_id, **fields)
    related(
        c,
        store,
        parent,
        str(uuid4()),
        2,
        2,
        "synthetic_owned_decision",
        {"immediate": False},
        event,
    )


def test_actual_bind_context_is_atomic_original_and_survives_channel_close_rebind(ledger):
    game, *_ = setup_game(ledger)
    original = scene(game)
    with ledger.engine.connect() as c:
        first = dict(c.execute(sa.select(t.m3["m3_scene_contexts"])).mappings().one())
        event = (
            c.execute(sa.select(t.events).where(t.events.c.id == first["binding_event"]))
            .mappings()
            .one()
        )
    assert first["id"] == original and first["channel_id"] == "900"
    assert (
        event["kind"] == "m2.scene_bound"
        and json.loads(event["payload_json"])["scene_id"] == original
    )
    assert game.bind_scene(ADMIN, "bind", 900)["scene"] == original
    game.close_scene(ADMIN, "actual-close", 900)
    game.bind_scene(ADMIN, "actual-rebind", 900)
    with ledger.engine.connect() as c:
        rows = list(c.execute(sa.select(t.m3["m3_scene_contexts"])).mappings())
    assert len(rows) == 2 and dict(next(x for x in rows if x["id"] == original)) == first
    assert scene(game) != original


def test_scene_and_explicit_campaign_work_have_real_sources_and_no_invented_period(ledger):
    game, *_ = setup_game(ledger)
    identity = scene(game)
    with ledger.transaction() as c:
        event = source(game, c)
        append(ledger, c, event, scene_id=identity)
        append(ledger, c, event, campaign_context=True)
    with ledger.engine.connect() as c:
        rows = list(c.execute(sa.select(t.m3["m3_required_work"])).mappings())
    assert len(rows) == 2 and all(x["mission_id"] is x["off_duty_id"] is None for x in rows)
    assert {x["scene_id"] for x in rows} == {None, identity}
    assert sum(x["campaign_context"] for x in rows) == 1


@pytest.mark.parametrize(
    "fields",
    (
        {},
        {"scene_id": "not-real"},
        {"scene_id": "not-real", "campaign_context": True},
        {"mission_id": "not-real"},
        {"off_duty_id": "not-real"},
    ),
)
def test_required_work_rejects_unknown_missing_or_multiple_parent_contexts(ledger, fields):
    game, *_ = setup_game(ledger)
    with pytest.raises(WorkflowError):
        with ledger.transaction() as c:
            event = source(game, c)
            append(ledger, c, event, **fields)
    with ledger.engine.connect() as c:
        assert not c.scalar(sa.select(t.m3["m3_required_work"].c.id))


def test_cross_campaign_event_cannot_back_a_current_campaign_scene_decision(ledger):
    game, *_ = setup_game(ledger)
    identity = scene(game)
    foreign, event = str(uuid4()), str(uuid4())
    with ledger.transaction() as c:
        c.execute(t.campaigns.insert().values(id=foreign, guild_id="999", revision=0))
        c.execute(
            t.events.insert().values(
                campaign_id=foreign,
                seq=1,
                command_key="foreign",
                event_index=0,
                id=event,
                kind="synthetic.source",
                actor_id="2",
                payload_json="{}",
                created_utc="2026-11-04T00:00:00Z",
            )
        )
    with pytest.raises(WorkflowError, match="matching campaign source"):
        with ledger.transaction() as c:
            append(ledger, c, event, scene_id=identity)


@pytest.mark.parametrize("action", ("update", "delete"))
def test_scene_context_and_work_history_are_append_only(ledger, action):
    game, *_ = setup_game(ledger)
    identity = scene(game)
    with ledger.transaction() as c:
        append(ledger, c, source(game, c), scene_id=identity)
    for table in (t.m3["m3_scene_contexts"], t.m3["m3_required_work"]):
        with pytest.raises(IntegrityError, match="append-only"):
            with ledger.transaction() as c:
                operation = (
                    table.delete() if action == "delete" else table.update().values(id="changed")
                )
                c.execute(operation)


def test_pending_scene_work_blocks_close_until_an_actual_typed_resolution_event(ledger):
    game, *_ = setup_game(ledger)
    identity = scene(game)
    with ledger.transaction() as c:
        append(ledger, c, source(game, c), scene_id=identity)
    with pytest.raises(WorkflowError, match="source-bound scene work"):
        game.close_scene(ADMIN, "no-discard-scene", 900)
    with ledger.transaction() as c:
        row = dict(c.execute(sa.select(t.m3["m3_required_work"])).mappings().one())
        event = source(game, c, "synthetic-owned-resolution")
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                revision=2,
                state="resolved",
                event_id=event,
            )
        )
    assert game.close_scene(ADMIN, "no-discard-scene", 900)["closed"]


@pytest.mark.parametrize("channel", (0, -1, 2**64, True, "901"))
def test_scene_registration_rejects_non_snowflake_channel_identity(ledger, channel):
    game, *_ = setup_game(ledger)
    with pytest.raises(WorkflowError, match="actual server text channel"):
        game.bind_scene(ADMIN, str(uuid4()), channel)
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m3["m3_scene_contexts"])) == 1


def test_unrelated_source_event_cannot_register_an_invented_scene_context(ledger):
    game, *_ = setup_game(ledger)
    identity = scene(game)
    with pytest.raises(WorkflowError, match="actual same-campaign bind"):
        with ledger.transaction() as c:
            bind_scene_context(c, ledger, identity, 900, source(game, c))


def test_scene_bind_failure_rolls_back_operational_row_context_event_and_command(
    ledger, monkeypatch
):
    import girlframe.services.m3_work as implementation

    game, *_ = setup_game(ledger)
    original = implementation.bind_scene_context

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic after actual scene index failure")

    monkeypatch.setattr(implementation, "bind_scene_context", fail)
    with pytest.raises(RuntimeError):
        game.bind_scene(ADMIN, "retry-bind-context", 901)
    with ledger.engine.connect() as c:
        assert not c.scalar(
            sa.select(t.m2["m2_scenes"].c.id).where(t.m2["m2_scenes"].c.channel_id == "901")
        )
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m3["m3_scene_contexts"])) == 1
    monkeypatch.setattr(implementation, "bind_scene_context", original)
    assert game.bind_scene(ADMIN, "retry-bind-context", 901)


def test_actual_known_actor_roll_cannot_lose_its_scene_after_staff_restores_chat(ledger):
    from test_actor_play_service import begin, ready
    from test_m2_game import Gateway, tick

    from girlframe.delivery.m2_worker import GameWorker

    svc, game, cast, ref, director = ready(ledger)
    action = begin(svc, ref)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    game.abort(ADMIN, "abort-known-actor-scene", action)
    tick(worker, gateway, 5)
    with pytest.raises(WorkflowError, match="known roll"):
        game.close_scene(ADMIN, "cannot-close-known-actor-scene", 900)
    saved = svc.saved(ADMIN)[0]
    assert svc.recover(ADMIN, "resume-after-rejected-close", action, saved["revision"])[
        "receipt_preserved"
    ]
    assert game.dice.calls == 1


def test_ooc_admin_can_bind_and_close_other_empty_scene_while_playing_handler_girl_rules(ledger):
    from test_actor_play_service import ready

    svc, game, cast, ref, director = ready(ledger)
    before = state(game)
    ledger.safety(OTHER, "pause-ooc-scenes", ledger.status(OTHER)["revision"], pause=True)
    game.bind_scene(ADMIN, "ooc-bind-while-girl", 901)
    game.close_scene(ADMIN, "ooc-close-while-girl", 901)
    assert state(game) == before
    with pytest.raises(WorkflowError):
        game.bind_scene(PLAYER, "not-an-admin", 902)


def test_downgrade_refuses_to_discard_real_scene_or_campaign_work(ledger):
    game, *_ = setup_game(ledger)
    with ledger.transaction() as c:
        append(ledger, c, source(game, c), scene_id=scene(game))
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    with pytest.raises(RuntimeError, match="Refuse to discard"):
        command.downgrade(config, "0013")
    with ledger.engine.connect() as c:
        assert c.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0014"
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m3["m3_required_work"])) == 1


def test_0014_preserves_populated_period_history_and_work_and_backfills_historical_scenes(ledger):
    from test_off_duty_cycle import prepared

    cycle, game, period = prepared(ledger)
    original = scene(game)
    game.close_scene(ADMIN, "historical-close-before-migration", 900)
    game.bind_scene(ADMIN, "historical-rebind-before-migration", 900)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))

    def snapshot():
        with ledger.engine.connect() as c:
            inspector = sa.inspect(c)
            result = {}
            for name in inspector.get_table_names():
                if name in ("alembic_version", "m3_scene_contexts"):
                    continue
                columns = [
                    x["name"]
                    for x in inspector.get_columns(name)
                    if name != "m3_required_work"
                    or x["name"] not in ("scene_id", "campaign_context")
                ]
                projection = ", ".join('"' + x + '"' for x in columns)
                result[name] = sorted(
                    tuple(x)
                    for x in c.execute(sa.text("SELECT " + projection + ' FROM "' + name + '"'))
                )
            return result

    before = snapshot()
    assert before["m3_off_duty"] and before["m3_off_duty_history"] and before["m3_required_work"]
    command.downgrade(config, "0013")
    assert snapshot() == before
    command.upgrade(config, "head")
    command.check(config)
    assert snapshot() == before
    with ledger.engine.connect() as c:
        contexts = list(c.execute(sa.select(t.m3["m3_scene_contexts"])).mappings())
        assert len(contexts) == 2 and original in {x["id"] for x in contexts}
        assert all(
            x["scene_id"] is None and not x["campaign_context"]
            for x in c.execute(sa.select(t.m3["m3_required_work"])).mappings()
        )
        assert c.scalar(sa.text("PRAGMA integrity_check")) == "ok"
        assert not c.execute(sa.text("PRAGMA foreign_key_check")).all()


def test_actual_scene_identity_is_not_inferred_from_current_profile_or_channel_row_on_upgrade(
    ledger,
):
    game, *_ = setup_game(ledger)
    original = scene(game)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.downgrade(config, "0013")
    # Synthetic malformed operational projection: no bind event exists for this ID.
    unknown = str(uuid4())
    with ledger.transaction() as c:
        c.execute(
            t.m2["m2_scenes"]
            .update()
            .where(t.m2["m2_scenes"].c.channel_id == "900")
            .values(id=unknown)
        )
    command.upgrade(config, "head")
    with ledger.engine.connect() as c:
        ids = set(c.scalars(sa.select(t.m3["m3_scene_contexts"].c.id)))
        assert original in ids and unknown not in ids


def test_a_new_revision_cannot_move_a_required_decision_to_another_scene_or_campaign(ledger):
    game, *_ = setup_game(ledger)
    with ledger.transaction() as c:
        event = source(game, c)
        append(ledger, c, event, scene_id=scene(game))
    with pytest.raises(IntegrityError, match="immutable required-work context"):
        with ledger.transaction() as c:
            row = dict(c.execute(sa.select(t.m3["m3_required_work"])).mappings().one())
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "scene_id", "campaign_context")
                    },
                    revision=2,
                    scene_id=None,
                    campaign_context=True,
                )
            )


@pytest.mark.parametrize(
    "fields", ({}, {"scene_id": "unknown"}, {"campaign_context": True, "scene_id": "unknown"})
)
def test_database_context_constraints_do_not_rely_on_the_service_wrapper(ledger, fields):
    game, *_ = setup_game(ledger)
    with pytest.raises(IntegrityError):
        with ledger.transaction() as c:
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    campaign_id=ledger.campaign_id,
                    id=str(uuid4()),
                    revision=1,
                    mission_id=None,
                    off_duty_id=None,
                    owner_id="2",
                    subject_id="2",
                    kind="synthetic",
                    state="pending",
                    body_json="{}",
                    event_id=source(game, c),
                    **fields,
                )
            )


def test_inbox_distinguishes_real_scene_and_campaign_work_from_mission_reactions(ledger):
    from girlframe.services.inbox import InboxService

    game, *_ = setup_game(ledger)
    with ledger.transaction() as c:
        event = source(game, c)
        append(ledger, c, event, scene_id=scene(game))
        append(ledger, c, event, campaign_context=True)
    records = [x for x in InboxService(ledger).items(PLAYER) if x.source == "mission_work"]
    assert {x.category for x in records} == {"plays", "world"}
    assert {x.title for x in records} == {"Required scene work", "Required campaign work"}
    assert all(x.task is None for x in records)
