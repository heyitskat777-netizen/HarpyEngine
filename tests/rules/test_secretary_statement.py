"""Characterize the statement path without inventing a scene-history audience."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state
from test_mission_ui import current
from test_secretary import acquire, form, play, ready

from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine import m3_secretary as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_secretary import SecretaryService
from girlframe.services.onboarding import WorkflowError


def test_authoritative_statement_records_owner_history_without_implied_scene_delivery(
    ledger, tmp_path, monkeypatch
):
    game, service, _, _ = ready(ledger, tmp_path, monkeypatch)
    secretary = acquire(service, game)
    casts = CastService(ActorService(MissionService(ledger)))
    change(casts, OTHER, "withdraw", current_ref(state(game), 3))
    play(
        service,
        secretary.id,
        "appear",
        scene=("900",),
        place=("base0",),
        account="The Secretary joins the actual briefing scene",
    )
    before = state(game)
    dice = Dice(())
    service.game.dice = dice
    statement = "The original Handler confirms the briefing begins now."
    step = form(service, secretary.id, play=("authority",))

    async def record():
        view = step.edit_original_response.call_args.kwargs["view"]
        assert "Record-only statements stay in your private History" in view.instructions
        assert "Addressed notices share the exact statement" in view.instructions
        view.values.update(scene=("900",), target=("statement",), text=statement)
        result = current(1, 41299)
        await result.response.defer(ephemeral=True)
        await view.confirm.callback(result)
        assert view.completed, result.edit_original_response.call_args
        confirmation = result.edit_original_response.call_args.kwargs["content"]
        assert "Statement recorded in your History only" in confirmation
        assert "Share it in the scene yourself" in confirmation

    asyncio.run(record())
    after = state(game)
    spoken = next(x for x in rules.performances(after) if x.play == "authority")
    assert spoken.actor == secretary.actor and spoken.principal == secretary.handler
    assert spoken.account == statement and spoken.scene == before.scene_casts[0].id
    assert spoken.order is None and spoken.recipients == ()
    assert after.model_dump(exclude={"revision", "facts"}) == before.model_dump(
        exclude={"revision", "facts"}
    )
    assert after.facts[:-1] == before.facts and after.facts[-1]["id"] == spoken.id
    assert dice.calls == 0 and game.choices(PLAYER) == []

    # This records the current limitation, not a ruling that speech must stay private.
    # A future audience change must specify recipients instead of trusting current cast.
    with ledger.engine.connect() as c:
        assert 2 in game.scene(c, 900)["participants"]
        assert 3 not in game.scene(c, 900)["participants"]
    reopened = SecretaryService(ledger)
    inbox = InboxService(ledger)
    for viewer in (PLAYER, OTHER):
        assert not any(x.identity == spoken.id for x in inbox.items(viewer))
        with pytest.raises(WorkflowError, match="original recipients"):
            reopened.menu(viewer, spoken.id)

    async def history():
        item = next(
            x for x in inbox.items(ADMIN) if x.task == "m3_secretary" and x.identity == spoken.id
        )
        own = current(1, 41300)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        response = own.edit_original_response.call_args.kwargs
        assert statement in response["content"]
        assert not response["allowed_mentions"].everyone

    asyncio.run(history())
    assert state(game) == after


def test_addressed_scene_statement_reaches_only_frozen_original_recipients(
    ledger, tmp_path, monkeypatch
):
    from uuid import uuid4

    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.services.m3_secretary import prove_performed

    game, service, _, _ = ready(ledger, tmp_path, monkeypatch)
    secretary = acquire(service, game)
    play(
        service,
        secretary.id,
        "appear",
        scene=("900",),
        place=("base0",),
        account="The actual original Secretary appears for this statement",
    )
    before = state(game)
    recipient = current_ref(before, 2)
    unaddressed = current_ref(before, 3)
    assert {recipient, unaddressed} <= {x.actor for x in before.scene_casts[0].roles}
    dice = Dice(())
    service.game.dice = dice
    statement = "The original Handler confirms our actual briefing begins now."
    with pytest.raises(WorkflowError, match="actual addressed roles"):
        service.speak(
            ADMIN,
            str(uuid4()),
            secretary.id,
            before.revision,
            900,
            statement,
            recipients=(ActorRef(kind="npc", entity="not-in-this-cast"),),
        )
    with pytest.raises(WorkflowError):
        service.speak(
            PLAYER,
            str(uuid4()),
            secretary.id,
            before.revision,
            900,
            statement,
            recipients=(recipient,),
        )
    assert state(game) == before
    step = form(service, secretary.id, play=("authority",))

    async def address():
        view = step.edit_original_response.call_args.kwargs["view"]
        view.values.update(scene=("900",), target=("addressed_statement",), text=statement)
        chosen = current(1, 976001)
        await view.confirm.callback(chosen)
        assert view.completed, str(chosen.edit_original_response.call_args)
        audience = chosen.edit_original_response.call_args.kwargs["view"]
        assert "Requests/History" in audience.instructions and statement in audience.instructions
        assert not await audience.interaction_check(current(2))
        audience.values.update(recipients=(recipient.token,))
        confirmed = current(1, 976002)
        await audience.confirm.callback(confirmed)
        assert audience.completed, str(confirmed.edit_original_response.call_args)
        assert (
            "selected original recipients in Requests/History"
            in confirmed.edit_original_response.call_args.kwargs["content"]
        )

    asyncio.run(address())
    after = state(game)
    spoken = next(x for x in rules.performances(after) if x.play == "authority")
    assert spoken.recipients == (recipient,) and len(spoken.recipient_roles) == 1
    assert spoken.recipient_roles[0].controller == PLAYER.user_id
    assert spoken.recipient_roles[0] in before.scene_casts[0].roles
    assert (
        spoken.statement_channel == 900
        and spoken.statement_cast_revision == before.scene_casts[0].revision
    )
    assert spoken.account == statement and spoken.order is None
    assert after.model_dump(exclude={"revision", "facts"}) == before.model_dump(
        exclude={"revision", "facts"}
    )
    assert dice.calls == 0 and game.choices(PLAYER) == []
    assert (
        service.speak(
            ADMIN, "976002", secretary.id, before.revision, 900, statement, recipients=(recipient,)
        )["id"]
        == spoken.id
    )
    assert state(game) == after
    with ledger.engine.connect() as c:
        assert prove_performed(service.game, c, after, spoken.id) == spoken
        forged = after.model_copy(deep=True)
        changed = spoken.model_copy(
            update=dict(
                recipient_roles=(spoken.recipient_roles[0].model_copy(update=dict(controller=3)),)
            )
        )
        for fact in forged.facts:
            if fact.get("kind") == "secretary_performed" and fact.get("id") == spoken.id:
                fact["body"] = changed.model_dump_json()
        with pytest.raises(WorkflowError):
            prove_performed(service.game, c, forged, spoken.id)
        assert statement not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    inbox = InboxService(ledger)
    assert not any(x.identity == spoken.id for x in inbox.items(OTHER))
    with pytest.raises(WorkflowError, match="original recipients"):
        service.menu(OTHER, spoken.id)
    projected = service.menu(PLAYER, spoken.id)["body"]
    assert projected["recipients"] == [recipient.model_dump(mode="json")]
    assert "statement_channel" not in projected and "statement_cast_revision" not in projected
    assert unaddressed.model_dump(mode="json") not in projected["recipients"]

    async def read(viewer, nonce):
        item = next(
            x for x in inbox.items(viewer) if x.task == "m3_secretary" and x.identity == spoken.id
        )
        assert not item.incoming
        own = current(viewer.user_id, nonce)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(own, item)
        reply = own.edit_original_response.call_args.kwargs
        assert "Addressed Secretary notice" in reply["content"] and statement in reply["content"]
        assert "OWNER_PROFILE_SECRET" not in reply["content"]
        assert not reply["allowed_mentions"].everyone

    asyncio.run(read(PLAYER, 976003))
    asyncio.run(read(ADMIN, 976004))
    casts = CastService(ActorService(MissionService(ledger)))
    change(casts, OTHER, "withdraw", unaddressed)
    change(casts, OTHER, "join", unaddressed)
    assert not any(x.identity == spoken.id for x in inbox.items(OTHER))
    with pytest.raises(WorkflowError):
        service.menu(OTHER, spoken.id)
    final = state(game)
    assert game.rebuild() > 0 and state(game) == final
    asyncio.run(read(PLAYER, 976005))
