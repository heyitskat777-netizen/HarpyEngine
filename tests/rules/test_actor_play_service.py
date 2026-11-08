"""Actual-role Play integration; no proxy Pilot and no invented human responses."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_actor_service import ready as actor_ready
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, state, tick

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_director import enter
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_cast import CastService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store, *, faces=(4, 5)):
    actors, game = actor_ready(store)
    game.dice.faces = faces
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=(
                *canon.world.npcs,
                Npc(
                    id="director",
                    name="Actual Director",
                    controller=3,
                    cell=(0, 0),
                    jobs=("director",),
                    detail="PRIVATE_DIRECTOR_DETAIL",
                ),
            ),
        )
        canon = enter(
            canon,
            1,
            "director",
            "actual-presence-event",
            ("Afraid", "Defiant"),
            "actual-source-work",
        )
        canon.handler_tags.append(
            TagState(id="tag", label="PRIVATE_HANDLER_TAG", giver=2, observers=(1, 2, 3))
        )
        game.event(c, 1, "synthetic-director-presence", "synthetic.director_context", canon)
    cast = CastService(actors)
    ref = ActorRef(kind="handler", entity="1", incarnation=state(game).director_contexts[-1].id)
    director = ActorRef(kind="npc", entity="director")
    change(cast, ADMIN, "join", ref)
    change(cast, OTHER, "join", director)
    change(cast, OTHER, "adjudicate", director)
    return ActorPlayService(game), game, cast, ref, director


def begin(service, ref, **kwargs):
    view = service.preview(ADMIN, 900, ref)
    prepared = dict(
        play="keep_your_head", context="PRIVATE_HANDLER_DANGER", trigger_confirmed=True, heat=0
    )
    prepared.update(kwargs)
    return service.begin(
        ADMIN,
        str(uuid4()),
        900,
        ref,
        view["actor"]["source_sha256"],
        ActorRef.model_validate(view["adjudicator"]["ref"]),
        view["cast_revision"],
        PlayInput(**prepared),
    )["action_id"]


def pass_tags(game):
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))


def proposal(game, viewer, ref, direction=1):
    return answer(
        game,
        viewer,
        "tag_window",
        options=("tag",),
        denied=("tag",),
        number=direction,
        fields={"as_actor": ref.token},
        text="Actual relevance shared with the scene",
    )


@pytest.mark.parametrize(
    "faces,positive,negative,tag",
    [
        ((2, 3), ("tough",), (), ""),
        ((4, 5), ("tough", "in_control"), ("desperate",), ""),
        ((6, 6), (), (), "PRIVATE_TIER_TAG"),
    ],
)
def test_actual_handler_keep_all_tiers_uses_actual_director_and_shared_locks(
    ledger, faces, positive, negative, tag
):
    svc, game, cast, ref, director = ready(ledger, faces=faces)
    original = state(game)
    action = begin(svc, ref)
    assert game.dice.calls == 0 and state(game) == original
    with pytest.raises(WorkflowError, match="LOCK_NOT_ACKNOWLEDGED"):
        game.roll(ADMIN, "too-early", action)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    assert game.dice.calls == 1
    pass_tags(game)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "actor_keep")
    with pytest.raises(WorkflowError, match="another player"):
        game.respond(
            OTHER,
            "not-your-choice",
            row["id"],
            row["revision"],
            ChoiceAnswer(options=positive, denied=negative, text=tag),
        )
    answer(game, ADMIN, "actor_keep", options=positive, denied=negative, text=tag)
    assert any(x["kind"] == "handler_keep" for x in game.choices(OTHER))
    assert not game.choices(ADMIN)
    answer(game, OTHER, "handler_keep", flag=True, text="PRIVATE_ACTUAL_DIRECTOR_RULING")
    assert game.inspect(ADMIN, action)["state"] == "complete"
    assert (
        state(game).sheets == original.sheets
        and state(game).order == original.order
        and "1" not in state(game).sheets
    )
    assert cast.view(ADMIN, 900)["facilitator"] == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_" not in json.dumps(gateway.messages)


def test_actor_commitment_is_atomic_actual_context_and_duplicate_roll_preserves_receipt(ledger):
    svc, game, cast, ref, director = ready(ledger)
    before = state(game)
    identity = before.director_contexts[-1].identities[0].id
    action = begin(svc, ref, identity=identity, gain=3, heat=2)
    tick(GameWorker(game), Gateway())
    after = state(game)
    assert after.handler_heat == 1 and after.director_contexts[-1].identities[0].marked
    receipt = game.inspect(ADMIN, action)["receipt"]
    assert game.roll(ADMIN, "retry-known-actor-roll", action)["receipt"] == receipt
    assert game.dice.calls == 1 and state(game) == after and after.sheets == before.sheets


def test_actual_cast_role_tag_uses_its_own_bond_not_the_controllers_pilot(ledger):
    svc, game, cast, ref, director = ready(ledger)
    npc = ActorRef(kind="npc", entity="secret-npc")
    change(cast, PLAYER, "join", npc)
    with ledger.transaction() as c:
        canon = state(game)
        canon.bonds["1:2"] = 2
        game.event(c, 1, "synthetic-handler-bond", "synthetic.bond", canon)
    action = begin(svc, ref)
    tick(GameWorker(game), Gateway())
    proposal(game, PLAYER, npc)
    for viewer in (ADMIN, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    with ledger.engine.connect() as c:
        actual = game.action(c, action)
    assert actual["data"]["result"]["total"] == 10
    assert actual["data"]["modifiers"][0]["amount"] == 1
    assert actual["data"]["modifiers"][0]["actor_ref"] == npc.model_dump(mode="json")
    assert game.dice.calls == 1


def test_disputed_tag_requires_each_humans_actual_agreement_then_applies_one_modifier(ledger):
    svc, game, cast, ref, director = ready(ledger)
    pc = ActorRef(kind="pilot", entity="2", incarnation=state(game).sheets["2"].character_id)
    action = begin(svc, ref)
    tick(GameWorker(game), Gateway())
    proposal(game, PLAYER, pc, 1)
    proposal(game, OTHER, director, -1)
    answer(game, ADMIN, "tag_window", options=("pass",))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "actor_tag_selection")
    choice = game.decision(OTHER, row["id"])["proposals"][0]["id"]
    answer(game, OTHER, "actor_tag_selection", options=(choice,))
    answer(game, ADMIN, "actor_tag_agreement", flag=False)
    answer(game, PLAYER, "actor_tag_agreement", flag=True)
    assert not state(game).handler_tags[0].marked
    assert any(x["kind"] == "actor_tag_selection" for x in game.choices(OTHER))
    answer(game, OTHER, "actor_tag_selection", options=(choice,))
    answer(game, ADMIN, "actor_tag_agreement", flag=True)
    answer(game, PLAYER, "actor_tag_agreement", flag=True)
    with ledger.engine.connect() as c:
        data = game.action(c, action)["data"]
    assert len(data["modifiers"]) == 1 and data["result"]["total"] == 10
    assert state(game).handler_tags[0].marked and game.dice.calls == 1


def test_known_actor_abort_blocks_recasting_and_resumes_same_receipt_choices_and_spend(ledger):
    svc, game, cast, ref, director = ready(ledger)
    action = begin(
        svc, ref, identity=state(game).director_contexts[-1].identities[0].id, gain=3, heat=2
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    answer(game, PLAYER, "tag_window", options=("pass",))
    before, receipt = state(game), game.inspect(ADMIN, action)["receipt"]
    game.abort(ADMIN, "abort-actual-role", action)
    with pytest.raises(WorkflowError, match="Restore chat"):
        change(cast, OTHER, "withdraw", director)
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.pending_actions(c)
    with pytest.raises(WorkflowError, match="Restore chat"):
        change(cast, OTHER, "withdraw", director)
    saved = svc.saved(ADMIN)[0]
    assert any(
        x.task == "m3_actor_recovery" and x.identity == action
        for x in InboxService(ledger).items(ADMIN)
    )
    assert not any(x.task == "m3_actor_recovery" for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError, match="cannot be discarded"):
        svc.recover(ADMIN, "no-known-reroll", action, saved["revision"], cancel=True)
    restarted = ActorPlayService(GameService(ledger, dice=game.dice))
    assert restarted.recover(ADMIN, "resume-known-actor", action, saved["revision"])[
        "receipt_preserved"
    ]
    tick(worker, gateway)
    assert game.inspect(ADMIN, action)["receipt"] == receipt and state(game) == before
    assert game.dice.calls == 1
    assert not game.choices(PLAYER)
    assert not any(x.task == "m3_actor_recovery" for x in InboxService(ledger).items(ADMIN))
    for viewer in (ADMIN, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(game, ADMIN, "actor_keep", text="Actual high-result Tag")
    answer(game, OTHER, "handler_keep", flag=False, text="Not enough")
    assert game.inspect(ADMIN, action)["state"] == "complete"


def test_actor_stale_resources_failed_receipt_insert_and_pause_never_commit_partial_effects(
    ledger, monkeypatch
):
    svc, game, cast, ref, director = ready(ledger)
    action = begin(
        svc, ref, identity=state(game).director_contexts[-1].identities[0].id, gain=3, heat=2
    )
    worker, gateway = GameWorker(game), Gateway()
    # Acquire the external lock without letting the worker confirm a roll yet.
    job = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(job, gateway))
    before = state(game)
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic after-receipt failure")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        game.roll(ADMIN, "retry-after-rollback", action)
    assert state(game) == before
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"])) == 0
    monkeypatch.setattr(game, "event", original)
    ledger.safety(PLAYER, "pause-actual-role", ledger.status(PLAYER)["revision"], pause=True)
    calls = game.dice.calls
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        game.roll(ADMIN, "retry-after-rollback", action)
    assert game.dice.calls == calls
    ledger.safety(PLAYER, "resume-actual-role", ledger.status(PLAYER)["revision"], pause=False)
    game.roll(ADMIN, "retry-after-rollback", action)
    assert state(game).handler_heat == 1


def test_actual_pilot_bond_applies_after_roll_and_repeated_tag_requires_owned_resolution(ledger):
    svc, game, cast, ref, director = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.bonds["1:2"] = 2
        canon.handler_tags[0].marked = True
        game.event(c, 1, "synthetic-repeated-tag", "synthetic.tag", canon)
    pc = ActorRef(kind="pilot", entity="2", incarnation=state(game).sheets["2"].character_id)
    action = begin(svc, ref)
    tick(GameWorker(game), Gateway())
    assert game.inspect(ADMIN, action)["receipt"]["pre_total"] == 9
    proposal(game, PLAYER, pc)
    for viewer in (ADMIN, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    assert not any(x["kind"] == "actor_keep" for x in game.choices(ADMIN))
    answer(game, ADMIN, "tag_resolution", options=("embrace",))
    assert len(state(game).director_contexts[-1].identities) == 3 and not state(game).handler_tags
    answer(game, ADMIN, "actor_keep", text="A new actual Tag")
    answer(game, OTHER, "handler_keep", flag=True, text="Enough")
    assert game.inspect(ADMIN, action)["result"]["total"] == 11
    assert len(game.inspect(ADMIN, action)["modifiers"]) == 1 and game.dice.calls == 1


def test_owned_rejection_is_an_actual_locked_action_and_does_not_roll_again(ledger):
    svc, game, cast, ref, director = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.handler_tags[0].marked = True
        game.event(c, 1, "synthetic-rejectable-tag", "synthetic.tag", canon)
    begin(svc, ref)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    pc = ActorRef(kind="pilot", entity="2", incarnation=state(game).sheets["2"].character_id)
    proposal(game, PLAYER, pc)
    for viewer in (ADMIN, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_resolution", options=("reject",))
    assert state(game).handler_tags[0].rejection_pending
    answer(game, ADMIN, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, OTHER, "handler_keep", flag=True, text="Enough")
    tick(worker, gateway, 5)
    item = next(x for x in state(game).obligations if x.kind == "actor_reject_tag")
    assert any(
        x.task == "m3_actor_rejection" and x.identity == item.id
        for x in InboxService(ledger).items(ADMIN)
    )
    view = svc.preview(ADMIN, 900, ref)
    rejected = svc.begin(
        ADMIN,
        "actual-rejection",
        900,
        ref,
        view["actor"]["source_sha256"],
        director,
        view["cast_revision"],
        PlayInput(
            play="actor_reject_tag",
            context="Explicitly take action to reject the Tag",
            trigger_confirmed=True,
            heat=0,
        ),
        rejection=item.id,
    )
    assert state(game).handler_tags and game.dice.calls == 1
    tick(worker, gateway)
    assert (
        not state(game).handler_tags
        and next(x for x in state(game).obligations if x.id == item.id).state == "fulfilled"
    )
    assert (
        game.inspect(ADMIN, rejected["action_id"])["state"] == "complete" and game.dice.calls == 1
    )


def test_actual_role_and_controller_are_revalidated_before_owned_response(ledger):
    svc, game, cast, ref, director = ready(ledger)
    action = begin(svc, ref)
    tick(GameWorker(game), Gateway())
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=tuple(
                x.model_copy(update={"controller": 2}) if x.id == "director" else x
                for x in canon.world.npcs
            ),
        )
        game.event(c, 1, "synthetic-controller-mismatch", "synthetic.controller", canon)
    before = state(game)
    with pytest.raises(WorkflowError, match="STALE_CAST"):
        game.respond(
            PLAYER,
            "no-controller-borrowing",
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("pass",)),
        )
    assert state(game) == before and game.dice.calls == 1
    assert game.inspect(ADMIN, action)["receipt"]


def test_own_handler_cannot_mark_own_tag_using_another_role_or_inherit_pilot_traits(ledger):
    svc, game, cast, ref, director = ready(ledger)
    before = state(game)
    view = svc.preview(ADMIN, 900, ref)
    with pytest.raises(WorkflowError, match="ordinary Identity"):
        svc.begin(
            ADMIN,
            "foreign-identity",
            900,
            ref,
            view["actor"]["source_sha256"],
            director,
            view["cast_revision"],
            PlayInput(
                play="keep_your_head",
                context="A danger",
                trigger_confirmed=True,
                heat=1,
                identity=before.sheets["2"].identities[0].id,
                gain=1,
            ),
        )
    assert state(game) == before and game.dice.calls == 0
    begin(svc, ref)
    tick(GameWorker(game), Gateway())
    with pytest.raises(WorkflowError):
        proposal(game, ADMIN, director)
    pass_tags(game)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "actor_keep")
    with pytest.raises(WorkflowError, match="ordinary"):
        game.respond(
            ADMIN,
            "no-borrowed-oldgen",
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("tough", "in_control"), denied=("desperate",), flag=True),
        )
    data = game.decision(ADMIN, row["id"])
    assert data["own"]["girl"] is None and len(data["own"]["identities"]) == 2
    assert "PRIVATE_DIRECTOR_DETAIL" not in str(data)


def test_unrolled_actor_reservation_can_cancel_after_restoration_and_policy_revocation_blocks(
    ledger,
):
    svc, game, cast, ref, director = ready(ledger)
    original = state(game)
    action = begin(svc, ref)
    game.abort(ADMIN, "abort-unrolled-actor", action)
    tick(GameWorker(game), Gateway(), 5)
    saved = svc.saved(ADMIN)[0]
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        svc.recover(ADMIN, "cancel-unrolled-actor", action, saved["revision"], cancel=True)
    ledger.policy = policy
    svc.recover(ADMIN, "cancel-unrolled-actor", action, saved["revision"], cancel=True)
    assert state(game) == original and game.dice.calls == 0 and not svc.saved(ADMIN)
    assert begin(svc, ref)


def test_native_actual_role_play_has_private_owned_dropdowns_and_native_director_responses(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_choice, open_play

    svc, game, cast, ref, director = ready(ledger)

    async def run():
        owner = current(1, 15401)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_play(owner, game)
        picker = owner.edit_original_response.call_args.kwargs["view"]
        assert not await picker.interaction_check(current(3))
        review = current(1, 15402)
        review.channel_id = 900
        await review.response.defer(ephemeral=True)
        await picker.open_item(review, "keep_your_head")
        form = review.edit_original_response.call_args.kwargs["view"]
        assert not game.dice.calls and "Actual Director" in form.instructions
        assert {x.key for x in form.fields} == {"context", "identity", "gain", "heat", "confirm"}
        form.values.update(
            context="PRIVATE_KEEP_CONTEXT", gain=("1",), heat=("0",), confirm=("yes",)
        )
        await form.confirm.callback(current(1, 15403))
        assert form.completed and game.dice.calls == 0
        await GameWorker(game).tick(Gateway())
        pass_tags(game)
        response = next(x for x in game.choices(ADMIN) if x["kind"] == "actor_keep")
        native = current(1, 15404)
        await native.response.defer(ephemeral=True)
        await open_choice(native, game, response["id"])
        choices = native.edit_original_response.call_args.kwargs["view"]
        assert not await choices.interaction_check(current(3))
        choices.values.update(options=("tough", "in_control"), denied=("desperate",))
        await choices.confirm.callback(current(1, 15405))
        assert choices.completed and any(x["kind"] == "handler_keep" for x in game.choices(OTHER))

    asyncio.run(run())


def test_concurrent_actual_actor_roll_commands_commit_one_receipt_and_one_resource_spend(ledger):
    svc, game, cast, ref, director = ready(ledger)
    action = begin(
        svc, ref, identity=state(game).director_contexts[-1].identities[0].id, gain=3, heat=2
    )
    worker, gateway = GameWorker(game), Gateway()
    job = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(job, gateway))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda key: game.roll(ADMIN, key, action), ("parallel-a", "parallel-b"))
        )
    assert results[0]["receipt"] == results[1]["receipt"]
    assert game.dice.calls == 1 and state(game).handler_heat == 1
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"])) == 1


def test_native_actor_recovery_is_owned_and_old_choice_revision_cannot_answer_after_resume(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_pending

    svc, game, cast, ref, director = ready(ledger)
    action = begin(svc, ref)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    stale = next(x for x in game.choices(ADMIN) if x["kind"] == "tag_window")
    game.abort(ADMIN, "abort-for-native-resume", action)
    tick(worker, gateway, 5)

    async def run():
        own = current(1, 15501)
        await own.response.defer(ephemeral=True)
        await open_pending(own, game)
        queue = own.edit_original_response.call_args.kwargs["view"]
        assert not await queue.interaction_check(current(3))
        selected = current(1, 15502)
        await selected.response.defer(ephemeral=True)
        await queue.open_item(selected, "recover:" + action)
        form = selected.edit_original_response.call_args.kwargs["view"]
        assert form.fields[0].options == (("resume", "Resume the saved Play"),)
        form.values["operation"] = ("resume",)
        await form.confirm.callback(current(1, 15503))
        assert form.completed

    asyncio.run(run())
    tick(worker, gateway)
    with pytest.raises(WorkflowError, match="STALE_CHOICE"):
        game.respond(
            ADMIN,
            "old-native-form",
            stale["id"],
            stale["revision"],
            ChoiceAnswer(options=("pass",)),
        )
    assert game.dice.calls == 1
