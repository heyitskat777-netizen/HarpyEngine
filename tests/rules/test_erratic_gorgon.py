"""A real Class III arrival applies the printed Tag to an actual off-scene NPC."""

import asyncio

import pytest
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.m3_world import open_world
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_erratic_gorgon import RULE, ErraticService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_original_erratic_native_actor_applies_one_real_npc_tag(ledger, tmp_path, monkeypatch):
    strain, game = ready(ledger, face=2)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    world = WorldService(strain.missions)
    world_map = initial()
    world.initialize(
        ADMIN,
        "world",
        state(game).revision,
        world_map.board,
        world_map.locations,
        world_map.gorgons[0],
    )
    with ledger.transaction() as c:
        canon = state(game)
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "nonvoid-roster", "synthetic.nonvoid_cadre", canon)
    prepared(strain, game)
    request = next(x for x in state(game).strain.requests if x.track == "void")
    strain.roll(ADMIN, "saved-low-two", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "actual-low-column", request.id, 2, state(game).revision, 1)
    effect = request.id + ":effect"
    original = gorgon("erratic", "class-three", (0, 1), revealed=True)
    EffectService(strain).apply(
        ADMIN,
        "actual-erratic-arrival",
        effect,
        1,
        state(game).revision,
        Choice(
            rule_id="strain.void.low.2.1",
            account="The Erratic arrives beside the base.",
            gorgon=original,
        ),
    )
    world.npc(
        ADMIN,
        "far-person",
        state(game).revision,
        Npc(
            id="off-scene",
            name="Actual distant technician",
            detail="An original NPC elsewhere.",
            controller=ADMIN.user_id,
            jobs=("scientist",),
            cell=(8, 4),
        ),
    )
    ref = ActorRef(kind="gorgon", entity=original.id)
    change(CastService(ActorService(strain.missions)), ADMIN, "join", ref)
    service = ErraticService(game)
    with pytest.raises(WorkflowError, match="implementation and review"):
        service.view(ADMIN, 900)
    approved(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    assert service.view(ADMIN, 900)["npcs"] == (("off-scene", "Actual distant technician"),)
    assert service.view(PLAYER, 900)["npcs"] == ()
    rev = state(game).revision
    args = (original.id, "off-scene", "PRIVATE_ERRATIC_TAG", "What the original Gorgon did.")
    with pytest.raises(WorkflowError, match="controlled Erratic"):
        service.tag(PLAYER, "not-my-gorgon", 900, rev, *args)
    with pytest.raises(WorkflowError, match="STALE_ERRATIC"):
        service.tag(ADMIN, "old-source", 900, rev - 1, *args)
    ledger.safety(OTHER, "pause-erratic", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.tag(ADMIN, "paused-source", 900, rev, *args)
    ledger.safety(OTHER, "resume-erratic", ledger.status(OTHER)["revision"], pause=False)

    async def native():
        click = current(ADMIN.user_id, 89800)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_world(click, WorldService(MissionService(ledger)))
        menu = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(menu, Picker)
        choose = current(ADMIN.user_id, 89801)
        choose.channel_id = 900
        await choose.response.defer(ephemeral=True)
        await menu.open_item(choose, "erratic_tag")
        form = choose.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(gorgon=(args[0],), npc=(args[1],), tag=args[2], account=args[3])
        await form.confirm.callback(current(ADMIN.user_id, 89802))
        assert form.completed

    asyncio.run(native())
    result = service.tag(ADMIN, "89802", 900, rev, *args)
    assert result["state"] == "resolved"
    ledger.engine.dispose()
    after = state(game)
    npc = next(x for x in after.world.npcs if x.id == "off-scene")
    (tag,) = npc.tags
    assert tag.id == result["event"] and tag.label == args[2]
    assert ActorRef.model_validate_json(tag.giver_entity) == ref
    assert npc.cell == (8, 4) and npc.alive
    assert args[2] not in str(WorldService(MissionService(ledger)).get(PLAYER))
    assert game.dice.calls == 0


def test_erratic_flight_moves_original_and_waits_for_real_engage_advance(
    ledger, tmp_path, monkeypatch
):
    from test_beneath_service import ready as battlefield
    from test_engage_actual import pass_tags
    from test_harpy_flirt import submit_form
    from test_m2_game import answer, tick
    from test_physical_operations import place

    from girlframe.discord_adapter.m3_cast import open_cast
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_battle_state import Declaration
    from girlframe.services.m3_battle import BattleService
    from girlframe.services.m3_movement import MovementService

    game, worker, gateway = battlefield(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"world"}))
        )
    )
    layout = initial()
    gorgon_state = gorgon("erratic", "fleeing-erratic", (0, 0), revealed=True)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = layout.model_copy(update=dict(gorgons=(*layout.gorgons, gorgon_state)))
        game.event(
            c,
            1,
            "original-erratic-on-battlefield",
            "synthetic.placement",
            place(canon, 2, mode="outside_frame"),
        )
    ref = ActorRef(kind="gorgon", entity=gorgon_state.id)
    caster = current_ref(state(game), 2)
    world = WorldService(MissionService(ledger))
    change(CastService(ActorService(world.missions)), ADMIN, "join", ref)

    def engage(key, maneuver):
        result = game.begin(
            PLAYER,
            key,
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="engage",
                heat=0,
                trigger_confirmed=True,
                target_actor=ref,
                context="I cut across its actual approach.",
            ),
        )
        tick(worker, gateway, 3)
        pass_tags(game)
        own_asset = state(game).sheets["2"].assets[0].id
        answer(
            game,
            PLAYER,
            "engage_maneuvers",
            options=(maneuver, "cover"),
            fields={maneuver: own_asset, "cover": own_asset},
            text="I follow its original movement.",
        )
        tick(worker, gateway, 4)
        assert game.inspect(PLAYER, result["action_id"])["state"] == "complete"
        return result["action_id"]

    first = engage("first-engagement", "reposition")
    service = ErraticService(game)
    before = state(game)
    with pytest.raises(WorkflowError):
        service.flee(
            PLAYER, "unowned-flight", 900, before.revision, ref.entity, first, (1, 0), "I leave."
        )

    async def world_menu(click, option):
        await open_world(click, world)
        picker = click.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(click, option)

    replay_key = asyncio.run(
        submit_form(
            ADMIN,
            lambda click: world_menu(click, "erratic_flee"),
            dict(case=("0",), x="1", y="0", account="The Gorgon bolts east."),
            89810,
        )
    )
    replay = service.flee(
        ADMIN, replay_key, 900, before.revision, ref.entity, first, (1, 0), "The Gorgon bolts east."
    )
    flight_event = replay["event"]
    after = state(game)
    assert next(x for x in after.world.gorgons if x.id == ref.entity).cell == (1, 0)
    with pytest.raises(WorkflowError, match="real Engage"):
        service.catch(PLAYER, "before-pursuit", 900, after.revision, flight_event, first)

    battle = BattleService(ledger)

    def declare(key):
        data = battle.preview(PLAYER, 900)
        actor, target = (
            next(x for x in data["actors"] if x["token"] == body.token) for body in (caster, ref)
        )
        return battle.propose(
            PLAYER,
            key,
            data["revision"],
            900,
            Declaration(
                play="all_out_assault",
                actor=caster,
                target=ref,
                attacking_asset=actor["assets"][0]["id"],
                target_asset=target["assets"][0]["id"],
                actor_sha256=actor["sha256"],
                target_sha256=target["sha256"],
                account="I take an actual opening against the Gorgon.",
            ),
        )

    with pytest.raises(WorkflowError, match="pursuit Play"):
        declare("cannot-hit-while-fled")
    engage("real-pursuit", "advance")
    with pytest.raises(WorkflowError, match="Reach the original"):
        service.catch(
            PLAYER,
            "still-too-far",
            900,
            state(game).revision,
            flight_event,
            service.flight_view(PLAYER, 900)["pursuits"][0]["action"],
        )
    MovementService(game).move(
        PLAYER,
        "move-to-gorgon",
        state(game).revision,
        900,
        caster,
        (1, 0),
        account="I follow to its actual square.",
    )
    ledger.engine.dispose()

    async def catch_from_cast(click):
        await open_cast(click, CastService(ActorService(world.missions)))
        picker = click.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(click, "erratic_catch")

    asyncio.run(submit_form(PLAYER, catch_from_cast, dict(case=("0",)), 89820))
    assert not service.flight_view(PLAYER, 900)["pursuits"]
    assert declare("actual-renewed-attack")["id"] and game.dice.calls == 2
