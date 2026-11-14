"""Leaving an unpaid purchase and reopening it cannot create a second charge."""

import asyncio

from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_personal_firearm_service import setup

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_personal_firearm import open_acquisition
from girlframe.services.m3_personal_firearm import PersonalFirearmService


def test_native_unconfirmed_purchase_reopens_and_old_form_cannot_charge_again(
    ledger, tmp_path, monkeypatch
):
    service, _, game, _ = setup(ledger, tmp_path, monkeypatch)
    before = state(game).model_dump_json()

    async def open_form(source, interaction_id):
        caller = current(2, interaction_id)
        await caller.response.defer(ephemeral=True)
        await open_acquisition(caller, source, "frame_grafting")
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            replace=("none",),
            account="Actual player-selected Personal Firearm acquisition",
            payment=("yes",),
        )
        return form

    async def run():
        # Filling the form is not payment. The player leaves it unconfirmed,
        # then reopens the purchase with a new service over the saved database.
        abandoned = await open_form(service, 21401)
        assert state(game).model_dump_json() == before
        reopened_service = PersonalFirearmService(game, service.registry)
        reopened = await open_form(reopened_service, 21402)
        assert state(game).model_dump_json() == before
        await reopened.confirm.callback(current(2, 21403))
        assert reopened.completed
        saved = state(game)
        assert saved.sheets["2"].permissions == 2
        assert len(saved.personal_firearms) == 1
        assert len(saved.personal_firearms[0].issues) == 1
        assert sum(x.name == "Personal Firearm" for x in saved.sheets["2"].assets) == 1
        receipt = saved.personal_firearms[0].purchase
        assert receipt is not None
        assert sum(x.id == receipt for x in saved.requisitions) == 1

        # Returning to the still-open earlier form must not buy the same rule
        # again or consume additional Permissions under a new interaction key.
        stale = current(2, 21404)
        await abandoned.confirm.callback(stale)
        assert not abandoned.completed
        assert stale.edit_original_response.call_args.kwargs["view"] is abandoned
        assert state(game).model_dump_json() == saved.model_dump_json()
        assert game.dice.calls == 0

    asyncio.run(run())
