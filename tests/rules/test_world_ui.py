import asyncio
from unittest.mock import AsyncMock

import pytest
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import service
from test_mission_ui import current
from test_world_service import ready

from girlframe.discord_adapter.m2_forms import Field, FormSelect, NativeForm
from girlframe.discord_adapter.m3_world import MapPages, open_world
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_setup_uses_native_choices_and_does_not_create_a_world_until_confirmed(ledger):
    missions, game = service(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    svc = WorldService(missions)

    async def run():
        viewer = current(1)
        await viewer.response.defer(ephemeral=True)
        await open_world(viewer, svc)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and state(game).world is None
        assert not await form.interaction_check(current(2))
        form.values.update(
            layout=("starter",),
            base=("0",),
            type=("growth",),
            secret_name="PRIVATE_CLASS_ZERO",
            assets="Resonance\nCrystalline body",
            core_assets=("0", "1"),
            weakness="It must be distracted and pinned",
        )
        await form.confirm.callback(current(1, 601))
        assert len(state(game).world.locations) == 8
        assert svc.get(PLAYER)["world"]["gorgons"] == []
        assert svc.get(ADMIN, private=True)["world"]["gorgons"][0]["name"] == "PRIVATE_CLASS_ZERO"

    asyncio.run(run())


def test_public_map_pages_recheck_membership_and_never_include_hidden_gorgons(ledger):
    svc, _ = ready(ledger)

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        pages = MapPages(svc, 2)
        await pages.show(viewer)
        content = viewer.edit_original_response.call_args.kwargs["content"]
        assert "secret" not in content and "base0" in content
        assert not await pages.interaction_check(current(3))
        with pytest.raises(WorkflowError):
            await open_world(viewer, svc)

    asyncio.run(run())


def test_multi_page_dropdown_retains_selections_and_enforces_total_maximum():
    async def run():
        form = NativeForm(
            2,
            "Choose",
            "Options across pages",
            [
                Field(
                    "items",
                    "Choose two",
                    tuple((str(i), "Option " + str(i)) for i in range(60)),
                    1,
                    2,
                )
            ],
            AsyncMock(),
        )
        first = next(x for x in form.children if isinstance(x, FormSelect))
        first._values = ["1"]
        await first.callback(current(2))
        form.option_page = 1
        form.controls()
        second = next(x for x in form.children if isinstance(x, FormSelect))
        second._values = ["26"]
        await second.callback(current(2))
        assert form.values["items"] == ("1", "26")
        form.option_page = 2
        form.controls()
        third = next(x for x in form.children if isinstance(x, FormSelect))
        third._values = ["51"]
        await third.callback(current(2))
        assert form.values["items"] == ("1", "26")

    asyncio.run(run())
