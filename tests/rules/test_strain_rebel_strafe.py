"""Low Rebellion resolves only after the owning Rebel's actual physical pass."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_void_spread import strain_source

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_rebel_strafe import RULE, passes
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_rebel_strafe import StrafeService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_rebel_strafe_verifies_cockpit_and_owned_physical_movement(ledger):
    strain, game, _, period, work = strain_source(ledger, 2, "rebellion", column=1, high=False)
    effects = EffectService(strain)
    assert effects.get(ADMIN, work)["rule_id"] == RULE
    world = WorldService(strain.missions)
    world.faction(
        ADMIN,
        "rebel-faction",
        state(game).revision,
        Faction(id="field-group", name="Field Group", kind="rebel", cells=((0, -1),)),
    )
    pilot = AdversaryPilot(
        id="strafing-original",
        name="Original Rebel",
        kind="rebel",
        girl="MOCKINGBIRD",
        frame="JANUS",
        controller=OTHER.user_id,
        faction="field-group",
        cell=(0, -1),
        assets=(
            Asset(id="launcher", name="Launcher", description="Fires", family="frame"),
            Asset(id="jacket", name="Jacket", description="Old", family="girl"),
        ),
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(canon.world, pilots=(pilot,))
        game.event(c, ADMIN.user_id, "existing-roster", "synthetic.rebel_roster", canon)
    for track, face, column, choice in (
        (
            "void",
            5,
            1,
            Choice(
                rule_id="strain.void.high.5.1",
                account="The Handler reveals what is happening.",
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

    async def native(viewer, number, task, **values):
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(viewer) if x.identity == work and x.task == task)
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        confirmation = current(viewer.user_id, number + 1)
        await form.confirm.callback(confirmation)
        assert form.completed, confirmation.edit_original_response.call_args

    asyncio.run(
        native(
            ADMIN,
            88200,
            "m3_strain_effect",
            strafe_pilot=(pilot.id,),
            strafe_base=("base0",),
            account="There is a pass near the base.",
        )
    )
    (case,) = passes(state(game))
    assert case.base == "base0" and case.controller == OTHER.user_id
    assert effects.get(ADMIN, work)["state"] == "pending"
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="Resolve actual Strain"):
        activate(cycle, game, period)
    service = StrafeService(strain)
    for viewer in (ADMIN, PLAYER):
        with pytest.raises(WorkflowError, match="original"):
            service.act(viewer, "not-owner", work, state(game).revision, "propose", "False.")
    assert not any(x.task == "m3_rebel_strafe" for x in InboxService(ledger).items(PLAYER))
    asyncio.run(
        native(OTHER, 88210, "m3_rebel_strafe", account="I am in my Frame beside the base.")
    )
    assert not state(game).external_poses
    asyncio.run(native(ADMIN, 88220, "m3_rebel_strafe", account="I confirm the original cockpit."))
    assert service.get(OTHER, work)["mode"] == "perform"
    assert effects.get(ADMIN, work)["state"] == "pending"
    scene = CastService(ActorService(strain.missions))
    change(scene, OTHER, "join", case.actor)
    before = state(game)
    with pytest.raises(WorkflowError, match="functional original Frame Asset"):
        service.act(
            OTHER,
            "wrong-asset",
            work,
            before.revision,
            "perform",
            "Strafing.",
            channel=900,
            destination=(1, 0),
            asset="jacket",
        )
    account = "The Frame fires while crossing the base perimeter."
    asyncio.run(
        native(
            OTHER,
            88230,
            "m3_rebel_strafe",
            account=account,
            destination=("1,0",),
            asset=("launcher",),
        )
    )
    result = service.act(
        OTHER,
        "88231",
        work,
        before.revision,
        "perform",
        account,
        channel=900,
        destination=(1, 0),
        asset="launcher",
    )
    assert result["state"] == "resolved"
    after = state(game)
    (receipt,) = passes(after)
    assert receipt.origin == (0, -1) and receipt.destination == (1, 0)
    assert (
        receipt.pose_event
        and receipt.pose_review
        and receipt.performance
        and receipt.asset == "launcher"
    )
    actual = resolve(after, case.actor, ())
    assert actual.cell == actual.frame_cell == (1, 0) and actual.piloting
    assert after.strain.events == before.strain.events
    assert after.world.locations == before.world.locations and after.sheets == before.sheets
    assert activate(cycle, game, period)["phase"] == "active"
