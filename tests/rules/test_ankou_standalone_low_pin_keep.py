"""A real standalone low Beneath after Feedback reverses pin roles before owned responses."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_beneath_feedback import actual_social_source
from test_ankou_feedback import choose
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_feedback import FeedbackService, prepare_child, prove
from girlframe.services.onboarding import WorkflowError


def episode(ledger, tmp_path, monkeypatch, *, recipe="keep_your_head"):
    game, worker, gateway, parent, source = actual_social_source(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    assert source.beneath_counter_source is None
    committed = state(game).sheets["2"].model_copy(deep=True)
    choose(game, "purpose", target)
    private = FeedbackService(game).view(OTHER, source.id)
    assert not {"prepared", "identity", "heat_before", "heat_committed"} & set(private)
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=True,
        text="PRIVATE_STANDALONE_LOW_PIN: protect our friends",
    )
    replacement = next(x.id for x in committed.identities if not x.protected)
    answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replacement})
    before_roll = state(game).sheets["2"].model_copy(deep=True)
    assert before_roll.heat == committed.heat
    game.dice.faces = (1, 1)
    tick(worker, gateway, 4)
    pass_tags(game)
    receipt = game.inspect(PLAYER, parent)["receipt"]
    assert receipt and receipt["heat"] == 1 and receipt["pre_total"] == 3
    assert game.dice.calls == 1 and game.inspect(PLAYER, parent)["result"] is None

    # The target, not the original acting Ankou, owns this actual low result.
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "beneath_select")
    assert game.decision(OTHER, choice["id"])["beneath"]["level"] == "low"
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("pin",), text="I cannot select her low consequence"),
        )
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("pin",),
        text="PRIVATE_STANDALONE_LOW_PIN: pin the original acting Ankou",
    )
    pinned = state(game)
    pin = next(x for x in pinned.facts if x.get("kind") == "physical_pin")
    assert pin["action"] == parent and pin["owner"] == "3" and pin["target"] == "2"
    assert pin["owner_character"] == str(target.incarnation)
    assert pin["target_character"] == str(actor.incarnation)
    owed = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_pin_response")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), owed["id"], owed["revision"], ChoiceAnswer(options=("play",))
        )
    reopened = GameService(ledger, dice=game.dice)
    key = str(uuid4())
    response = ChoiceAnswer(options=("play",))
    outcome = reopened.respond(PLAYER, key, owed["id"], owed["revision"], response)
    saved = state(game)
    assert reopened.respond(PLAYER, key, owed["id"], owed["revision"], response) == outcome
    assert state(game) == saved
    expected = PlayInput(
        play=recipe,
        target=OTHER.user_id if recipe == "flirt" else None,
        parent=parent,
        heat=0,
        context="PRIVATE_STANDALONE_LOW_PIN: endure her pin without undoing it",
        trigger_confirmed=True,
    )
    with game.store.engine.connect() as c:
        assert prepare_child(game, c, PLAYER, saved, expected, 900) is None
        for person, attempt in (
            (OTHER, expected),
            (PLAYER, expected.model_copy(update={"source_work": source.id})),
            (PLAYER, expected.model_copy(update={"play": "check_sensors"})),
            (PLAYER, expected.model_copy(update={"target": PLAYER.user_id})),
        ):
            with pytest.raises(WorkflowError):
                prepare_child(game, c, person, saved, attempt, 900)
        if recipe == "flirt":
            for update in (
                {"target": None},
                {"target_actor": target},
                {"learned_keep_rider": "foreign-lesson"},
                {"kicked_puppy_basis": True},
                {"prince_exception": "foreign-demand"},
                {"piloting": True},
            ):
                with pytest.raises(WorkflowError):
                    prepare_child(game, c, PLAYER, saved, expected.model_copy(update=update), 900)
        missing_pin = saved.model_copy(deep=True)
        missing_pin.facts.remove(pin)
        with pytest.raises(WorkflowError, match="canonical actual low Beneath pin"):
            prepare_child(game, c, PLAYER, missing_pin, expected, 900)
    assert game.inspect(PLAYER, parent)["state"] == "awaiting_choices"
    request = next(x for x in reopened.choices(PLAYER) if x["kind"] == "beneath_response_play")
    decision = reopened.decision(PLAYER, request["id"])

    async def native_response():
        opened = current(PLAYER.user_id, 99661)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_play(opened, reopened, parent=decision, _pilot=True)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(OTHER.user_id, 99660))
        form.values.update(
            play=(recipe,),
            target=(str(OTHER.user_id),) if recipe == "flirt" else (),
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
        submitted = current(PLAYER.user_id, 99662)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        after = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == after

    game.dice.faces = (4, 4)
    asyncio.run(native_response())
    with game.store.engine.connect() as c:
        actions = t.m2["m2_actions"]
        child = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == ledger.campaign_id,
                actions.c.parent_id == parent,
                actions.c.actor_id == "2",
            )
        )
        assert child and not game.action(c, child)["data"].get("ankou_feedback")
        assert not game.action(c, child)["data"].get("ankou_feedback_child")
    tick(worker, gateway, 4)
    pass_tags(game)
    response_receipt = game.inspect(PLAYER, child)["receipt"]
    assert response_receipt and response_receipt["heat"] == 0 and game.dice.calls == 2
    if recipe == "flirt":
        expected_identities, expected_bonds = finish_pin_flirt(game, worker, gateway, parent, child)
    else:
        own = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
        with pytest.raises(WorkflowError):
            game.respond(
                OTHER,
                str(uuid4()),
                own["id"],
                own["revision"],
                ChoiceAnswer(options=("tough", "in_control"), denied=("desperate",)),
            )
        answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
        for identity in (parent, child):
            assert game.inspect(PLAYER, identity)["state"] != "complete"
        handler = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_keep")
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER, str(uuid4()), handler["id"], handler["revision"], ChoiceAnswer(flag=True)
            )
        answer(
            game,
            ADMIN,
            "handler_keep",
            flag=True,
            text="PRIVATE_STANDALONE_LOW_PIN: enough to endure",
        )
        expected_identities, expected_bonds = before_roll.identities, pinned.bonds
    for identity in (parent, child):
        assert game.inspect(PLAYER, identity)["state"] == "complete"
    after = state(game)
    assert pin in after.facts and after.order == pinned.order and after.bonds == expected_bonds
    assert after.sheets["2"].identities == expected_identities
    assert after.sheets["2"].heat == before_roll.heat
    assert game.inspect(PLAYER, parent)["result"]["response_play"] == child
    assert game.inspect(PLAYER, parent)["receipt"] == receipt
    restarted = GameService(ledger, dice=game.dice)
    for identity, actual in ((parent, receipt), (child, response_receipt)):
        assert restarted.roll(PLAYER, str(uuid4()), identity)["receipt"] == actual
    assert game.dice.calls == 2 and state(game) == after
    with ledger.engine.connect() as c:
        value = prove(restarted, c, after, source.id)
        assert value.receipt == receipt["id"] and value.choice == "purpose"
        assert value.purpose_given is True and value.child is None
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_STANDALONE_LOW_PIN" not in json.dumps(gateway.messages)
    assert "PRIVATE_BENEATH_FEEDBACK" not in json.dumps(gateway.messages)


def finish_pin_flirt(game, worker, gateway, parent, child):
    before = state(game)
    own = tuple(x.id for x in before.sheets["2"].identities if x.marked)[:2]
    theirs = tuple(x.id for x in before.sheets["3"].identities if x.marked)[:2]
    assert len(own) == 2
    request = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_flirt")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            request["id"],
            request["revision"],
            ChoiceAnswer(options=("name",), denied=own),
        )
    answer(game, PLAYER, "actor_flirt", options=("name",), denied=own)
    request = next(x for x in game.choices(OTHER) if x["kind"] == "target_flirt")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), request["id"], request["revision"], ChoiceAnswer(text="Forged")
        )
    for identity in (parent, child):
        assert game.inspect(PLAYER, identity)["state"] != "complete"
    reopened = GameService(game.store, dice=game.dice)
    key = str(uuid4())
    reply = ChoiceAnswer(denied=theirs, text="PRIVATE_STANDALONE_LOW_PIN: use my chosen name")
    result = reopened.respond(OTHER, key, request["id"], request["revision"], reply)
    after = state(game)
    assert reopened.respond(OTHER, key, request["id"], request["revision"], reply) == result
    assert state(game) == after
    for uid, picked in (("2", own), ("3", theirs)):
        expected = before.sheets[uid].model_copy(deep=True)
        for identity in expected.identities:
            if identity.id in picked:
                identity.marked = False
        assert after.sheets[uid].identities == expected.identities
        assert after.sheets[uid].heat == before.sheets[uid].heat
    assert after.bonds == before.bonds
    for identity in (parent, child):
        assert game.inspect(PLAYER, identity)["state"] == "complete"
    owed = next(
        x
        for x in game.own_obligations(PLAYER)
        if x["kind"] == "flirt_followthrough" and x["action"] == child
    )
    tick(worker, gateway, 8)
    follow = game.fulfill(
        PLAYER,
        str(uuid4()),
        900,
        owed["id"],
        "PRIVATE_STANDALONE_LOW_PIN: I use her chosen name",
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
    final = state(game)
    assert final.bonds["2:3"] == min(2, after.bonds["2:3"] + 1)
    assert next(x for x in final.obligations if x.id == owed["id"]).state == "fulfilled"
    return after.sheets["2"].identities, final.bonds


def test_standalone_accepted_feedback_low_pin_continues_actual_owned_keep(
    ledger, tmp_path, monkeypatch
):
    episode(ledger, tmp_path, monkeypatch)
