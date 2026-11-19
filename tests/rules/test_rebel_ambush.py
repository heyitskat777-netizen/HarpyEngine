"""Low Rebellion opens a private next-mission attack using the original Rebel's resources."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_physical_operations import place
from test_punishment_service import submit as submit_punishment
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_battle import open_context, open_declaration
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import IdentityState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_resources import rebel_inventory
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_leviathan_arrival import install_external_pose
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_rebel_ambush import HUNT_RULE, RULE, SIEGE_RULE, ambushes, hunts, sieges
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_consequences import HandlerConsequenceService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_rebel_ambush import AmbushService, HuntService, SiegeService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize(
    "rule,introduce,target_handler",
    (
        (RULE, False, False),
        (HUNT_RULE, False, False),
        (SIEGE_RULE, False, False),
        (SIEGE_RULE, True, False),
        (SIEGE_RULE, False, True),
    ),
)
def test_actual_rebel_attacks_use_original_roles(ledger, rule, introduce, target_handler):
    pursuit, siege = rule == HUNT_RULE, rule == SIEGE_RULE
    target_id = "1" if target_handler else "2"
    strain, game = ready(ledger)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": policy.model_copy(
                update={"subsystems": policy.subsystems | {"plays", "world", "discipline"}}
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
    second_actor = ActorRef(kind="external_pilot", entity="second-siege-original")
    second_weapon = weapon.model_copy(update=dict(id="second-source-launcher"))
    second_rebel = rebel.model_copy(
        update=dict(id=second_actor.entity, name="Second Rebel", assets=(second_weapon, spare))
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial().model_copy(
            update=dict(
                pilots=() if introduce else (rebel, second_rebel) if siege else (rebel,),
                factions=() if introduce else (faction,),
            )
        )
        canon = place(place(canon, 2), 3)
        if not introduce:
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
        if siege:
            if not introduce:
                canon = install_external_pose(
                    canon,
                    second_actor,
                    (0, 0),
                    (0, 0),
                    "piloting",
                    "fixture-second-siege-pose",
                    "Second original Rebel cockpit",
                    owner=3,
                    judge=1,
                )
        if target_handler:
            canon.facts.append(
                dict(
                    kind="ordinary_handler_movement",
                    actor=current_ref(canon, 1).model_dump_json(),
                    cell=json.dumps((0, 0)),
                    event="fixture-present-handler",
                )
            )
        if siege and not target_handler:
            reserve = next(x for x in canon.sheets["2"].assets if x.family == "frame")
            for index in range(2 if introduce else 1):
                canon.sheets["2"].assets.append(
                    reserve.model_copy(
                        update=dict(id=f"ace-reserve-frame-asset-{index}", name="Reserve Plate")
                    )
                )
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "ambush-original-pose", "synthetic.original_rebel_roster", canon)
    actors = ActorService(strain.missions)
    if not introduce:
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
        if siege:
            actors.confirm_rebel_inventory(
                OTHER,
                "second-siege-actual-pool",
                state(game).revision,
                second_actor,
                (),
                2,
                "I confirm the second independently controlled Rebel's Heat",
                actual=True,
            )
    period = prepared(strain, game, high=frozenset({"rebellion"}) if rule != RULE else frozenset())
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
        ("rebellion", 1 if siege else 4 if pursuit else 5, 1, None),
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
    assert outcome["rule_id"] == rule

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

    recruits = {}
    if introduce:
        recruits.update(siege_group_name="Three original Rebels", siege_group_site=("city0",))
        for i in range(1, 4):
            recruits.update(
                {
                    f"siege_{i}_name": f"Original Siege Rebel {i}",
                    f"siege_{i}_controller": ("3",),
                    f"siege_{i}_frame": "JANUS",
                    f"siege_{i}_asset": f"Operable Asset {i}",
                }
            )
    asyncio.run(
        native_form(
            ADMIN,
            40400,
            lambda click: open_effect(click, effects, identity),
            account="PRIVATE_AMBUSH_SOURCE",
            **({"siege_base": ("base0",)} if siege else {"ambusher": (actor.entity,)}),
            **({"siege_target": ("handler",)} if target_handler else {}),
            **({"hunt_victim": ("2",)} if pursuit else {}),
            **recruits,
        )
    )
    assert not any(x.mission for x in ambushes(state(game)))
    cycle = CycleService(strain.periods)
    missions = strain.missions
    if siege:
        with pytest.raises(WorkflowError, match="Strain"):
            activate(cycle, game, period)
        (plan,) = sieges(state(game))
        assert plan.target.entity == target_id
        assert plan.target.kind == ("handler" if target_handler else "pilot")
        if introduce:
            actor, second_actor, third_actor = plan.attackers
            bodies = {x.id: x for x in state(game).world.pilots}
            assert len(bodies) == 3 and len({x.faction for x in bodies.values()}) == 1
            assert all(not x.revealed for x in bodies.values())
            weapon = bodies[actor.entity].assets[0]
            second_weapon = bodies[second_actor.entity].assets[0]
            third_weapon = bodies[third_actor.entity].assets[0]
            siege_inbox = InboxService(ledger)
            for number, recruit in enumerate(plan.attackers):
                case = next(x for x in ambushes(state(game)) if x.attacker == recruit)
                assert case.introduced and not rebel_inventory(state(game), recruit)

                async def confirm_recruit(click, case=case):
                    entry = next(x for x in siege_inbox.items(OTHER) if x.identity == case.id)
                    await InboxView(siege_inbox, 3).route(click, entry)

                asyncio.run(
                    native_form(
                        OTHER,
                        40500 + number * 2,
                        confirm_recruit,
                        identities="Defiant",
                        heat="2",
                        account="Original piloting confirmed",
                    )
                )
                inventory = rebel_inventory(state(game), recruit)
                assert inventory is not None and inventory.heat == 2
        else:
            assert plan.attackers == (actor, second_actor)
        with pytest.raises(WorkflowError, match="every original Rebel attack"):
            SiegeService(strain).finish(ADMIN, "premature-siege", identity, state(game).revision)
    else:
        activate(cycle, game, period)
        recover_both(cycle, game, period)
        finish_routine(cycle, game, period)
        assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
        invitation = missions.offer(
            ADMIN, "first-actual-ambush-mission", "Transport a synthetic cargo", (2,)
        )
        assert not any(x.mission for x in ambushes(state(game)))
        accepted = missions.respond(
            PLAYER, "accept-ambush-mission", invitation["id"], invitation["revision"], "accept"
        )
        mission = missions.start(
            ADMIN, "dispatch-ambush-mission", invitation["id"], accepted["revision"]
        )
    bound = next(x for x in ambushes(state(game)) if x.attacker == actor)
    root = identity
    identity = bound.id
    if siege:
        assert bound.siege == root and bound.mission is None
    else:
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
    if target_handler:
        assert service.get(OTHER, identity, 900)["targets"] == ()
        change(cast, ADMIN, "join", plan.target)
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="actual (mission|base) cast"):
        service.open(OTHER, "not-a-mission-target", identity, revision, 900, "3", "Invalid attempt")
    with pytest.raises(WorkflowError, match="Only the original Rebel"):
        service.open(ADMIN, "admin-cannot-open", identity, revision, 900, "2", "Invalid speaker")
    ledger.safety(PLAYER, "pause-ambush", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.open(
            OTHER, "paused-ambush", identity, revision, 900, target_id, "Actual original attempt"
        )
    ledger.safety(PLAYER, "resume-ambush", ledger.status(PLAYER)["revision"], pause=False)

    async def inbox_open(click):
        entry = next(
            x for x in inbox.items(OTHER) if x.task == "m3_rebel_ambush" and x.identity == identity
        )
        await InboxView(inbox, 3).route(click, entry)

    asyncio.run(
        native_form(
            OTHER, 40410, inbox_open, target=(target_id,), account="Actual original attempt"
        )
    )
    assert service.open(
        OTHER, "40411", identity, revision, 900, target_id, "Actual original attempt"
    )["opened"]
    ledger.engine.dispose()
    asset = next(x.id for x in state(game).sheets["2"].assets if x.family == "frame")
    worker, gateway = GameWorker(game), Gateway()
    old_other = state(game).sheets["3"].model_copy(deep=True)

    def assault(number, target_asset, *, vast, assailant=actor, attacking_asset=weapon.id):
        fight = BattleService(ledger)
        data = fight.preview(OTHER, 900)
        fighter = next(x for x in data["actors"] if x["ref"]["entity"] == assailant.entity)
        chased = next(x for x in data["actors"] if x["ref"]["entity"] == target_id)
        account = (
            "I close on the original Handler in the occupied base."
            if target_handler
            else "I flank the transport, aiming to capture the Girl."
        )
        declaration = Declaration(
            play="all_out_assault",
            actor=assailant,
            target=ActorRef.model_validate(chased["ref"]),
            attacking_asset=attacking_asset,
            target_asset=target_asset,
            actor_sha256=fighter["sha256"],
            target_sha256=chased["sha256"],
            account=account,
        )
        proposal_key = f"ambush-declaration-{number}"
        if target_handler:
            sequence = 10_000 + number
            proposal_key = str(sequence + 2)

            async def native_declaration():
                click = current(OTHER.user_id, sequence)
                click.channel_id = 900
                await click.response.defer(ephemeral=True)
                await open_declaration(click, fight)
                form = click.edit_original_response.call_args.kwargs["view"]
                form.values.update(
                    actor=(assailant.token,),
                    target=(chased["token"],),
                    play=("all_out_assault",),
                )
                choose = current(OTHER.user_id, sequence + 1)
                choose.channel_id = 900
                await choose.response.defer(ephemeral=True)
                await form.confirm.callback(choose)
                confirm = choose.edit_original_response.call_args.kwargs["view"]
                assert isinstance(confirm, NativeForm)
                assert "target_asset" not in {f.key for f in confirm.fields}
                confirm.values.update(asset=(attacking_asset,), account=account)
                sent = current(OTHER.user_id, sequence + 2)
                await confirm.confirm.callback(sent)
                assert confirm.completed, sent.followup.send.call_args

            asyncio.run(native_declaration())
        offered = fight.propose(OTHER, proposal_key, data["revision"], 900, declaration)
        fight.confirm(
            ADMIN,
            f"ambush-review-{number}",
            state(game).revision,
            offered["id"],
            opening=True,
            reach=True,
            outside_permission=False,
            indirect=False,
            evidence="Actual close-range ambush",
        )
        game.dice.faces = (4, 4)
        asyncio.run(
            native_form(
                OTHER,
                number,
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
            answer(game, member, "battle_assault_table", flag=vast, text="Original table view")

    def settle_body():
        if target_handler:
            body = HandlerConsequenceService(ledger)
            consequence = next(x for x in body.tasks(ADMIN) if x["trigger"] == "asset_damage")
            preview = body.get(ADMIN, consequence["id"])
            body.respond(
                ADMIN,
                str(uuid4()),
                consequence["id"],
                preview["game_revision"],
                "injury",
                "The original Handler suffers the actual combat injury.",
            )

    initial_girl = state(game).sheets["2"].model_copy(deep=True)
    assault(40420, None if target_handler else asset, vast=False)
    settle_body()
    completed_attack = next(x for x in ambushes(state(game)) if x.attacker == actor)
    assert completed_attack.action and completed_attack.completed is None
    assert game.inspect(OTHER, completed_attack.action)["state"] == "complete"
    canon = state(game)
    if target_handler:
        assert canon.sheets["2"] == initial_girl
        assert canon.handler_injuries[-1].actor == plan.target
    else:
        assert next(x for x in canon.sheets["2"].assets if x.id == asset).damaged
    assert canon.sheets["3"] == old_other
    assert rebel_inventory(canon, actor).heat == 1
    tick(worker, gateway, 5)

    if siege:
        review = SiegeService(strain)
        with pytest.raises(WorkflowError, match="original Handler"):
            review.get(OTHER, root)
        assert review.get(ADMIN, root)["resolved"] == 1
        with pytest.raises(WorkflowError, match="every original Rebel attack"):
            review.finish(ADMIN, "one-attack-is-insufficient", root, state(game).revision)
        second = next(x for x in ambushes(state(game)) if x.attacker == second_actor)
        change(cast, OTHER, "join", second_actor)
        identity = second.id
        asyncio.run(
            native_form(
                OTHER, 40434, inbox_open, target=(target_id,), account="Second original attack"
            )
        )
        remaining = next(
            x.id for x in state(game).sheets["2"].assets if x.family == "frame" and not x.damaged
        )
        assault(
            40436,
            None if target_handler else remaining,
            vast=False,
            assailant=second_actor,
            attacking_asset=second_weapon.id,
        )
        settle_body()
        assert review.get(ADMIN, root)["resolved"] == 2
        assert rebel_inventory(state(game), second_actor).heat == 1
        tick(worker, gateway, 5)
        if introduce:
            with pytest.raises(WorkflowError, match="every original Rebel attack"):
                review.finish(ADMIN, "two-attacks-insufficient", root, state(game).revision)
            with pytest.raises(WorkflowError, match="Strain"):
                activate(cycle, game, period)
            third = next(x for x in ambushes(state(game)) if x.attacker == third_actor)
            change(cast, OTHER, "join", third_actor)
            identity = third.id
            asyncio.run(
                native_form(
                    OTHER, 40520, inbox_open, target=("2",), account="Third original attack"
                )
            )
            remaining = next(
                x.id
                for x in state(game).sheets["2"].assets
                if x.family == "frame" and not x.damaged
            )
            assault(
                40522, remaining, vast=False, assailant=third_actor, attacking_asset=third_weapon.id
            )
            assert review.get(ADMIN, root)["resolved"] == 3
            assert rebel_inventory(state(game), third_actor).heat == 1
            tick(worker, gateway, 5)
        revision = state(game).revision
        asyncio.run(
            native_form(
                ADMIN, 40432, lambda click: open_effect(click, effects, root), decision=("finish",)
            )
        )
        assert review.finish(ADMIN, "40433", root, revision)["complete"]
        completion = sieges(state(game))[0].completed
        assert completion and {x.completed for x in ambushes(state(game))} == {completion}
        assert activate(cycle, game, period)["phase"] == "active"
        return

    def finish_mission(value, number):
        settled = missions.end(
            ADMIN, f"ambush-finish-{number}", value["id"], value["revision"], True
        )
        discipline = PunishmentService(ledger, missions.access.registry)
        for entry in missions.get(ADMIN, value["id"])["work"]:
            submit_punishment(
                discipline,
                ADMIN,
                entry["id"],
                Details(kind="stimulant_injection"),
                f"ambush-dog-punishment-{number}",
            )
        assert (
            missions.complete(ADMIN, f"ambush-complete-{number}", value["id"], settled["revision"])[
                "phase"
            ]
            == "complete"
        )

    finish_mission(mission, 1)
    assert ambushes(state(game))[0].completed

    def dispatch(number):
        offer = missions.offer(ADMIN, f"ambush-offer-{number}", "Separate mission", (2,))
        reply = missions.respond(PLAYER, f"ambush-accept-{number}", offer["id"], 1, "accept")
        return missions.start(ADMIN, f"ambush-start-{number}", offer["id"], reply["revision"])

    next_mission = dispatch(2)
    if not pursuit:
        assert next_mission["id"] != ambushes(state(game))[0].mission
        assert len(ambushes(state(game))) == 1
        return
    second = next(x for x in ambushes(state(game)) if x.mission == next_mission["id"])
    assert second.pursuit == root and second.id != bound.id
    with pytest.raises(WorkflowError, match="Complete the actual Rebel ambush"):
        missions.end(
            ADMIN,
            "second-mission-before-pursuit",
            next_mission["id"],
            next_mission["revision"],
            True,
        )
    service.open(
        OTHER,
        "repeated-capture-attempt",
        second.id,
        state(game).revision,
        900,
        "2",
        "I return to try again.",
    )
    undamaged = next(
        x.id for x in state(game).sheets["2"].assets if x.family == "frame" and not x.damaged
    )
    assault(40430, undamaged, vast=True)
    tick(worker, gateway, 5)
    finish_mission(next_mission, 2)
    hunt_service = HuntService(game)
    assert hunt_service.get(OTHER, root)["attempts"] == 2
    with pytest.raises(WorkflowError, match="original Rebel and Handler"):
        hunt_service.get(PLAYER, root)

    async def open_pursuit(click):
        viewer = ADMIN if click.user.id == 1 else OTHER
        entry = next(x for x in inbox.items(viewer) if x.task == "m3_rebel_hunt")
        await InboxView(inbox, viewer.user_id).route(click, entry)

    asyncio.run(
        native_form(
            OTHER, 40440, open_pursuit, choice=("propose",), account="I genuinely call it off."
        )
    )
    assert hunts(state(game))[0].ended is None
    ledger.engine.dispose()
    asyncio.run(
        native_form(
            ADMIN, 40450, open_pursuit, choice=("approve",), account="The pursuit ends here."
        )
    )
    assert hunts(state(game))[0].ended
    third = dispatch(3)
    assert len(ambushes(state(game))) == 2 and all(
        x.mission != third["id"] for x in ambushes(state(game))
    )
    finish_mission(third, 3)
