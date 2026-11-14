"""Original sight ends with its scene even when no observation was authored."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_changeling import define, ready, roll
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_changeling import open_changeling
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_changeling import ChangelingService, prove_fingers, prove_node
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("counter_kind", ("question", "pass"))
def test_native_unobserved_sight_expires_with_original_scene_without_forging_answers(
    ledger, tmp_path, monkeypatch, counter_kind
):
    # Existing bodies/resources are synthetic. The source speech, roll, Bond,
    # String, remote scene, reciprocal response and actual expiry are genuine.
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    action = roll(game, worker, gateway, source=define(game, controls))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    target = current_ref(state(game), 3)
    node = next(x for x in rules.records(state(game), rules.String) if x.origin == "deepen")
    cast_change(CastService(ActorService(MissionService(ledger))), OTHER, "withdraw", target)
    remote = game.bind_scene(ADMIN, str(uuid4()), 901)["scene"]
    game.join_scene(OTHER, str(uuid4()), 901)
    receipt, rolls = game.inspect(PLAYER, action)["receipt"], game.dice.calls
    resources = {key: value.model_dump_json() for key, value in state(game).sheets.items()}

    async def initiate():
        own = current(2, 993201)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_changeling(own, controls)
        menu = own.edit_original_response.call_args.kwargs["view"]
        menu.values["entry"] = ("fingers",)
        response = current(2, 993202)
        response.channel_id = 900
        await menu.confirm.callback(response)
        form = response.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            node=(node.id,),
            kind=("sight",),
            account="I use my earned String to see through her eyes for this scene",
        )
        confirm = current(2, 993203)
        confirm.channel_id = 900
        await form.confirm.callback(confirm)
        assert form.completed, confirm.response.events

    asyncio.run(initiate())
    use = next(x for x in rules.records(state(game), rules.Fingers) if x.node == node.id)
    view = rules.record(state(game), rules.EyeView, use.id)
    assert view.cast.id == remote and view.cast.facilitator is None
    assert not rules.records(state(game), rules.EyeObservation)

    async def counter():
        own = current(3, 993204)
        await own.response.defer(ephemeral=True)
        await open_changeling(own, controls, use.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1, 993205))
        form.values["kind"] = (counter_kind,)
        if counter_kind == "question":
            form.values["text"] = "PRIVATE_EYES_QUESTION: What are you afraid of?"
        confirm = current(3, 993206)
        await form.confirm.callback(confirm)
        assert form.completed, confirm.response.events

    asyncio.run(counter())
    before_close = state(game)
    pending = rules.get(before_close, use.id)
    assert pending.completed_event is None
    assert pending.phase == ("answer" if counter_kind == "question" else "effect")
    close_key = str(uuid4())
    result = game.close_scene(ADMIN, close_key, 901)
    saved = state(game)
    ended = rules.record(saved, rules.EyeView, use.id)
    assert ended.ended_event and ended.model_copy(update={"ended_event": None}) == view
    assert not rules.records(saved, rules.EyeObservation)
    finished = rules.get(saved, use.id)
    assert finished.counter_event == pending.counter_event
    assert finished.counter_closed_event == pending.counter_closed_event
    assert finished.counter == counter_kind
    if counter_kind == "pass":
        assert finished.phase == "complete" and finished.completed_event == ended.ended_event
    else:
        assert finished.phase == "answer" and finished.completed_event is None
        question = rules.record(saved, rules.Question, finished.counter_question)
        assert question.answer is None and question.answer_event is None
    with ledger.engine.connect() as c:
        source = (
            c.execute(sa.select(t.events).where(t.events.c.id == ended.ended_event))
            .mappings()
            .one()
        )
        assert source["kind"] == "m2.scene_closed"
        assert json.loads(source["payload_json"])["channel"] == 901
        assert rules.record(_history(c, game, ended.ended_event), rules.EyeView, use.id) == ended
        assert prove_node(game, c, saved, node.id).spent_event == use.event
        assert prove_fingers(game, c, saved, use.id) == finished
    # The same actual close command does not create another endpoint or revision.
    assert game.close_scene(ADMIN, close_key, 901) == result
    assert state(game).model_dump_json() == saved.model_dump_json()

    reopened = GameService(ledger, dice=game.dice)
    reloaded = ChangelingService(reopened)
    shown = reloaded.view(OTHER, use.id)
    assert not shown["observe"] and not shown["effect"]["active"]
    with pytest.raises(WorkflowError):
        reloaded.view(ADMIN, use.id)

    async def finish():
        own = current(2, 993207)
        await own.response.defer(ephemeral=True)
        await open_changeling(own, reloaded, use.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        if counter_kind == "question":
            assert [x.key for x in form.fields] == ["question", "answer"]
            assert not await form.interaction_check(current(1, 993208))
            form.values.update(
                question=(finished.counter_question,),
                answer="PRIVATE_EYES_ANSWER: Losing my own direction",
            )
            confirm = current(2, 993209)
            await form.confirm.callback(confirm)
            assert form.completed, confirm.response.events
        else:
            assert "Completed" in "".join(page.content for page in form.pages)

    asyncio.run(finish())
    complete = rules.get(state(game), use.id)
    assert complete.phase == "complete" and complete.completed_event
    assert not rules.records(state(game), rules.EyeObservation)
    assert rules.record(state(game), rules.EyeView, use.id) == ended
    assert {key: value.model_dump_json() for key, value in state(game).sheets.items()} == resources
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == rolls
    assert "PRIVATE_EYES_" not in str(gateway.messages)

    # Reusing the original channel does not revive its expired sight or rewrite its end.
    replacement = reopened.bind_scene(ADMIN, str(uuid4()), 901)["scene"]
    assert replacement != remote
    reopened.join_scene(OTHER, str(uuid4()), 901)
    final = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="original eyes"):
        reloaded.observe_eyes(OTHER, str(uuid4()), state(game).revision, use.id, "A later scene")
    assert state(game).model_dump_json() == final
    reopened.close_scene(ADMIN, str(uuid4()), 901)
    assert rules.record(state(game), rules.EyeView, use.id) == ended
