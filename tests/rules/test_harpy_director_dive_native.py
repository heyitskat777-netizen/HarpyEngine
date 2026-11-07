"""A real Harpy Dive keeps its frozen Tag table separate from its selected Director."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
from test_cast_service import change
from test_harpy_actor_plays import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_actor_plays import open_actor_play
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_director import enter
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_handler_void import HandlerVoidService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_tag_markers import context
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_director_harpy_native_roll_tags_and_owned_dive_choices_keep_bodies_separate(ledger):
    _, game, cast, actor = ready(ledger, faces=(4, 5), heat=3)
    roles = NpcRoleService(WorldService(MissionService(ledger)))
    offered = roles.offer(
        ADMIN,
        "invite-real-director",
        state(game).revision,
        Npc(
            id="real-dive-director",
            name="Actual Dive Director",
            jobs=("director",),
            detail="An actual separately accepted role",
            controller=3,
            cell=(0, 0),
            revealed=True,
        ),
    )
    roles.respond(OTHER, "accept-real-director", offered["id"], state(game).revision, "accept")
    director = ActorRef(kind="npc", entity="real-dive-director")
    with ledger.transaction() as c:
        canon, event = state(game), str(uuid4())
        canon = enter(canon, 1, director.entity, offered["id"], ("Composed", "Defiant"), event)
        canon.handler_heat = 4
        game.event(
            c,
            1,
            "actual-director-presence",
            "synthetic.actual_director_presence",
            canon,
            event_id=event,
        )
    handler_role = ActorRef(
        kind="handler", entity="1", incarnation=state(game).director_contexts[-1].id
    )
    change(cast, ADMIN, "join", handler_role)
    change(cast, OTHER, "join", director)
    change(cast, OTHER, "adjudicate", director)
    before = state(game)
    pilot = before.sheets["2"].model_dump_json()
    director_pilot = before.sheets["3"].model_dump_json()

    async def start():
        caller = current(2, 99201)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_actor_play(caller, game, actor)
        menu = caller.edit_original_response.call_args.kwargs["view"]
        assert "dive_deep" in dict(menu.options)
        await menu.open_item(caller, "dive_deep")
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and "Actual Dive Director" in form.instructions
        form.values.update(
            context="Actual original Harpy connection",
            identity=("actual-free",),
            gain=("1",),
            heat=("2",),
            confirm=("yes",),
        )
        response = current(2, 99202)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args

    asyncio.run(start())
    tick(GameWorker(game), Gateway(), 3)
    choices = game.choices(PLAYER)
    action_id = choices[0]["action_id"]
    with ledger.engine.connect() as c:
        action = game.action(c, action_id)
    assert action["data"]["dive"]["handler"] == director.model_dump(mode="json")
    assert action["data"]["tag_context"]["handler"] == active_handler(before).model_dump(
        mode="json"
    )
    assert context(action) == action["data"]["tag_context"]
    assert action["data"]["receipt"]["faces"] == [4, 5]
    assert action["data"]["receipt"]["pre_total"] == 11 and game.dice.calls == 1
    forged = copy.deepcopy(action)
    forged["data"]["tag_context"]["actor"] = director.model_dump(mode="json")
    with pytest.raises(WorkflowError, match="frozen Tag context"):
        context(forged)

    async def submit(user, kind, values, identity):
        viewer = {1: ADMIN, 2: PLAYER, 3: OTHER}[user]
        choice = next(x for x in game.choices(viewer) if x["kind"] == kind)
        caller = current(user, identity)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, choice["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        if kind == "dive_effect" and "confirm" in values:
            assert [x.key for x in form.fields] == ["confirm"]
            assert "Handler physiology" in form.instructions
        assert not await form.interaction_check(current(4))
        form.values.update(values)
        response = current(user, identity + 1)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args

    for user in (1, 2, 3):
        asyncio.run(submit(user, "tag_window", {"options": ("pass",)}, 99210 + user * 2))
    asyncio.run(
        submit(
            2,
            "dive_select",
            {
                "option": ("erase_identity_and_table_question",),
                "account": "Actual owned connection",
            },
            99220,
        )
    )
    asyncio.run(
        submit(2, "dive_effect", {"identity": ("actual-free",), "text": "What remains?"}, 99222)
    )
    for human in (ADMIN, PLAYER, OTHER):
        answer(game, human, "dive_table_answer", text="My own actual answer " + str(human.user_id))
    assert not any(x["kind"] == "dive_select" for x in game.choices(ADMIN))
    asyncio.run(
        submit(
            3,
            "dive_select",
            {
                "option": ("nearby_npcs_gain_void",),
                "account": "The actual Director chooses this source consequence",
            },
            99230,
        )
    )
    asyncio.run(submit(3, "dive_effect", {"confirm": ("yes",)}, 99232))
    pending = state(game)
    assert game.inspect(PLAYER, action_id)["state"] == "awaiting_choices"
    assert pending.handler_void[-1].actor == director
    assert pending.handler_void[-1].phase == "choice"
    assert next(x for x in pending.world.npcs if x.id == director.entity).tags == ()
    assert not any(x["kind"] == "dive_handler_void" for x in game.choices(ADMIN))
    asyncio.run(
        submit(
            3,
            "dive_handler_void",
            {
                "choice": ("knife",),
                "site": "Actual left forearm",
                "manifestation": ("none",),
                "account": "The actual Director cuts out her corruption and keeps the wound",
            },
            99234,
        )
    )
    after = state(game)
    assert game.inspect(PLAYER, action_id)["state"] == "complete" and game.dice.calls == 1
    assert after.handler_void[-1].actor == director
    assert after.handler_void[-1].phase == "removed" and after.handler_void[-1].wound
    assert next(x for x in after.world.npcs if x.id == director.entity).tags == ()
    assert after.native_harpies[-1].heat == 2 and after.handler_heat == 4
    assert after.sheets["2"].model_dump_json() == pilot
    assert after.sheets["3"].model_dump_json() == director_pilot
    assert after.order == before.order


def test_director_dive_hides_private_targets_but_retains_every_owned_consequence(
    ledger, monkeypatch
):
    import test_dive_handler_void as source

    original_ready, original_answer = source.ready, source.answer
    hidden = ActorRef(kind="npc", entity="private-uncast-director")
    secret = "PRIVATE_UNCAST_DIRECTOR_NAME"

    def ready_with_hidden_director(store, **kwargs):
        result = original_ready(store, **kwargs)
        _, game, _, _ = result
        roles = NpcRoleService(WorldService(MissionService(store)))
        offered = roles.offer(
            ADMIN,
            "private-director-invite",
            state(game).revision,
            Npc(
                id=hidden.entity,
                name=secret,
                jobs=("director",),
                detail="An accepted original role not revealed to the table",
                controller=PLAYER.user_id,
                cell=(0, 0),
                revealed=False,
            ),
        )
        roles.respond(
            PLAYER, "private-director-accept", offered["id"], state(game).revision, "accept"
        )
        return result

    def native_effect(game, viewer, kind, **values):
        if kind != "dive_effect":
            return original_answer(game, viewer, kind, **values)
        assert viewer == OTHER and viewer.user_id != state(game).handler
        choice = next(x for x in game.choices(viewer) if x["kind"] == kind)
        decision = game.decision(viewer, choice["id"])
        assert decision["dive"]["npcs"] == []
        assert secret not in json.dumps(decision)
        assert hidden.entity not in json.dumps(decision)
        for wrong in (ADMIN, PLAYER):
            with pytest.raises(WorkflowError):
                game.decision(wrong, choice["id"])

        async def confirm():
            caller = current(3, 99400)
            caller.channel_id = 900
            await caller.response.defer(ephemeral=True)
            await open_choice(caller, game, choice["id"])
            form = caller.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm)
            assert [x.key for x in form.fields] == ["confirm"]
            assert secret not in form.text() and hidden.entity not in form.text()
            form.values["confirm"] = ("yes",)
            await form.confirm.callback(current(3, 99401))
            assert form.completed

        return asyncio.run(confirm())

    monkeypatch.setattr(source, "ready", ready_with_hidden_director)
    monkeypatch.setattr(source, "answer", native_effect)
    game, worker, gateway, action, director, _ = source.nearby_director(ledger, harpy=True)
    pending = state(game)
    assert {x.actor for x in pending.handler_void} == {hidden, director}
    assert all(not x.tags for x in pending.world.npcs if x.id in (hidden.entity, director.entity))
    service = HandlerVoidService(ledger, game)
    for target, owner, wrong in ((director, OTHER, PLAYER), (hidden, PLAYER, OTHER)):
        work = next(x.work for x in state(game).handler_void if x.actor == target)
        with pytest.raises(WorkflowError):
            service.get(wrong, work)
        assert game.inspect(PLAYER, action)["state"] == "awaiting_choices"
        service.choose(
            owner,
            "original-removal-" + str(owner.user_id),
            work,
            service.get(owner, work)["revision"],
            "knife",
            "The original Director removes the corruption and retains the actual wound",
            site="Original left forearm",
        )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert all(x.phase == "removed" and x.wound for x in state(game).handler_void)
    tick(worker, gateway, 6)
    assert secret not in json.dumps(gateway.messages)
    assert hidden.entity not in json.dumps(gateway.messages)
