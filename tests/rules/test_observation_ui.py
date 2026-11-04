import asyncio

from test_ledger import ADMIN
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, state, tick
from test_mission_ui import current
from test_observation_service import pending, roll_for, setup, work_id

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_observation import open_work
from girlframe.discord_adapter.m3_off_duty_cycle import open_action

ledger = ledger_fixture


def test_native_observation_confirmation_defers_status_and_dice_until_chat_lock(ledger):
    svc, cycle, game, period = setup(ledger)
    before = state(game)

    async def run():
        viewer = current(2)
        viewer.channel_id = 900
        await viewer.response.defer(ephemeral=True)
        await open_action(viewer, cycle, period, "play")
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert "Void Observation" in form.text()
        assert "heat" not in {x.key for x in form.fields}
        form.values.update(context="Observed at base", gain=("0",), share=("0",), confirm=("yes",))
        await form.confirm.callback(current(2, 901))
        assert form.completed and state(game).order == before.order and game.dice.calls == 0

    asyncio.run(run())
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    assert state(game).order == (3, 2) and game.dice.calls == 1


def test_native_owned_observation_choices_create_separate_handler_tag_details(ledger):
    svc, _, game, period = setup(ledger)
    roll_for(svc, game, period)

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_work(viewer, svc, work_id(period, 2, 2))
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1))
        assert form.fields[0].minimum == form.fields[0].maximum == 1
        form.values["choices"] = ("public_display_tag",)
        await form.confirm.callback(current(2, 902))
        assert form.completed and not state(game).sheets["2"].tags
        identity = pending(svc, ADMIN, period)
        handler = current(1, 903)
        await handler.response.defer(ephemeral=True)
        await open_work(handler, svc, identity)
        effect = handler.edit_original_response.call_args.kwargs["view"]
        assert not await effect.interaction_check(current(2))
        effect.values.update(tag="Watched", account="The actual populace display")
        await effect.confirm.callback(current(1, 904))
        assert effect.completed and state(game).sheets["2"].tags[-1].label == "Watched"

    asyncio.run(run())
