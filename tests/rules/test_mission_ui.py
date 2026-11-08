import asyncio
from unittest.mock import AsyncMock

import pytest
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_mission_service import service
from test_read_only_bot import interaction

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_missions import MissionQueue, MissionSelect, open_mission
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def current(user=2, identity=500):
    value = interaction()
    value.user.id = user
    value.id = identity
    return value


def test_native_offer_response_requires_owner_confirmation_and_handler_dispatch(ledger):
    svc, _ = service(ledger)
    row = svc.offer(ADMIN, "offer", "Synthetic objective", (2,))

    async def run():
        viewer = current()
        await viewer.response.defer(ephemeral=True)
        await open_mission(viewer, svc, row["id"])
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert {x[0] for x in form.fields[0].options} == {"accept", "decline"}
        assert svc.get(PLAYER, row["id"])["mission"]["responses"] == {}
        form.values["action"] = ("accept",)
        await form.confirm.callback(current(identity=501))
        assert svc.get(PLAYER, row["id"])["mission"]["responses"] == {"2": "accept"}
        assert svc.get(PLAYER, row["id"])["mission"]["phase"] == "offered"
        handler = current(1, 502)
        await handler.response.defer(ephemeral=True)
        await open_mission(handler, svc, row["id"])
        controls = handler.edit_original_response.call_args.kwargs["view"]
        assert controls.fields[0].options == (("start", "Dispatch accepted participants"),)

    asyncio.run(run())


def test_mission_queue_pages_native_selects_and_rejects_other_users():
    async def run():
        rows = [
            {"id": str(i), "objective": "Mission " + str(i), "phase": "offered"} for i in range(61)
        ]
        view = MissionQueue(AsyncMock(), 2, rows)
        assert len(next(x for x in view.children if isinstance(x, MissionSelect)).options) == 25
        view.page = 2
        view.controls()
        assert len(next(x for x in view.children if isinstance(x, MissionSelect)).options) == 11
        assert not await view.interaction_check(current(3))

    asyncio.run(run())


def test_noninvitee_cannot_open_mission_details_or_controls(ledger):
    svc, _ = service(ledger)
    row = svc.offer(ADMIN, "offer", "Private objective", (2,))

    async def run():
        viewer = current(3)
        with pytest.raises(WorkflowError):
            await open_mission(viewer, svc, row["id"])
        viewer.edit_original_response.assert_not_awaited()

    asyncio.run(run())
