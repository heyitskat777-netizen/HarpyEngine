"""One genuine four-Limiter progression ends PC authority without replacing the person."""

import asyncio
from uuid import uuid4

import pytest
from test_am_scrutinized import rolled
from test_enforcement_initiative import cast_target
from test_items import carried_asset
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine import m3_am as am
from girlframe.engine import m3_am_reset as reset
from girlframe.engine.m2 import PilotSheet, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle import assets
from girlframe.engine.m3_careers import profile_character
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_am_reset import FactoryResetService
from girlframe.services.m3_items import prove_item
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_four_low_progression_native_reset_same_person_hardware_and_source_completion(
    ledger, tmp_path, monkeypatch
):
    game, service, npc, identity, root, action, worker, gateway = rolled(
        ledger, tmp_path, monkeypatch, (1, 1)
    )
    original = current_ref(state(game), 2)
    physical = next(x for x in state(game).placements if x.actor == original)
    original_assets = tuple(state(game).sheets["2"].assets)
    item = None
    for index, (freedom, _) in enumerate(am.FREEDOMS):
        current_state = state(game)
        selected = am.identities(current_state, original)[0]
        answer(
            game,
            ADMIN,
            "am_limiter",
            options=(selected.id,),
            fields={"freedom": freedom},
            text="The actual discoverer installs this real default-slot Limiter",
        )
        if index == 3:
            break
        assert game.inspect(PLAYER, action)["state"] == "complete"
        tick(worker, gateway, 5)
        if index == 0:
            carried_asset(game, PLAYER, next(x for x in original_assets if x.family == "girl"))
            item = state(game).held_items[-1]
        world = WorldService(MissionService(ledger))
        npc = ActorRef(kind="npc", entity="actual-next-am-discoverer-" + str(index))
        world.npc(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            Npc(
                id=npc.entity,
                name="New actual discoverer " + str(index),
                controller=1,
                jobs=("guard",),
                cell=(0, 0),
                revealed=True,
                detail="A different actual ordinary NPC newly recognizes the adjustment",
            ),
        )
        cast_target(game, npc)
        identity = service.propose(
            PLAYER,
            str(uuid4()),
            900,
            npc,
            state(game).revision,
            "This different actual NPC newly realizes the adjustment",
        )["id"]
        root = service.confirm(
            ADMIN,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            True,
            True,
            "My own NPC's genuine new realization",
        )["action_id"]
        tick(worker, gateway, 3)
        remaining = am.identities(state(game), original)
        prep = dict(gain=1, identity=remaining[0].id, heat=1) if index == 0 else dict(heat=0)
        action = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play=am.PLAY,
                parent=root,
                source_work=identity,
                target_actor=npc,
                context="I react to this actual distinct new discovery",
                trigger_confirmed=True,
                **prep,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
    before_reset = state(game)
    assert len(am.limiters(before_reset, original)) == 4 and game.dice.calls == 4
    assert any(x.marked for x in before_reset.sheets["2"].identities)
    assert game.inspect(PLAYER, action)["state"] != "complete"
    pending = next(x for x in game.choices(ADMIN) if x["kind"] == "am_factory_reset")
    native = FactoryResetService(game)
    data = native.get(ADMIN, identity)
    with pytest.raises(WorkflowError):
        native.get(PLAYER, identity)

    async def finish():
        interaction = current(1, 903001)
        interaction.channel_id = 999
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, pending["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and "<#900>" in form.instructions
        form.values.update(
            job=("ex_pilot",), account="I take the reset original as this actual Ex-Pilot NPC"
        )
        await form.confirm.callback(current(1, 903002))
        assert form.completed

    asyncio.run(finish())
    actual = state(game)
    value = reset.records(actual)[0]
    saved = next(x for x in actual.career_archives if x.id == value.archive)
    old = PilotSheet.model_validate_json(saved.sheet_json)
    assert saved.ending == "factory_reset" and saved.actor == original
    assert "2" not in actual.sheets and 2 not in actual.order
    assert tuple(old.identities) == tuple(before_reset.sheets["2"].identities)
    actor = resolve(actual, value.actor, ())
    assert actor.rules == "npc" and actor.controller == 1 and actor.heat is None
    assert actor.vessel_id == physical.vessel_id and actor.cell == physical.girl_cell
    assert actor.inside_frame is False and {x.id for x in actor.identities} == {
        x.id for x in old.identities
    }
    assert {x.id for x in assets(actual, value.actor, ())} == {
        x.id for x in original_assets if x.family == "girl"
    }
    parked = next(x for x in actual.parked_frames if x.owner == original)
    assert parked.frame_instance == physical.frame_instance and parked.cell == physical.frame_cell
    assert PilotSheet.model_validate_json(parked.frame_json).assets == old.assets
    assert item is not None
    moved = next(x for x in actual.held_items if x.id == item.id)
    assert moved.holder == value.actor and moved.asset_owner == value.actor
    assert (
        moved.source_owner == item.source_owner
        and moved.origin_asset_json == item.origin_asset_json
    )
    with ledger.engine.connect() as c:
        assert prove_item(c, game, actual, item.id) == moved
    with pytest.raises(ValueError, match="CAREER_ENDED"):
        profile_character(actual, 2, saved.profile_id, saved.profile_revision)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert game.dice.calls == 4 and len(reset.records(actual)) == 1
    with pytest.raises(WorkflowError):
        native.complete(
            ADMIN, str(uuid4()), identity, data["revision"], "ex_pilot", "No second NPC"
        )
