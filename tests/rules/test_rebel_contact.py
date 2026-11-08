"""Real source, private original Girl route and actual NPC-owned confirmation."""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_effect_service import pending

from girlframe.database import tables as t
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m3_rebel_contact import open_contact
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_rebel_contact import get
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_rebel_contact import ContactService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_secret_regular_contact_owned_revision_confirmation_and_private_reference(ledger):
    effects, game, _, _ = pending(ledger)
    worlds = WorldService(effects.strain.missions)
    roles = NpcRoleService(worlds)
    offer = roles.offer(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-city-contact",
            name="Known city mechanic",
            jobs=("mechanic",),
            controller=3,
            detail="The actual known mechanic from the nearby city",
            cell=(0, 4),
            revealed=True,
        ),
    )
    roles.respond(OTHER, str(uuid4()), offer["id"], state(game).revision, "accept")
    request = next(x for x in state(game).strain.requests if x.track == "rebellion")
    effects.strain.dice.face = 5
    effects.strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
    effects.strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    source = request.id + ":effect"
    identity = source + ":contact"

    async def ask_table():
        interaction = current(1, 29300)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, source)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(contact_city=("city0",), account="This existing city is nearby our base")
        await form.confirm.callback(current(1, 29301))
        assert form.completed

    asyncio.run(ask_table())
    service = ContactService(ledger)
    before = state(game)
    assert get(before, identity).phase == "choose"
    for viewer in (PLAYER, OTHER):
        assert (
            next(x for x in InboxService(ledger).items(viewer) if x.identity == identity).task
            == "m3_rebel_contact"
        )
    first = "PRIVATE_CONTACT_ROUTE: a private repeatable radio connection"
    revised = "PRIVATE_CONTACT_ROUTE: the actual tested frequency and scheduled callback"

    async def act(user, number, values, *, read=False):
        interaction = current(user, number)
        await interaction.response.defer(ephemeral=True)
        await open_contact(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        if read:
            reading = current(user, number + 1)
            reading.response.send_message = AsyncMock()
            await form.read_details.callback(reading)
            assert reading.response.send_message.call_args.kwargs["ephemeral"]
            assert reading.response.send_message.call_args.kwargs["embeds"][0].description == clean(
                first
            )
        form.values.update(values)
        await form.confirm.callback(current(user, number + 2))
        assert form.completed

    asyncio.run(act(2, 29310, dict(action=("claim",), npc=("actual-city-contact",), account=first)))
    with pytest.raises(WorkflowError, match="private contact"):
        service.view(ADMIN, identity)
    npc_view = service.view(OTHER, identity)
    assert npc_view["controller"] and not npc_view["girl"]
    asyncio.run(
        act(
            3,
            29320,
            dict(action=("revise",), account="That frequency is no longer workable"),
            read=True,
        )
    )
    assert get(state(game), identity).phase == "revise"
    asyncio.run(
        act(2, 29330, dict(action=("claim",), npc=("actual-city-contact",), account=revised))
    )
    asyncio.run(
        act(
            3,
            29340,
            dict(action=("confirm",), account="This actual regular contact route is established"),
        )
    )
    actual = state(game)
    contact = get(actual, identity)
    assert (
        contact.phase == "complete" and contact.girl.incarnation == before.sheets["2"].character_id
    )
    assert service.view(PLAYER, identity)["method"] == revised
    assert service.view(OTHER, identity)["method"] == revised

    async def reopen_completed():
        interaction = current(2, 29350)
        await interaction.response.defer(ephemeral=True)
        await open_contact(interaction, service, identity)
        card = interaction.edit_original_response.call_args.kwargs
        assert card["view"] is None
        assert [x.description for x in card["embeds"]] == [
            clean(revised),
            clean("This actual regular contact route is established"),
        ]
        assert card["allowed_mentions"].to_dict() == {"parse": []}

    asyncio.run(reopen_completed())
    assert state(game) == actual  # Reading the completed card never changes its saved source.
    with pytest.raises(WorkflowError, match="private contact"):
        service.view(ADMIN, identity)
    assert actual.sheets == before.sheets and actual.world == before.world
    assert actual.actor_bonds == before.actor_bonds and actual.handler_tags == before.handler_tags
    assert "PRIVATE_CONTACT_ROUTE" not in json.dumps(worlds.get(PLAYER, private=False))
    with ledger.engine.connect() as c:
        assert "PRIVATE_CONTACT_ROUTE" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
        assert "PRIVATE_CONTACT_ROUTE" not in str(
            list(c.scalars(sa.select(t.commands.c.outcome_json)))
        )
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == ledger.campaign_id, work.c.id == identity)
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert row["state"] == "resolved"
