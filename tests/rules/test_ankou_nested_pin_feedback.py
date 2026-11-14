"""A real second last mark in Keep preserves its resolved Beneath Feedback ancestry."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_beneath_feedback import actual_social_source
from test_ankou_feedback import choose, finish_keep
from test_ankou_standalone_low_pin_keep import finish_pin_flirt
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_feedback import FeedbackService, prove
from girlframe.services.m3_ankou_pin import source_binding, validate_pending
from girlframe.services.onboarding import WorkflowError


def worker_outcome(game, key):
    """Observe the real dispatcher command; never submit a replacement roll."""
    with game.store.engine.connect() as c:
        outcome = c.scalar(
            sa.select(t.commands.c.outcome_json).where(
                t.commands.c.campaign_id == game.store.campaign_id,
                t.commands.c.interaction_key == key,
            )
        )
    return json.loads(outcome) if outcome is not None else None


def episode(ledger, tmp_path, monkeypatch, given, *, recipe="keep_your_head"):
    game, worker, gateway, parent, first = actual_social_source(ledger, tmp_path, monkeypatch)
    target = current_ref(state(game), OTHER.user_id)
    choose(game, "purpose", target)
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=True,
        text="PRIVATE_NESTED_PIN: protect the Cadre",
    )
    replace = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
    answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
    first = feedback.get(state(game), first.id)
    assert first.new_identity and first.phase == "resolved"
    game.dice.faces = (1, 1)
    tick(worker, gateway, 4)
    pass_tags(game)
    parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    assert parent_receipt and parent_receipt["pre_total"] == 3 and game.dice.calls == 1
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("pin",),
        text="PRIVATE_NESTED_PIN: reverse the confrontation and pin her",
    )
    before = state(game)
    first = feedback.get(before, first.id)
    pin = next(
        x for x in before.facts if x.get("kind") == "physical_pin" and x.get("action") == parent
    )
    assert pin["owner"] == "3" and pin["target"] == "2"
    assert [x.id for x in before.sheets["2"].identities if not x.marked] == [first.new_identity]
    answer(game, PLAYER, "beneath_pin_response", options=("play",))
    request = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_response_play")
    decision = game.decision(PLAYER, request["id"])
    reopened = GameService(ledger, dice=game.dice)

    async def native_response():
        opened = current(PLAYER.user_id, 99771)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_play(opened, reopened, parent=decision, _pilot=True)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(OTHER.user_id, 99770))
        form.values.update(
            play=(recipe,),
            target=(str(OTHER.user_id),) if recipe == "flirt" else (),
            identity=(first.new_identity,),
            gain=("1",),
            pair_share=("0",),
            heat=("1",),
            disposable_heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="PRIVATE_NESTED_PIN: lean on my new last Identity to endure",
        )
        submitted = current(PLAYER.user_id, 99772)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        after = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == after
        with ledger.engine.connect() as c:
            return json.loads(
                c.scalar(
                    sa.select(t.commands.c.outcome_json).where(
                        t.commands.c.campaign_id == ledger.campaign_id,
                        t.commands.c.interaction_key == str(submitted.id),
                    )
                )
            )["action_id"]

    game.dice.faces = (4, 4)
    child = asyncio.run(native_response())
    confirmed_key = "m2.confirmed_roll:" + child
    assert worker_outcome(game, confirmed_key) is None
    assert not any(x.action == child for x in feedback.sources(state(game)))
    assert game.inspect(PLAYER, child)["receipt"] is None and game.dice.calls == 1
    # A fresh worker must discover the persisted native child. No direct roll
    # fallback is allowed: failure to dispatch must fail this normal episode.
    worker = GameWorker(GameService(ledger, dice=game.dice))
    tick(worker, gateway, 4)
    confirmed = worker_outcome(game, confirmed_key)
    assert confirmed is not None, "The native worker did not commit the pending response Feedback"
    held = state(game)
    second = next(x for x in feedback.sources(held) if x.action == child)
    assert len(feedback.sources(held)) == 2
    assert second.id != first.id and second.mark_event != first.mark_event
    assert second.phase == "choice" and second.pin_source
    assert confirmed == dict(action_id=child, receipt=None, ankou_feedback=second.id)
    resume_key = "m3.ankou_resume:" + child + ":" + second.mark_event
    assert worker_outcome(game, resume_key) is None
    assert second.prepared.identity == first.new_identity
    assert second.heat_before == second.heat_committed == before.sheets["2"].heat
    assert game.dice.calls == 1 and game.inspect(PLAYER, child)["receipt"] is None
    assert next(x for x in held.sheets["2"].identities if x.id == first.new_identity).marked
    assert feedback.get(held, first.id) == first
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert game.inspect(PLAYER, parent)["state"] == "awaiting_choices"
    with ledger.engine.connect() as c:
        saved = game.action(c, child)
        mark = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.command_key).where(
                t.events.c.campaign_id == ledger.campaign_id,
                t.events.c.id == second.mark_event,
            )
        ).one()
        assert tuple(mark) == ("m3.ankou_feedback_committed", str(PLAYER.user_id), confirmed_key)
        assert not saved["data"].get("ankou_feedback_child")
        assert source_binding(game, c, held, saved) == second.pin_source
        assert prove(game, c, held, second.id) == second
        validate_pending(game, c, held, saved)
        forged = copy.deepcopy(saved)
        forged["data"]["prepared"]["source_work"] = first.id
        with pytest.raises(WorkflowError, match="SOURCE_ANKOU_PIN_PORT_REQUIRED"):
            source_binding(game, c, held, forged)
        if recipe == "flirt":
            for update in (
                {"target": PLAYER.user_id},
                {"target": None},
                {"target_actor": target.model_dump(mode="json")},
                {"kicked_puppy_basis": True, "heat": 0},
                {"piloting": True},
                {"learned_keep_rider": "foreign-lesson"},
                {"prince_exception": "foreign-demand"},
            ):
                foreign = copy.deepcopy(saved)
                foreign["data"]["prepared"].update(update)
                # These probes must reach the source guard, not fail an
                # unrelated input-schema constraint before that guard runs.
                PlayInput.model_validate(foreign["data"]["prepared"])
                with pytest.raises(WorkflowError, match="SOURCE_ANKOU_PIN_PORT_REQUIRED"):
                    source_binding(game, c, held, foreign)
            # A Flirt binding cannot be substituted for a Keep against the same
            # pin. Existing Keep fingerprints remain byte-for-byte unchanged.
            keep = copy.deepcopy(saved)
            keep["data"]["prepared"].update(play="keep_your_head", target=None)
            assert source_binding(game, c, held, keep) != second.pin_source
        missing_pin = held.model_copy(deep=True)
        missing_pin.facts.remove(pin)
        with pytest.raises(WorkflowError, match="canonical original physical pin"):
            source_binding(game, c, missing_pin, saved)
        # Reject proof cycles before following any recursive source adapter.
        cyclic = held.model_copy(deep=True)
        feedback.put(cyclic, first.model_copy(update={"pin_source": second.pin_source}))
        with pytest.raises(WorkflowError, match="resolved standalone accepted-purpose"):
            source_binding(game, c, cyclic, saved)
    with pytest.raises(WorkflowError):
        FeedbackService(game).view(ADMIN, second.id)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("purpose",), fields={"target": target.token}),
        )
    choose(game, "purpose", target)
    private = FeedbackService(game).view(OTHER, second.id)
    assert not {"prepared", "identity", "heat_before", "heat_committed", "pin_source"} & set(
        private
    )
    owed = next(x for x in game.choices(OTHER) if x["kind"] == "ankou_feedback_purpose")
    with pytest.raises(WorkflowError):
        game.respond(PLAYER, str(uuid4()), owed["id"], owed["revision"], ChoiceAnswer(flag=True))
    key = str(uuid4())
    reply = ChoiceAnswer(
        flag=given,
        text="PRIVATE_NESTED_PIN: remain yourself" if given else "I decline another purpose",
    )
    reopened = GameService(ledger, dice=game.dice)
    outcome = reopened.respond(OTHER, key, owed["id"], owed["revision"], reply)
    saved_state = state(game)
    assert reopened.respond(OTHER, key, owed["id"], owed["revision"], reply) == outcome
    assert state(game) == saved_state and game.dice.calls == 1
    receipt = None
    expected_bonds = before.bonds
    if given:
        replace = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
        answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
        ready = state(game).sheets["2"].model_copy(deep=True)
        with ledger.engine.connect() as c:
            validate_pending(game, c, state(game), game.action(c, child))
        assert worker_outcome(game, resume_key) is None
        # Reopening the worker preserves the first confirmed command and uses
        # the actual committed mark's distinct resume key, rather than rerolling it.
        worker = GameWorker(GameService(ledger, dice=game.dice))
        tick(worker, gateway, 4)
        resumed = worker_outcome(game, resume_key)
        assert resumed is not None, (
            "The native worker did not resume the resolved response Feedback"
        )
        assert resumed == dict(action_id=child, receipt=game.inspect(PLAYER, child)["receipt"])
        assert resumed["receipt"] is not None
        assert game.inspect(PLAYER, parent)["state"] == "awaiting_choices"
        if recipe == "flirt":
            assert game.inspect(PLAYER, child)["state"] == "tag_window"
            pass_tags(game)
            expected_identities, expected_bonds = finish_pin_flirt(
                game, worker, gateway, parent, child
            )
        else:
            finish_keep(game, worker, gateway, child)
            expected_identities = ready.identities
        receipt = game.inspect(PLAYER, child)["receipt"]
        assert receipt and receipt["heat"] == 1 and receipt["pre_total"] == 9
        assert game.dice.calls == 2
        assert state(game).sheets["2"].identities == expected_identities
        assert state(game).sheets["2"].heat == ready.heat
    else:
        assert is_helpless(state(game), second.actor, target)
        assert feedback.get(state(game), second.id).phase == "ended"
        assert game.inspect(PLAYER, child)["receipt"] is None and game.dice.calls == 1
    final = state(game)
    assert worker_outcome(game, confirmed_key) == confirmed
    assert worker_outcome(game, resume_key) == (
        dict(action_id=child, receipt=receipt) if given else None
    )
    original = game.inspect(PLAYER, parent)
    assert original["state"] == game.inspect(PLAYER, child)["state"] == "complete"
    assert original["receipt"] == parent_receipt
    assert original["result"]["response_play"] == child
    assert original["result"]["pinned_response_performed"] is given
    assert original["result"]["pinned_response_feedback"] == second.id
    assert "escaped" not in original["result"]
    assert pin in final.facts and final.bonds == expected_bonds and final.order == before.order
    assert feedback.get(final, first.id) == first
    restarted = GameService(ledger, dice=game.dice)
    assert restarted.roll(PLAYER, str(uuid4()), parent)["receipt"] == parent_receipt
    if given:
        assert restarted.roll(PLAYER, str(uuid4()), child)["receipt"] == receipt
    assert state(game) == final and game.dice.calls == (2 if given else 1)
    with ledger.engine.connect() as c:
        assert prove(restarted, c, final, first.id) == first
        actual = prove(restarted, c, final, second.id)
        assert actual.receipt == (receipt["id"] if receipt else None)
        receipts = t.m2["m2_receipts"]
        assert c.scalar(
            sa.select(sa.func.count())
            .select_from(receipts)
            .where(
                receipts.c.campaign_id == ledger.campaign_id,
                receipts.c.action_id == child,
            )
        ) == int(given)
        choices = t.m2["m2_choices"]
        assert (
            c.scalar(
                sa.select(choices.c.state).where(
                    choices.c.campaign_id == ledger.campaign_id,
                    choices.c.id == request["id"],
                )
            )
            == "completed_by_child"
        )
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_NESTED_PIN" not in json.dumps(gateway.messages)
    assert "PRIVATE_BENEATH_FEEDBACK" not in json.dumps(gateway.messages)
    assert "PRIVATE_STANDALONE_LOW_PIN" not in json.dumps(gateway.messages)


@pytest.mark.parametrize("given", [True, False])
def test_native_nested_pin_keep_feedback_preserves_both_sources(
    ledger, tmp_path, monkeypatch, given
):
    episode(ledger, tmp_path, monkeypatch, given)
