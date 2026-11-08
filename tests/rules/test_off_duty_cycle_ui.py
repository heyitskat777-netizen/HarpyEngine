import asyncio

from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, prepared, roll_for

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_off_duty import open_period
from girlframe.discord_adapter.m3_off_duty_cycle import open_action
from girlframe.services.inbox import InboxService

ledger = ledger_fixture


def test_native_play_confirmation_uses_actual_period_and_no_dice_before_worker(ledger):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)

    async def run():
        viewer = current(2)
        viewer.channel_id = 900
        await viewer.response.defer(ephemeral=True)
        await open_action(viewer, cycle, identity, "play")
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert "heat" not in {x.key for x in form.fields}
        assert not await form.interaction_check(current(3))
        form.values.update(
            context="Actual time at base", gain=("0",), share=("0",), confirm=("yes",)
        )
        await form.confirm.callback(current(2, 702))
        with ledger.engine.connect() as c:
            saved = cycle.periods._get(c, identity)
            action = game.action(c, saved.progress["2"].action_id)
        assert action["data"]["m3"]["period_id"] == identity
        assert action["data"]["receipt"] is None

    asyncio.run(run())


def test_recovery_selectors_and_inbox_never_claim_an_absent_participants_confirmation(ledger):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)
    roll_for(cycle, game, identity, PLAYER, (6, 6))
    call(cycle, game, PLAYER, identity, "scene", "nearby_city", (2, 3), "PRIVATE_SCENE_ACCOUNT")
    inbox = InboxService(ledger)
    private_items = inbox.items(PLAYER)
    assert any(x.task == "m3_off_duty" for x in private_items)
    assert "PRIVATE_SCENE_ACCOUNT" not in str(inbox.items(ADMIN))

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_action(viewer, cycle, identity, "recover")
        form = viewer.edit_original_response.call_args.kwargs["view"]
        form.values.update(repairs=("yes",))
        await form.confirm.callback(current(2, 703))
        assert not cycle.review(PLAYER, identity)["own"]["recovered"]
        assert (
            "required on-screen"
            in viewer.edit_original_response.call_args.kwargs.get("content", "")
            or not form.completed
        )
        await open_action(viewer, cycle, identity, "ack:2")
        form = viewer.edit_original_response.call_args.kwargs["view"]
        form.values.update(confirm=("yes",))
        await form.confirm.callback(current(2, 704))
        assert cycle.review(PLAYER, identity)["own"]["scene"]["acknowledgements"] == [2]

    asyncio.run(run())


def test_period_dashboard_exposes_owned_choices_without_advancing_on_open(ledger):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)
    before = state(game)

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_period(viewer, cycle.periods)
        view = viewer.edit_original_response.call_args.kwargs["view"]
        assert any(value == "action:play" for value, label in view.options)
        assert not await view.interaction_check(current(3))

    asyncio.run(run())
    assert state(game) == before
