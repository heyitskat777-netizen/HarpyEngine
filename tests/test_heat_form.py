"""Native Play options follow actual resources and the selected trigger."""

import asyncio
from unittest.mock import AsyncMock

from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game
from test_start_dashboard_ui import current

from girlframe.discord_adapter.heat_form import HeatForm
from girlframe.discord_adapter.m2_forms import Field, FormSelect
from girlframe.discord_adapter.m2_ui import open_play


def choices(form, key):
    return tuple(x for x, _ in next(f for f in form.fields if f.key == key).options)


async def choose(form, key, value, interaction):
    form.index = next(i for i, field in enumerate(form.fields) if field.key == key)
    form.controls()
    selector = next(x for x in form.children if isinstance(x, FormSelect))
    selector._values = [] if value is None else [value]
    await selector.callback(interaction)


def test_actual_pilot_wizard_limits_heat_and_only_asks_witness_for_refusal(ledger):
    game, _, _, dice = setup_game(ledger)

    async def run():
        opened = current(PLAYER, 89801)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_play(opened, game, _pilot=True)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, HeatForm)
        assert choices(form, "heat") == ("0",)
        assert not {"witnessed", "pair_share", "gain"} & {x.key for x in form.fields}
        await choose(form, "play", "disobey_orders", current(PLAYER, 89802))
        assert "witnessed" in {x.key for x in form.fields}
        await choose(form, "witnessed", "yes", current(PLAYER, 89803))
        await choose(form, "play", "keep_your_head", current(PLAYER, 89804))
        assert "witnessed" not in {x.key for x in form.fields}
        assert "witnessed" not in form.values
        identity = choices(form, "identity")[0]
        await choose(form, "identity", identity, current(PLAYER, 89805))
        assert choices(form, "gain") == ("1", "2", "3")
        assert choices(form, "heat") == ("0",)
        await choose(form, "gain", "3", current(PLAYER, 89806))
        assert choices(form, "heat") == ("0", "1", "2", "3")
        await choose(form, "heat", "3", current(PLAYER, 89807))
        await choose(form, "gain", "1", current(PLAYER, 89808))
        assert choices(form, "heat") == ("0", "1") and "heat" not in form.values
        assert dice.calls == 0 and game.sheet(PLAYER)["heat"] == 0
        assert all(not x["marked"] for x in game.sheet(PLAYER)["identities"])

    asyncio.run(run())


def test_paired_split_and_current_balance_refresh_cannot_submit_stale_spend():
    fields = [
        Field("identity", "Identity", (("paired", "Paired"), ("none", "None"))),
        Field("gain", "Gain", (("5", "5"),)),
        Field("pair_share", "Share", (("0", "0"),)),
        Field("heat", "Spend", (("99", "99"),)),
    ]
    resources = {
        "girl": "BONDED",
        "heat": 0,
        "pair": 3,
        "identities": [{"id": "paired", "paired": True, "marked": False}],
    }

    async def run():
        submit = AsyncMock(return_value="Saved")
        refresh = AsyncMock(return_value=resources)
        form = HeatForm(
            2, "Play", "Confirm choices", fields, submit, resources=resources, refresh=refresh
        )
        await form.present(current(OTHER, 89900))
        assert refresh.await_count == 0
        await choose(form, "identity", "paired", current(PLAYER, 89901))
        await choose(form, "gain", "5", current(PLAYER, 89902))
        assert choices(form, "heat") == ("5",)
        await choose(form, "pair_share", "2", current(PLAYER, 89903))
        assert choices(form, "heat") == ("0", "1", "2", "3")
        await choose(form, "identity", "none", current(PLAYER, 89904))
        assert form.values["identity"] == ("none",)
        assert "pair_share" not in {x.key for x in form.fields}
        resources["heat"] = 2
        await form.present(current(PLAYER, 89905))
        await choose(form, "heat", "2", current(PLAYER, 89906))
        resources["heat"] = 1
        await form.confirm.callback(current(PLAYER, 89907))
        assert submit.await_count == 0 and choices(form, "heat") == ("0", "1")
        await choose(form, "heat", "1", current(PLAYER, 89908))
        await form.confirm.callback(current(PLAYER, 89909))
        assert submit.await_count == 1 and form.completed

    asyncio.run(run())


def test_explicit_no_heat_counter_and_disposal_alias_preserve_source_budgets():
    fields = [
        Field("play", "Play", (("keep_your_head", "Keep"), ("dose_up", "Dose"))),
        Field("identity", "Mark", (("i", "Identity"),), minimum=0, required=False),
        Field("gain", "Gain", (("0", "0"),)),
        Field("disposable", "Disposal", (("0", "Keep"), ("4", "Remove"))),
        Field("heat", "Spend", (("99", "99"),)),
    ]
    resources = {"heat": 2, "identities": [{"id": "i", "marked": False}]}

    async def run():
        form = HeatForm(
            2,
            "Counter",
            "Original source",
            fields,
            AsyncMock(),
            resources=resources,
            no_heat_plays=("keep_your_head",),
            identity_plays=("dose_up",),
            disposal_plays=("dose_up",),
            disposal_key="disposable",
            disposal_allowed=True,
        )
        await choose(form, "play", "keep_your_head", current(PLAYER, 89920))
        assert choices(form, "heat") == ("0",)
        assert "identity" not in {x.key for x in form.fields}
        await choose(form, "play", "dose_up", current(PLAYER, 89921))
        await choose(form, "identity", "i", current(PLAYER, 89922))
        await choose(form, "gain", "3", current(PLAYER, 89923))
        await choose(form, "disposable", "4", current(PLAYER, 89924))
        assert choices(form, "heat") == ("9",)
        await choose(form, "play", "keep_your_head", current(PLAYER, 89925))
        assert choices(form, "heat") == ("0",) and "disposable" not in form.values
        minimum = HeatForm(
            2,
            "Actual cost",
            "Requires Heat",
            [fields[-1]],
            AsyncMock(),
            resources={"heat": 0},
            minimum_spend=1,
        )
        assert choices(minimum, "heat") == ("unavailable",)
        assert "1" not in choices(minimum, "heat")

    asyncio.run(run())
