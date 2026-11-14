"""One actual Princess-selected NPC job move, owned performance and private durable readback."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, pass_tags, state, tick
from test_mission_ui import current
from test_princess_sex import setup

from girlframe.database import tables as t
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m3_princess_sex import open_choice, open_princess
from girlframe.engine import m3_princess_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_npc import NARRATIVE
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_princess_npc_play import prove_direction
from girlframe.services.m3_princess_sex import SexService, prove
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    game, worker, gateway, service = setup(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE, "npc.npc.journalist"))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(store)
    npc = ActorRef(kind="npc", entity="original-directed-journalist")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("journalist",),
            controller=1,
            detail="PRIVATE_PRINCESS_NPC_DETAIL",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(CastService(ActorService(missions)), ADMIN, "join", npc)
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "I witness the actual original journalist's ordinary human body and brain",
    )
    with store.transaction() as c:
        actual = state(game)
        actual.sheets["2"].heat = 2
        game.event(c, 1, str(uuid4()), "synthetic.princess_original_heat", actual)
    identity = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE_PRINCESS_NPC_SOURCE Actual voluntary original interaction",
    )["id"]
    service.confirm(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "The original NPC controller explicitly confirms this disclosed source",
        npc_contact_account="Actual original body contact here outside enclosures and rides",
    )
    game.dice = Dice((6, 6))
    original = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        original.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            target_actor=npc,
            heat=1,
            context="Actual confirmed voluntary source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    assert state(game).sheets["2"].heat == original.sheets["2"].heat - 1
    assert rules.get(state(game), identity).tier == "high"
    return game, worker, gateway, service, npc, identity, action


def interaction(viewer):
    result = current(viewer.user_id, uuid4().int % 1000000000)
    result.channel_id = 900
    return result


async def native(game, viewer, row, values):
    opened = interaction(viewer)
    await opened.response.defer(ephemeral=True)
    await open_choice(opened, game, row["id"])
    form = opened.edit_original_response.call_args.kwargs["view"]
    assert not await form.interaction_check(interaction(OTHER))
    form.values.update(values)
    submitted = interaction(viewer)
    await form.confirm.callback(submitted)
    assert form.completed, submitted.edit_original_response.call_args_list
    return form


def test_native_princess_npc_job_direction_actual_controller_performance_and_private_reopen(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service, npc, identity, action = ready(ledger, tmp_path, monkeypatch)
    source = rules.get(state(game), identity)
    receipt = game.inspect(PLAYER, action)["receipt"]
    before = state(game)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "princess_sex_direct")
    detail = game.decision(PLAYER, choice["id"])["princess_sex"]
    assert detail["npc_conversation"] and not detail["unsupported_npc"]
    assert [x["id"] for x in detail["plays"]] == ["journalist"]
    context = " PRIVATE_PRINCESS_NPC_DIRECT Take a candid picture of me here, not a new target "
    for viewer, response in (
        (ADMIN, ChoiceAnswer(options=("journalist",), text=context)),
        (PLAYER, ChoiceAnswer(options=("all_out_assault",), text="Unsupported physical damage")),
        (
            PLAYER,
            ChoiceAnswer(options=("journalist",), fields={"target": "invented"}, text=context),
        ),
    ):
        with pytest.raises(WorkflowError):
            game.respond(viewer, str(uuid4()), choice["id"], choice["revision"], response)
    assert state(game) == before
    form = asyncio.run(native(game, PLAYER, choice, dict(play=("journalist",), text=context)))
    selected = state(game)
    direction = rules.get(selected, identity).npc_direction
    assert direction.author == source.actor and direction.author_controller == 2
    assert direction.actor == npc and direction.controller == 1
    assert direction.move == NARRATIVE["journalist"][0] and direction.context == context
    assert direction.rendition is None and direction.performance_event is None
    assert game.inspect(PLAYER, action)["state"] != "complete"
    perform = next(x for x in game.choices(ADMIN) if x["kind"] == "princess_sex_npc_perform")
    assert any(x.identity == perform["id"] for x in InboxService(ledger).items(ADMIN))
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            perform["id"],
            perform["revision"],
            ChoiceAnswer(options=("perform",), text="Fabricated NPC occurrence"),
        )
    assert state(game) == selected
    rendition = " PRIVATE_PRINCESS_NPC_RENDITION Pat takes the actual directed candid picture. "
    response_form = asyncio.run(native(game, ADMIN, perform, dict(text=rendition)))
    actual = state(game)
    value = rules.get(actual, identity)
    assert value.phase == "complete" and value.npc_direction.rendition == rendition
    assert value.direction is None
    assert value.completed_event == value.npc_direction.performance_event
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert actual.sheets == before.sheets and actual.world == before.world
    assert actual.bonds == before.bonds and npc.entity not in actual.sheets
    assert game.dice.calls == 1 and game.inspect(PLAYER, action)["receipt"] == receipt
    with ledger.engine.connect() as c:
        assert prove_direction(game, c, actual, value) == value.npc_direction
        assert prove(game, c, actual, identity) == value
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(t.m2["m2_actions"])
                .where(
                    t.m2["m2_actions"].c.campaign_id == ledger.campaign_id,
                    t.m2["m2_actions"].c.parent_id == action,
                )
            )
            == 0
        )
    assert "cast" not in service.view(ADMIN, identity)["npc_direction"]
    with pytest.raises(WorkflowError):
        service.view(OTHER, identity)

    async def reopen():
        # The real NPC controller has no Girl sheet, but can recover this owned source.
        opened = interaction(ADMIN)
        await opened.response.defer(ephemeral=True)
        await open_princess(opened, SexService(game))
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["action"] = (identity,)
        selected = interaction(ADMIN)
        await menu.confirm.callback(selected)
        history = selected.edit_original_response.call_args.kwargs["view"]
        content = "".join(x.body for x in history.pages)
        assert clean(context) in content and clean(rendition) in content
        assert not await history.interaction_check(interaction(OTHER))
        snapshot = state(game)
        await form.confirm.callback(interaction(PLAYER))
        await response_form.confirm.callback(interaction(ADMIN))
        assert state(game) == snapshot

    asyncio.run(reopen())
    tick(worker, gateway, 8)
    assert "PRIVATE_PRINCESS_NPC" not in json.dumps(gateway.messages)
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt and game.dice.calls == 1
