import asyncio

from test_ledger import ADMIN, OTHER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_reaction_service import setup, work

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_reactions import open_reaction

ledger = ledger_fixture


def test_doctor_native_confirmation_applies_the_source_effect_once(ledger):
    svc, missions, game, mission = setup(ledger)
    task = work(missions, mission, "doctor_obsolescence")

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_reaction(interaction, svc, task["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert state(game).sheets["2"].obsolescence_marked == 0
        form.values["confirm"] = ("yes",)
        await form.confirm.callback(current(1, 12345))
        assert form.completed and state(game).sheets["2"].obsolescence_marked == 1

    asyncio.run(run())


def test_princess_native_review_saves_human_fact_and_does_not_commit_normal_rewards(ledger):
    svc, missions, game, mission = setup(ledger, girl="PRINCESS", frame="JANUS-B")
    task = work(missions, mission, "princess_mission_end")

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_reaction(interaction, svc, task["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert "counts as an order" in form.instructions
        assert state(game).sheets["2"].permissions == 0
        form.values = {"upheld": ("yes",), "rationale": "Synthetic factual review"}
        await form.confirm.callback(current(1, 12346))
        assert form.completed and state(game).sheets["2"].permissions == 1
        assert missions.get(ADMIN, mission["id"])["mission"]["phase"] == "ending"

    asyncio.run(run())


def test_reaction_is_in_requests_but_unrelated_pilot_cannot_see_it(ledger):
    from girlframe.services.inbox import InboxService

    _, _, _, _ = setup(ledger)
    items = InboxService(ledger).items(ADMIN)
    assert any(x.task == "m3_reaction" for x in items)
    assert not any(x.task == "m3_reaction" for x in InboxService(ledger).items(OTHER))
