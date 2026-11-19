"""An actual Speak installation binds private answers and the printed high refusal."""

import asyncio

import pytest
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, call, prepared

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.discord_adapter.m3_off_duty_cycle import open_action
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService
from girlframe.services.m3_trainer_control import CHOICE
from girlframe.services.m3_trainer_phrases import HEAR, SPEAK
from girlframe.services.onboarding import WorkflowError


def create_trainer(ledger, *, start_with_speak):
    creation = HandlerCreationService(ledger)
    approval, rulings = ledger.policy.m3_approval, ledger.policy.owner_m3_rulings
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"plays", "playbooks"})
            ),
            owner_m3_rulings=rulings.model_copy(
                update=dict(handler_creation="owned_shared_choices_preserve_existing")
            ),
        )
    )
    draft = complete(creation, "Trainer")
    if start_with_speak:
        ace, dog = draft.starting
        draft = draft.model_copy(update=dict(starting=(ace, dog.model_copy(update=dict(prompt=2)))))
    save(creation, draft)
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(ADMIN, "speak-trainer", preview["revision"], preview["game_revision"], True)


@pytest.mark.parametrize("character_answer", ("trainer_yes", "trainer_understands"))
def test_private_trainer_source_installs_speak_or_erases_only_the_owned_identity(
    ledger, character_answer
):
    from girlframe.engine.m3_handler_private_scene import records

    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=False)
    game.leave_scene(PLAYER, "private-trainer-scene", 900)
    service = HandlerPrivateSceneService(ledger, game)
    inbox = InboxService(ledger)

    async def offer():
        click = current(1, 49300)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_handler_plays(click, HandlerPlayService(ledger))
        hub = click.edit_original_response.call_args.kwargs["view"]
        await hub.open_item(click, "trainer_private")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(offer=("offer",))
        sent = current(1, 49301)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(offer())
    (value,) = records(state(game))
    assert value.playbook == "Trainer"
    assert not any(x.identity == value.id for x in inbox.items(PLAYER))
    with pytest.raises(WorkflowError):
        service.menu(PLAYER, value.id)

    async def native(viewer, number, step, **values):
        click = current(viewer.user_id, number)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(viewer) if x.identity == value.id)
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(choice=(step,), **values)
        sent = current(viewer.user_id, number + 1)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(native(OTHER, 49310, "consent"))
    asyncio.run(native(ADMIN, 49312, "attest"))
    asyncio.run(native(OTHER, 49314, "attest"))
    asyncio.run(native(ADMIN, 49316, "trainer_ask"))
    before = state(game)
    identities = tuple(before.sheets["3"].identities)
    assert not service.menu(ADMIN, value.id)["identities"] and identities
    with pytest.raises(WorkflowError, match="your own"):
        service.respond(
            ADMIN, "cannot-answer-for-girl", value.id, before.revision, character_answer
        )
    with pytest.raises(WorkflowError, match="current private choice"):
        service.respond(OTHER, "old-answer", value.id, before.revision - 1, character_answer)
    selector = {}
    if character_answer == "trainer_understands":
        with pytest.raises(WorkflowError, match="SOURCE_IDENTITY_REQUIRED"):
            service.respond(
                OTHER, "fake-id", value.id, before.revision, character_answer, text="different-body"
            )
        selector["identity"] = (identities[0].id,)
    asyncio.run(native(OTHER, 49320, character_answer, **selector))
    if selector:
        assert service.menu(OTHER, value.id)["outcome"] == "identity_erased"
        assert state(game).sheets["3"].identities == list(identities[1:])
        assert state(game).handler_persona.conditioning == before.handler_persona.conditioning
        return

    assert service.menu(ADMIN, value.id)["phase"] == "trainer_install"
    assert state(game).sheets["3"].identities == list(identities)
    ledger.engine.dispose()
    revision = state(game).revision
    asyncio.run(native(ADMIN, 49322, "install_speak"))
    assert (
        service.respond(ADMIN, "49323", value.id, revision, "install_speak")["phase"] == "complete"
    )
    (finished,) = records(state(game))
    assert finished.outcome == "speak_installed"
    worker, gateway = GameWorker(game), Gateway()
    made = game.issue_order(
        ADMIN,
        "private-trained-speak",
        900,
        3,
        "What happened in the briefing?",
        conditioning_phrase="speak",
    )
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("obedient",))
    answer(game, OTHER, SPEAK, text="I wrote this account myself.")
    answer(game, ADMIN, HEAR, flag=True)
    tick(worker, gateway, 4)
    assert game.inspect(OTHER, made["action_id"])["state"] == "complete"


@pytest.mark.parametrize("reaction", ("obeyed", "high", "mid"))
def test_original_speak_order_uses_its_own_phrasing_and_saved_refusal(ledger, reaction):
    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=True)
    game.dice = Dice((6, 5) if reaction == "high" else (4, 5))
    worker, gateway = GameWorker(game), Gateway()
    inbox = InboxService(ledger)
    issuer = PLAYER if reaction == "obeyed" else ADMIN
    uninvolved = ADMIN if issuer == PLAYER else PLAYER
    with pytest.raises(WorkflowError, match="installed Speak"):
        game.issue_order(
            ADMIN, "unconditioned", 900, 2, "Uninstalled.", conditioning_phrase="speak"
        )
    order = game.issue_order(
        issuer, "owned-speak", 900, 3, "PRIVATE_QUESTION", conditioning_phrase="speak"
    )
    tick(worker, gateway, 3)
    play = order["action_id"]
    if reaction == "obeyed":
        answer(game, OTHER, "order_response", options=("obedient",))
    else:
        answer(game, OTHER, "order_response", options=("disobey",))
        play = game.begin(
            OTHER,
            "refuse-speak",
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="disobey_orders",
                context="I attempt to refuse the spoken question.",
                trigger_confirmed=True,
                heat=0,
                order_id=order["order_id"],
                parent=order["action_id"],
                witnessed=False,
            ),
        )["action_id"]
        tick(worker, gateway, 4)
        pass_tags(game)
        if reaction == "mid":
            answer(game, OTHER, "actor_disobey", options=("tag_heat",), number=2, text="Defiant")
            answer(game, OTHER, CHOICE, options=("pass",))
        else:
            assert not any(x["kind"] == "actor_disobey" for x in game.choices(OTHER))
            assert state(game).order == (3, 2) and state(game).sheets["3"].heat == 2
        answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.dice.calls == int(reaction != "obeyed")
    if reaction == "mid":
        assert game.inspect(OTHER, play)["result"]["can_disobey"]
        assert not any(x["kind"] == SPEAK for x in game.choices(OTHER))
        assert state(game).order == (2, 3)
        return
    (asked,) = (x for x in game.choices(OTHER) if x["kind"] == SPEAK)
    assert "PRIVATE_QUESTION" in game.decision(OTHER, asked["id"])["conditioning_text"]
    with pytest.raises(WorkflowError):
        game.respond(
            issuer, "forge-speak", asked["id"], asked["revision"], ChoiceAnswer(text="Fake")
        )
    ledger.engine.dispose()

    async def native(viewer, work, sequence, **values):
        click = current(viewer.user_id, sequence)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(viewer) if x.identity == work["id"])
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        sent = current(viewer.user_id, sequence + 1)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(native(OTHER, asked, 47200, text="PRIVATE_ORIGINAL_ANSWER"))
    (heard,) = (x for x in game.choices(issuer) if x["kind"] == HEAR)
    assert "PRIVATE_ORIGINAL_ANSWER" not in heard["body_json"]
    assert game.decision(issuer, heard["id"])["conditioning_text"] == "PRIVATE_ORIGINAL_ANSWER"
    for outsider in (OTHER, uninvolved):
        with pytest.raises(WorkflowError):
            game.decision(outsider, heard["id"])
    assert game.inspect(OTHER, play)["state"] != "complete"
    asyncio.run(native(issuer, heard, 47210, flag=("yes",)))
    receipt = game.respond(issuer, "47211", heard["id"], heard["revision"], ChoiceAnswer(flag=True))
    assert receipt["state"] == "complete"
    with pytest.raises(WorkflowError):
        game.respond(
            issuer, "stale-hearing", heard["id"], heard["revision"], ChoiceAnswer(flag=True)
        )
    assert game.inspect(OTHER, play)["state"] == "complete"
    if reaction == "high":
        result = game.inspect(OTHER, play)["result"]
        assert result["total"] == 11 and result["conditioning"] and not result["can_disobey"]
    with ledger.engine.connect() as c:
        saved = game.action(c, play)["data"]
        assert (
            saved["trainer_heard_event"]
            and saved["trainer_spoken"]["answer"] == "PRIVATE_ORIGINAL_ANSWER"
        )


def test_actual_off_duty_speak_installation_needs_both_originals_and_can_trigger(ledger):
    cycle, game, period = prepared(
        ledger,
        before_period=lambda _: create_trainer(ledger, start_with_speak=False),
    )
    activate(cycle, game, period)

    async def arrange():
        click = current(1, 47300)
        await click.response.defer(ephemeral=True)
        await open_action(click, cycle, period, "handler_scene")
        form = click.edit_original_response.call_args.kwargs["view"]
        assert "trainer_conditioning" in dict(form.fields[0].options)
        form.values.update(
            kind=("trainer_conditioning",),
            participants=("3",),
            summary="PRIVATE_TRAINING_SCENE",
        )
        form.controls()
        sent = current(1, 47301)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(arrange())
    assert cycle.review(PLAYER, period)["handler_scene"] is None
    assert cycle.review(OTHER, period)["handler_scene"]["conditioning_phrase"] == "speak"
    with pytest.raises(WorkflowError):
        call(cycle, game, PLAYER, period, "acknowledge", None)
    call(cycle, game, ADMIN, period, "acknowledge", None)
    assert not any("speak" in x.phrases for x in state(game).handler_persona.conditioning)
    with pytest.raises(WorkflowError, match="installed Speak"):
        game.issue_order(
            ADMIN, "premature-speak-command", 900, 3, "Test", conditioning_phrase="speak"
        )
    ledger.engine.dispose()
    pending = cycle.review(OTHER, period)

    async def attest():
        click = current(3, 47310)
        await click.response.defer(ephemeral=True)
        await open_action(click, cycle, period, "ack:handler")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(confirm=("yes",))
        sent = current(3, 47311)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(attest())
    cycle.acknowledge(OTHER, "47311", period, pending["revision"], pending["game_revision"], None)
    spell = [x for x in state(game).handler_persona.conditioning if "speak" in x.phrases]
    assert len(spell) == 1 and spell[0].pilot.entity == "3"
    assert spell[0].source_event != state(game).handler_persona.source_event
    worker, gateway = GameWorker(game), Gateway()
    issued = game.issue_order(
        ADMIN, "later-valid-speak", 900, 3, "PRIVATE_FOLLOWUP", conditioning_phrase="speak"
    )
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("immediate",))
    answer(game, OTHER, SPEAK, text="Yes.")
    answer(game, ADMIN, HEAR, flag=True)
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"
