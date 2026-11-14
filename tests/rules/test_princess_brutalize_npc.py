"""Princess-owned Alpha actions retain actual NPC consequences and Guard agency."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcement_initiative import cast_target
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick
from test_mission_ui import current
from test_princess_brutalize import ready
from test_princess_oldgen_advice import pass_directed
from test_princess_sex import _directed_native, _prepare_directed_native, roll

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_guard import GuardService
from girlframe.services.m3_princess_sex import _direction
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def directed_guard(store, tmp_path, monkeypatch, faces):
    game, worker, gateway, service = ready(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(princess.RULE, alpha.RULE, "npc.npc.guard"))
    npc = ActorRef(kind="npc", entity="princess-directed-actual-guard")
    WorldService(MissionService(store)).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Actual directed Guard",
            jobs=("guard",),
            detail="PRIVATE_DIRECTED_NPC_DETAIL",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    cast_target(game, npc)
    guard = GuardService(game)
    assessment = guard.assess(
        ADMIN,
        str(uuid4()),
        900,
        npc,
        current_ref(state(game), 3),
        state(game).revision,
        True,
        "I reviewed this actual Guard's body and possessions; they carry no weapon",
    )["id"]
    identity, parent = roll(game, worker, gateway, service, (6, 6), native=True)
    pass_directed(game)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "princess_sex_direct")
    detail = game.decision(PLAYER, choice["id"])["princess_sex"]
    assert any(
        x["ref"] == npc.model_dump(mode="json") and "brutalize" in x["plays"]
        for x in detail["targets"]
    )
    direction = _directed_native(game, identity, "brutalize", target=npc)
    original = state(game)
    game.dice = Dice(faces)
    child = _prepare_directed_native(game, service, identity, heat=("1",), gain=("0",), identity=())
    assert child is not None
    tick(worker, gateway, 3)
    pass_directed(game)
    with store.engine.connect() as connection:
        actual = game.action(connection, child)
        assert actual["actor_id"] == "3" and actual["parent_id"] == parent
        assert actual["data"]["alpha"]["actor_controller"] == 3
        assert actual["data"]["alpha"]["target"] == npc.model_dump(mode="json")
        assert actual["data"]["alpha"]["target_controller"] == 1
        assert actual["data"]["alpha"]["npc_assessment"] == assessment
        assert actual["data"]["princess_child"]["author"] == 2
    assert state(game).sheets["3"].heat == original.sheets["3"].heat - 1
    assert state(game).sheets["2"].heat == original.sheets["2"].heat
    return game, worker, gateway, service, guard, npc, identity, parent, direction.id, child


def native(game, viewer, kind, **values):
    async def run():
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        opened = current(viewer.user_id, int(uuid4().int % 1000000000))
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        submitted = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(run())


def assert_complete(game, worker, gateway, service, identity, parent, direction_id, child):
    final = state(game)
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert service.view(PLAYER, identity)["phase"] == "complete"
    with game.store.engine.connect() as connection:
        direction = _direction(game, connection, final, direction_id)
        event = (
            connection.execute(
                sa.select(t.events).where(t.events.c.id == direction.completed_event)
            )
            .mappings()
            .one()
        )
        assert event["kind"] == "m3.princess_directed_brutalize_completed"
        assert event["actor_id"] == "2"
    receipt = game.inspect(PLAYER, child)["receipt"]
    before = state(game)
    assert game.roll(PLAYER, str(uuid4()), child)["receipt"] == receipt
    assert state(game) == before and game.dice.calls == 1
    tick(worker, gateway, 8)
    with game.store.engine.connect() as connection:
        assert game.lock(connection, 900)["state"] == "released"
    assert "PRIVATE_DIRECTED" not in json.dumps(gateway.messages)


@pytest.mark.parametrize("faces,killed", [((4, 4), False), ((6, 6), True)])
def test_native_directed_brutalize_npc_injury_or_death_uses_original_alpha(
    ledger, tmp_path, monkeypatch, faces, killed
):
    game, worker, gateway, service, _, npc, identity, parent, direction_id, child = directed_guard(
        ledger, tmp_path, monkeypatch, faces
    )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_npc_damage")
    assert row["actor_id"] == "3"
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    assert not any(x["id"] == row["id"] for x in game.choices(OTHER))
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("kill",) if killed else ("injure",), text="Not my decision"),
        )
    native(
        game, PLAYER, "alpha_npc_damage", **({} if killed else {"injury": "Actual torn shoulder"})
    )
    final = state(game)
    actual = next(x for x in final.world.npcs if x.id == npc.entity)
    assert actual.alive is not killed
    if killed:
        assert not any(x.actor == npc for cast in final.scene_casts for x in cast.roles)
    else:
        injury = actual.tags[-1]
        assert injury.label == "Actual torn shoulder"
        assert ActorRef.model_validate_json(injury.giver_entity) == current_ref(final, 3)
        assert alpha.conditions(final, npc, current_ref(final, 3))
        assert not alpha.conditions(final, npc, current_ref(final, 2))
    assert_complete(game, worker, gateway, service, identity, parent, direction_id, child)


def test_native_directed_brutalize_npc_low_keeps_guard_counter_and_alpha_mercy_separate(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service, guard, npc, identity, parent, direction_id, child = (
        directed_guard(ledger, tmp_path, monkeypatch, (1, 1))
    )
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "alpha_low")
    assert not any(x["id"] == row["id"] for x in game.choices(PLAYER))
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("pass",))
        )
    answer(game, ADMIN, "alpha_low", options=("counter_broken",))
    counter = next(x for x in game.choices(ADMIN) if x["kind"] == "alpha_counter_play")
    with pytest.raises(WorkflowError):
        guard.counter(PLAYER, child, counter["id"])
    assert not alpha.conditions(state(game), current_ref(state(game), 3), npc)
    assert princess.direction(state(game), direction_id).completed_event is None
    native(
        game,
        ADMIN,
        "alpha_counter_play",
        move=("interpose",),
        account="This actual Guard steps into the Alpha's way, not the Princess's",
    )
    actual = state(game)
    assert alpha.conditions(actual, current_ref(actual, 3), npc)
    assert not alpha.conditions(actual, current_ref(actual, 2), npc)
    assert next(x for x in actual.world.npcs if x.id == npc.entity).alive
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert princess.direction(actual, direction_id).completed_event is None
    mercy = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_npc_mercy")
    assert mercy["actor_id"] == "3"
    assert not any(x["id"] == mercy["id"] for x in game.choices(OTHER))
    native(game, PLAYER, "alpha_npc_mercy", choice=("spare",))
    assert next(x for x in state(game).world.npcs if x.id == npc.entity).alive
    assert_complete(game, worker, gateway, service, identity, parent, direction_id, child)
