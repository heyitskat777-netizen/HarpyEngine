"""Native Beneath counter retains mandatory Feedback, real pin response and Alpha parent."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_dose_counter_feedback import ready
from test_ankou_feedback import finish_keep
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_alpha_counter import source_binding, validate_beneath_pending
from girlframe.services.m3_ankou_feedback import FeedbackService, prepare_child, prove
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError


def last_counter(game, worker, gateway, identity, *, mark_attacker=False):
    game.dice = Dice((1, 1))
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=current_ref(state(game), 3),
            identity=(
                next(x.id for x in state(game).sheets["2"].identities if not x.marked)
                if mark_attacker
                else None
            ),
            gain=int(mark_attacker),
            heat=int(mark_attacker),
            context="PRIVATE_BENEATH_COUNTER_FEEDBACK: original Alpha attack",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    assert parent_receipt and game.dice.calls == 1
    answer(game, OTHER, "alpha_low", options=("counter_broken",))
    request = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_counter_play")

    async def native():
        opened = current(OTHER.user_id, 99581)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, request["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert "identity" in {x.key for x in form.fields}
        identity_field = next(x for x in form.fields if x.key == "identity")
        assert "Beneath" in identity_field.label
        assert not await form.interaction_check(current(PLAYER.user_id, 99580))
        form.values.update(
            play=("put_someone_beneath_you",),
            identity=(identity,),
            gain=("1",),
            heat=("1",),
            context="PRIVATE_BENEATH_COUNTER_FEEDBACK: Use my last Identity against the Alpha",
        )
        submitted = current(OTHER.user_id, 99582)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    game.dice.faces = (5, 5)
    before = state(game)
    asyncio.run(native())
    with game.store.engine.connect() as c:
        actions = t.m2["m2_actions"]
        child = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == game.store.campaign_id,
                actions.c.parent_id == parent,
                actions.c.actor_id == "3",
            )
        )
    tick(worker, gateway, 4)
    if not any(x.action == child for x in feedback.sources(state(game))):
        game.roll(OTHER, "m2.confirmed_roll:" + child, child)
    value = next(x for x in feedback.sources(state(game)) if x.action == child)
    assert value.phase == "choice" and value.beneath_counter_source is not None
    assert value.heat_before == value.heat_committed == before.sheets["3"].heat
    assert state(game).sheets["3"].heat == before.sheets["3"].heat
    assert next(x for x in state(game).sheets["3"].identities if x.id == identity).marked
    assert game.dice.calls == 1 and game.inspect(OTHER, child)["receipt"] is None
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert game.inspect(PLAYER, parent)["state"] == "awaiting_choices"
    with game.store.engine.connect() as c:
        saved = game.action(c, child)
        assert prove(game, c, state(game), value.id) == value
        assert source_binding(game, c, state(game), saved) == value.beneath_counter_source
        wrong = copy.deepcopy(saved)
        wrong["data"]["alpha_counter_source"]["choice"] = "not-this-opportunity"
        with pytest.raises(WorkflowError, match="counter requirement"):
            source_binding(game, c, state(game), wrong)
        wrong = copy.deepcopy(saved)
        wrong["actor_id"] = str(PLAYER.user_id)
        with pytest.raises(WorkflowError, match="original ordinary Alpha"):
            source_binding(game, c, state(game), wrong)
    return parent, parent_receipt, child, value


def finish_pin_flirt(game, worker, gateway, parent, child, response_id):
    pass_tags(game)
    before = state(game)
    own = tuple(x.id for x in before.sheets["2"].identities if x.marked)[:2]
    theirs = tuple(x.id for x in before.sheets["3"].identities if x.marked)[:2]
    assert own and len(theirs) == 2
    answer(game, PLAYER, "actor_flirt", options=("name",), denied=own)
    request = next(x for x in game.choices(OTHER) if x["kind"] == "target_flirt")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), request["id"], request["revision"], ChoiceAnswer(text="Forged")
        )
    for identity in (response_id, child, parent):
        assert game.inspect(PLAYER, identity)["state"] != "complete"
    assert not alpha.conditions(before, current_ref(before, 2), current_ref(before, 3))
    reopened = GameService(game.store, dice=game.dice)
    key = str(uuid4())
    actual = ChoiceAnswer(
        denied=theirs, text="PRIVATE_BENEATH_COUNTER_FEEDBACK: use my chosen name"
    )
    outcome = reopened.respond(OTHER, key, request["id"], request["revision"], actual)
    after = state(game)
    assert reopened.respond(OTHER, key, request["id"], request["revision"], actual) == outcome
    assert state(game) == after
    for uid, picked in (("2", own), ("3", theirs)):
        assert not any(x.marked for x in after.sheets[uid].identities if x.id in picked)
        assert after.sheets[uid].heat == before.sheets[uid].heat
    assert after.bonds == before.bonds
    for identity in (response_id, child, parent):
        assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert any(x.get("kind") == "physical_pin" and x.get("action") == child for x in after.facts)
    owed = next(
        x
        for x in game.own_obligations(PLAYER)
        if x["kind"] == "flirt_followthrough" and x["action"] == response_id
    )
    tick(worker, gateway, 8)
    follow = game.fulfill(
        PLAYER,
        str(uuid4()),
        900,
        owed["id"],
        "PRIVATE_BENEATH_COUNTER_FEEDBACK: I use the name she asked for",
    )["action_id"]
    tick(worker, gateway, 4)
    assert state(game).bonds == after.bonds
    request = next(x for x in game.choices(OTHER) if x["kind"] == "followthrough_confirm")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), request["id"], request["revision"], ChoiceAnswer(flag=True)
        )
    answer(game, OTHER, "followthrough_confirm", flag=True, text="She used my chosen name")
    assert game.inspect(PLAYER, follow)["state"] == "complete"
    assert state(game).bonds["2:3"] == min(2, after.bonds["2:3"] + 1)
    assert next(x for x in state(game).obligations if x.id == owed["id"]).state == "fulfilled"


def episode(
    ledger, tmp_path, monkeypatch, given, *, play_response=False, response_recipe="keep_your_head"
):
    game, worker, gateway, identity = ready(ledger, tmp_path, monkeypatch)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    parent, parent_receipt, child, value = last_counter(
        game, worker, gateway, identity, mark_attacker=response_recipe == "flirt"
    )
    actor, attacker = current_ref(state(game), 3), current_ref(state(game), 2)
    committed = state(game).sheets["3"].model_copy(deep=True)
    original_assets = state(game).sheets["2"].assets
    with pytest.raises(WorkflowError, match="Recover the root action"):
        game.abort(ADMIN, str(uuid4()), child)
    game.abort(ADMIN, str(uuid4()), parent)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == parent)
    assert saved["rolled"] and not saved["cancellable"] and saved["descendants"] == 1
    assert not any(x["id"] == child for x in recovery.saved(OTHER))
    recovery.recover(PLAYER, "recover-original-beneath-counter-feedback", parent, saved["revision"])
    tick(worker, gateway, 3)
    assert state(game).sheets["3"] == committed and game.dice.calls == 1
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert game.inspect(OTHER, child)["receipt"] is None
    answer(
        game,
        OTHER,
        "ankou_feedback_choice",
        options=("purpose",),
        fields={"target": attacker.token},
        text="PRIVATE_BENEATH_COUNTER_FEEDBACK: actual purpose plea",
    )
    private = FeedbackService(game).view(PLAYER, value.id)
    assert not {"prepared", "identity", "heat_before", "heat_committed"} & set(private)
    request = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_purpose")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), request["id"], request["revision"], ChoiceAnswer(flag=True)
        )
    answer(
        game,
        PLAYER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_BENEATH_COUNTER_FEEDBACK: keep us safe" if given else "I give no purpose",
    )
    if given:
        replacement = next(x.id for x in state(game).sheets["3"].identities if not x.protected)
        answer(game, OTHER, "ankou_feedback_identity", fields={"replace": replacement})
        before_roll = state(game).sheets["3"].model_copy(deep=True)
        with ledger.engine.connect() as c:
            validate_beneath_pending(game, c, state(game), game.action(c, child))
        tick(worker, gateway, 4)
        pass_tags(game)
        receipt = game.inspect(OTHER, child)["receipt"]
        assert receipt["heat"] == 1 and game.dice.calls == 2
        assert state(game).sheets["3"].heat == before_roll.heat
        assert state(game).sheets["3"].identities == before_roll.identities
        choice = next(x for x in game.choices(OTHER) if x["kind"] == "beneath_select")
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER,
                str(uuid4()),
                choice["id"],
                choice["revision"],
                ChoiceAnswer(options=("tag", "pin"), fields={"tag": "Forged"}, text="Forged"),
            )
        answer(
            game,
            OTHER,
            "beneath_select",
            options=("tag", "pin"),
            fields={"tag": "PRIVATE_BENEATH_COUNTER_FEEDBACK: humbled"},
            text="PRIVATE_BENEATH_COUNTER_FEEDBACK: turn her own pressure against her",
        )
        actual = state(game)
        tags = [x for x in actual.sheets["2"].tags if x.id.startswith(child + ":tag:")]
        assert len(tags) == 1 and tags[0].giver == 3
        assert any(
            x.get("kind") == "physical_pin" and x.get("action") == child for x in actual.facts
        )
        owed = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_pin_response")
        with pytest.raises(WorkflowError):
            game.respond(
                OTHER, str(uuid4()), owed["id"], owed["revision"], ChoiceAnswer(text="Forged reply")
            )
        assert game.inspect(OTHER, child)["state"] != "complete"
        assert game.inspect(PLAYER, parent)["state"] != "complete"
        assert not alpha.conditions(state(game), attacker, actor)
        reopened = GameService(ledger, dice=game.dice)
        assert reopened.decision(PLAYER, owed["id"])["kind"] == "beneath_pin_response"
        own = (
            ChoiceAnswer(options=("play",))
            if play_response
            else ChoiceAnswer(text="PRIVATE_BENEATH_COUNTER_FEEDBACK: I concede this moment")
        )
        key = str(uuid4())
        outcome = reopened.respond(PLAYER, key, owed["id"], owed["revision"], own)
        saved = state(game)
        assert reopened.respond(PLAYER, key, owed["id"], owed["revision"], own) == outcome
        assert state(game) == saved
        if play_response:
            response = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_response_play")
            expected = PlayInput(
                play=response_recipe,
                parent=child,
                target=3 if response_recipe == "flirt" else None,
                heat=0,
                context="PRIVATE_BENEATH_COUNTER_FEEDBACK: my own Play while actually pinned",
                trigger_confirmed=True,
            )
            with game.store.engine.connect() as c:
                assert prepare_child(game, c, PLAYER, saved, expected, 900) is None
                for person, attempt in (
                    (OTHER, expected),
                    (PLAYER, expected.model_copy(update={"source_work": value.id})),
                    (PLAYER, expected.model_copy(update={"play": "check_sensors"})),
                ):
                    with pytest.raises(WorkflowError):
                        prepare_child(game, c, person, saved, attempt, 900)
                if response_recipe == "flirt":
                    for update in (
                        {"target": None},
                        {"target": PLAYER.user_id},
                        {"target_actor": actor},
                        {"learned_keep_rider": "foreign-lesson"},
                        {"kicked_puppy_basis": True},
                        {"prince_exception": "foreign-demand"},
                    ):
                        with pytest.raises(WorkflowError):
                            prepare_child(
                                game, c, PLAYER, saved, expected.model_copy(update=update), 900
                            )
                missing_pin = saved.model_copy(deep=True)
                missing_pin.facts = [
                    x
                    for x in missing_pin.facts
                    if not (x.get("kind") == "physical_pin" and x.get("action") == child)
                ]
                with pytest.raises(WorkflowError, match="canonical actual high Beneath pin"):
                    prepare_child(game, c, PLAYER, missing_pin, expected, 900)
            assert game.inspect(OTHER, child)["state"] != "complete"
            assert game.inspect(PLAYER, parent)["state"] != "complete"
            assert not alpha.conditions(saved, attacker, actor)
            decision = game.decision(PLAYER, response["id"])

            async def native_response():
                opened = current(PLAYER.user_id, 99585)
                opened.channel_id = 900
                await opened.response.defer(ephemeral=True)
                await open_play(opened, game, parent=decision, _pilot=True)
                form = opened.edit_original_response.call_args.kwargs["view"]
                form.values.update(
                    play=(response_recipe,),
                    target=("3",) if response_recipe == "flirt" else (),
                    identity=(),
                    gain=("0",),
                    pair_share=("0",),
                    heat=("0",),
                    disposable_heat=("0",),
                    piloting=("no",),
                    witnessed=("no",),
                    trigger=("yes",),
                    context=expected.context,
                )
                submitted = current(PLAYER.user_id, 99586)
                await form.confirm.callback(submitted)
                assert form.completed, submitted.edit_original_response.call_args_list

            game.dice.faces = (4, 4)
            asyncio.run(native_response())
            with game.store.engine.connect() as c:
                actions = t.m2["m2_actions"]
                response_id = c.scalar(
                    sa.select(actions.c.id).where(
                        actions.c.campaign_id == game.store.campaign_id,
                        actions.c.parent_id == child,
                        actions.c.actor_id == str(PLAYER.user_id),
                    )
                )
            tick(worker, gateway, 4)
            if response_recipe == "flirt":
                finish_pin_flirt(game, worker, gateway, parent, child, response_id)
            else:
                finish_keep(game, worker, gateway, response_id)
            response_receipt = game.inspect(PLAYER, response_id)["receipt"]
            assert response_receipt and response_receipt["heat"] == 0
            assert game.inspect(OTHER, child)["result"]["response_play"] == response_id
            assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
            assert game.inspect(OTHER, child)["receipt"] == receipt
            assert game.roll(PLAYER, str(uuid4()), response_id)["receipt"] == response_receipt
        else:
            assert game.inspect(OTHER, child)["result"]["pinned_response"] == own.text
        assert alpha.conditions(state(game), attacker, actor)
        assert game.dice.calls == 2 + int(play_response)
    else:
        receipt = None
        assert game.dice.calls == 1 and is_helpless(state(game), actor, attacker)
        assert not alpha.conditions(state(game), attacker, actor)
        assert game.inspect(OTHER, child)["result"]["blocked_before_roll"]
        assert not any(x.action == child for x in state(game).obligations)
        assert not any(x.get("action") == child for x in state(game).facts)
        assert not any(x.id.startswith(child + ":tag:") for x in state(game).sheets["2"].tags)
        with game.store.engine.connect() as c:
            original = game.action(c, parent)
            assert original["data"]["alpha"]["counter_performed"] is False
            assert original["data"]["alpha"]["counter_feedback"] == value.id
    assert state(game).sheets["2"].assets == original_assets
    assert (
        game.inspect(OTHER, child)["state"] == game.inspect(PLAYER, parent)["state"] == "complete"
    )
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert game.inspect(OTHER, child)["receipt"] == receipt
    restarted = GameService(ledger, dice=game.dice)
    assert restarted.inspect(OTHER, child) == game.inspect(OTHER, child)
    if given:
        assert restarted.roll(OTHER, str(uuid4()), child)["receipt"] == receipt
        assert game.dice.calls == 2 + int(play_response)
    with ledger.engine.connect() as c:
        assert prove(restarted, c, state(restarted), value.id).receipt == (
            receipt["id"] if given else None
        )
        assert game.action(c, child)["data"]["alpha_counter_completed"]
        assert game.action(c, parent)["data"]["alpha"]["counter_child"] == child
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_BENEATH_COUNTER_FEEDBACK" not in json.dumps(gateway.messages)
    restarted.close_scene(ADMIN, "close-completed-beneath-counter-scene", 900)
    rebound = restarted.bind_scene(ADMIN, "rebind-completed-beneath-counter-channel", 900)["scene"]
    assert rebound != value.cast.id
    with ledger.engine.connect() as c:
        assert prove(restarted, c, state(restarted), value.id).receipt == (
            receipt["id"] if given else None
        )


@pytest.mark.parametrize("given", [True, False])
def test_native_beneath_counter_feedback_preserves_original_opportunity(
    ledger, tmp_path, monkeypatch, given
):
    episode(ledger, tmp_path, monkeypatch, given)


def test_native_beneath_counter_feedback_pin_continues_actual_owned_keep(
    ledger, tmp_path, monkeypatch
):
    episode(ledger, tmp_path, monkeypatch, True, play_response=True)


def test_native_beneath_counter_feedback_pin_continues_actual_owned_flirt(
    ledger, tmp_path, monkeypatch
):
    episode(ledger, tmp_path, monkeypatch, True, play_response=True, response_recipe="flirt")
