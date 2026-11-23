"""The higher-ups' actual attack and its owned consequences survive reopening."""

import asyncio
import json

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
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_foundation_attack import RULE, attacks
from girlframe.engine.m3_leviathan_arrival import install_external_pose
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Location
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_foundation_attack import FoundationAttackService
from girlframe.services.m3_handler_consequences import HandlerConsequenceService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


@pytest.mark.parametrize(
    "target,verdict",
    (
        ("base0", "destroyed"),
        ("base0", "averted"),
        ("handler", "strike"),
        ("handler", "withdraw"),
        ("girl:2", "strike"),
        ("girl:2", "averted"),
    ),
)
def test_high_budget_uses_original_pilot_scene_and_actual_outcome(ledger, target, verdict):
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
        if target == "handler":
            canon.facts.append(
                dict(
                    kind="ordinary_handler_movement",
                    actor=current_ref(canon, 1).model_dump_json(),
                    cell=json.dumps((0, 0)),
                    event="fixture-present-handler",
                )
            )
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
        if (target, verdict) == ("girl:2", "strike"):
            frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
            for spare in frames[1:]:
                spare.damaged = True
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

    async def native(viewer, number, *, select=False, task="m3_foundation_attack", **values):
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        if select:
            await open_effect(click, effects, work)
        else:
            entry = next(x for x in inbox.items(viewer) if x.task == task)
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
            attacked_base=(target,),
            foundation_pilot=(actor.entity,),
            account="The higher-ups send the original Pilot against this target.",
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
    if target == "handler":
        original = current_ref(state(game), 1)
        with pytest.raises(WorkflowError, match="original person must join"):
            service.act(controller, "handler-absent", work, revision, 900, "attempt", "Not there")
        change(cast, ADMIN, "join", original)
        revision = state(game).revision
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
    if verdict == "withdraw":
        MovementService(game).move(
            ADMIN,
            "actual-handler-withdrawal",
            before.revision,
            900,
            current_ref(before, 1),
            (1, 0),
            account="The original Handler leaves the attack square.",
        )
        verdict = "averted"
    elif verdict == "averted":
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
    final_values = {}
    if target == "girl:2" and verdict == "strike":
        asset = next(x.id for x in before.sheets["2"].assets if x.family == "frame")
        with pytest.raises(WorkflowError, match="actual target Asset"):
            service.act(ADMIN, "forged-asset", work, revision, 900, "strike", "No", "fake")
        final_values["asset"] = (asset,)
    asyncio.run(native(ADMIN, 41720, choice=(verdict,), account="Final result.", **final_values))
    assert (
        service.act(
            ADMIN,
            "41721",
            work,
            revision,
            900,
            verdict,
            "Final result.",
            (final_values.get("asset") or (None,))[0],
        )["decision"]
        == verdict
    )
    if verdict == "strike":
        saved = attacks(state(game))[0]
        assert saved.strike and saved.resolution is None and len(saved.followups) == 1
        assert effects.get(ADMIN, work)["state"] == "pending"
        with pytest.raises(WorkflowError, match="Strain|immediate sheet work"):
            activate(cycle, game, period)
        with pytest.raises(WorkflowError, match="original strike consequences"):
            service.act(ADMIN, "premature-finish", work, state(game).revision, 900, "finish", "No")
        ledger.engine.dispose()
        if target == "handler":
            body = HandlerConsequenceService(ledger)
            consequence = next(x for x in body.tasks(ADMIN) if x["trigger"] == "asset_damage")
            with pytest.raises(WorkflowError, match="Handler's human"):
                body.get(controller, consequence["id"])
            asyncio.run(
                native(
                    ADMIN,
                    41730,
                    task="m3_handler_consequence",
                    choice=("injury",),
                    account="The original body bears the actual injury.",
                )
            )
            assert state(game).handler_injuries[-1].actor == saved.target
        else:
            assert next(x for x in state(game).sheets["2"].assets if x.id == asset).damaged
            game.dice.faces = (4, 4)
            action = game.begin(
                PLAYER,
                "actual-foundation-defeat",
                900,
                state(game).sheets["2"].revision,
                PlayInput(
                    play="defeat",
                    heat=0,
                    source_work=saved.followups[0],
                    context="Forced out of the cockpit",
                    trigger_confirmed=True,
                ),
            )["action_id"]
            worker, gateway = GameWorker(game), Gateway()
            tick(worker, gateway, 3)
            pass_tags(game)
            answer(game, controller, "tag_window", options=("pass",))
            answer(
                game,
                PLAYER,
                "defeat_select",
                options=("escape_cockpit_choose_location",),
                text="The original Girl actually escapes her cockpit.",
            )
            assert game.inspect(PLAYER, action)["state"] == "complete"
            tick(worker, gateway, 5)
        asyncio.run(native(ADMIN, 41740, choice=("finish",), account="Verify the actual result."))
    canon = state(game)
    result = "struck" if verdict == "strike" else verdict
    assert attacks(canon)[0].result == result and effects.get(ADMIN, work)["state"] == "resolved"
    location = next(x for x in canon.world.locations if x.id == "base0")
    assert location.condition == ("destroyed" if verdict == "destroyed" else "intact")
    assert any(
        x.entity == "base0" and x.kind == "structure_destroyed" for x in canon.strain.triggers
    ) == (verdict == "destroyed")
    assert activate(cycle, game, period)["phase"] == "active"
