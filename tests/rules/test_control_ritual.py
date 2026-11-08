"""Actual High Rebellion source, first successful Girl and later Tag-like use."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, start, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_refusal_service import refusal
from test_strain_effect_service import selected
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_control_ritual import rituals, tags
from girlframe.engine.m3_strain_effects import Choice
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def source(store, *, rebellion_face=4, rebellion_values=None):
    strain, game = ready(store, face=4)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN, "world", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    with store.transaction() as c:
        actual = state(game)
        for sheet in actual.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "synthetic-prior-care", "synthetic.baseline", actual)
    period = prepared(strain, game, frozenset({"rebellion"}))
    effects = EffectService(strain)
    for track, face, column, choice in (
        ("void", 1, 1, selected()),
        ("rebellion", rebellion_face, 2, None),
        (
            "budget",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="Actual rooms", rooms=((2, 3),)),
        ),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, track + "-die", request.id, 1, state(game).revision)
        strain.choose(ADMIN, track + "-column", request.id, 2, state(game).revision, column)
        identity = request.id + ":effect"
        if choice:
            effects.apply(ADMIN, track + "-effect", identity, 1, state(game).revision, choice)
        else:

            async def native_source(identity=identity):
                interaction = current(1, 29500)
                await interaction.response.defer(ephemeral=True)
                await open_effect(interaction, effects, identity)
                form = interaction.edit_original_response.call_args.kwargs["view"]
                assert {x.key for x in form.fields} == (
                    {"account"}
                    if rebellion_values is None
                    else {"account", "backstory_tag", "backstory_observers"}
                )
                form.values.update(
                    account="The actual next successful refusal can develop a Ritual"
                )
                form.values.update(rebellion_values or {})
                await form.confirm.callback(current(1, 29501))
                assert form.completed

            asyncio.run(native_source())
    activate(CycleService(strain.periods), game, period)
    return game, GameWorker(game), Gateway()


def successful(game, worker, gateway, *, viewer=PLAYER, key="successful", faces=(6, 6)):
    game.dice = Dice(faces)
    identity = refusal(game, viewer=viewer, key=key)
    tick(worker, gateway)
    pass_tags(game)
    if sum(faces) >= 11:
        answer(game, viewer, "actor_disobey", flag=True)
    else:
        answer(
            game, viewer, "actor_disobey", options=("tag_heat",), number=1, text="Actual refusal"
        )
    return identity


@pytest.mark.parametrize("faces", [(4, 4), (6, 6)])
def test_original_next_success_owned_native_creation_and_later_real_mark(ledger, faces):
    game, worker, gateway = source(ledger)
    identity = successful(game, worker, gateway, faces=faces)
    pending = next(x for x in game.choices(PLAYER) if x["kind"] == "control_ritual_create")
    before = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            "wrong-ritual-owner",
            pending["id"],
            pending["revision"],
            ChoiceAnswer(flag=True, text="Not mine"),
        )
    assert state(game) == before
    # Handler may finish their real response before the original Girl decides.
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.inspect(PLAYER, identity)["state"] != "complete"

    async def create_native():
        interaction = current(2, 29510)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, pending["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(flag=("yes",), text="Count the breaths, then refuse")
        await form.confirm.callback(current(2, 29511))
        assert form.completed

    asyncio.run(create_native())
    tick(worker, gateway, 5)
    ritual = rituals(state(game))[0]
    assert ritual.actor.entity == "2" and ritual.action == identity
    assert tags(state(game), 2)[0].label == "Count the breaths, then refuse"
    assert all(x.id != ritual.id for x in state(game).sheets["2"].tags)
    # Existing unrelated Play and another human cannot use this ritual.
    game.dice = Dice((6, 6))
    other_play = start(game)
    tick(worker, gateway)
    own = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
    assert ritual.id not in {x["id"] for x in game.decision(PLAYER, own["id"])["tags"]}
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", text="Actual high Keep Tag")
    answer(game, ADMIN, "handler_keep", flag=True, text="Enough")
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, other_play)["state"] == "complete"
    game.dice = Dice((4, 5))
    later = refusal(game, key="later-refusal")
    tick(worker, gateway)
    own = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
    assert ritual.id in {x["id"] for x in game.decision(PLAYER, own["id"])["tags"]}
    for viewer in (OTHER, ADMIN):
        row = next(x for x in game.choices(viewer) if x["kind"] == "tag_window")
        assert ritual.id not in {x["id"] for x in game.decision(viewer, row["id"])["tags"]}
    answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=(ritual.id,),
        number=1,
        text="Counting breaths gives me control to refuse",
    )
    for viewer in (OTHER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    actual = game.inspect(PLAYER, later)
    assert actual["receipt"]["pre_total"] == 9
    assert actual["modifiers"] == [{"source": "control_ritual", "amount": 1}]
    with ledger.engine.connect() as c:
        saved = game.action(c, later)["data"]
        assert saved["tag_marker_applied"]["tag"] == ritual.id
        assert saved["result"]["total"] == 10
    assert tags(state(game), 2)[0].marked
    answer(game, PLAYER, "actor_disobey", options=("tag_heat",), number=1, text="I refuse")
    answer(game, ADMIN, "handler_disobey", flag=False)
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, later)["state"] == "complete"
    assert not any(x["kind"] == "control_ritual_create" for x in game.choices(PLAYER))
    assert game.roll(PLAYER, "known-later-roll", later)["receipt"] == actual["receipt"]

    game.close_scene(ADMIN, "end-ritual-scene", 900)
    game.bind_scene(ADMIN, "next-ritual-scene", 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, "join-again-" + str(viewer.user_id), 900)
    repeated = refusal(game, key="repeat-ritual-in-next-scene")
    tick(worker, gateway)
    answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=(ritual.id,),
        number=-1,
        text="This ritual now distracts me from the command",
    )
    for viewer in (OTHER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    if faces == (6, 6):
        answer(game, PLAYER, "tag_resolution", options=("reject",))
        assert tags(state(game), 2)[0].rejection_pending
    else:
        replaced = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
        answer(game, PLAYER, "tag_resolution", options=("embrace",), denied=(replaced,))
        assert not tags(state(game), 2)
        assert any(x.name == ritual.tag.label for x in state(game).sheets["2"].identities)
    answer(game, PLAYER, "actor_disobey", options=("tag_heat",), number=1, text="Still refuse")
    answer(game, ADMIN, "handler_disobey", flag=False)
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, repeated)["result"]["total"] == 8
    if faces == (6, 6):
        obligation = next(x for x in game.own_obligations(PLAYER) if x["kind"] == "reject_tag")
        game.fulfill(
            PLAYER,
            "actual-ritual-rejection",
            900,
            obligation["id"],
            "I act against my old Control Ritual at the first opportunity",
        )
        tick(worker, gateway, 5)
        assert not tags(state(game), 2) and rituals(state(game))[0].removed
        assert not any(x["kind"] == "reject_tag" for x in game.own_obligations(PLAYER))


def test_low_does_not_claim_next_success_decline_consumes_opportunity(ledger):
    game, worker, gateway = source(ledger)
    game.dice = Dice((1, 1))
    low = refusal(game)
    tick(worker, gateway)
    pass_tags(game)
    answer(game, ADMIN, "handler_disobey", flag=False)
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, low)["state"] == "complete"
    assert rituals(state(game))[0].actor is None
    identity = successful(game, worker, gateway, viewer=OTHER, key="actual-next-other")
    answer(game, OTHER, "control_ritual_create", flag=False)
    answer(game, ADMIN, "handler_disobey", flag=False)
    tick(worker, gateway, 5)
    value = rituals(state(game))[0]
    assert value.action == identity and value.actor.entity == "3" and value.declined
    assert not tags(state(game), 3)
