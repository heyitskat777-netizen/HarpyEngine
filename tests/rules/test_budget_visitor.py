"""One actual source visit, owned demand, response and independent ending."""

import asyncio
from unittest.mock import AsyncMock

import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_physical_operations import place
from test_strain_effect_service import pending

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_budget_visitor import open_visit
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_budget_visitor import get
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_visitor import VisitorService
from girlframe.services.m3_world import WorldService


def test_actual_higher_up_visit_demand_native_response_and_source_ending(ledger):
    effects, game, _, _ = pending(ledger)
    with ledger.transaction() as c:
        located = place(state(game), 2, mode="outside_frame")
        game.event(c, 1, "synthetic-real-prior-placement", "synthetic.placement", located)
    WorldService(effects.strain.missions).npc(
        ADMIN,
        "actual-visitor",
        state(game).revision,
        Npc(
            id="visiting-superior",
            name="Visiting regional superior",
            controller=1,
            jobs=("handler",),
            detail="An actual regional superior visiting this base",
            cell=(0, 0),
            revealed=True,
        ),
    )
    effects.strain.dice.face = 5
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    effects.strain.roll(ADMIN, "visitor-die", request.id, 1, state(game).revision)
    effects.strain.choose(ADMIN, "visitor-column", request.id, 2, state(game).revision, 1)
    source = request.id + ":effect"
    identity = source + ":visit"

    async def start_visit():
        interaction = current(1, 29000)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, source)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            visitor=("visiting-superior",), account="This actual regional superior visits our base"
        )
        await form.confirm.callback(current(1, 29001))
        assert form.completed

    asyncio.run(start_visit())
    service = VisitorService(ledger)
    before = state(game)
    assert get(before, identity).visitor.entity == "visiting-superior"
    assert any(
        x.identity == identity and x.task == "m3_budget_visitor"
        for x in InboxService(ledger).items(ADMIN)
    )

    async def act(user, number, values):
        interaction = current(user, number)
        await interaction.response.defer(ephemeral=True)
        await open_visit(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        form.controls()
        if values["action"] == ("respond",):
            reading = current(user, number + 1)
            reading.response.send_message = AsyncMock()
            await form.read_demand.callback(reading)
            embeds = reading.response.send_message.call_args.kwargs["embeds"]
            assert embeds[1].description == "A personal apology during our next conversation"
        await form.confirm.callback(current(user, number + 2))
        assert form.completed

    asyncio.run(
        act(
            1,
            29010,
            dict(
                action=("demand",),
                target=("2",),
                account="I observed this Girl insulting my regional appointment at this base",
                demand="A personal apology during our next conversation",
            ),
        )
    )
    demand = get(state(game), identity).demands[0]
    assert demand.girl.incarnation == before.sheets["2"].character_id
    assert any(x.identity == identity for x in InboxService(ledger).items(PLAYER))
    assert not any(x.identity == identity for x in InboxService(ledger).items(OTHER))
    # Ending the visit does not invent a settlement or impose an unprinted deadline.
    asyncio.run(act(1, 29020, dict(action=("end",), account="The actual superior leaves the base")))
    assert get(state(game), identity).phase == "complete"
    assert not get(state(game), identity).demands[0].settlement
    assert any(x.identity == identity for x in InboxService(ledger).items(PLAYER))
    asyncio.run(
        act(
            2,
            29030,
            dict(
                action=("respond",),
                target=(demand.id,),
                account="At our next conversation I actually make the requested personal apology",
            ),
        )
    )
    asyncio.run(
        act(
            1,
            29040,
            dict(
                action=("settle",),
                target=(demand.id,),
                account="I heard this actual apology and accept it as satisfying my demand",
            ),
        )
    )
    after = state(game)
    assert get(after, identity).demands[0].settlement
    assert after.sheets == before.sheets and after.world == before.world
    assert after.handler_tags == before.handler_tags and after.requisitions == before.requisitions
    assert not any(x.identity == identity for x in InboxService(ledger).items(PLAYER))
    with ledger.engine.connect() as c:
        rows = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(rows)
                .where(rows.c.campaign_id == ledger.campaign_id, rows.c.id == identity)
                .order_by(rows.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert row["state"] == "resolved"
