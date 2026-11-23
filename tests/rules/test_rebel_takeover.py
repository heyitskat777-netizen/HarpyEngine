"""A new rival group takes the original Rebel body and applies the printed Broken effect."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_alpha import status
from girlframe.engine.m3_leviathan_arrival import install_external_pose
from girlframe.engine.m3_rebel_takeover import RULE, takeovers
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_rebel_takeover import TakeoverService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def test_rebel_takeover_requires_original_custody_and_broken(ledger):
    strain, game = ready(ledger, face=6)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "plays"}),
            )
        )
    )
    captor_controller = GuildViewer(4, 200, True, False)
    ledger.join(captor_controller, "new-rebel-controller")
    world = initial()
    worlds = WorldService(strain.missions)
    worlds.initialize(
        ADMIN,
        "takeover-world",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    group = Faction(id="old-group", name="Old Rebel Group", kind="rebel", cells=((0, 4),))
    worlds.faction(ADMIN, "original-group", state(game).revision, group)
    original = ActorRef(kind="external_pilot", entity="takeover-pilot")
    pilot = AdversaryPilot(
        id=original.entity,
        name="Original Pilot",
        kind="rebel",
        girl="MOCKINGBIRD",
        frame="JANUS",
        assets=(
            Asset(
                id="original-frame-equipment",
                name="Old hardware",
                description="Synthetic",
                family="frame",
            ),
        ),
        controller=3,
        faction=group.id,
        cell=(0, 0),
        revealed=True,
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(canon.world, pilots=(pilot,))
        canon = install_external_pose(
            canon,
            original,
            (0, 0),
            (1, 1),
            "outside_frame",
            "original-captive-position",
            "The Pilot is on foot.",
            owner=3,
            judge=1,
        )
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "takeover-original-pilot", "synthetic.original_rebel", canon)
    cast = CastService(ActorService(strain.missions))
    change(cast, OTHER, "join", original)
    period = prepared(strain, game, high=frozenset({"rebellion"}))
    index = 0
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "rebellion" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, f"takeover-roll-{index}", request.id, 1, state(game).revision)
        strain.choose(ADMIN, f"takeover-cascade-{index}", request.id, 2, state(game).revision, 2)
        index += 1
    selected = strain.choose(
        ADMIN,
        "takeover-slot",
        request.id,
        1,
        state(game).revision,
        8,
        endgame=True,
        faction=group.id,
    )
    assert selected["rule_id"] == RULE
    work = request.id + ":effect"
    effects = EffectService(strain)
    for index, request in enumerate(tuple(state(game).strain.requests)):
        if request.track == "void":
            face, column, choice = (
                2,
                1,
                Choice(
                    rule_id="strain.void.low.2.1",
                    account="Unrelated arrival.",
                    gorgon=gorgon("dormant", "takeover-other-gorgon", (0, 1)),
                ),
            )
        elif request.track == "rebellion":
            face, column, choice = (
                1,
                2,
                Choice(rule_id="strain.rebellion.low.1.2", account="Control slips."),
            )
        else:
            face, column, choice = (
                5,
                2,
                Choice(rule_id="strain.budget.low.5.2", account="Unrelated room.", rooms=((2, 3),)),
            )
        strain.dice.face = face
        strain.roll(ADMIN, f"takeover-other-roll-{index}", request.id, 1, state(game).revision)
        strain.choose(
            ADMIN, f"takeover-other-column-{index}", request.id, 2, state(game).revision, column
        )
        effects.apply(
            ADMIN,
            f"takeover-other-effect-{index}",
            request.id + ":effect",
            1,
            state(game).revision,
            choice,
        )
    inbox = InboxService(ledger)

    async def native(viewer, number, **values):
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        cards = [
            x for x in inbox.items(viewer) if x.identity == work and x.task == "m3_rebel_takeover"
        ]
        assert len(cards) == 1
        await InboxView(inbox, viewer.user_id).route(click, cards[0])
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm), click.edit_original_response.call_args
        form.values.update(values)
        submitted = current(viewer.user_id, number + 1)
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.edit_original_response.call_args,
            submitted.followup.send.call_args,
        )

    service = TakeoverService(strain)
    cycle = CycleService(strain.periods)
    asyncio.run(
        native(
            ADMIN, 44200, name="New Group", description="They are far better organized.", cell="0,0"
        )
    )
    (record,) = takeovers(state(game))
    assert record.pilots == (original,) and not record.completed
    assert next(x for x in state(game).world.factions if x.id == group.id).active
    with pytest.raises(WorkflowError, match="actual Strain|work"):
        activate(cycle, game, period)
    with pytest.raises(WorkflowError, match="actual original participants"):
        service.get(PLAYER, work, 900)
    captor = ActorRef(kind="npc", entity="new-captor")
    roles = NpcRoleService(worlds)
    offer = roles.offer(
        ADMIN,
        "takeover-captor-offer",
        state(game).revision,
        Npc(
            id=captor.entity,
            name="New Rebel guard",
            cell=(0, 0),
            controller=4,
            jobs=("guard",),
            detail="Original participant from the new group",
            faction=record.replacement.id,
            revealed=True,
        ),
    )
    roles.respond(
        captor_controller, "takeover-captor-accept", offer["id"], state(game).revision, "accept"
    )
    assert not service.get(captor_controller, work, 900)["choices"]
    change(cast, captor_controller, "join", captor)
    (capture,) = service.get(captor_controller, work, 900)["choices"]
    with pytest.raises(WorkflowError, match="actual new rebel"):
        service.resolve(
            ADMIN, "will-not-speak-for-captor", work, state(game).revision, 900, capture[0], "No"
        )
    asyncio.run(
        native(captor_controller, 44210, choice=(capture[0],), account="I seize the real Pilot.")
    )
    after_capture = state(game)
    assert (
        after_capture.world.pilots[0].custody == "captured"
        and after_capture.world.pilots[0].assets == pilot.assets
    )
    assert not after_capture.alpha_broken and not takeovers(after_capture)[0].completed
    with pytest.raises(WorkflowError, match="actual Strain|work"):
        activate(cycle, game, period)
    assert (
        service.get(OTHER, work, 900)["captured"] == 1
        and service.get(OTHER, work, 900)["total"] is None
    )
    ledger.engine.dispose()
    (broken,) = service.get(captor_controller, work, 900)["choices"]
    ledger.safety(PLAYER, "pause-takeover", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.resolve(
            captor_controller, "paused-takeover", work, state(game).revision, 900, broken[0], "No"
        )
    ledger.safety(PLAYER, "resume-takeover", ledger.status(PLAYER)["revision"], pause=False)
    revision = state(game).revision
    asyncio.run(
        native(
            captor_controller,
            44220,
            choice=(broken[0],),
            account="The original captive is Broken against me.",
        )
    )
    assert service.resolve(
        captor_controller,
        "44221",
        work,
        revision,
        900,
        broken[0],
        "The original captive is Broken against me.",
    )["complete"]
    canon = state(game)
    (case,) = takeovers(canon)
    assert case.prisoners[0].actor == original and case.completed
    assert not next(x for x in canon.world.factions if x.id == group.id).active
    assert status(canon, captor, original) is True and status(canon, original, captor) is False
    assert canon.alpha_broken[-1].source_work == work
    assert activate(cycle, game, period)["phase"] == "active"
