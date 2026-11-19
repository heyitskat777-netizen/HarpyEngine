"""A saved High Void face produces a real Aggressive Gorgon and retains the subsumed Pilot."""

import asyncio

import pytest
import sqlalchemy as sa
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_physical_operations import place
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_physical import open_initial
from girlframe.discord_adapter.m3_strain_effects import ASSETS, open_effect
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_berserk_frame import RULE, threats
from girlframe.engine.m3_gorgon_combat import Contest, Exposure
from girlframe.engine.m3_physical import open_cockpit
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_gorgon import GorgonService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_high_void_berserk_activates_once_and_stays_required_until_actual_core_defeat(ledger):
    strain, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            ),
        }
    )
    witness = Npc(
        id="activation-casualty",
        name="Local civilian",
        jobs=("civilian",),
        controller=1,
        detail="Actual NPC at the activating cockpit",
        cell=(0, 0),
    )
    opponent = gorgon("erratic", "source-contest", revealed=True)
    with ledger.transaction() as c:
        canon = state(game)
        world = initial()
        canon.world = world.model_copy(
            update=dict(gorgons=(*world.gorgons, opponent), npcs=(witness,))
        )
        canon = place(place(canon, 2, mode="outside_frame"), 3)
        game.event(c, 1, "berserk-original-placement", "synthetic.actual_battlefield", canon)
    period = prepared(strain, game, high=frozenset({"void"}))
    effects = EffectService(strain)
    for track, face, column, choice in (
        ("rebellion", 1, 2, Choice(rule_id="strain.rebellion.low.1.2", account="Control slips.")),
        (
            "budget",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="Rooms reassigned.", rooms=((2, 3),)),
        ),
        ("void", 4, 1, None),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "berserk-die-" + track, request.id, 1, state(game).revision)
        outcome = strain.choose(
            ADMIN, "berserk-column-" + track, request.id, 2, state(game).revision, column
        )
        identity = request.id + ":effect"
        if choice:
            effects.apply(
                ADMIN, "berserk-other-" + track, identity, 1, state(game).revision, choice
            )
    assert outcome["rule_id"] == RULE
    names = ASSETS["incubus"][:6]
    assert len(names) == 6

    async def arm_native():
        click = current(1, 40300)
        await click.response.defer(ephemeral=True)
        await open_effect(click, effects, identity)
        view = click.edit_original_response.call_args.kwargs["view"]
        view.values.update(
            berserk_owner=("2",),
            account="The Frame goes berserk when it activates.",
            victim=(witness.id,),
            **{"class": ("aggressive",)},
            type=("incubus",),
            assets=tuple(names),
            core=(names[0],),
            weakness="Overload the exposed inner channel",
            name="The former Frame",
        )
        submitted = current(1, 40301)
        await view.confirm.callback(submitted)
        assert view.completed, submitted.edit_original_response.call_args

    asyncio.run(arm_native())
    (planned,) = threats(state(game))
    assert planned.activated is None and planned.defeated is None
    inbox = InboxService(ledger)
    assert any(x.task == "m3_berserk_frame" for x in inbox.items(ADMIN))
    assert not any(x.task == "m3_berserk_frame" for x in inbox.items(PLAYER))
    assert state(game).world.npcs[0].alive and not any(
        x.id == planned.design.id for x in state(game).world.gorgons
    )
    assert activate(CycleService(strain.periods), game, period)["phase"] == "active"
    actor = current_ref(state(game), 2)
    physical = PhysicalService(ledger)
    data = physical.preview(PLAYER)
    sit = CockpitAction(
        actor=actor,
        operation="sit",
        expected_position=data["position_sha256"],
        account="I sit in my own cockpit.",
        confirmed=True,
    )
    physical.operate(PLAYER, "sit-before-activation", data["game_revision"], sit)
    assert threats(state(game))[0].activated is None
    data = physical.preview(PLAYER)
    revision = data["game_revision"]
    command = CockpitAction(
        actor=actor,
        operation="pilot",
        expected_position=data["position_sha256"],
        account="I activate my actual Frame.",
        confirmed=True,
    )
    with pytest.raises(WorkflowError, match="original Girl"):
        physical.operate(OTHER, "wrong-activation-owner", revision, command)
    ledger.safety(OTHER, "pause-activation", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        physical.operate(PLAYER, "paused-activation", revision, command)
    ledger.safety(OTHER, "resume-activation", ledger.status(OTHER)["revision"], pause=False)

    async def activate_native():
        click = current(2, 40310)
        await click.response.defer(ephemeral=True)
        await open_initial(click, physical)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(operation=("pilot",), account=command.account)
        submitted = current(2, 40311)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args

    asyncio.run(activate_native())
    assert (
        physical.operate(PLAYER, "40311", revision, command, channel=900)["operation"] == "berserk"
    )
    canon = state(game)
    (active,) = threats(canon)
    assert active.activated and not active.defeated and not canon.world.npcs[0].alive
    target = ActorRef(kind="gorgon", entity=active.design.id)
    assert resolve(canon, target, ()).cell == (0, 0)
    with ledger.engine.connect() as c:
        body = resolve(canon, actor, profiles(c, ledger.campaign_id), require_current_profile=False)
    assert body.subsumed and not body.vitals_active and not body.piloting
    frame_lock = next(x for x in canon.frame_locks if x.owner == actor)
    with pytest.raises(ValueError, match="Defeat the actual Berserk Gorgon"):
        open_cockpit(
            canon, actor, frame_lock.frame_instance, 1, "premature-open", "I cannot open it"
        )

    def required():
        work = t.m3["m3_required_work"]
        with ledger.engine.connect() as c:
            return c.execute(
                sa.select(work.c.state, work.c.event_id)
                .where(work.c.id == identity + ":berserk")
                .order_by(work.c.revision)
            ).all()

    assert [x.state for x in required()] == ["pending", "pending"]
    ledger.engine.dispose()
    combat = GorgonService(WorldService(strain.missions))
    attacker = ActorRef(kind="gorgon", entity=opponent.id)
    for i, resource in enumerate(active.design.assets[:3]):
        canon = state(game)
        combat.contest(
            ADMIN,
            "berserk-contest-" + str(i),
            canon.revision,
            Contest(
                attacker=attacker,
                defender=target,
                attacking_assets=(opponent.assets[0].id,),
                defending_assets=(resource.id,),
                attacker_sha256=resolve(canon, attacker, ()).source_sha256,
                defender_sha256=resolve(canon, target, ()).source_sha256,
                winner="attacker",
                losing_asset=resource.id,
                approach="direct",
                account="The Erratic tears open the shield.",
                trigger_confirmed=True,
            ),
        )
    canon = state(game)
    combat.expose(
        ADMIN,
        "berserk-exposed",
        canon.revision,
        Exposure(
            actor=target,
            source_sha256=resolve(canon, target, ()).source_sha256,
            account="I verify the inner channel is exposed.",
            weakness_confirmed=True,
        ),
    )
    cast = CastService(ActorService(strain.missions))
    change(cast, ADMIN, "join", target)
    fight = BattleService(ledger)
    scene = fight.preview(OTHER, 900)
    pilot = next(x for x in scene["actors"] if x["ref"]["entity"] == "3")
    enemy = next(x for x in scene["actors"] if x["ref"]["entity"] == target.entity)
    declaration = Declaration(
        play="go_for_the_core",
        actor=ActorRef.model_validate(pilot["ref"]),
        target=target,
        attacking_asset=next(x.id for x in state(game).sheets["3"].assets if x.family == "frame"),
        actor_sha256=pilot["sha256"],
        target_sha256=enemy["sha256"],
        account="Attack the genuine exposed Core.",
    )
    offered = fight.propose(OTHER, "berserk-final-proposal", scene["revision"], 900, declaration)
    fight.confirm(
        ADMIN,
        "berserk-final-review",
        state(game).revision,
        offered["id"],
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="The exposed channel is within reach.",
    )
    game.dice.faces = (6, 6)
    action = game.begin(
        OTHER,
        "berserk-final-play",
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="go_for_the_core",
            heat=0,
            target_actor=target,
            attacking_asset=declaration.attacking_asset,
            battle_context=offered["id"],
            context=declaration.account,
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    pass_tags(game)
    assert game.inspect(OTHER, action)["state"] == "complete"
    canon = state(game)
    (defeated,) = threats(canon)
    assert defeated.defeated == required()[-1].event_id and required()[-1].state == "resolved"
    assert not next(x for x in canon.world.gorgons if x.id == target.entity).alive
    assert canon.sheets["2"].character_id == actor.incarnation
    assert next(x for x in canon.placements if x.actor == actor).subsumed
    assert not any(x.task == "m3_berserk_frame" for x in inbox.items(OTHER))

    async def reopen_native():
        entry = next(x for x in inbox.items(PLAYER) if x.task == "m3_berserk_frame")
        assert entry.state == "resolved"
        click = current(2, 40320)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(click, entry)
        content = click.edit_original_response.call_args.kwargs["content"]
        assert "was defeated" in content and "Local civilian" not in content

    asyncio.run(reopen_native())
