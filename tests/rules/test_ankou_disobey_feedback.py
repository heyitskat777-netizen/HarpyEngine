"""A genuine received Order keeps its native refusal, costs and one next-roll bonus."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_feedback import begin_mark, choose, finish_keep
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_physical_operations import place
from test_refusal_service import ready as refusal_ready

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_disobey import pre_roll, source_binding
from girlframe.services.m3_ankou_feedback import prove
from girlframe.services.onboarding import WorkflowError


def actual_order_source(ledger, tmp_path, monkeypatch):
    import test_strain_service

    original = test_strain_service.service
    monkeypatch.setattr(
        test_strain_service,
        "service",
        lambda *a, **kw: original(*a, **(kw | {"frame": "PROJECT ANKOU", "girl": "STIM-BLISSED"})),
    )
    _, game, bonus_id = refusal_ready(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(feedback.RULE,))
    worker, gateway = GameWorker(game), Gateway()
    with ledger.transaction() as c:
        placed = place(place(state(game), 2, mode="outside_frame"), 3, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.prior_actual_body_context", placed)
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        prior = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, prior)
    game.dice = Dice((4, 5))
    issued = game.issue_order(
        ADMIN, str(uuid4()), 900, PLAYER.user_id, "PRIVATE_ORDER: hold position"
    )
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("disobey",))
    request = next(x for x in game.choices(PLAYER) if x["kind"] == "order_disobey")
    parent = game.decision(PLAYER, request["id"])

    async def native_refusal():
        first = current(PLAYER.user_id, 99931)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_play(first, game, parent=parent, _pilot=True)
        form = first.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("disobey_orders",),
            target=(),
            identity=(identities[-1],),
            gain=("1",),
            pair_share=("0",),
            heat=("1",),
            disposable_heat=("0",),
            piloting=("no",),
            witnessed=("yes",),
            context="PRIVATE_ORDER_REFUSAL: rely on my last Identity to resist",
            trigger=("yes",),
        )
        response = current(PLAYER.user_id, 99932)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        with ledger.engine.connect() as c:
            return json.loads(
                c.scalar(
                    sa.select(t.commands.c.outcome_json).where(
                        t.commands.c.campaign_id == ledger.campaign_id,
                        t.commands.c.interaction_key == str(response.id),
                    )
                )
            )["action_id"]

    action = asyncio.run(native_refusal())
    tick(worker, gateway, 3)
    if not any(x.action == action for x in feedback.sources(state(game))):
        # Surface the worker's swallowed workflow failure without fabricating its source.
        game.roll(PLAYER, "m2.confirmed_roll:" + action, action)
    value = next(x for x in feedback.sources(state(game)) if x.action == action)
    assert value.phase == "choice" and value.refusal_source is not None
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    assert state(game).sheets["2"].heat == value.heat_committed == 0
    assert next(x for x in state(game).sheets["2"].identities if x.id == identities[-1]).marked
    assert state(game).refusal_bonuses[0].id == bonus_id
    assert state(game).refusal_bonuses[0].action is None
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        assert saved["parent_id"] == issued["action_id"]
        assert saved["data"]["prepared"]["order_id"] == issued["order_id"]
        assert prove(game, c, state(game), value.id) == value
        assert source_binding(game, c, state(game), saved) == value.refusal_source
        forged = copy.deepcopy(saved)
        forged["data"]["prepared"]["order_id"] = "a-different-order"
        with pytest.raises(WorkflowError, match="SOURCE_ANKOU_REFUSAL"):
            source_binding(game, c, state(game), forged)
    return game, worker, gateway, issued, action, value


def finish_readback(game, worker, gateway, issued, action, value, calls):
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, issued["action_id"])["state"] == "complete"
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["heat"] == 1
    assert receipt["pre_modifiers"] == [{"source": "control_slips", "amount": 2}]
    assert state(game).refusal_bonuses[0].action == action
    assert state(game).refusal_bonuses[0].actor == value.actor
    restarted = GameService(game.store, dice=game.dice)
    assert restarted.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    assert game.dice.calls == calls
    with game.store.engine.connect() as c:
        assert prove(restarted, c, state(restarted), value.id).receipt == receipt["id"]
        original = restarted.action(c, issued["action_id"])
        assert original["data"]["result"]["response_play"] == action
    tick(worker, gateway, 5)
    with game.store.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_ORDER" not in json.dumps(gateway.messages)


@pytest.mark.parametrize("given", [True, False])
def test_native_order_feedback_purpose_keeps_exact_parent_and_unspent_bonus_until_roll(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway, issued, action, value = actual_order_source(
        ledger, tmp_path, monkeypatch
    )
    target = current_ref(state(game), OTHER.user_id)
    choose(game, "purpose", target)
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_ORDER_PURPOSE: protect the people here" if given else "I refuse",
    )
    assert state(game).refusal_bonuses[0].action is None and game.dice.calls == 0
    if not given:
        assert feedback.get(state(game), value.id).phase == "ended"
        assert is_helpless(state(game), value.actor, target)
        assert game.inspect(PLAYER, action)["receipt"] is None
        assert game.inspect(PLAYER, action)["state"] == "complete"
        assert game.inspect(PLAYER, issued["action_id"])["state"] == "complete"
        with ledger.engine.connect() as c:
            assert not game.action(c, action)["data"]["result"].get("can_disobey")
            assert prove(game, c, state(game), value.id).rolled_event is None
        tick(worker, gateway, 5)
        with ledger.engine.connect() as c:
            assert game.lock(c, 900)["state"] == "released"
        assert state(game).refusal_bonuses[0].action is None and game.dice.calls == 0
        return
    replace = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
    answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        pre_roll(game, c, state(game), saved)
        forged = copy.deepcopy(saved)
        forged["data"]["m3_refusal"] = []
        with pytest.raises(WorkflowError, match="original Feedback-held direct Order"):
            pre_roll(game, c, state(game), forged)
    original_identities = state(game).sheets["2"].identities
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.inspect(PLAYER, action)["receipt"]["pre_total"] == 12
    assert state(game).order == (3, 2)
    answer(game, PLAYER, "actor_disobey", flag=True)
    answer(game, ADMIN, "handler_disobey", flag=True)
    assert state(game).sheets["2"].identities == original_identities
    assert state(game).sheets["2"].heat == 2
    assert game.inspect(PLAYER, action)["result"]["can_disobey"] is True
    assert any(
        x.kind == "punishment" and x.owner == PLAYER.user_id for x in state(game).obligations
    )
    finish_readback(game, worker, gateway, issued, action, value, 1)


def test_native_order_feedback_tear_keeps_bonus_for_original_roll_after_actual_reprisal(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, issued, action, value = actual_order_source(
        ledger, tmp_path, monkeypatch
    )
    target = current_ref(state(game), OTHER.user_id)
    lost = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    choose(game, "tear", target, asset=lost.id)
    assert state(game).sheets["2"].heat == 5
    assert not any(x.id == lost.id for x in state(game).sheets["2"].assets)
    game.dice = Dice((1, 2))
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=OTHER.user_id,
            parent=action,
            source_work=value.id,
            heat=5,
            context="PRIVATE_ORDER_REPRISAL: demand the other person's actual name",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="PRIVATE_ORDER_ANSWER: my name")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert state(game).refusal_bonuses[0].action is None
    assert game.dice.calls == 1 and game.inspect(PLAYER, action)["receipt"] is None
    game.dice.faces = (1, 1)
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.inspect(PLAYER, action)["receipt"]["pre_total"] == 5
    assert not any(x["kind"] == "actor_disobey" for x in game.choices(PLAYER))
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert state(game).sheets["2"].heat == 0
    assert game.inspect(PLAYER, action)["result"]["can_disobey"] is False
    finish_readback(game, worker, gateway, issued, action, value, 2)
