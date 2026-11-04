import asyncio

from test_frame_reward_service import own, setup
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import roll_for

from girlframe.discord_adapter.m3_frame_rewards import open_reward
from girlframe.discord_adapter.m3_strain_effects import DependentForm
from girlframe.engine.m3_frame_state import FrameRuntime

ledger = ledger_fixture


def test_janus_native_selector_records_actual_named_official_only_on_confirmation(ledger):
    svc, cycle, game, period = setup(ledger)
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    identity = own(svc, PLAYER, period)["id"]

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_reward(viewer, svc, identity)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, DependentForm)
        assert not await form.interaction_check(current(1))
        form.values.update(fulfilled=("yes",))
        form.controls()
        official = next(x for x in form.fields if x.key == "official")
        assert ("handler:1", "Handler at this Off-Duty Play") in official.options
        assert state(game).sheets["2"].permissions == 0
        form.values.update(
            official=("handler:1",), account="The owner records its actual demonstration"
        )
        await form.confirm.callback(current(2, 801))
        assert form.completed and state(game).sheets["2"].permissions == 1

    asyncio.run(run())


def test_read_only_frame_review_before_its_roll_has_no_premature_submission(ledger):
    svc, _, game, period = setup(ledger)
    identity = own(svc, PLAYER, period)["id"]

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_reward(viewer, svc, identity)
        content = viewer.edit_original_response.call_args.kwargs["content"]
        assert "Tag choices first" in content
        assert state(game).sheets["2"].permissions == 0

    asyncio.run(run())


def test_wyvern_native_offering_and_separate_handler_interest_controls(ledger):
    svc, cycle, game, period = setup(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].frame = "WYVERN 0.4"
        canon.sheets["2"].frame_runtime = FrameRuntime(
            id="wyvern", generation=1, source_work="synthetic-frame"
        )
        canon.sheets["2"].revision += 1
        game.event(c, 1, "wyvern-ui-frame", "synthetic.frame", canon)
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    identity = own(svc, PLAYER, period)["id"]

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_reward(viewer, svc, identity)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            fulfilled=("yes",), offering="A peculiar specimen", account="I brought it back"
        )
        form.controls()
        await form.confirm.callback(current(2, 802))
        assert form.completed and state(game).sheets["2"].permissions == 0
        child = next(
            x
            for x in svc.periods.get(ADMIN, period)["work"]
            if x["kind"] == "frame_reward_interest"
        )
        handler = current(1, 803)
        await handler.response.defer(ephemeral=True)
        await open_reward(handler, svc, child["id"])
        answer = handler.edit_original_response.call_args.kwargs["view"]
        assert "A peculiar specimen" in answer.text()
        assert not await answer.interaction_check(current(2))
        answer.values["interest"] = ("yes",)
        await answer.confirm.callback(current(1, 804))
        assert answer.completed and state(game).sheets["2"].permissions == 1

    asyncio.run(run())
