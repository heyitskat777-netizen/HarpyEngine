"""Control Freak responds to an actual native Disobey with a privately owned Tag."""

import asyncio

import pytest
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.inbox import InboxService
from girlframe.services.m3_trainer_control import CHOICE
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("response", ("give_tag", "pass", "low"))
def test_trainer_refusal_leaves_the_tag_choice_with_original_girl(ledger, response):
    creation, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"plays"}))
        )
    )
    save(creation, complete(creation, "Trainer"))
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(
        ADMIN, "activate-trainer", preview["revision"], preview["game_revision"], True
    )
    game.dice = Dice((2, 3) if response == "low" else (4, 5))
    worker, gateway = GameWorker(game), Gateway()

    order = game.issue_order(ADMIN, "native-trainer-order", 900, 2, "Answer the intercom.")
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("disobey",))
    child = game.begin(
        PLAYER,
        "original-girl-refuses-trainer",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            context="I keep the intercom silent.",
            trigger_confirmed=True,
            heat=0,
            order_id=order["order_id"],
            parent=order["action_id"],
            witnessed=False,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    if response == "low":
        assert not any(x["kind"] == CHOICE for x in game.choices(PLAYER))
        answer(game, ADMIN, "handler_disobey", flag=False)
        assert not game.inspect(PLAYER, child)["result"]["can_disobey"]
        assert not state(game).handler_tags
        return

    answer(game, PLAYER, "actor_disobey", options=("tag_heat",), number=2, text="Defiant")
    (decision,) = (x for x in game.choices(PLAYER) if x["kind"] == CHOICE)
    inbox = InboxService(ledger)
    for outsider in (ADMIN, OTHER):
        assert decision["id"] not in {x.identity for x in inbox.items(outsider)}
        with pytest.raises(WorkflowError, match="another player"):
            game.respond(
                outsider,
                "forged-trainer-tag",
                decision["id"],
                decision["revision"],
                ChoiceAnswer(options=("give_tag",), text="forged"),
            )
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.inspect(PLAYER, child)["state"] != "complete"
    assert not state(game).handler_tags
    ledger.engine.dispose()
    label = "PRIVATE_TWO_PERSON_TAG" if response == "give_tag" else ""

    async def choose():
        click = current(2, 46700)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(PLAYER) if x.identity == decision["id"])
        await InboxView(inbox, 2).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(options=(response,))
        if label:
            form.values["text"] = label
        submitted = current(2, 46701)
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.followup.send.call_args,
            submitted.edit_original_response.call_args,
        )

    asyncio.run(choose())
    submitted = ChoiceAnswer(options=(response,), text=label)
    game.respond(PLAYER, "46701", decision["id"], decision["revision"], submitted)
    with pytest.raises(WorkflowError):
        game.respond(PLAYER, "stale-trainer-tag", decision["id"], decision["revision"], submitted)
    after = state(game)
    assert len(after.handler_tags) == int(response == "give_tag")
    if label:
        (tag,) = after.handler_tags
        assert tag.label == label
        assert tag.giver_actor == current_ref(after, 2)
        assert set(tag.observers) == {1, 2}
        assert label not in str(game.inspect(OTHER, child))
    assert game.inspect(PLAYER, child)["result"]["can_disobey"]
    assert game.dice.calls == 1
