"""A live Rebel source arms the real next-Girl Punishment exactly once."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_void_spread import strain_source

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_rebel_taunt import RULE, taunts
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_rebel_taunt import TauntService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("interaction", ("order", "play", "conversation"))
def test_radio_arms_the_original_handler_tag_and_actual_first_girl(ledger, interaction):
    strain, game, _, period, work = strain_source(ledger, 4, "rebellion", column=1, high=False)
    effects = EffectService(strain)
    assert effects.get(ADMIN, work)["rule_id"] == RULE
    world = WorldService(strain.missions)
    world.faction(
        ADMIN,
        "group",
        state(game).revision,
        Faction(id="radio-group", name="Radio Group", kind="rebel", cells=((2, 2),)),
    )
    caster = NpcRoleService(world)
    offer = caster.offer(
        ADMIN,
        "rebel-handler",
        state(game).revision,
        Npc(
            id="radio-source",
            name="Rival Handler",
            jobs=("handler",),
            detail="Actual Rebel officer.",
            controller=OTHER.user_id,
            cell=(2, 2),
            faction="radio-group",
        ),
    )
    caster.respond(OTHER, "accept-source", offer["id"], state(game).revision, "accept")
    for track, face, column, choice in (
        (
            "void",
            5,
            1,
            Choice(
                rule_id="strain.void.high.5.1",
                account="The real threat is nearby.",
                revelation_channel=900,
                revelation_play="reveal_near_disaster",
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(
                rule_id="strain.budget.low.5.2", account="Original room choice.", rooms=((2, 3),)
            ),
        ),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "die-" + track, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + track, request.id, 2, state(game).revision, column)
        effects.apply(
            ADMIN, "other-" + track, request.id + ":effect", 1, state(game).revision, choice
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
            88300,
            "m3_strain_effect",
            rebel_handler=("radio-source",),
            account="A radio call.",
        )
    )
    service = TauntService(strain)
    with pytest.raises(WorkflowError, match="actual radio speaker and recipient"):
        service.get(ADMIN, work, 900)
    asyncio.run(native(OTHER, 88310, "m3_rebel_taunt", account="PRIVATE_RADIO_WORDS"))
    assert service.get(ADMIN, work, 900)["account"] == "PRIVATE_RADIO_WORDS"
    with pytest.raises(WorkflowError, match="actual radio speaker and recipient"):
        service.get(PLAYER, work, 900)
    assert not any(x.task == "m3_rebel_taunt" for x in InboxService(ledger).items(PLAYER))
    asyncio.run(
        native(ADMIN, 88320, "m3_rebel_taunt", account="I take it to heart.", tag="Rattled")
    )
    armed = state(game)
    (case,) = taunts(armed)
    assert case.tag_event and case.radio_event and case.work is None
    assert next(x for x in armed.handler_tags if x.id == case.tag).label == "Rattled"
    assert effects.get(ADMIN, work)["state"] == "resolved"
    assert activate(CycleService(strain.periods), game, period)["phase"] == "active"
    girl = current_ref(state(game), PLAYER.user_id)
    if interaction == "order":
        issued = game.issue_order(ADMIN, "first-actual-order", 900, PLAYER.user_id, "Stand by.")
        assert (
            game.issue_order(ADMIN, "first-actual-order", 900, PLAYER.user_id, "Stand by.")
            == issued
        )
        worker, gateway = GameWorker(game), Gateway()
        tick(worker, gateway, 3)
        answer(game, PLAYER, "order_response", options=("obedient",))
        tick(worker, gateway, 5)
    elif interaction == "play":
        plays = HandlerPlayService(ledger)
        grant = plays.start(ADMIN, "source-play", state(game).revision, (girl,))["id"]
        plays.submit(
            ADMIN,
            "original-play",
            grant,
            state(game).revision,
            "mess",
            Effect(kind="tag", account="I call out her conduct.", target=girl, tag="Reliable"),
        )
    else:
        cast = CastService(ActorService(strain.missions))
        change(cast, ADMIN, "join", case.handler)
        asyncio.run(
            native(ADMIN, 88330, "m3_rebel_taunt", account="I speak with her.", girl=("2",))
        )

    (triggered,) = taunts(state(game))
    assert triggered.girl == girl and triggered.work and triggered.interaction_event
    assert triggered.tag == case.tag and triggered.radio_event == case.radio_event
    assert state(game).strain.events == armed.strain.events
    assert not any(x.identity == triggered.work for x in InboxService(ledger).items(OTHER))
    work_item = PunishmentService(ledger)
    assert work_item.get(ADMIN, triggered.work)["subject_id"] == str(PLAYER.user_id)
    scene = work_item.propose_scene(
        ADMIN,
        "discipline-scene",
        triggered.work,
        1,
        state(game).revision,
        "Actual on-screen discipline.",
    )
    for witness in (ADMIN, PLAYER):
        scene = work_item.attest_scene(
            witness,
            f"discipline-attest-{witness.user_id}",
            triggered.work,
            scene["revision"],
            state(game).revision,
        )
    work_item.apply(
        ADMIN,
        "discipline-applied",
        triggered.work,
        scene["revision"],
        state(game).revision,
        Details(kind="stimulant_injection"),
    )
    assert work_item.get(ADMIN, triggered.work)["state"] == "resolved"
    assert taunts(state(game))[0] == triggered
