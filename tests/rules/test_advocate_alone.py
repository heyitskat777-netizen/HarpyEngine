"""An actual private Advocate conversation hands off to native Receive Orders."""

import asyncio

import pytest
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.engine.m3_advocate_alone import records
from girlframe.services.inbox import InboxService
from girlframe.services.m3_advocate_alone import AdvocateAloneService
from girlframe.services.m3_advocate_empathy import CHOICE
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("order", ("silence", "amuse"))
def test_private_advocate_question_and_order_require_exact_original_audience(ledger, order):
    creation, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"plays"}))
        )
    )
    save(creation, complete(creation, "Advocate"))
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(ADMIN, "get-them-alone", preview["revision"], state(game).revision, True)
    service = AdvocateAloneService(ledger, game)
    inbox = InboxService(ledger)
    question, owned_answer, label = "PRIVATE_QUESTION", "PRIVATE_ORIGINAL_ANSWER", "PRIVATE_TAG"
    message = "Perform an imitation of the briefing chime." if order == "amuse" else ""
    with pytest.raises(WorkflowError, match="one-on-one"):
        service.ask(ADMIN, "crowded", state(game).revision, 900, question, order)
    game.leave_scene(OTHER, "initial-quiet", 900)

    async def start():
        click = current(1, 48800)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_handler_plays(click, HandlerPlayService(ledger))
        hub = click.edit_original_response.call_args.kwargs["view"]
        await hub.open_item(click, "advocate_alone")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(question=question, order=(order,))
        sent = current(1, 48801)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(start())
    (original,) = records(state(game))
    assert not original.effect and not original.answer
    assert not any(x.identity == original.id for x in inbox.items(ADMIN))
    with pytest.raises(WorkflowError, match="original Girl"):
        service.answer(ADMIN, "does-not-answer-for-her", original.id, state(game).revision, "Fake")
    with pytest.raises(WorkflowError, match="original two participants"):
        service.get(OTHER, original.id)
    game.join_scene(OTHER, "interrupts-private-scene", 900)
    assert not any(x.identity == original.id for x in inbox.items(PLAYER))
    with pytest.raises(WorkflowError, match="one-on-one"):
        service.answer(
            PLAYER, "cannot-answer-with-witness", original.id, state(game).revision, owned_answer
        )
    game.leave_scene(OTHER, "one-on-one-recovered", 900)

    async def route(viewer, number, **values):
        click = current(viewer.user_id, number)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(viewer) if x.identity == original.id)
        assert question not in repr(item) and owned_answer not in repr(item)
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        sent = current(viewer.user_id, number + 1)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(route(PLAYER, 48810, answer=owned_answer))
    before = state(game)
    (answered,) = records(before)
    assert answered.answer.text == owned_answer and answered.effect is None
    assert all(tag.label != label for tag in before.sheets["2"].tags)
    assert not any(x.identity == original.id for x in inbox.items(OTHER))
    ledger.engine.dispose()
    ledger.safety(OTHER, "pause-private-effect", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="(?i)paused"):
        service.issue(ADMIN, "paused-issue", original.id, before.revision, message, label)
    ledger.safety(OTHER, "resume-private-effect", ledger.status(OTHER)["revision"], pause=False)
    with pytest.raises(WorkflowError, match="unissued private order"):
        service.issue(ADMIN, "stale-issue", original.id, before.revision - 1, message, label)
    assert state(game) == before
    asyncio.run(route(ADMIN, 48820, tag=label, **({"message": message} if message else {})))
    result = service.issue(ADMIN, "48821", original.id, before.revision, message, label)
    after = state(game)
    (resolved,) = records(after)
    (tag,) = (x for x in after.sheets["2"].tags if x.id == resolved.effect.tag)
    assert tag.observers == (1, 2) and tag.giver_actor == original.handler
    assert resolved.effect.order == result["order_id"] and tag.label == label
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    assert not any(x["kind"] == "order_response" for x in game.choices(OTHER))
    (choice,) = (x for x in game.choices(PLAYER) if x["kind"] == "order_response")
    decision = game.decision(PLAYER, choice["id"])
    expected = message if message else "Do not tell anyone about this."
    assert decision["order_text"] == expected and decision["participants"] == [1, 2]
    assert owned_answer not in str(decision)
    with pytest.raises(WorkflowError):
        game.decision(OTHER, choice["id"])
    answer(game, PLAYER, "order_response", options=("obedient",))
    answer(game, ADMIN, CHOICE, options=("pass",))
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, result["action_id"])["state"] == "complete"
    assert all(
        text not in repr(gateway.messages) for text in (question, owned_answer, label, expected)
    )
    assert not any(x.identity == original.id for x in inbox.items(ADMIN))
