"""Counter tear reprisal stays bound through the pinned Ankou's final-mark Feedback."""

import json
from uuid import uuid4

import pytest
from test_ankou_beneath_counter_feedback import last_counter
from test_ankou_dose_counter_feedback import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_feedback import prove
from girlframe.services.m3_ankou_pin import source_binding
from girlframe.services.onboarding import WorkflowError


def test_counter_tear_pin_keeps_two_native_feedback_sources(ledger, tmp_path, monkeypatch):
    import test_alpha_dose_counter as counter

    creation_ready = counter.creation_ready
    monkeypatch.setattr(
        counter,
        "creation_ready",
        lambda *args, **kwargs: creation_ready(*args, **(kwargs | {"frame": "PROJECT ANKOU"})),
    )
    game, worker, gateway, identity = ready(ledger, tmp_path, monkeypatch)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    # Actual ordinary Plays leave the original Alpha one unmarked Identity.
    marks = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for mark in marks[:-1]:
        game.dice.faces = (4, 4)
        earlier = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                identity=mark,
                gain=1,
                heat=1,
                trigger_confirmed=True,
                context="PRIVATE_COUNTER_TEAR prior pressure",
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
        answer(game, ADMIN, "handler_keep", flag=True, text="Actual sufficient response")
        assert game.inspect(PLAYER, earlier)["state"] == "complete"
        tick(worker, gateway, 5)
    parent, first_receipt, counter_id, first = last_counter(game, worker, gateway, identity)
    alpha, ankou = current_ref(state(game), 2), current_ref(state(game), 3)
    lost = next(x for x in state(game).sheets["3"].assets if x.family == "frame" and not x.void)
    answer(
        game,
        OTHER,
        "ankou_feedback_choice",
        options=("tear",),
        fields={"target": alpha.token, "asset": lost.id},
        text="PRIVATE_COUNTER_TEAR my actual tear",
    )
    assert lost not in state(game).sheets["3"].assets
    game.dice.faces = (1, 1)
    reprisal = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="flirt",
            target=PLAYER.user_id,
            parent=counter_id,
            source_work=first.id,
            heat=state(game).sheets["3"].heat,
            trigger_confirmed=True,
            context="PRIVATE_COUNTER_TEAR actual reprisal",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_flirt", options=("name",))
    answer(game, PLAYER, "target_flirt", text="PRIVATE_COUNTER_TEAR my actual name")
    assert game.inspect(OTHER, reprisal)["state"] == "complete"
    resolved = feedback.get(state(game), first.id)
    assert resolved.phase == "resolved" and resolved.child == reprisal
    assert resolved.beneath_counter_source and resolved.beneath_source
    assert resolved.new_identity is None
    game.dice.faces = (6, 6)
    tick(worker, gateway, 4)
    pass_tags(game)
    counter_receipt = game.inspect(OTHER, counter_id)["receipt"]
    assert counter_receipt and game.dice.calls == 3
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("status", "pin"),
        text="PRIVATE_COUNTER_TEAR my actual high pin",
    )
    pin = next(x for x in state(game).facts if x.get("kind") == "physical_pin")
    assert pin["owner"] == "3" and pin["target"] == "2"
    answer(game, PLAYER, "beneath_pin_response", options=("play",))
    remaining = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    assert remaining == marks[-1:]
    response = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            parent=counter_id,
            identity=remaining[0],
            gain=1,
            heat=1,
            trigger_confirmed=True,
            context="PRIVATE_COUNTER_TEAR my owned response",
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    second = next(x for x in feedback.sources(state(game)) if x.action == response)
    assert second.phase == "choice" and second.pin_source
    assert game.inspect(PLAYER, response)["receipt"] is None and game.dice.calls == 3
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), second.id) == second
        assert source_binding(game, c, state(game), game.action(c, response)) == second.pin_source
        missing = state(game).model_copy(deep=True)
        missing.sheets["3"].assets.append(lost)
        with pytest.raises(WorkflowError, match="original source-bound reprisal"):
            source_binding(game, c, missing, game.action(c, response))
        cyclic = state(game).model_copy(deep=True)
        original = feedback.get(cyclic, first.id)
        feedback.put(cyclic, original.model_copy(update={"pin_source": second.pin_source}))
        with pytest.raises(WorkflowError):
            source_binding(game, c, cyclic, game.action(c, response))
    answer(
        game,
        PLAYER,
        "ankou_feedback_choice",
        options=("purpose",),
        fields={"target": ankou.token},
        text="PRIVATE_COUNTER_TEAR my purpose request",
    )
    answer(
        game, OTHER, "ankou_feedback_purpose", flag=True, text="PRIVATE_COUNTER_TEAR stay yourself"
    )
    replace = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
    answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
    game.dice.faces = (4, 4)
    tick(worker, gateway, 4)
    pass_tags(game)
    response_receipt = game.inspect(PLAYER, response)["receipt"]
    assert response_receipt and game.dice.calls == 4
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    answer(game, ADMIN, "handler_keep", flag=True, text="PRIVATE_COUNTER_TEAR sufficient")
    for owner, action in ((PLAYER, parent), (OTHER, counter_id), (PLAYER, response)):
        assert game.inspect(owner, action)["state"] == "complete"
    saved = state(game)
    assert pin in saved.facts and lost not in saved.sheets["3"].assets
    reopened = GameService(ledger, dice=game.dice)
    for owner, action, receipt in (
        (PLAYER, parent, first_receipt),
        (OTHER, counter_id, counter_receipt),
        (PLAYER, response, response_receipt),
    ):
        assert reopened.roll(owner, str(uuid4()), action)["receipt"] == receipt
    assert state(game) == saved and game.dice.calls == 4
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_COUNTER_TEAR" not in json.dumps(gateway.messages)
