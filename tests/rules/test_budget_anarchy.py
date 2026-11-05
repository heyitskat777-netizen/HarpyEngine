"""Actual anarchy source, unavailable city consumer and native civic restoration."""

import asyncio

import pytest
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_budget_anarchy import get
from girlframe.engine.m3_world import end_off_duty, update
from girlframe.services.inbox import InboxService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService


def test_actual_anarchy_native_restoration_preserves_physical_city_and_history(ledger):
    strain, game = ready(ledger, face=5)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}},
            )
        }
    )
    worlds = WorldService(strain.missions)
    world = initial()
    worlds.initialize(
        ADMIN, "anarchy-world", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    prepared(strain, game, high=frozenset({"budget"}))
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    strain.roll(ADMIN, "anarchy-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "anarchy-column", request.id, 2, state(game).revision, 1)
    identity = request.id + ":effect"
    effects = EffectService(strain)
    original = next(x for x in state(game).world.locations if x.kind == "city")

    async def select():
        interaction = current(1, 28600)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = dict(target=(original.id,), account="The actual city falls into anarchy")
        await form.confirm.callback(current(1, 28601))
        assert form.completed

    asyncio.run(select())
    source_event = get(state(game), identity).source_event
    city = next(x for x in state(game).world.locations if x.id == original.id)
    assert not city.operational and city.condition == original.condition
    public = worlds.get(PLAYER)["world"]["locations"]
    assert not next(x for x in public if x["id"] == city.id)["operational"]
    assert not state(game).world.territory
    # World advancement consumes the same actual condition: this is no surviving location.
    aggressive = (
        state(game)
        .world.gorgons[0]
        .model_copy(
            update={
                "gorgon_class": "aggressive",
                "cell": city.cell,
            }
        )
    )
    preview = update(state(game).world, gorgons=(aggressive,))
    with pytest.raises(ValueError, match="outside a surviving location"):
        end_off_duty(preview, "actual-anarchy-world-preview", (), ())

    async def restore():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(ADMIN) if x.task == "m3_budget_anarchy")
        assert not any(x.task == "m3_budget_anarchy" for x in inbox.items(PLAYER))
        interaction = current(1, 28602)
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(interaction, item)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = dict(
            method="The actual settlement negotiations were carried out",
            result="The civic authority was restored during play",
        )
        await form.confirm.callback(current(1, 28603))
        assert form.completed

    asyncio.run(restore())
    final = get(state(game), identity)
    assert final.restored_event and final.source_event == source_event
    city = next(x for x in state(game).world.locations if x.id == original.id)
    assert city.operational and city.condition == original.condition and not city.blocked_by
    assert not state(game).world.territory
    assert next(x for x in worlds.get(PLAYER)["world"]["locations"] if x["id"] == city.id)[
        "operational"
    ]
