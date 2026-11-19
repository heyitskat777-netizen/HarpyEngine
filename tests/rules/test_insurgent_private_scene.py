"""The Insurgent's printed reactions use own consent, beliefs, Status and known Tags."""

import asyncio

import pytest
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_handler_private_scene import records
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("suspects", (True, False))
def test_insurgent_private_scene_keeps_suspicion_and_tags_with_original_owners(ledger, suspects):
    creation, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"plays"}))
        )
    )
    save(creation, complete(creation, "Insurgent"))
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(ADMIN, "actual-insurgent", preview["revision"], state(game).revision, True)
    plays = HandlerPlayService(ledger)
    original = current_ref(state(game), 2)
    choice = plays.start(ADMIN, "actual-known-tag-grant", state(game).revision, (original,))
    plays.submit(
        ADMIN,
        "actual-known-tag",
        choice["id"],
        choice["game_revision"],
        "mess",
        Effect(
            kind="tag",
            target=original,
            tag="Known tag",
            account="The original Handler gives a Tag.",
        ),
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].tags.append(
            TagState(
                id="unknown-original-tag",
                label="UNKNOWN_PRIVATE_TAG",
                giver=3,
                observers=(2, 3),
            )
        )
        game.event(c, 2, "synthetic-private-tag", "synthetic.original_knowledge", canon)
    game.leave_scene(OTHER, "insurgent-private-scene", 900)
    service, inbox = HandlerPrivateSceneService(ledger, game), InboxService(ledger)

    async def offer():
        click = current(1, 49500)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_handler_plays(click, plays)
        hub = click.edit_original_response.call_args.kwargs["view"]
        await hub.open_item(click, "insurgent_private")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(offer=("offer",))
        sent = current(1, 49501)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(offer())
    (value,) = records(state(game))
    assert not any(x.identity == value.id for x in inbox.items(OTHER))
    with pytest.raises(WorkflowError, match="original participants"):
        service.menu(OTHER, value.id)

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

    asyncio.run(native(PLAYER, 49510, "consent"))
    asyncio.run(native(ADMIN, 49512, "attest"))
    asyncio.run(native(PLAYER, 49514, "attest"))
    asyncio.run(native(ADMIN, 49516, "insurgent_ask"))
    with pytest.raises(WorkflowError, match="your own"):
        service.respond(
            ADMIN, "invented-suspicion", value.id, state(game).revision, "insurgent_yes"
        )
    asyncio.run(native(PLAYER, 49518, "insurgent_yes" if suspects else "insurgent_no"))
    before = state(game)
    ledger.engine.dispose()
    if suspects:
        assert service.menu(ADMIN, value.id)["phase"] == "insurgent_suspicion"
        asyncio.run(native(ADMIN, 49520, "insurgent_leave_suspicions"))
        assert state(game).sheets == before.sheets and state(game).order == before.order
        assert service.menu(ADMIN, value.id)["outcome"] == "insurgent_left_suspicions"
        return

    tag = next(x.id for x in before.sheets["2"].tags if x.label == "Known tag")
    selector = f"2:{tag}"
    assert service.menu(ADMIN, value.id)["tags"] == ((selector, "Known tag"),)
    with pytest.raises(WorkflowError, match="known to the original Insurgent"):
        service.respond(
            ADMIN,
            "unknown-erasure",
            value.id,
            before.revision,
            "insurgent_apply",
            effects=("erase_tag",),
            tag="2:unknown-original-tag",
        )
    text = "PRIVATE_CONFESSION"
    reactions = ("confess", "lower_status", "erase_tag")
    asyncio.run(
        native(
            ADMIN,
            49520,
            "insurgent_apply",
            effects=reactions,
            account=text,
            tag=(selector,),
        )
    )
    assert (
        service.respond(
            ADMIN,
            "49521",
            value.id,
            before.revision,
            "insurgent_apply",
            effects=reactions,
            text=text,
            tag=selector,
        )["phase"]
        == "complete"
    )
    final = state(game)
    (performed,) = records(final)
    assert performed.effects == reactions and performed.tag == tag
    assert final.order == (3, 2)
    assert [x.id for x in final.sheets["2"].tags] == ["unknown-original-tag"]
    assert service.menu(PLAYER, value.id)["account"] == text
