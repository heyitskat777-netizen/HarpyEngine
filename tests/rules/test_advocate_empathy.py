"""Advocate responses use actual owned obedience, refusal and discovery."""

import asyncio

import pytest
from test_handler_creation import agree, complete, ready
from test_ledger import ADMIN, OTHER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.inbox import InboxService
from girlframe.services.m3_advocate_empathy import BAD_GIRL, CHOICE
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("discovered", (False, True))
def test_advocate_rewards_obedience_and_tags_actual_discovered_refusal(ledger, discovered):
    creation, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"plays"}),
            )
        )
    )
    draft = complete(creation, "Advocate")
    preview = creation.view(ADMIN)
    creation.save(ADMIN, "draw-advocate", preview["revision"], preview["appointment"], draft)
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(ADMIN, "activate-advocate", preview["revision"], state(game).revision, True)
    dice = Dice((4, 5))
    game.dice = dice
    worker, gateway = GameWorker(game), Gateway()
    inbox = InboxService(ledger)

    def order(number, target, response):
        root = game.issue_order(
            ADMIN, "actual-advocate-order-" + str(number), 900, target.user_id, "Actual direction"
        )
        tick(worker, gateway, 2)
        answer(game, target, "order_response", options=(response,))
        return root

    async def reward(number, selected, **values):
        (request,) = (x for x in game.choices(ADMIN) if x["kind"] == CHOICE)
        click = current(1, number)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == request["id"])
        await InboxView(inbox, 1).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(options=(selected,), **values)
        submitted = current(1, number + 1)
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.followup.send.call_args,
            submitted.edit_original_response.call_args,
        )
        return request

    obeyed = order(1, OTHER, "obedient")
    (decision,) = (x for x in game.choices(ADMIN) if x["kind"] == CHOICE)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            "choose-for-advocate",
            decision["id"],
            decision["revision"],
            ChoiceAnswer(options=("raise_status",)),
        )
    ledger.engine.dispose()
    asyncio.run(reward(46600, "raise_status"))
    game.respond(
        ADMIN,
        "46601",
        decision["id"],
        decision["revision"],
        ChoiceAnswer(options=("raise_status",)),
    )
    assert game.inspect(OTHER, obeyed["action_id"])["state"] == "complete"
    assert state(game).order == (3, 2)
    tick(worker, gateway, 6)

    refused = order(2, OTHER, "disobey")
    child = game.begin(
        OTHER,
        "advocate-refused",
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="disobey_orders",
            context="I defy the actual order",
            trigger_confirmed=True,
            heat=0,
            order_id=refused["order_id"],
            parent=refused["action_id"],
            witnessed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    answer(game, OTHER, "actor_disobey", options=("tag_heat",), number=2, text="Defiant")
    answer(game, ADMIN, "handler_disobey", flag=discovered)
    assert game.inspect(OTHER, child)["result"]["can_disobey"]
    tags = [x for x in state(game).sheets["3"].tags if x.label == BAD_GIRL]
    assert len(tags) == int(discovered)
    if discovered:
        assert tags[0].giver == 1 and tags[0].giver_actor.kind == "handler"
    tick(worker, gateway, 6)
    subsequent = order(3, OTHER, "hesitant")
    assert bool([x for x in game.choices(ADMIN) if x["kind"] == CHOICE]) == (not discovered)
    if not discovered:
        asyncio.run(
            reward(
                46610, "compliment_tag", text="I appreciate your work.", **{"fields.tag": "Patient"}
            )
        )
        assert any(x.label == "Patient" for x in state(game).sheets["3"].tags)
    assert game.inspect(OTHER, subsequent["action_id"])["state"] == "complete"
    assert dice.calls == 1 and not any(x.label == BAD_GIRL for x in state(game).sheets["2"].tags)
