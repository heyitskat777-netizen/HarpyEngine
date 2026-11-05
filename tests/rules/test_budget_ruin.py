"""Actual recursive Budget Endgame, owned native choice and two saved map losses."""

import asyncio

import pytest
from test_budget_persistent_tag import source
from test_ledger import ADMIN
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_world import initial

from girlframe.discord_adapter.m3_budget_ruin import open_ruin
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_ruin import RuinService
from girlframe.services.m3_world import WorldService


@pytest.mark.parametrize("last_base", [False, True])
def test_actual_budget_endgame_native_two_locations(ledger, last_base):
    _, game, strain, identity, _ = source(ledger, option=3)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN,
        "budget-ruin-map",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    chosen = ("base1", "base2") if last_base else ("city0", "important0")
    if last_base:
        from girlframe.engine.m3_world import destroy

        with ledger.transaction() as c:
            canon = state(game)
            canon.world = destroy(canon.world, "base0", gorgon_cause=False).world
            game.event(c, 1, "prior-first-base-lost", "synthetic.prior_base_loss", canon)
    service = RuinService(ledger)
    before = state(game)
    data = service.view(ADMIN, identity)
    card = next(x for x in InboxService(ledger).items(ADMIN) if x.identity == identity)
    assert card.task == "m3_budget_ruin"

    async def normal_native():
        interaction = current(1, 28080)
        await interaction.response.defer(ephemeral=True)
        await open_ruin(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert form.fields[0].minimum == form.fields[0].maximum == 2
        form.values = {
            "locations": chosen,
            "account": "The two existing places fall into ruin",
        }
        await form.confirm.callback(current(1, 28081))
        assert form.completed

    asyncio.run(normal_native())
    after = state(game)
    newly_lost = {x.id for x in after.world.locations if x.condition == "destroyed"} - {
        x.id for x in before.world.locations if x.condition == "destroyed"
    }
    assert newly_lost == set(chosen)
    assert after.world.territory == before.world.territory
    actual = [x for x in after.strain.triggers if x.id.startswith(identity + ":structure:")]
    assert {x.entity for x in actual} == set(chosen)
    assert service.view(ADMIN, identity)["state"] == "resolved"
    assert (
        service.apply(
            ADMIN,
            "28081",
            identity,
            data["revision"],
            data["game_revision"],
            chosen,
            "The two existing places fall into ruin",
        )["state"]
        == "resolved"
    )
    assert state(game) == after

    if last_base:
        from girlframe.engine.m3_collateral import loss
        from girlframe.services.m3_quadrant_loss import LossService

        record = next(x for x in after.facts if x.get("kind") == "quadrant_loss")
        assert loss(after, record["id"]).phase == "employment"
        # Prove the existing continuation recognizes the genuine loss transition.
        with ledger.engine.connect() as c:
            row, pending = LossService(ledger)._proof(c, record["id"])
            assert row["state"] == "pending" and pending.source.startswith("budget-ruin:")
