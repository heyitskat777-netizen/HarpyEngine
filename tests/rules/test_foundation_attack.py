"""The original higher-up attack changes the actual base only after resolution."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_physical_operations import place
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_foundation_attack import RULE, attacks
from girlframe.engine.m3_leviathan_arrival import install_external_pose
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Location
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_foundation_attack import FoundationAttackService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


@pytest.mark.parametrize("verdict", ("destroyed", "averted"))
def test_high_budget_uses_original_pilot_scene_and_actual_base_outcome(ledger, verdict):
    strain, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "plays"})
            )
        )
    )
    controller = GuildViewer(4, 200, True, False)
    ledger.join(controller, "original-foundation-controller")
    actor = ActorRef(kind="external_pilot", entity="the-foundation-pilot")
    pilot = AdversaryPilot(
        id=actor.entity,
        name="Foundation Pilot",
        kind="foundation",
        girl="MOCKINGBIRD",
        frame="JANUS",
        controller=4,
        cell=(0, 0),
        revealed=True,
        assets=(
            Asset(
                id="pilot-frame-asset", name="Frame Asset", description="Synthetic", family="frame"
            ),
        ),
    )
    with ledger.transaction() as c:
        canon = state(game)
        world = initial()
        canon.world = world.model_copy(
            update=dict(
                pilots=(pilot,),
                locations=world.locations
                + (Location(id="secondary-base", name="Secondary Base", cell=(3, 1), kind="base"),),
            )
        )
        canon = place(place(canon, 2), 3, cell=(2, 1))
        canon = install_external_pose(
            canon,
            actor,
            (0, 0),
            (0, 0),
            "piloting",
            "founder-pose",
            "The actual Foundation Pilot occupies their active cockpit.",
            owner=4,
            judge=1,
        )
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "setup-higher-ups-attack", "synthetic.setup", canon)
    cast = CastService(ActorService(strain.missions))
    change(cast, controller, "join", actor)
    period = prepared(strain, game, high=frozenset({"budget"}))
    effects = EffectService(strain)
    for track, face, column, choice in (
        (
            "void",
            2,
            1,
            Choice(
                rule_id="strain.void.low.2.1",
                account="Dormant Gorgon arrives.",
                gorgon=gorgon("dormant", "unrelated-new-gorgon", (0, 1)),
            ),
        ),
        ("rebellion", 1, 2, Choice(rule_id="strain.rebellion.low.1.2", account="Control slips.")),
        ("budget", 5, 2, None),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "actual-foundation-roll-" + track, request.id, 1, state(game).revision)
        selected = strain.choose(
            ADMIN, "actual-foundation-column-" + track, request.id, 2, state(game).revision, column
        )
        work = request.id + ":effect"
        if choice:
            effects.apply(ADMIN, "setup-unrelated-" + track, work, 1, state(game).revision, choice)
    assert selected["rule_id"] == RULE
    inbox = InboxService(ledger)

    async def native(viewer, number, *, select=False, **values):
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        if select:
            await open_effect(click, effects, work)
        else:
            entry = next(x for x in inbox.items(viewer) if x.task == "m3_foundation_attack")
            await InboxView(inbox, viewer.user_id).route(click, entry)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submit = current(viewer.user_id, number + 1)
        await form.confirm.callback(submit)
        assert form.completed, submit.followup.send.call_args

    asyncio.run(
        native(
            ADMIN,
            41700,
            select=True,
            attacked_base=("base0",),
            foundation_pilot=(actor.entity,),
            account="The higher-ups send the original Pilot for the base.",
        )
    )
    service = FoundationAttackService(strain)
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="Strain"):
        activate(cycle, game, period)
    assert not any(x.task == "m3_foundation_attack" for x in inbox.items(PLAYER))
    with pytest.raises(WorkflowError, match="actual participants"):
        service.get(OTHER, work)
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="original piloting actor"):
        service.act(ADMIN, "original-owner-only", work, revision, 900, "attempt", "Wrong owner")
    with pytest.raises(WorkflowError, match="actual base scene"):
        service.act(controller, "wrong-scene", work, revision, 901, "attempt", "Wrong scene")
    ledger.safety(PLAYER, "pause-foundation", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.act(
            controller, "paused-foundation", work, revision, 900, "attempt", "Actual attempt"
        )
    ledger.safety(PLAYER, "resume-foundation", ledger.status(PLAYER)["revision"], pause=False)
    asyncio.run(native(controller, 41710, choice=("attempt",), account="WITNESSED_ATTEMPT"))
    assert service.get(PLAYER, work)["account"] == "WITNESSED_ATTEMPT"
    with pytest.raises(WorkflowError, match="actual participants"):
        service.get(OTHER, work)
    with pytest.raises(WorkflowError, match="human referee"):
        service.act(controller, "actor-cannot-rule", work, state(game).revision, 900, verdict, "No")
    ledger.engine.dispose()
    with pytest.raises(WorkflowError, match="actual original interception"):
        service.act(
            ADMIN,
            "no-fictional-defense",
            work,
            state(game).revision,
            900,
            "averted",
            "False interception",
        )
    before = state(game)
    assert next(x for x in before.world.locations if x.id == "base0").condition == "intact"
    if verdict == "averted":
        asset = next(x.id for x in before.sheets["2"].assets if x.family == "frame")
        game.dice.faces = (4, 5)
        action = game.begin(
            PLAYER,
            "actual-foundation-counter",
            900,
            before.sheets["2"].revision,
            PlayInput(
                play="engage",
                heat=0,
                target_actor=actor,
                context="Drive the attacker back",
                trigger_confirmed=True,
                piloting=True,
            ),
        )["action_id"]
        worker, gateway = GameWorker(game), Gateway()
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, controller, "tag_window", options=("pass",))
        answer(
            game,
            PLAYER,
            "engage_maneuvers",
            options=("drive_back", "protect"),
            fields={"drive_back": asset, "protect": asset},
            text="The attacker retreats from the base.",
        )
        assert game.inspect(PLAYER, action)["state"] == "complete"
        tick(worker, gateway, 5)
        with pytest.raises(WorkflowError, match="interception averted"):
            service.act(
                ADMIN,
                "ignore-real-interception",
                work,
                state(game).revision,
                900,
                "destroyed",
                "No",
            )
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.act(ADMIN, "stale-foundation", work, revision - 1, 900, verdict, "Final result.")
    asyncio.run(native(ADMIN, 41720, choice=(verdict,), account="Final result."))
    assert (
        service.act(ADMIN, "41721", work, revision, 900, verdict, "Final result.")["decision"]
        == verdict
    )
    canon = state(game)
    assert attacks(canon)[0].result == verdict and effects.get(ADMIN, work)["state"] == "resolved"
    location = next(x for x in canon.world.locations if x.id == "base0")
    assert location.condition == ("destroyed" if verdict == "destroyed" else "intact")
    assert any(
        x.entity == "base0" and x.kind == "structure_destroyed" for x in canon.strain.triggers
    ) == (verdict == "destroyed")
    assert activate(cycle, game, period)["phase"] == "active"
