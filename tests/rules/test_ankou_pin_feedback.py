"""Actual Beneath pin, target-owned Keep, mandatory last mark and real parent closure."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_feedback import begin_mark, choose, finish_keep, ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_feedback import prove
from girlframe.services.m3_ankou_pin import source_binding, validate_pending
from girlframe.services.onboarding import WorkflowError


def actual_pin_response(game, worker, gateway):
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        prior = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, prior)
    game.dice = Dice((6, 6))
    parent = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=PLAYER.user_id,
            heat=0,
            context="PRIVATE_PIN_SOURCE: pin the actual other Girl",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("tag", "pin"),
        fields={"tag": "PRIVATE_PIN_TAG: pinned"},
        text="PRIVATE_PIN_CONTACT: physically pin her down",
    )
    answer(game, PLAYER, "beneath_pin_response", options=("play",))
    parent_receipt = game.inspect(OTHER, parent)["receipt"]
    assert parent_receipt is not None and game.dice.calls == 1
    request = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_response_play")
    decision = game.decision(PLAYER, request["id"])

    async def native_response():
        first = current(PLAYER.user_id, 99181)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_play(first, game, parent=decision, _pilot=True)
        form = first.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("keep_your_head",),
            target=(),
            identity=(identities[-1],),
            gain=("1",),
            pair_share=("0",),
            heat=("1",),
            disposable_heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="PRIVATE_PIN_KEEP: rely on my own last Identity while pinned",
        )
        response = current(PLAYER.user_id, 99182)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        with game.store.engine.connect() as c:
            return json.loads(
                c.scalar(
                    sa.select(t.commands.c.outcome_json).where(
                        t.commands.c.campaign_id == game.store.campaign_id,
                        t.commands.c.interaction_key == str(response.id),
                    )
                )
            )["action_id"]

    game.dice = Dice((4, 4))
    before_heat = state(game).sheets["2"].heat
    action = asyncio.run(native_response())
    tick(worker, gateway, 3)
    if not any(x.action == action for x in feedback.sources(state(game))):
        game.roll(PLAYER, "m2.confirmed_roll:" + action, action)
    value = next(x for x in feedback.sources(state(game)) if x.action == action)
    assert value.phase == "choice" and value.pin_source is not None
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    assert value.heat_before == before_heat
    assert value.heat_committed == state(game).sheets["2"].heat == before_heat
    assert next(x for x in state(game).sheets["2"].identities if x.id == identities[-1]).marked
    assert game.inspect(OTHER, parent)["receipt"] == parent_receipt
    assert game.inspect(OTHER, parent)["state"] == "awaiting_choices"
    with game.store.engine.connect() as c:
        saved = game.action(c, action)
        assert saved["parent_id"] == parent
        assert prove(game, c, state(game), value.id) == value
        assert source_binding(game, c, state(game), saved) == value.pin_source
        forged = copy.deepcopy(saved)
        forged["data"]["prepared"]["source_work"] = "foreign-required-work"
        with pytest.raises(WorkflowError, match="SOURCE_ANKOU_PIN_PORT_REQUIRED"):
            source_binding(game, c, state(game), forged)
        missing_pin = state(game).model_copy(deep=True)
        missing_pin.facts = [
            x
            for x in missing_pin.facts
            if not (x.get("kind") == "physical_pin" and x.get("action") == parent)
        ]
        with pytest.raises(WorkflowError, match="canonical original physical pin"):
            source_binding(game, c, missing_pin, saved)
    return parent, parent_receipt, action, value


@pytest.mark.parametrize("given", [True, False])
def test_native_pin_response_feedback_preserves_original_pin_and_real_response(
    ledger, tmp_path, monkeypatch, given
):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    counterpart = current_ref(state(game), OTHER.user_id)
    parent, parent_receipt, action, value = actual_pin_response(game, worker, gateway)
    choose(game, "purpose", counterpart)
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_PIN_PURPOSE: defend this place" if given else "I give no purpose",
    )
    assert game.dice.calls == 0
    if given:
        replace = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
        answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
        with ledger.engine.connect() as c:
            validate_pending(game, c, state(game), game.action(c, action))
        before_roll = state(game).sheets["2"].model_copy(deep=True)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, action)
        receipt = game.inspect(PLAYER, action)["receipt"]
        assert receipt["heat"] == 1 and game.dice.calls == 1
        assert state(game).sheets["2"].heat == before_roll.heat
        assert state(game).sheets["2"].identities == before_roll.identities
    else:
        assert is_helpless(state(game), value.actor, counterpart)
        assert is_helpless(state(game), value.actor, current_ref(state(game), OTHER.user_id))
        assert feedback.get(state(game), value.id).phase == "ended"
        assert game.inspect(PLAYER, action)["receipt"] is None and game.dice.calls == 0
    assert game.inspect(PLAYER, action)["state"] == "complete"
    original = game.inspect(OTHER, parent)
    assert original["state"] == "complete" and original["receipt"] == parent_receipt
    assert original["result"]["response_play"] == action
    assert original["result"]["pinned_response_performed"] is given
    assert original["result"]["pinned_response_feedback"] == value.id
    assert "escaped" not in original["result"] and "helpless" not in original["result"]
    assert any(
        x.get("kind") == "physical_pin" and x.get("action") == parent for x in state(game).facts
    )
    assert (
        len([x for x in state(game).sheets["2"].tags if x.label == "PRIVATE_PIN_TAG: pinned"]) == 1
    )
    restarted = GameService(game.store, dice=game.dice)
    assert restarted.inspect(PLAYER, action) == game.inspect(PLAYER, action)
    if given:
        assert restarted.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
        assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        verified = prove(restarted, c, state(restarted), value.id)
        assert verified.receipt == (receipt["id"] if given else None)
        choice = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == ledger.campaign_id,
                    t.m2["m2_choices"].c.action_id == parent,
                    t.m2["m2_choices"].c.kind == "beneath_response_play",
                )
            )
            .mappings()
            .one()
        )
        assert choice["state"] == "completed_by_child"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_PIN" not in json.dumps(gateway.messages)
