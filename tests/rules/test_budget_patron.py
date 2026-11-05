"""One actual patron interest and two real visits, with no private-state inference."""

import asyncio

from test_ledger import ADMIN
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_effect_service import pending

from girlframe.discord_adapter.m3_budget_patron import open_patron
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_patron import PatronService
from girlframe.services.m3_world import WorldService


def test_actual_patron_bond_native_visits_and_observed_tag(ledger):
    effects, game, _, _ = pending(ledger)
    WorldService(effects.strain.missions).npc(
        ADMIN,
        "real-rich-patron",
        state(game).revision,
        Npc(
            id="rich-patron",
            name="An actual wealthy patron",
            controller=1,
            jobs=("patron",),
            detail="A local patron with considerable wealth",
            revealed=True,
            cell=(0, 0),
        ),
    )
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    effects.strain.roll(ADMIN, "patron-budget-die", request.id, 1, state(game).revision)
    effects.strain.choose(ADMIN, "patron-budget-column", request.id, 2, state(game).revision, 2)
    identity = request.id + ":effect"
    before = state(game)

    async def interest():
        interaction = current(1, 28200)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = {
            "girl": ("2",),
            "patron": ("rich-patron",),
            "account": "The real patron takes a liking to this Girl",
        }
        await form.confirm.callback(current(1, 28201))
        assert form.completed

    asyncio.run(interest())
    assert (
        depth(state(game), current_ref(state(game), 2), ActorRef(kind="npc", entity="rich-patron"))
        == 1
    )
    assert effects.get(ADMIN, identity)["state"] == "resolved"
    service = PatronService(ledger)
    assert (
        next(x for x in InboxService(ledger).items(ADMIN) if x.identity == identity).task
        == "m3_budget_patron"
    )
    data = service.view(ADMIN, identity)
    service.visit(
        ADMIN,
        "actual-first-visit",
        identity,
        data["revision"],
        False,
        "The actual patron visits and sees no evidence",
    )
    assert state(game).handler_tags == before.handler_tags

    async def visit():
        interaction = current(1, 28202)
        await interaction.response.defer(ephemeral=True)
        await open_patron(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = {
            "witnessed": ("yes",),
            "tag": "Cruel",
            "account": "On this actual visit the patron observes evidence of Punishment",
        }
        await form.confirm.callback(current(1, 28203))
        assert form.completed

    asyncio.run(visit())
    after = state(game)
    assert len(after.handler_tags) == len(before.handler_tags) + 1
    assert after.handler_tags[-1].label == "Cruel"
    assert after.handler_tags[-1].giver_actor == ActorRef(kind="npc", entity="rich-patron")
