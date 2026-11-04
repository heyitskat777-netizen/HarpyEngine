import asyncio

from test_actor_service import legacy, ready
from test_ledger import PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_actors import open_actors

ledger = ledger_fixture


def test_owned_role_dropdown_keeps_girl_and_npc_resources_separate(ledger):
    svc, game = ready(ledger)

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_actors(viewer, svc)
        picker = viewer.edit_original_response.call_args.kwargs["view"]
        assert len(picker.options) == 2
        assert not await picker.interaction_check(current(3))
        npc = next(x for x in svc.choices(PLAYER)["actors"] if x["kind"] == "npc")
        result = current(2, 995)
        await result.response.defer(ephemeral=True)
        await picker.open_item(result, npc["token"])
        text = result.edit_original_response.call_args.kwargs["content"]
        assert "PRIVATE_NPC_NAME" in text and "Assets: 0" in text
        assert "Heat:" not in text and state(game).sheets["2"].assets

    asyncio.run(run())


def test_legacy_character_link_is_explicit_and_uses_its_actual_snapshot(ledger):
    svc, game = ready(ledger)
    legacy(svc, game)

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_actors(viewer, svc)
        picker = viewer.edit_original_response.call_args.kwargs["view"]
        assert "bind-legacy" in dict(picker.options)
        review = current(2, 996)
        await review.response.defer(ephemeral=True)
        await picker.open_item(review, "bind-legacy")
        form = review.edit_original_response.call_args.kwargs["view"]
        assert state(game).sheets["2"].character_id is None
        form.values["confirm"] = ("yes",)
        await form.confirm.callback(current(2, 997))
        assert form.completed and state(game).sheets["2"].character_id is not None

    asyncio.run(run())
