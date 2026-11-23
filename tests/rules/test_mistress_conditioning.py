"""An actual Mistress chooses whether to adjust an original Intense-Bond refusal."""

import asyncio

import pytest
from test_handler_creation import agree, complete, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.inbox import InboxService
from girlframe.services.m3_mistress_conditioning import CHOICE, RULE
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("response", ("apply", "pass", "personal"))
def test_owned_mistress_adjustment_uses_actual_refusal_and_preserves_dice(ledger, response):
    creation, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"plays"}),
            )
        )
    )
    draft = complete(creation, "Mistress")
    first, second = draft.starting
    draft = draft.model_copy(
        update=dict(
            starting=(
                first.model_copy(update=dict(depth=2)),
                second.model_copy(update=dict(depth=1)),
            )
        )
    )
    preview = creation.view(ADMIN)
    creation.save(ADMIN, "condition-mistress", preview["revision"], preview["appointment"], draft)
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(
        ADMIN, "activate-actual-mistress", preview["revision"], state(game).revision, True
    )

    target = OTHER if response == "personal" else PLAYER
    dice = Dice((4, 5))
    game.dice = dice
    worker, gateway = GameWorker(game), Gateway()
    root = game.issue_order(
        ADMIN, "actual-mistress-order", 900, target.user_id, "Original private direction"
    )
    tick(worker, gateway)
    answer(game, target, "order_response", options=("disobey",))
    child = game.begin(
        target,
        "actual-mistress-refusal",
        900,
        state(game).sheets[str(target.user_id)].revision,
        PlayInput(
            play="disobey_orders",
            context="I refuse my Handler's order",
            trigger_confirmed=True,
            heat=0,
            order_id=root["order_id"],
            parent=root["action_id"],
            witnessed=True,
        ),
    )["action_id"]
    tick(worker, gateway)
    options = [x for x in game.choices(ADMIN) if x["kind"] == CHOICE]
    assert bool(options) == (response != "personal")
    pass_tags(game)
    inbox = InboxService(ledger)
    if response != "personal":
        (choice,) = options
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER,
                "choose-for-mistress",
                choice["id"],
                choice["revision"],
                ChoiceAnswer(options=("apply",)),
            )
        assert not any(x["kind"] == "actor_disobey" for x in game.choices(target))
        ledger.engine.dispose()

        async def native():
            click = current(1, 46100)
            await click.response.defer(ephemeral=True)
            item = next(x for x in inbox.items(ADMIN) if x.identity == choice["id"])
            await InboxView(inbox, 1).route(click, item)
            form = click.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm)
            form.values.update(options=(response,))
            submitted = current(1, 46101)
            await form.confirm.callback(submitted)
            assert form.completed, (
                submitted.followup.send.call_args,
                submitted.edit_original_response.call_args,
            )

        asyncio.run(native())
        game.respond(
            ADMIN, "46101", choice["id"], choice["revision"], ChoiceAnswer(options=(response,))
        )

    if response != "apply":
        answer(game, target, "actor_disobey", options=("tag_heat",), number=2, text="Defiant")
    answer(game, ADMIN, "handler_disobey", flag=True)
    result = game.inspect(target, child)["result"]
    assert result["total"] == (7 if response == "apply" else 9)
    assert result["can_disobey"] == (response != "apply") and dice.calls == 1
    with ledger.engine.connect() as c:
        data = game.action(c, child)["data"]
        assert data["receipt"]["faces"] == [4, 5]
        assert sum(x["amount"] for x in data["modifiers"] if x["source"] == RULE) == (
            -2 if response == "apply" else 0
        )
