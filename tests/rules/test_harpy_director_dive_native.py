"""A real Harpy Dive keeps its frozen Tag table separate from its selected Director."""

import asyncio
import copy
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
    asyncio.run(submit(3, "dive_effect", {"npc_0": ("brain",)}, 99232))
    after = state(game)
    assert game.inspect(PLAYER, action_id)["state"] == "complete" and game.dice.calls == 1
    assert after.native_harpies[-1].heat == 2 and after.handler_heat == 4
    assert after.sheets["2"].model_dump_json() == pilot
    assert after.sheets["3"].model_dump_json() == director_pilot
    assert after.order == before.order
