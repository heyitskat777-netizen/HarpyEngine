"""A present city permits the genuine Show Dog new-NPC choice without travel fiction."""

import asyncio
from uuid import uuid4

import pytest
import test_show_dog as existing
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import call

from girlframe.discord_adapter.m3_show_dog import open_show_dog
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_native_show_dog_introduces_one_present_city_npc_and_keeps_source(
    ledger, tmp_path, monkeypatch
):
    original_world = existing.initial()
    # Synthetic pre-existing geography: the known physical position is a city, not a base.
    city_world = original_world.model_copy(
        update={
            "locations": tuple(
                x.model_copy(update={"cell": (2, 4) if x.id == "base0" else (0, 0)})
                if x.id in ("base0", "city1")
                else x
                for x in original_world.locations
            )
        }
    )
    monkeypatch.setattr(existing, "initial", lambda: city_world)
    game, cycle, period, action, controls, identity = existing.setup(
        ledger, tmp_path, monkeypatch, (6, 6)
    )
    call(cycle, game, PLAYER, period, "scene", "nearby_city", (2, 3), "Actual city appearance")
    before = state(game)
    receipt = game.inspect(PLAYER, action)
    menu = controls.menu(PLAYER, identity)
    assert [x["id"] for x in menu["locations"]] == ["city1"]
    world = WorldService(MissionService(ledger))
    with pytest.raises(WorkflowError, match="present permitted"):
        world.npc(
            PLAYER,
            str(uuid4()),
            before.revision,
            Npc(
                id="remote",
                name="Remote civilian",
                controller=2,
                jobs=("civilian",),
                cell=(0, 4),
                detail="Remote civilian",
            ),
            show_dog=identity,
        )
    assert state(game) == before

    async def introduce():
        opened = current(2, 99451)
        await opened.response.defer(ephemeral=True)
        await open_show_dog(opened, controls, identity)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["action"] = ("create",)
        selected = current(2, 99452)
        await form.confirm.callback(selected)
        creation = selected.edit_original_response.call_args.kwargs["view"]
        creation.values.update(
            name="Actual city spectator", detail="PRIVATE_CITY_DETAIL", location=("city1",)
        )
        response = current(2, 99453)
        await creation.confirm.callback(response)
        assert creation.completed, response.edit_original_response.call_args_list

    asyncio.run(introduce())
    after = state(game)
    created = after.world.npcs[-1]
    assert created.cell == (0, 0) and created.controller == PLAYER.user_id
    assert len(after.world.npcs) == len(before.world.npcs) + 1
    assert after.placements == before.placements
    assert game.inspect(PLAYER, action) == receipt
    replay = world.npc(PLAYER, "99453", before.revision, created, show_dog=identity)
    assert replay["id"] == created.id and state(game) == after
    with pytest.raises(WorkflowError, match="at most one"):
        world.npc(
            PLAYER,
            str(uuid4()),
            after.revision,
            created.model_copy(update={"id": "second"}),
            show_dog=identity,
        )
    existing.second(controls, identity, ActorRef(kind="npc", entity=created.id), "emulate")
    existing.first(controls, PLAYER, identity, "quiet", account="I smile and obey")
    assert controls.view(PLAYER, identity)["complete"]
