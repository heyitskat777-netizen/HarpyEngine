"""Low Rebellion opens a private next-mission attack using the original Rebel's resources."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_physical_operations import place
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_battle import open_context
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import IdentityState
from girlframe.engine.m3_actor_resources import rebel_inventory
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_leviathan_arrival import install_external_pose
from girlframe.engine.m3_rebel_ambush import RULE, ambushes
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_rebel_ambush import AmbushService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError


def test_actual_rebel_ambush_costs_its_own_heat_and_only_the_next_dispatched_mission(ledger):
    strain, game = ready(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": policy.model_copy(
                update={"subsystems": policy.subsystems | {"plays", "world"}}
            )
        }
    )
    actor = ActorRef(kind="external_pilot", entity="ambush-origin")
    weapon = Asset(
        id="source-launcher",
        name="Net Launcher",
        description="Synthetic capture capability",
        family="frame",
    )
    spare = Asset(
        id="source-shield",
        name="Shield",
        description="Synthetic defense capability",
        family="frame",
    )
    faction = Faction(id="friendly-rebel-cell", kind="rebel", name="Local Cell", cells=((0, 0),))
    rebel = AdversaryPilot(
        id=actor.entity,
        kind="rebel",
        name="Genuine Rebel",
        girl="MOCKINGBIRD",
        frame="JANUS",
        assets=(weapon, spare),
        faction=faction.id,
        cell=(0, 0),
        controller=3,
        revealed=True,
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial().model_copy(update=dict(pilots=(rebel,), factions=(faction,)))
        canon = place(place(canon, 2), 3)
        canon = install_external_pose(
            canon,
            actor,
            (0, 0),
            (0, 0),
            "piloting",
            "fixture-ambush-pose",
            "Actual Rebel cockpit",
            owner=3,
            judge=1,
        )
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "ambush-original-pose", "synthetic.original_rebel_roster", canon)
    actors = ActorService(strain.missions)
    actors.confirm_rebel_inventory(
        OTHER,
        "ambush-actual-pool",
        state(game).revision,
        actor,
        (IdentityState(id="independent-identity", name="Driven", slot=1),),
        2,
        "My original Rebel's own Heat and Identity",
        actual=True,
    )
    period = prepared(strain, game)
    effects = EffectService(strain)
    for track, face, column, choice in (
        (
            "void",
            2,
            1,
            Choice(
                rule_id="strain.void.low.2.1",
                account="New Gorgon at the base perimeter.",
                gorgon=gorgon("dormant", "ambush-near-base", (0, 1)),
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="Rooms reassigned.", rooms=((2, 3),)),
        ),
        ("rebellion", 5, 1, None),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "ambush-die-" + track, request.id, 1, state(game).revision)
        outcome = strain.choose(
            ADMIN, "ambush-column-" + track, request.id, 2, state(game).revision, column
        )
        identity = request.id + ":effect"
        if choice is not None:
            effects.apply(
                ADMIN, "ambush-effect-" + track, identity, 1, state(game).revision, choice
            )
    assert outcome["rule_id"] == RULE

    async def native_form(viewer, sid, display, **values):
        click = current(viewer.user_id, sid)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await display(click)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm), click.edit_original_response.call_args
        form.values.update(values)
        submitted = current(viewer.user_id, sid + 1)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.edit_original_response.call_args,
            submitted.followup.send.call_args,
        )

    asyncio.run(
        native_form(
            ADMIN,
            40400,
            lambda click: open_effect(click, effects, identity),
            ambusher=(actor.entity,),
            account="PRIVATE_AMBUSH_SOURCE",
        )
    )
    assert ambushes(state(game))[0].mission is None
    cycle = CycleService(strain.periods)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    missions = strain.missions
    invitation = missions.offer(
        ADMIN, "first-actual-ambush-mission", "Transport a synthetic cargo", (2,)
    )
    assert ambushes(state(game))[0].mission is None
    accepted = missions.respond(
        PLAYER, "accept-ambush-mission", invitation["id"], invitation["revision"], "accept"
    )
    mission = missions.start(
        ADMIN, "dispatch-ambush-mission", invitation["id"], accepted["revision"]
    )
    (bound,) = ambushes(state(game))
    assert bound.mission == mission["id"] and bound.dispatch
    with pytest.raises(WorkflowError, match="Complete the actual Rebel ambush"):
        missions.end(ADMIN, "premature-mission", mission["id"], mission["revision"], True)
    inbox = InboxService(ledger)
    assert not any(x.task == "m3_rebel_ambush" for x in inbox.items(PLAYER))
    service = AmbushService(game)
    with pytest.raises(WorkflowError, match="original Rebel and Handler"):
        service.get(PLAYER, identity, 900)
    cast = CastService(actors)
    change(cast, OTHER, "join", actor)
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="actual mission cast"):
        service.open(OTHER, "not-a-mission-target", identity, revision, 900, "3", "Invalid attempt")
    with pytest.raises(WorkflowError, match="Only the original Rebel"):
        service.open(ADMIN, "admin-cannot-open", identity, revision, 900, "2", "Invalid speaker")
    ledger.safety(PLAYER, "pause-ambush", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.open(
            OTHER, "paused-ambush", identity, revision, 900, "2", "Actual original attempt"
        )
    ledger.safety(PLAYER, "resume-ambush", ledger.status(PLAYER)["revision"], pause=False)

    async def inbox_open(click):
        entry = next(x for x in inbox.items(OTHER) if x.task == "m3_rebel_ambush")
        await InboxView(inbox, 3).route(click, entry)

    asyncio.run(
        native_form(OTHER, 40410, inbox_open, target=("2",), account="Actual original attempt")
    )
    assert service.open(OTHER, "40411", identity, revision, 900, "2", "Actual original attempt")[
        "opened"
    ]
    ledger.engine.dispose()
    fight = BattleService(ledger)
    data = fight.preview(OTHER, 900)
    fighter = next(x for x in data["actors"] if x["ref"]["entity"] == actor.entity)
    chased = next(x for x in data["actors"] if x["ref"]["entity"] == "2")
    asset = next(x.id for x in state(game).sheets["2"].assets if x.family == "frame")
    declaration = Declaration(
        play="all_out_assault",
        actor=actor,
        target=ActorRef.model_validate(chased["ref"]),
        attacking_asset=weapon.id,
        target_asset=asset,
        actor_sha256=fighter["sha256"],
        target_sha256=chased["sha256"],
        account="I flank the transport, aiming to capture the Girl.",
    )
    offered = fight.propose(OTHER, "ambush-assault-declaration", data["revision"], 900, declaration)
    fight.confirm(
        ADMIN,
        "ambush-assault-confirmed",
        state(game).revision,
        offered["id"],
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="Actual close-range ambush",
    )
    old_other = state(game).sheets["3"].model_copy(deep=True)
    worker, gateway = GameWorker(game), Gateway()
    game.dice.faces = (4, 4)
    asyncio.run(
        native_form(
            OTHER,
            40420,
            lambda click: open_context(click, fight, offered["id"]),
            identity=("none",),
            gain=("0",),
            pair_share=("0",),
            heat=("1",),
        )
    )
    tick(worker, gateway, 3)
    pass_tags(game)
    for member in (ADMIN, PLAYER, OTHER):
        answer(game, member, "battle_assault_table", flag=False, text="Original table view")
    (completed_attack,) = ambushes(state(game))
    assert completed_attack.action and completed_attack.completed is None
    assert game.inspect(OTHER, completed_attack.action)["state"] == "complete"
    canon = state(game)
    assert next(x for x in canon.sheets["2"].assets if x.id == asset).damaged
    assert canon.sheets["3"] == old_other
    assert rebel_inventory(canon, actor).heat == 1
    tick(worker, gateway, 5)
    missions.end(ADMIN, "actual-ambush-outcome", mission["id"], mission["revision"], True)
    assert ambushes(state(game))[0].completed
    next_offer = missions.offer(ADMIN, "second-ambush-test-mission", "Separate mission", (2,))
    assert next_offer["id"] != ambushes(state(game))[0].mission
