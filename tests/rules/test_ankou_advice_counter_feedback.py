"""Native Oldgen counter, actual last mark, owned Feedback and genuine advice listening."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick
from test_mission_ui import current
from test_oldgen import native_choice
from test_princess_oldgen_advice import pass_directed

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine import m3_oldgen as advice
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_intracadre_marriage import rank
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_advice import source_binding
from girlframe.services.m3_ankou_feedback import FeedbackService, prove
from girlframe.services.m3_oldgen import prove_advice
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    import test_oldgen_sleep_counter as counter

    creation_ready = counter.creation_ready
    monkeypatch.setattr(
        counter,
        "creation_ready",
        lambda *args, **kwargs: creation_ready(
            *args, **(kwargs | {"other_frame": "PROJECT ANKOU"})
        ),
    )
    selected = counter.selected
    monkeypatch.setattr(
        counter,
        "selected",
        lambda girl, frame: selected(girl, "PROJECT ANKOU" if frame == "JANUS-B" else frame),
    )
    game, worker, gateway = counter.ready(store, tmp_path, monkeypatch)
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(feedback.RULE, alpha.RULE, advice.RULE, advice.ADVICE),
    )
    identities = [x.id for x in state(game).sheets["3"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
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
                context="Actual earlier pressure and reliance on my own Identity",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_directed(game)
        answer(game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
        answer(game, ADMIN, "handler_keep", flag=True, text="Actual sufficient source result")
        assert game.inspect(OTHER, action)["state"] == "complete"
        tick(worker, gateway, 5)
    return game, worker, gateway, identities[-1]


def last_counter(game, worker, gateway, identity):
    game.dice = Dice((1, 1))
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=current_ref(state(game), 3),
            heat=0,
            context="PRIVATE_ADVICE_COUNTER_FEEDBACK: original Alpha attack",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_directed(game)
    parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    assert parent_receipt and game.dice.calls == 1
    answer(game, OTHER, "alpha_low", options=("counter_broken",))
    request = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_counter_play")

    async def native():
        opened = current(OTHER.user_id, 99381)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, request["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert "identity" in {x.key for x in form.fields}
        assert not await form.interaction_check(current(PLAYER.user_id, 99380))
        form.values.update(
            play=(advice.PLAY,),
            identity=(identity,),
            gain=("1",),
            heat=("1",),
            context="PRIVATE_ADVICE_COUNTER_FEEDBACK: answer using my actual last Identity",
        )
        submitted = current(OTHER.user_id, 99382)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    game.dice.faces = (3, 4)
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
    assert value.phase == "choice" and value.advice_source is not None
    assert value.heat_before == value.heat_committed == before.sheets["3"].heat
    assert state(game).sheets["3"].heat == before.sheets["3"].heat
    assert next(x for x in state(game).sheets["3"].identities if x.id == identity).marked
    assert game.dice.calls == 1 and game.inspect(OTHER, child)["receipt"] is None
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert game.inspect(PLAYER, parent)["state"] == "awaiting_choices"
    with game.store.engine.connect() as c:
        saved = game.action(c, child)
        assert prove(game, c, state(game), value.id) == value
        assert source_binding(game, c, state(game), saved) == value.advice_source
        wrong = copy.deepcopy(saved)
        wrong["data"]["alpha_counter_source"]["choice"] = "not-this-opportunity"
        with pytest.raises(WorkflowError, match="counter requirement"):
            source_binding(game, c, state(game), wrong)
        wrong = copy.deepcopy(saved)
        wrong["data"]["oldgen"]["caster"] = ADMIN.user_id
        with pytest.raises(WorkflowError, match="original ordinary Alpha"):
            source_binding(game, c, state(game), wrong)
    return parent, parent_receipt, child, value


@pytest.mark.parametrize("given", [True, False])
def test_native_advice_counter_feedback_preserves_listening_and_parent(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway, identity = ready(ledger, tmp_path, monkeypatch)
    parent, parent_receipt, child, value = last_counter(game, worker, gateway, identity)
    actor, attacker = current_ref(state(game), 3), current_ref(state(game), 2)
    committed = state(game).sheets["3"].model_copy(deep=True)
    original_assets = state(game).sheets["2"].assets
    # The actual root owns the shared scene lock, including its unrolled child.
    with pytest.raises(WorkflowError, match="Recover the root action"):
        game.abort(ADMIN, str(uuid4()), child)
    game.abort(ADMIN, str(uuid4()), parent)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == parent)
    assert saved["rolled"] and not saved["cancellable"] and saved["descendants"] == 1
    assert not any(x["id"] == child for x in recovery.saved(OTHER))
    recovery.recover(PLAYER, "recover-original-advice-counter-feedback", parent, saved["revision"])
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
        text="PRIVATE_ADVICE_COUNTER_FEEDBACK: actual purpose plea",
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
        text="PRIVATE_ADVICE_COUNTER_FEEDBACK: keep us safe" if given else "I give no purpose",
    )
    before_status = rank(state(game), 3)
    if given:
        replacement = next(x.id for x in state(game).sheets["3"].identities if not x.protected)
        answer(game, OTHER, "ankou_feedback_identity", fields={"replace": replacement})
        before_roll = state(game).sheets["3"].model_copy(deep=True)
        tick(worker, gateway, 4)
        pass_directed(game)
        receipt = game.inspect(OTHER, child)["receipt"]
        assert receipt["heat"] == 1 and game.dice.calls == 2
        assert state(game).sheets["3"].heat == before_roll.heat
        assert state(game).sheets["3"].identities == before_roll.identities
        assert game.inspect(PLAYER, parent)["state"] == "awaiting_choices"
        assert not alpha.conditions(state(game), attacker, actor)
        assert rank(state(game), 3) == max(0, before_status - 1)
        native_choice(
            game, OTHER, "oldgen_write_maxim", "PRIVATE_ADVICE_COUNTER_MAXIM: keep yourself alive"
        )
        owed = next(x for x in game.choices(PLAYER) if x["kind"] == "oldgen_listen")
        with pytest.raises(WorkflowError):
            game.respond(
                OTHER,
                str(uuid4()),
                owed["id"],
                owed["revision"],
                ChoiceAnswer(text="I cannot perform the original Alpha's listening"),
            )
        assert game.inspect(OTHER, child)["state"] != "complete"
        assert game.inspect(PLAYER, parent)["state"] != "complete"
        assert not alpha.conditions(state(game), attacker, actor)
        native_choice(game, PLAYER, "oldgen_listen", "I actually sit and hear her advice")
        with ledger.engine.connect() as c:
            original = prove_advice(game, c, state(game), child)
            assert original.actor == actor and original.target == attacker
            assert original.total == 8 and original.heat == 1
            assert original.caster == 3 and original.counterpart == 2
            completed = game.action(c, child)["data"]["alpha_counter_completed"]
            assert c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == completed)) == "2"
            assert c.scalar(
                sa.select(t.m2["m2_responses"].c.event_id).where(
                    t.m2["m2_responses"].c.choice_id == owed["id"]
                )
            )
        maxim = next(x for x in advice.records(state(game), advice.Maxim) if x.advice == child)
        assert maxim.owner == actor and maxim.subject == attacker
        assert state(game).sheets["2"].assets == original_assets
        assert alpha.conditions(state(game), attacker, actor)
        assert game.dice.calls == 2
    else:
        receipt = None
        assert game.dice.calls == 1 and is_helpless(state(game), actor, attacker)
        assert state(game).sheets["2"].assets == original_assets
        assert not alpha.conditions(state(game), attacker, actor)
        assert not advice.records(state(game), advice.Advice)
        assert rank(state(game), 3) == before_status
        assert game.inspect(OTHER, child)["result"]["blocked_before_roll"]
        with game.store.engine.connect() as c:
            original = game.action(c, parent)
            assert original["data"]["alpha"]["counter_performed"] is False
            assert original["data"]["alpha"]["counter_feedback"] == value.id
    assert (
        game.inspect(OTHER, child)["state"] == game.inspect(PLAYER, parent)["state"] == "complete"
    )
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert game.inspect(OTHER, child)["receipt"] == receipt
    restarted = GameService(ledger, dice=game.dice)
    assert restarted.inspect(OTHER, child) == game.inspect(OTHER, child)
    if given:
        assert restarted.roll(OTHER, str(uuid4()), child)["receipt"] == receipt
        assert game.dice.calls == 2
    with ledger.engine.connect() as c:
        assert prove(restarted, c, state(restarted), value.id).receipt == (
            receipt["id"] if given else None
        )
        assert game.action(c, child)["data"]["alpha_counter_completed"]
        assert game.action(c, parent)["data"]["alpha"]["counter_child"] == child
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_ADVICE_COUNTER_FEEDBACK" not in json.dumps(gateway.messages)
    assert "PRIVATE_ADVICE_COUNTER_MAXIM" not in json.dumps(gateway.messages)
    with ledger.engine.connect() as c:
        assert "PRIVATE_ADVICE_COUNTER_MAXIM" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    restarted.close_scene(ADMIN, "close-completed-advice-counter-scene", 900)
    rebound = restarted.bind_scene(ADMIN, "rebind-completed-advice-counter-channel", 900)["scene"]
    assert rebound != value.cast.id
    with ledger.engine.connect() as c:
        assert prove(restarted, c, state(restarted), value.id).receipt == (
            receipt["id"] if given else None
        )
