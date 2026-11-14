"""Accepted Feedback's real low Beneath reverses pin ownership, then completes Keep."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_beneath_counter_feedback import last_counter
from test_ankou_dose_counter_feedback import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.engine import m3_alpha as alpha
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_feedback import FeedbackService, prepare_child, prove
from girlframe.services.onboarding import WorkflowError


def episode(ledger, tmp_path, monkeypatch, *, recipe="keep_your_head"):
    game, worker, gateway, identity = ready(ledger, tmp_path, monkeypatch)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    parent, parent_receipt, child, value = last_counter(game, worker, gateway, identity)
    actor, attacker = current_ref(state(game), 3), current_ref(state(game), 2)
    committed = state(game).sheets["3"].model_copy(deep=True)
    answer(
        game,
        OTHER,
        "ankou_feedback_choice",
        options=("purpose",),
        fields={"target": attacker.token},
        text="PRIVATE_LOW_PIN_KEEP: ask the actual Alpha for purpose",
    )
    private = FeedbackService(game).view(PLAYER, value.id)
    assert not {"prepared", "identity", "heat_before", "heat_committed"} & set(private)
    answer(
        game,
        PLAYER,
        "ankou_feedback_purpose",
        flag=True,
        text="PRIVATE_LOW_PIN_KEEP: protect our friends",
    )
    replacement = next(x.id for x in committed.identities if not x.protected)
    answer(game, OTHER, "ankou_feedback_identity", fields={"replace": replacement})
    before_roll = state(game).sheets["3"].model_copy(deep=True)
    assert before_roll.heat == committed.heat
    game.dice.faces = (1, 1)
    tick(worker, gateway, 4)
    pass_tags(game)
    receipt = game.inspect(OTHER, child)["receipt"]
    assert receipt and receipt["heat"] == 1 and game.dice.calls == 2
    assert game.inspect(OTHER, child)["result"] is None
    assert state(game).sheets["3"].identities == before_roll.identities
    assert state(game).sheets["3"].heat == before_roll.heat

    # At 7-, the original Alpha selects the counter's effect; the Ankou is pinned.
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_select")
    assert game.decision(PLAYER, choice["id"])["beneath"]["level"] == "low"
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("pin",), text="I cannot select her low consequence"),
        )
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("pin",),
        text="PRIVATE_LOW_PIN_KEEP: the Alpha pins the actual Ankou counter actor",
    )
    original = state(game)
    pin = next(x for x in original.facts if x.get("kind") == "physical_pin")
    assert pin["action"] == child and pin["owner"] == "2" and pin["target"] == "3"
    assert pin["owner_character"] == str(attacker.incarnation)
    assert pin["target_character"] == str(actor.incarnation)
    owed = next(x for x in game.choices(OTHER) if x["kind"] == "beneath_pin_response")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), owed["id"], owed["revision"], ChoiceAnswer(options=("play",))
        )
    reopened = GameService(ledger, dice=game.dice)
    key = str(uuid4())
    response = ChoiceAnswer(options=("play",))
    outcome = reopened.respond(OTHER, key, owed["id"], owed["revision"], response)
    saved = state(game)
    assert reopened.respond(OTHER, key, owed["id"], owed["revision"], response) == outcome
    assert state(game) == saved
    expected = PlayInput(
        play=recipe,
        target=PLAYER.user_id if recipe == "flirt" else None,
        parent=child,
        heat=0,
        context="PRIVATE_LOW_PIN_KEEP: keep my head while the Alpha pins me",
        trigger_confirmed=True,
    )
    with game.store.engine.connect() as c:
        assert prepare_child(game, c, OTHER, saved, expected, 900) is None
        for person, attempt in (
            (PLAYER, expected),
            (OTHER, expected.model_copy(update={"source_work": value.id})),
            (OTHER, expected.model_copy(update={"play": "check_sensors"})),
            (OTHER, expected.model_copy(update={"target": OTHER.user_id})),
        ):
            with pytest.raises(WorkflowError):
                prepare_child(game, c, person, saved, attempt, 900)
        if recipe == "flirt":
            for update in (
                {"target": None},
                {"target_actor": attacker},
                {"kicked_puppy_basis": True},
                {"learned_keep_rider": "foreign"},
                {"prince_exception": "foreign"},
            ):
                with pytest.raises(WorkflowError):
                    prepare_child(game, c, OTHER, saved, expected.model_copy(update=update), 900)
        missing_pin = saved.model_copy(deep=True)
        missing_pin.facts.remove(pin)
        with pytest.raises(WorkflowError, match="canonical actual low Beneath pin"):
            prepare_child(game, c, OTHER, missing_pin, expected, 900)
    for identity in (parent, child):
        assert game.inspect(OTHER, identity)["state"] != "complete"
    assert not alpha.conditions(saved, attacker, actor)
    request = next(x for x in reopened.choices(OTHER) if x["kind"] == "beneath_response_play")
    decision = reopened.decision(OTHER, request["id"])

    async def native_response():
        opened = current(OTHER.user_id, 99641)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_play(opened, reopened, parent=decision, _pilot=True)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(PLAYER.user_id, 99640))
        form.values.update(
            play=(recipe,),
            target=(str(PLAYER.user_id),) if recipe == "flirt" else (),
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
        submitted = current(OTHER.user_id, 99642)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        after = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == after

    game.dice.faces = (4, 4)
    asyncio.run(native_response())
    with game.store.engine.connect() as c:
        actions = t.m2["m2_actions"]
        response_id = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == ledger.campaign_id,
                actions.c.parent_id == child,
                actions.c.actor_id == "3",
            )
        )
        assert response_id and not game.action(c, response_id)["data"].get("ankou_feedback")
    tick(worker, gateway, 4)
    pass_tags(game)
    response_receipt = game.inspect(OTHER, response_id)["receipt"]
    assert response_receipt and response_receipt["heat"] == 0 and game.dice.calls == 3
    if recipe == "flirt":
        expected_identities, expected_bonds = finish_pin_flirt(
            game, worker, gateway, child, response_id
        )
    else:
        own = next(x for x in game.choices(OTHER) if x["kind"] == "actor_keep")
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER,
                str(uuid4()),
                own["id"],
                own["revision"],
                ChoiceAnswer(options=("tough", "in_control"), denied=("desperate",)),
            )
        answer(game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
        for identity in (parent, child, response_id):
            assert game.inspect(OTHER, identity)["state"] != "complete"
        assert not alpha.conditions(state(game), attacker, actor)
        handler = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_keep")
        with pytest.raises(WorkflowError):
            game.respond(
                OTHER, str(uuid4()), handler["id"], handler["revision"], ChoiceAnswer(flag=True)
            )
        answer(
            game, ADMIN, "handler_keep", flag=True, text="PRIVATE_LOW_PIN_KEEP: enough to endure"
        )
        expected_identities, expected_bonds = before_roll.identities, saved.bonds
    for identity in (parent, child, response_id):
        assert game.inspect(OTHER, identity)["state"] == "complete"
    after = state(game)
    assert pin in after.facts
    assert after.sheets["3"].identities == expected_identities
    assert after.bonds == expected_bonds
    assert after.sheets["3"].heat == before_roll.heat
    assert alpha.conditions(after, attacker, actor)
    assert game.inspect(OTHER, child)["result"]["response_play"] == response_id
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert game.inspect(OTHER, child)["receipt"] == receipt
    restarted = GameService(ledger, dice=game.dice)
    for identity, owner, actual in (
        (child, OTHER, receipt),
        (response_id, OTHER, response_receipt),
        (parent, PLAYER, parent_receipt),
    ):
        assert restarted.roll(owner, str(uuid4()), identity)["receipt"] == actual
    assert game.dice.calls == 3 and state(game) == after
    with ledger.engine.connect() as c:
        assert prove(restarted, c, after, value.id).receipt == receipt["id"]
        assert game.action(c, child)["data"]["alpha_counter_completed"]
        assert game.action(c, parent)["data"]["alpha"]["counter_child"] == child
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_LOW_PIN_KEEP" not in json.dumps(gateway.messages)
    assert "PRIVATE_BENEATH_COUNTER_FEEDBACK" not in json.dumps(gateway.messages)


def finish_pin_flirt(game, worker, gateway, parent, child):
    before = state(game)
    own = tuple(x.id for x in before.sheets["3"].identities if x.marked)[:2]
    theirs = tuple(x.id for x in before.sheets["2"].identities if x.marked)[:2]
    assert len(own) == 2
    request = next(x for x in game.choices(OTHER) if x["kind"] == "actor_flirt")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            request["id"],
            request["revision"],
            ChoiceAnswer(options=("name",), denied=own),
        )
    answer(game, OTHER, "actor_flirt", options=("name",), denied=own)
    request = next(x for x in game.choices(PLAYER) if x["kind"] == "target_flirt")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), request["id"], request["revision"], ChoiceAnswer(text="Forged")
        )
    for identity in (parent, child):
        assert game.inspect(OTHER, identity)["state"] != "complete"
    reopened = GameService(game.store, dice=game.dice)
    key = str(uuid4())
    reply = ChoiceAnswer(denied=theirs, text="PRIVATE_LOW_PIN_KEEP: use my chosen name")
    result = reopened.respond(PLAYER, key, request["id"], request["revision"], reply)
    after = state(game)
    assert reopened.respond(PLAYER, key, request["id"], request["revision"], reply) == result
    assert state(game) == after
    for uid, picked in (("3", own), ("2", theirs)):
        expected = before.sheets[uid].model_copy(deep=True)
        for identity in expected.identities:
            if identity.id in picked:
                identity.marked = False
        assert after.sheets[uid].identities == expected.identities
        assert after.sheets[uid].heat == before.sheets[uid].heat
    assert after.bonds == before.bonds
    for identity in (parent, child):
        assert game.inspect(OTHER, identity)["state"] == "complete"
    owed = next(
        x
        for x in game.own_obligations(OTHER)
        if x["kind"] == "flirt_followthrough" and x["action"] == child
    )
    tick(worker, gateway, 8)
    follow = game.fulfill(
        OTHER,
        str(uuid4()),
        900,
        owed["id"],
        "PRIVATE_LOW_PIN_KEEP: I use her chosen name",
    )["action_id"]
    tick(worker, gateway, 4)
    assert state(game).bonds == after.bonds
    request = next(x for x in game.choices(PLAYER) if x["kind"] == "followthrough_confirm")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), request["id"], request["revision"], ChoiceAnswer(flag=True)
        )
    answer(game, PLAYER, "followthrough_confirm", flag=True, text="She used my chosen name")
    assert game.inspect(OTHER, follow)["state"] == "complete"
    final = state(game)
    assert final.bonds["2:3"] == min(2, after.bonds["2:3"] + 1)
    assert next(x for x in final.obligations if x.id == owed["id"]).state == "fulfilled"
    return after.sheets["3"].identities, final.bonds


def test_native_beneath_counter_feedback_low_pin_continues_actual_owned_keep(
    ledger, tmp_path, monkeypatch
):
    episode(ledger, tmp_path, monkeypatch)
