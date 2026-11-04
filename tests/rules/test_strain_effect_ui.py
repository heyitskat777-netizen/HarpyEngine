import asyncio

import pytest
from test_ledger import ADMIN
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_strain_effect_service import pending

from girlframe.discord_adapter.m3_strain_effects import DependentForm, open_effect
from girlframe.engine.m3_gorgon_catalog import ASSETS
from girlframe.services.inbox import InboxService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_native_gorgon_effect_has_legal_dependent_selectors_and_commits_once(ledger):
    svc, game, _, identity = pending(ledger)
    inbox = InboxService(ledger)
    assert any(x.task == "m3_strain_effect" for x in inbox.items(ADMIN))

    async def run():
        viewer = current(1)
        await viewer.response.defer(ephemeral=True)
        await open_effect(viewer, svc, identity)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, DependentForm) and len(state(game).world.gorgons) == 1
        assert not await form.interaction_check(current(2))
        chosen = ASSETS["incubus"][:5]
        form.values.update(
            {
                "class": ("directed",),
                "type": ("incubus",),
                "assets": chosen,
                "protected": (chosen[0],),
                "core": (chosen[1],),
                "weakness": "Draw it out and flank it",
                "goal": ("city0",),
                "name": "Edge threat",
                "cell": ("10,0",),
                "revealed": ("no",),
                "account": "A Directed Gorgon arrives and advances toward the city",
            }
        )
        form.controls()
        core = next(x for x in form.fields if x.key == "core")
        assert {x[0] for x in core.options} == set(chosen)
        await form.confirm.callback(current(1, 701))
        assert len(state(game).world.gorgons) == 2
        assert svc.get(ADMIN, identity)["state"] == "resolved"
        await form.confirm.callback(current(1, 701))
        assert len(state(game).world.gorgons) == 2

    asyncio.run(run())


def test_changing_type_clears_old_assets_instead_of_silently_applying_invalid_choices(ledger):
    svc, game, _, identity = pending(ledger)

    async def run():
        viewer = current(1)
        await viewer.response.defer(ephemeral=True)
        await open_effect(viewer, svc, identity)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            {"class": ("directed",), "type": ("incubus",), "assets": ASSETS["incubus"][:5]}
        )
        form.controls()
        form.values["type"] = ("mother",)
        form.controls()
        assert "assets" not in form.values
        assert len(state(game).world.gorgons) == 1
        other = current(2)
        with pytest.raises(WorkflowError):
            await open_effect(other, svc, identity)

    asyncio.run(run())
