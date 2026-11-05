"""Actual native Harpy setup and shared Play/Discord workflow, with a separate owned PC."""

import asyncio
from uuid import uuid4

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, state, tick
from test_world_service import ready as world_ready

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store, *, faces=(2, 3), heat=0):
    world, game = world_ready(store)
    game.dice.faces = faces
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    actor = ActorRef(kind="external_pilot", entity="actual-native-harpy")
    with store.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            pilots=(
                AdversaryPilot(
                    id=actor.entity,
                    name="HARPY",
                    kind="harpy",
                    girl="harpy",
                    frame="harpy",
                    controller=2,
                    cell=(0, 0),
                    assets=(
                        Asset(
                            id="actual-harpy-asset",
                            name="Actual Void Arm",
                            family="girl",
                            description="An actual established Harpy Asset",
                            void=True,
                        ),
                    ),
                ),
            ),
        )
        game.event(c, 1, "synthetic-native-introduction", "synthetic.world_actor", canon)
    setup = HarpyDefeatService(store, game)
    proposed = setup.propose_runtime(
        PLAYER,
        "owned-native-facts",
        state(game).revision,
        NativeHarpyFacts(
            actor=actor,
            linked=True,
            girl_cell=(0, 0),
            frame_cell=(0, 0),
            heat=heat,
            frame_shutdown=False,
            body_incapacitated=False,
            custody="free",
            identities=(HarpyIdentity(id="actual-free", name="Free"),),
            tags=(),
            account="The actual owner supplies the existing character facts",
            facts_confirmed=True,
        ),
    )
    setup.review_setup(
        ADMIN,
        "gm-native-facts",
        proposed["id"],
        state(game).revision,
        True,
        "The real GM confirms these existing facts, not starting resource awards",
    )
    cast = CastService(ActorService(world.missions))
    change(cast, PLAYER, "join", actor)
    return ActorPlayService(game), game, cast, actor


def begin(svc, actor, **values):
    view = svc.preview(PLAYER, 900, actor)
    prepared = dict(
        play="keep_your_head", context="PRIVATE_HARPY_DANGER", trigger_confirmed=True, heat=0
    )
    prepared.update(values)
    return svc.begin(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        view["actor"]["source_sha256"],
        None,
        view["cast_revision"],
        PlayInput(**prepared),
    )["action_id"]


def pass_tags(game):
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))


@pytest.mark.parametrize(
    "faces,positive,negative,label",
    [
        ((2, 3), ("beautiful",), (), ""),
        ((4, 4), ("beautiful", "in_control"), ("desperate",), ""),
        ((6, 6), (), (), "PRIVATE_SELF_TAG"),
    ],
)
def test_native_harpy_keep_all_tiers_has_one_real_roll_owned_traits_and_actual_gm(
    ledger, faces, positive, negative, label
):
    svc, game, cast, actor = ready(ledger, faces=faces)
    original = state(game)
    action = begin(svc, actor)
    with pytest.raises(WorkflowError, match="LOCK_NOT_ACKNOWLEDGED"):
        game.roll(PLAYER, "before-lock", action)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            "wrong-human",
            row["id"],
            row["revision"],
            ChoiceAnswer(options=positive, denied=negative, text=label),
        )
    answer(game, PLAYER, "actor_keep", options=positive, denied=negative, text=label)
    assert not game.choices(PLAYER)
    answer(game, ADMIN, "handler_keep", flag=True, text="The real GM judges sufficiency")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.dice.calls == 1 and state(game).sheets == original.sheets
    assert state(game).world.pilots[0].assets == original.world.pilots[0].assets
    result = game.inspect(PLAYER, action)["result"]
    assert "sexy" not in str(result)
    if label:
        tag = next(x for x in harpy(state(game), actor).tags if x.label == label)
        assert tag.giver_ref == actor and tag.giver == PLAYER.user_id
        assert tag.gm_setter_appointment is None
    tick(worker, gateway, 5)
    assert "PRIVATE_" not in str(gateway.messages)


def test_actual_harpy_mark_spend_and_retry_never_change_its_humans_other_character(ledger):
    svc, game, cast, actor = ready(ledger, heat=1)
    before = state(game)
    action = begin(svc, actor, identity="actual-free", gain=3, heat=2)
    tick(GameWorker(game), Gateway())
    body = harpy(state(game), actor)
    assert body.heat == 2 and body.identities[0].marked
    assert state(game).sheets == before.sheets
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert game.roll(PLAYER, "retry-owned-harpy", action)["receipt"] == receipt
    assert game.dice.calls == 1
    resumed = GameService(ledger, dice=game.dice)
    assert resumed.inspect(PLAYER, action)["receipt"] == receipt


def test_native_role_picker_separates_harpy_from_same_humans_pc_and_preserves_no_write_preview(
    ledger,
):
    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_play

    svc, game, cast, actor = ready(ledger)
    before = state(game)

    async def run():
        request = current(2, 265001)
        request.channel_id = 900
        await request.response.defer(ephemeral=True)
        await open_play(request, game)
        picker = request.edit_original_response.call_args.kwargs["view"]
        assert {x[0] for x in picker.options} == {actor.token, "pilot"}
        assert not await picker.interaction_check(current(3))
        selection = current(2, 265002)
        selection.channel_id = 900
        await selection.response.defer(ephemeral=True)
        await picker.open_item(selection, actor.token)
        plays = selection.edit_original_response.call_args.kwargs["view"]
        review = current(2, 265003)
        review.channel_id = 900
        await review.response.defer(ephemeral=True)
        await plays.open_item(review, "keep_your_head")
        form = review.edit_original_response.call_args.kwargs["view"]
        assert "Harpy" in form.title and "Harpy's own Heat" in form.instructions
        assert "Director-presence" not in form.instructions
        assert state(game) == before and not game.dice.calls

    asyncio.run(run())


def test_known_harpy_roll_recovers_with_same_receipt_resources_and_prior_answers(ledger):
    svc, game, cast, actor = ready(ledger, faces=(2, 3), heat=1)
    action = begin(svc, actor, identity="actual-free", gain=3, heat=2)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    answer(game, OTHER, "tag_window", options=("pass",))
    original, receipt = state(game), game.inspect(PLAYER, action)["receipt"]
    game.abort(ADMIN, "abort-owned-harpy", action)
    tick(worker, gateway, 5)
    saved = svc.saved(PLAYER)[0]
    assert not svc.saved(OTHER)
    with pytest.raises(WorkflowError, match="cannot be discarded"):
        svc.recover(PLAYER, "cannot-reroll-harpy", action, saved["revision"], cancel=True)
    restarted = ActorPlayService(GameService(ledger, dice=game.dice))
    restarted.recover(PLAYER, "resume-original-harpy", action, saved["revision"])
    tick(worker, gateway)
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert state(game) == original and game.dice.calls == 1
    assert not game.choices(OTHER)
    for viewer in (ADMIN, PLAYER):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(game, PLAYER, "actor_keep", options=("beautiful",))
    answer(game, ADMIN, "handler_keep", flag=False, text="The actual GM explains the outcome")
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_harpy_safety_pause_and_actual_incapacity_block_voluntary_keep_before_rng(ledger):
    from girlframe.engine.m3_harpy_defeat import update as update_harpy

    svc, game, cast, actor = ready(ledger)
    action = begin(svc, actor)
    worker, gateway = GameWorker(game), Gateway()
    job = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(job, gateway))
    original = state(game)
    ledger.safety(PLAYER, "pause-harpy", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        game.roll(PLAYER, "no-harpy-roll-paused", action)
    assert state(game) == original and game.dice.calls == 0
    ledger.safety(PLAYER, "resume-harpy", ledger.status(PLAYER)["revision"], pause=False)
    with ledger.transaction() as c:
        changed = update_harpy(state(game), actor, body_incapacitated=True)
        game.event(c, 2, "synthetic-physical-incapacity", "synthetic.physical", changed)
    with pytest.raises(WorkflowError, match="incapacitated"):
        game.roll(PLAYER, "no-subsumed-keep", action)
    assert game.dice.calls == 0 and state(game).sheets == original.sheets
