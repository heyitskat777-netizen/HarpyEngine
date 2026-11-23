"""The Mistress needs owned consent and an actual favor before any Status change."""

import asyncio

import pytest
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_handler_private_scene import records
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("worked", (True, False))
def test_mistress_favor_preserves_consent_and_applies_actual_rank(ledger, worked):
    creation, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"plays"}))
        )
    )
    save(creation, complete(creation, "Mistress"))
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(ADMIN, "activate-favor", preview["revision"], state(game).revision, True)
    game.leave_scene(PLAYER, "private-scene-for-favor", 900)
    service, inbox = HandlerPrivateSceneService(ledger, game), InboxService(ledger)
    before = state(game)
    assert before.order == (2, 3)
    ended = service.invite(ADMIN, "first-private-invitation", before.revision, 900)["id"]
    service.respond(OTHER, "original-withdrawal", ended, state(game).revision, "withdraw")
    assert service.menu(OTHER, ended)["phase"] == "withdrawn" and state(game).order == before.order

    async def offer():
        click = current(1, 49200)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_handler_plays(click, HandlerPlayService(ledger))
        hub = click.edit_original_response.call_args.kwargs["view"]
        await hub.open_item(click, "mistress_favor")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(offer=("offer",))
        sent = current(1, 49201)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(offer())
    value = next(x for x in records(state(game)) if x.phase == "invite")
    assert not any(x.identity == value.id for x in inbox.items(PLAYER))
    with pytest.raises(WorkflowError, match="original participants"):
        service.menu(PLAYER, value.id)
    with pytest.raises(WorkflowError, match="your own"):
        service.respond(ADMIN, "fake-consent", value.id, state(game).revision, "consent")

    async def native(viewer, number, choice, **values):
        click = current(viewer.user_id, number)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(viewer) if x.identity == value.id)
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(choice=(choice,), **values)
        sent = current(viewer.user_id, number + 1)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(native(OTHER, 49210, "consent"))
    asyncio.run(native(ADMIN, 49212, "attest"))
    with pytest.raises(WorkflowError, match="your own"):
        service.respond(
            ADMIN, "single-account-is-not-enough", value.id, state(game).revision, "ask"
        )
    asyncio.run(native(OTHER, 49214, "attest"))
    asyncio.run(native(ADMIN, 49216, "ask", account="PRIVATE_FAVOR: settle the briefing dispute."))
    ledger.engine.dispose()
    offered = state(game).revision
    ledger.safety(PLAYER, "pause-favor", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.respond(OTHER, "paused-favor", value.id, offered, "accept")
    ledger.safety(PLAYER, "resume-favor", ledger.status(PLAYER)["revision"], pause=False)
    with pytest.raises(WorkflowError, match="current private choice"):
        service.respond(OTHER, "stale-favor", value.id, offered - 1, "accept")
    asyncio.run(native(OTHER, 49220, "accept"))
    assert service.respond(OTHER, "49221", value.id, offered, "accept")["phase"] == "owed"
    assert state(game).order == (3, 2)

    if worked:
        with pytest.raises(WorkflowError):
            service.respond(
                OTHER,
                "fake-completed-play",
                value.id,
                state(game).revision,
                "fulfilled",
                text="Nothing happened",
                action="unrecorded",
            )
        # Complete an actual native Play by the owner after accepting the favor.
        game.join_scene(PLAYER, "join-after-private-scene", 900)
        game.dice = Dice((4, 5))
        worker, gateway = GameWorker(game), Gateway()
        action = game.begin(
            OTHER,
            "record-favor-play",
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="I settle the briefing dispute.",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, OTHER, "actor_keep", options=("tough", "sexy"), denied=("in_control",))
        answer(game, ADMIN, "handler_keep", flag=True, text="The dispute is settled.")
        tick(worker, gateway, 4)
        assert game.inspect(OTHER, action)["state"] == "complete"
        asyncio.run(
            native(OTHER, 49222, "fulfilled", account="The dispute is now settled.", action=action)
        )
        assert service.menu(ADMIN, value.id)["phase"] == "review"
        asyncio.run(native(ADMIN, 49224, "confirm", account="The agreed favor was performed."))
        assert "PRIVATE_FAVOR" not in repr(gateway.messages)
    else:
        asyncio.run(native(OTHER, 49222, "failed", account="I actually did not perform the favor."))
    final = service.menu(OTHER, value.id)
    assert final["phase"] == "complete" and final["outcome"] == (
        "fulfilled" if worked else "failed"
    )
    assert state(game).order == ((3, 2) if worked else (2, 3))
