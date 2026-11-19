"""The Bond's scene or the actual Off-Duty deadline determines defection."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, finish_routine, recover_both
from test_strain_void_spread import strain_source

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import DependentForm
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_rebel_defection import cases
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_rebel_defection import DefectionService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("stays", (False, True), ids=("defects", "addressed-in-scene"))
def test_original_bond_defects_only_at_actual_period_end_with_private_delivery(ledger, stays):
    strain, game, _, period, identity = strain_source(ledger, 6, "rebellion", column=2, high=False)
    effects = EffectService(strain)
    world = WorldService(strain.missions)
    roles = NpcRoleService(world)
    bond = state(game).sheets["2"].review.creation.npc_bonds[0]
    bonded_npc = Npc(
        id="contacted",
        name=bond.name or "Original Bond",
        jobs=("mechanic",),
        detail="Fixture NPC private biography",
        controller=OTHER.user_id,
        cell=(4, 0),
        revealed=True,
    )
    offered = roles.offer(ADMIN, "original-offer", state(game).revision, bonded_npc)
    roles.respond(OTHER, "original-accept", offered["id"], state(game).revision, "accept")
    world.import_starting_npc(
        PLAYER, "original-bond", state(game).revision, bond.slot, bonded_npc.id
    )
    world.faction(
        ADMIN,
        "rebel-group",
        state(game).revision,
        Faction(id="group", name="River Group", kind="rebel", cells=((1, 2),)),
    )
    rebel = Npc(
        id="recipient",
        name="Contact at the River",
        jobs=("civilian",),
        detail="Only the original recipient gets the factual report.",
        faction="group",
        controller=PLAYER.user_id,
        cell=(1, 2),
    )
    offered = roles.offer(ADMIN, "rebel-offer", state(game).revision, rebel)
    roles.respond(PLAYER, "rebel-accept", offered["id"], state(game).revision, "accept")

    for track, face, column, choice in (
        (
            "void",
            5,
            1,
            Choice(
                rule_id="strain.void.high.5.1",
                account="The Handler states the impending risk.",
                revelation_play="reveal_near_disaster",
                revelation_channel=900,
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="Shared quarters.", rooms=((2, 3),)),
        ),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "die-" + track, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + track, request.id, 2, state(game).revision, column)
        effects.apply(
            ADMIN, "resolve-" + track, request.id + ":effect", 1, state(game).revision, choice
        )

    async def route(viewer, number, task):
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(viewer) if x.identity == identity and x.task == task)
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(click, item)
        return click.edit_original_response.call_args.kwargs

    async def contact():
        form = (await route(ADMIN, 85900, "m3_strain_effect"))["view"]
        assert isinstance(form, DependentForm)
        form.values.update(
            defection_npc=(bonded_npc.id,),
            defection_faction=("group",),
            defection_contact=(rebel.id,),
            account="PRIVATE_REBEL_INVITATION",
        )
        await form.confirm.callback(current(ADMIN.user_id, 85901))
        assert form.completed

    asyncio.run(contact())
    service = DefectionService(strain)
    assert service.get(OTHER, identity)["account"] == "PRIVATE_REBEL_INVITATION"
    for viewer in (PLAYER, ADMIN):
        with pytest.raises(WorkflowError, match="eventual Rebel recipient"):
            service.get(viewer, identity)
    assert effects.get(ADMIN, identity)["state"] == "resolved"
    cycle = CycleService(strain.periods)
    assert activate(cycle, game, period)["phase"] == "active"
    if stays:
        with pytest.raises(WorkflowError, match="actual NPC and an original Bond"):
            service.stay(OTHER, "without-bond-scene", identity, state(game).revision, 900, "Stays.")
        casts = CastService(ActorService(strain.missions))
        original = ActorRef(kind="npc", entity=bonded_npc.id)
        change(casts, OTHER, "join", original)

        async def choose_stay():
            form = (await route(OTHER, 85910, "m3_rebel_defection"))["view"]
            assert isinstance(form, NativeForm)
            form.values["account"] = "After talking to her Bond, the mechanic decides to stay."
            await form.confirm.callback(current(OTHER.user_id, 85911))
            assert form.completed

        asyncio.run(choose_stay())
        change(casts, OTHER, "withdraw", original)

    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    before = state(game)
    original_state = next(x for x in before.world.npcs if x.id == bonded_npc.id)
    assert original_state.faction is None and before.strain.levels["rebellion"] == "low"
    revision = cycle.review(ADMIN, period)["revision"]
    receipt = cycle.finish(ADMIN, "complete-period", period, revision, before.revision)
    assert cycle.finish(ADMIN, "complete-period", period, revision, before.revision) == receipt
    assert receipt["phase"] == "complete"
    after = state(game)
    (case,) = cases(after)
    final_npc = next(x for x in after.world.npcs if x.id == bonded_npc.id)
    assert after.strain.events == before.strain.events
    if stays:
        assert case.outcome == "stayed" and case.stay_scene and case.report_event is None
        assert final_npc == original_state and after.strain.levels["rebellion"] == "low"
        with pytest.raises(WorkflowError, match="eventual Rebel recipient"):
            service.get(PLAYER, identity)
    else:
        assert case.outcome == "defected" and case.report_event == case.resolved_event
        assert final_npc.faction == "group" and after.strain.levels["rebellion"] == "high"
        report = asyncio.run(route(PLAYER, 85920, "m3_rebel_defection"))["content"]
        assert final_npc.name in report and "mechanic" in report and "(4, 0)" in report
        assert "PRIVATE_REBEL_INVITATION" not in report
        with pytest.raises(WorkflowError, match="eventual Rebel recipient"):
            service.get(ADMIN, identity)
