"""Two native Ankou preserve completed tear-reprisal ancestry through a pin response last mark."""

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
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, shift_status
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_feedback import FeedbackService, prepare_child, prove
from girlframe.services.m3_ankou_pin import source_binding
from girlframe.services.onboarding import WorkflowError


def test_nested_tear_pin_feedback_preserves_actual_two_ankou_sources(ledger, tmp_path, monkeypatch):
    import test_ankou_beneath_feedback
    import test_m2_game

    creation_ready = test_m2_game.ready
    monkeypatch.setattr(
        test_m2_game,
        "ready",
        lambda *args, **kwargs: creation_ready(
            *args, **(kwargs | {"other_frame": "PROJECT ANKOU"})
        ),
    )
    selected = test_m2_game.selected
    monkeypatch.setattr(
        test_m2_game, "selected", lambda girl, frame: selected(girl, "PROJECT ANKOU")
    )
    original_ready = test_ankou_beneath_feedback.ready

    def prepared_other(*args):
        result = original_ready(*args)
        _, game, worker, gateway, _, _ = result
        identities = [x.id for x in state(game).sheets["3"].identities if not x.marked]
        for identity in identities[:-1]:
            game.dice.faces = (4, 4)
            action = game.begin(
                OTHER,
                str(uuid4()),
                900,
                state(game).sheets["3"].revision,
                PlayInput(
                    play="keep_your_head",
                    identity=identity,
                    gain=1,
                    heat=1,
                    trigger_confirmed=True,
                    context="PRIVATE_NESTED_TEAR prior owned Keep",
                ),
            )["action_id"]
            tick(worker, gateway, 3)
            pass_tags(game)
            answer(
                game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("desperate",)
            )
            answer(game, ADMIN, "handler_keep", flag=True, text="Enough to endure")
            assert game.inspect(OTHER, action)["state"] == "complete"
            tick(worker, gateway, 5)
        return result

    monkeypatch.setattr(test_ankou_beneath_feedback, "ready", prepared_other)
    recipe = "keep_your_head"
    game, worker, gateway, parent, source = actual_social_source(ledger, tmp_path, monkeypatch)
    pinner, pinned = current_ref(state(game), 2), current_ref(state(game), 3)
    assert source.beneath_counter_source is None
    committed = state(game).sheets["2"].model_copy(deep=True)
    lost = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    choose(game, "tear", pinned, asset=lost.id)
    assert state(game).sheets["2"].heat == 5
    assert lost not in state(game).sheets["2"].assets
    game.dice.faces = (1, 2)
    reprisal = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=OTHER.user_id,
            parent=parent,
            source_work=source.id,
            heat=5,
            trigger_confirmed=True,
            context="PRIVATE_TEAR_PIN actual original reprisal",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="PRIVATE_TEAR_PIN my actual name")
    assert game.inspect(PLAYER, reprisal)["state"] == "complete"
    resolved = feedback.get(state(game), source.id)
    assert resolved.phase == "resolved" and resolved.child == reprisal
    private = FeedbackService(game).view(OTHER, source.id)
    assert not {"prepared", "identity", "heat_before", "heat_committed"} & set(private)
    before_roll = state(game).sheets["2"].model_copy(deep=True)
    assert before_roll.heat == committed.heat
    game.dice.faces = (6, 6)
    tick(worker, gateway, 4)
    pass_tags(game)
    receipt = game.inspect(PLAYER, parent)["receipt"]
    assert receipt and receipt["heat"] == 1 and receipt["pre_total"] == 13
    assert game.dice.calls == 2 and game.inspect(PLAYER, parent)["result"] is None
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_select")
    assert game.decision(PLAYER, choice["id"])["beneath"]["level"] == "high"
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("status", "pin"), text="I cannot choose her high result"),
        )
    expected_status = state(game).model_copy(deep=True)
    shift_status(expected_status, OTHER.user_id, -1)
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("status", "pin"),
        text="PRIVATE_STANDALONE_PIN: lower her Status and physically pin her",
    )
    saved = state(game)
    assert saved.order == expected_status.order
    pin = next(x for x in saved.facts if x.get("kind") == "physical_pin")
    assert pin["action"] == parent and pin["owner"] == "2" and pin["target"] == "3"
    assert pin["owner_character"] == str(pinner.incarnation)
    assert pin["target_character"] == str(pinned.incarnation)
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
        parent=parent,
        heat=0,
        context="PRIVATE_STANDALONE_PIN: endure the actual pin without undoing it",
        trigger_confirmed=True,
    )
    with game.store.engine.connect() as c:
        assert prepare_child(game, c, OTHER, saved, expected, 900) is None
        missing_asset = saved.model_copy(deep=True)
        missing_asset.sheets["2"].assets.append(lost)
        with pytest.raises(WorkflowError, match="original source-bound reprisal"):
            prepare_child(game, c, OTHER, missing_asset, expected, 900)
        for person, attempt in (
            (PLAYER, expected),
            (OTHER, expected.model_copy(update={"source_work": source.id})),
            (OTHER, expected.model_copy(update={"play": "check_sensors"})),
            (OTHER, expected.model_copy(update={"target": OTHER.user_id})),
        ):
            with pytest.raises(WorkflowError):
                prepare_child(game, c, person, saved, attempt, 900)
        if recipe == "flirt":
            for update in (
                {"target": None},
                {"target_actor": pinner},
                {"learned_keep_rider": "foreign-lesson"},
                {"kicked_puppy_basis": True},
                {"prince_exception": "foreign-demand"},
                {"piloting": True},
            ):
                with pytest.raises(WorkflowError):
                    prepare_child(game, c, OTHER, saved, expected.model_copy(update=update), 900)
        missing_pin = saved.model_copy(deep=True)
        missing_pin.facts.remove(pin)
        with pytest.raises(WorkflowError, match="canonical actual high Beneath pin"):
            prepare_child(game, c, OTHER, missing_pin, expected, 900)
    assert game.inspect(PLAYER, parent)["state"] == "awaiting_choices"
    last_identity = next(x.id for x in state(game).sheets["3"].identities if not x.marked)
    assert sum(not x.marked for x in state(game).sheets["3"].identities) == 1
    request = next(x for x in reopened.choices(OTHER) if x["kind"] == "beneath_response_play")
    decision = reopened.decision(OTHER, request["id"])

    async def native_response():
        opened = current(OTHER.user_id, 99651)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_play(opened, reopened, parent=decision, _pilot=True)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(PLAYER.user_id, 99650))
        form.values.update(
            play=(recipe,),
            target=(str(PLAYER.user_id),) if recipe == "flirt" else (),
            identity=(last_identity,),
            gain=("1",),
            pair_share=("0",),
            heat=("1",),
            disposable_heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context=expected.context,
        )
        submitted = current(OTHER.user_id, 99652)
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
                actions.c.actor_id == "3",
            )
        )
        assert child and not game.action(c, child)["data"].get("ankou_feedback")
        assert not game.action(c, child)["data"].get("ankou_feedback_child")
    tick(worker, gateway, 4)
    second = next(x for x in feedback.sources(state(game)) if x.action == child)
    assert second.phase == "choice" and second.pin_source
    assert game.dice.calls == 2 and game.inspect(OTHER, child)["receipt"] is None
    with ledger.engine.connect() as c:
        assert source_binding(game, c, state(game), game.action(c, child)) == second.pin_source
        missing = state(game).model_copy(deep=True)
        missing.sheets["2"].assets.append(lost)
        with pytest.raises(WorkflowError, match="original source-bound reprisal"):
            source_binding(game, c, missing, game.action(c, child))
    answer(
        game,
        OTHER,
        "ankou_feedback_choice",
        options=("purpose",),
        fields={"target": pinner.token},
        text="PRIVATE_NESTED_TEAR purpose",
    )
    answer(
        game,
        PLAYER,
        "ankou_feedback_purpose",
        flag=True,
        text="PRIVATE_NESTED_TEAR preserve yourself",
    )
    replacement = next(x.id for x in state(game).sheets["3"].identities if not x.protected)
    answer(game, OTHER, "ankou_feedback_identity", fields={"replace": replacement})
    second_resolved = feedback.get(state(game), second.id)
    assert second_resolved.new_identity
    tick(worker, gateway, 4)
    pass_tags(game)
    response_receipt = game.inspect(OTHER, child)["receipt"]
    assert response_receipt and response_receipt["heat"] == 1 and game.dice.calls == 3
    if recipe == "keep_your_head":
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
        assert game.inspect(PLAYER, parent)["state"] != "complete"
        assert game.inspect(OTHER, child)["state"] != "complete"
        handler = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_keep")
        with pytest.raises(WorkflowError):
            game.respond(
                OTHER, str(uuid4()), handler["id"], handler["revision"], ChoiceAnswer(flag=True)
            )
        answer(
            game, ADMIN, "handler_keep", flag=True, text="PRIVATE_STANDALONE_PIN: enough to endure"
        )
        expected_identities = before_roll.identities
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(OTHER, child)["state"] == "complete"
    after = state(game)
    assert pin in after.facts and after.order == expected_status.order
    assert after.sheets["2"].identities == expected_identities
    assert after.sheets["2"].heat == before_roll.heat
    assert game.inspect(PLAYER, parent)["result"]["response_play"] == child
    assert game.inspect(PLAYER, parent)["receipt"] == receipt
    restarted = GameService(ledger, dice=game.dice)
    for identity, owner, actual in (
        (parent, PLAYER, receipt),
        (child, OTHER, response_receipt),
    ):
        assert restarted.roll(owner, str(uuid4()), identity)["receipt"] == actual
    assert game.dice.calls == 3 and state(game) == after
    with ledger.engine.connect() as c:
        value = prove(restarted, c, after, source.id)
        assert value.receipt == receipt["id"] and value.choice == "tear"
        assert value.purpose_given is None and value.child == reprisal
        assert lost not in after.sheets["2"].assets
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_STANDALONE_PIN" not in json.dumps(gateway.messages)
    assert "PRIVATE_BENEATH_FEEDBACK" not in json.dumps(gateway.messages)

    assert "PRIVATE_TEAR_PIN" not in json.dumps(gateway.messages)
    assert "PRIVATE_NESTED_TEAR" not in json.dumps(gateway.messages)
    assert feedback.get(after, source.id).choice == "tear"
    assert feedback.get(after, second.id).receipt == response_receipt["id"]
