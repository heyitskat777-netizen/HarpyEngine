"""Saved High Void area freezes actual bodies and their ordinary consequences."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_physical_operations import place
from test_strain_void_spread import strain_source

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_void_spread import applications
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_void import HandlerVoidService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_void import VoidService
from girlframe.services.m3_void_spread import SpreadService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def footprint(ledger, *, threshold=False):
    strain, game, _, period, identity = strain_source(ledger, 2)
    world = WorldService(strain.missions)
    world.npc(
        ADMIN,
        "void-npc",
        state(game).revision,
        Npc(
            id="inside-npc",
            name="Original occupant",
            jobs=("civilian",),
            controller=1,
            detail="Actually inside at the source",
            cell=(0, 1),
        ),
    )
    roles = NpcRoleService(world)
    offered = roles.offer(
        ADMIN,
        "void-director",
        state(game).revision,
        Npc(
            id="inside-director",
            name="Actual Director",
            jobs=("director",),
            controller=OTHER.user_id,
            detail="Original Controller plays the Director",
            cell=(0, 0),
        ),
    )
    roles.respond(OTHER, "accept-void-director", offered["id"], state(game).revision, "accept")
    harpy = ActorRef(kind="external_pilot", entity="inside-harpy")
    with ledger.transaction() as connection:
        canon = state(game)
        canon.world = update(
            canon.world,
            pilots=(
                *canon.world.pilots,
                AdversaryPilot(
                    id=harpy.entity,
                    name="Original Harpy",
                    kind="harpy",
                    girl="HARPY",
                    frame="Original",
                    controller=OTHER.user_id,
                    cell=(4, 0),
                    assets=(
                        Asset(
                            id="harpy-possession",
                            name="Original Claw",
                            family="girl",
                            description="Uncorrupted",
                            void=False,
                        ),
                    ),
                ),
            ),
        )
        sheet = canon.sheets["2"]
        for asset in sheet.assets:
            asset.void = False
        if threshold:
            frame = [x for x in sheet.assets if x.family == "frame"]
            sheet.assets = [x for x in sheet.assets if x.family != "frame"] + frame[:1]
        canon = place(canon, 2, mode="piloting" if threshold else "outside_frame", cell=(0, 0))
        canon = place(canon, 3, mode="outside_frame", cell=(4, 0))
        handler = active_handler(canon)
        canon.facts.append(
            dict(
                kind="ordinary_handler_movement",
                actor=handler.model_dump_json(),
                cell="[0,1]",
                event="synthetic-position",
            )
        )
        game.event(connection, ADMIN.user_id, "spatial-fixture", "synthetic.positions", canon)
    setup = HarpyDefeatService(ledger, game)
    request = setup.propose_runtime(
        OTHER,
        "area-harpy-body",
        state(game).revision,
        NativeHarpyFacts(
            actor=harpy,
            linked=False,
            girl_cell=(0, 1),
            frame_cell=(4, 0),
            heat=0,
            frame_shutdown=False,
            body_incapacitated=False,
            custody="free",
            identities=(HarpyIdentity(id="original-free", name="Free", marked=True),),
            tags=(),
            account="The actual Harpy is outside her Frame.",
            facts_confirmed=True,
        ),
    )
    setup.review_setup(
        ADMIN,
        "verify-area-harpy",
        request["id"],
        state(game).revision,
        True,
        "Its actual body is present.",
    )
    effects = EffectService(strain)
    for track, face in (("rebellion", 1), ("budget", 5)):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "die-" + track, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + track, request.id, 2, state(game).revision, 2)
        effects.apply(
            ADMIN,
            "resolve-" + track,
            request.id + ":effect",
            1,
            state(game).revision,
            Choice(
                rule_id=f"strain.{track}.low.{face}.2",
                account="Actual other event.",
                rooms=((2, 3),) if track == "budget" else (),
            ),
        )
    strain.dice.face = 1
    effects.prepare_spread(ADMIN, "area-dice", identity, 1, state(game).revision)
    effects.prepare_spread(
        ADMIN, "set-area", identity, 2, state(game).revision, cells=((0, 0), (0, 1))
    )
    return strain, game, period, identity, effects


def native(ledger, viewer, number, item, values, *, root=None):
    async def run():
        click = current(viewer.user_id, number)
        await click.response.defer(ephemeral=True)
        if root:
            await open_effect(click, root, item)
        else:
            inbox = InboxService(ledger)
            entry = next(
                x
                for x in inbox.items(viewer)
                if x.identity == item and x.task == "m3_void_spread_gain"
            )
            await InboxView(inbox, viewer.user_id).route(click, entry)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    asyncio.run(run())


@pytest.mark.parametrize("threshold", (False, True), ids=("ordinary", "full-frame"))
def test_area_applies_normal_girl_npc_and_handler_void_to_original_occupants(ledger, threshold):
    strain, game, period, identity, effects = footprint(ledger, threshold=threshold)
    # The NPC moves after the scope snapshot. Her original exposure still applies.
    with ledger.transaction() as connection:
        current_state = state(game)
        current_state.world = update(
            current_state.world,
            npcs=tuple(
                npc.model_copy(update={"cell": (4, 0)}) if npc.id == "inside-npc" else npc
                for npc in current_state.world.npcs
            ),
        )
        game.event(
            connection, ADMIN.user_id, "later-npc-pose", "synthetic.later_position", current_state
        )
    revision = state(game).revision
    native(ledger, ADMIN, 84000, identity, dict(apply=("yes",)), root=effects)
    service = SpreadService(strain)
    assert (
        SpreadService(strain).start(ADMIN, "84001", identity, revision, 3, (), "")["required"] == 5
    )
    (record,) = applications(state(game))
    people = {x.actor.entity: x for x in record.occupants}
    assert set(people) == {"1", "2", "inside-npc", "inside-director", "inside-harpy"}
    assert people["inside-npc"].cell == (0, 1)
    assert {
        x.identity for x in InboxService(ledger).items(OTHER) if x.task == "m3_void_spread_gain"
    } == {people["inside-harpy"].work}
    with pytest.raises(WorkflowError, match="original occupant"):
        service.get(OTHER, people["2"].work)
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="Resolve actual Strain"):
        activate(cycle, game, period)

    work = people["2"].work
    asset = (
        next(x.id for x in state(game).sheets["2"].assets if x.family == "frame")
        if threshold
        else service.get(PLAYER, work)["assets"][0][0]
    )
    revision = state(game).revision
    ledger.safety(OTHER, "pause-spread", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.gain(PLAYER, "paused-gain", work, revision, asset, "My ordinary alteration")
    ledger.safety(OTHER, "resume-spread", ledger.status(OTHER)["revision"], pause=False)
    native(ledger, PLAYER, 84010, work, dict(pick=(asset,), account="My ordinary alteration"))
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset).void
    npc_work = people["inside-npc"].work
    native(ledger, ADMIN, 84020, npc_work, dict(pick=("bones",), account="Her hands warp."))
    assert (
        next(x for x in state(game).world.npcs if x.id == "inside-npc").tags[0].label
        == "Void of the bones"
    )
    native(
        ledger,
        OTHER,
        84030,
        people["inside-harpy"].work,
        dict(pick=("harpy-possession",), account="The original claw becomes Void."),
    )
    harpy_state = state(game)
    assert next(x for x in harpy_state.world.pilots if x.id == "inside-harpy").assets[0].void
    actual_harpy = next(x for x in harpy_state.native_harpies if x.id == "inside-harpy")
    assert actual_harpy.identities[0].marked and actual_harpy.frame_cell == (4, 0)
    for viewer, person in ((ADMIN, people["1"]), (OTHER, people["inside-director"])):
        handler_void = HandlerVoidService(ledger)
        assert any(
            x.identity == person.work and x.task == "handler_void"
            for x in InboxService(ledger).items(viewer)
        )
        handler_void.choose(
            viewer,
            "remove-" + person.work,
            person.work,
            state(game).revision,
            "knife",
            "I cut the growth out.",
            site="My hand",
        )
    assert {x.phase for x in state(game).handler_void} == {"removed"}
    if threshold:
        required = work + ":frame"
        assert effects.get(ADMIN, identity)["state"] == "pending"
        assert VoidService(ledger).get(PLAYER, required)["stage"] == "resist_pending"
        worker, gateway = GameWorker(game), Gateway()
        game.dice.faces = (1, 1)
        action = game.begin(
            PLAYER,
            "resist-area",
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                source_work=required,
                heat=state(game).sheets["2"].heat,
                context="Resist the full Frame alteration",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, PLAYER, "actor_keep", options=("in_control",))
        answer(game, ADMIN, "handler_keep", flag=True, text="The original resistance succeeds.")
        tick(worker, gateway, 4)
        assert game.inspect(PLAYER, action)["state"] == "complete"
        assert VoidService(ledger).get(PLAYER, required)["stage"] == "prevented"
    assert effects.get(ADMIN, identity)["state"] == "resolved"
    assert activate(cycle, game, period)["phase"] == "active"
