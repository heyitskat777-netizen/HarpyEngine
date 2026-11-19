"""Advocate responses use actual owned obedience, refusal and discovery."""

import asyncio

import pytest
from test_handler_creation import agree, complete, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_physical_operations import place

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_handler_private_scene import records
from girlframe.services.inbox import InboxService
from girlframe.services.m3_advocate_empathy import BAD_GIRL, CHOICE
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService
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


@pytest.mark.parametrize("raise_status", (True, False))
def test_advocate_private_effect_changes_original_tag_asset_and_status(ledger, raise_status):
    creation, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"plays"}))
        )
    )
    draft = complete(creation, "Advocate")
    preview = creation.view(ADMIN)
    creation.save(ADMIN, "draw-advocate", preview["revision"], preview["appointment"], draft)
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(ADMIN, "activate-advocate", preview["revision"], state(game).revision, True)
    subject, outsider = (OTHER, PLAYER) if raise_status else (PLAYER, OTHER)
    with ledger.transaction() as c:
        canon = place(state(game), subject.user_id, mode="outside_frame")
        first, private = [
            x for x in canon.sheets[str(subject.user_id)].assets if x.family == "girl"
        ]
        private.void, private.concealed = True, True
        game.event(c, subject.user_id, "synthetic-advocate-assets", "synthetic.fixture", canon)
    game.leave_scene(outsider, "private-advocate-effect", 900)
    service, inbox = HandlerPrivateSceneService(ledger, game), InboxService(ledger)

    async def invite():
        click = current(1, 49800)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_handler_plays(click, HandlerPlayService(ledger))
        hub = click.edit_original_response.call_args.kwargs["view"]
        await hub.open_item(click, "advocate_private")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(offer=("offer",))
        sent = current(1, 49801)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(invite())
    (scene,) = records(state(game))
    assert not any(x.identity == scene.id for x in inbox.items(outsider))
    before = state(game)
    for viewer, key, step in (
        (subject, "girl-consent", "consent"),
        (ADMIN, "handler-scene", "attest"),
        (subject, "girl-scene", "attest"),
    ):
        service.respond(viewer, key, scene.id, state(game).revision, step)
    pending = state(game)
    assert pending.sheets == before.sheets and pending.order == before.order
    assert service.menu(ADMIN, scene.id)["assets"] == ((first.id, first.name),)
    command = "advocate_raise" if raise_status else "advocate_lower"
    label = "PRIVATE_ADVOCATE_TAG"
    with pytest.raises(WorkflowError, match="original Girl Asset"):
        service.respond(
            ADMIN,
            "choose-concealed",
            scene.id,
            pending.revision,
            command,
            text=private.id,
            tag=label,
        )
    with pytest.raises(WorkflowError, match="your own"):
        service.respond(
            subject, "wrong-chooser", scene.id, pending.revision, command, text=first.id, tag=label
        )
    ledger.engine.dispose()

    async def perform():
        click = current(1, 49810)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == scene.id)
        await InboxView(inbox, 1).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(choice=(command,), asset=(first.id,), label=label)
        sent = current(1, 49811)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(perform())
    assert (
        service.respond(
            ADMIN, "49811", scene.id, pending.revision, command, text=first.id, tag=label
        )["phase"]
        == "complete"
    )
    after = state(game)
    (saved,) = records(after)
    assert saved.damaged_asset == first.id
    sheet = after.sheets[str(subject.user_id)]
    assert next(x for x in sheet.assets if x.id == first.id).damaged
    assert next(x for x in sheet.assets if x.id == private.id) == private
    assert any(
        x.id == saved.tag and x.label == label and x.observers == (1, subject.user_id)
        for x in sheet.tags
    )
    assert (
        after.order == (3, 2)
        and after.sheets[str(outsider.user_id)] == before.sheets[str(outsider.user_id)]
    )
    with pytest.raises(WorkflowError):
        service.menu(outsider, scene.id)
