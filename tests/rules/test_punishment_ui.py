import asyncio
from unittest.mock import AsyncMock

from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_punishment_service import ended, submit

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_punishments import (
    Picker,
    PickerSelect,
    open_details,
    open_discipline,
)
from girlframe.engine.m3_punishments import Details

ledger = ledger_fixture


def test_inflictor_selectors_require_confirmation_and_preserve_explicit_identity_choices(ledger):
    svc, _, game, _, identity = ended(ledger)

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_discipline(interaction, svc, identity)
        picker = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        assert "execution" not in dict(picker.options)
        await picker.open_item(interaction, "sedation")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert form.fields[0].minimum == form.fields[0].maximum == 2
        assert not any(x.marked for x in state(game).sheets["3"].identities)
        form.values["identities"] = ("identity:1", "identity:3")
        await form.confirm.callback(current(1, 9001))
        assert form.completed
        assert [x.marked for x in state(game).sheets["3"].identities] == [False, True, False, True]

    asyncio.run(run())


def test_subject_has_a_read_only_view_and_cannot_open_the_inflictors_controls(ledger):
    svc, _, _, _, identity = ended(ledger)

    async def run():
        interaction = current(3)
        await interaction.response.defer(ephemeral=True)
        await open_discipline(interaction, svc, identity)
        assert interaction.edit_original_response.call_args.kwargs["view"] is None
        assert "designated owner" in interaction.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())


def test_native_handler_consultation_is_not_automatic_punishment_application(ledger):
    svc, _, game, _, identity = ended(ledger)
    submit(svc, ADMIN, identity, Details(kind="passing_responsibility", delegate=2))

    async def run():
        interaction = current(2)
        await interaction.response.defer(ephemeral=True)
        await open_details(interaction, svc, identity, "frame_disassembly")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = {"asset": ("frame:0",), "operation": ("consult",)}
        await form.confirm.callback(current(2, 9010))
        consultation = svc.get(PLAYER, identity)["consultation"]
        handler = current(1)
        await handler.response.defer(ephemeral=True)
        await open_discipline(handler, svc, consultation["id"])
        review = handler.edit_original_response.call_args.kwargs["view"]
        review.values["approve"] = ("yes",)
        await review.confirm.callback(current(1, 9011))
        assert any(x.id == "frame:0" for x in state(game).sheets["3"].assets)
        await open_details(interaction, svc, identity, "frame_disassembly")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = {"asset": ("frame:0",), "operation": ("apply",)}
        await form.confirm.callback(current(2, 9012))
        assert not any(x.id == "frame:0" for x in state(game).sheets["3"].assets)

    asyncio.run(run())


def test_private_picker_pages_at_twenty_five_and_rejects_other_users():
    async def run():
        view = Picker(
            2, "Synthetic queue", tuple((str(i), "Work " + str(i)) for i in range(61)), AsyncMock()
        )
        assert len(next(x for x in view.children if isinstance(x, PickerSelect)).options) == 25
        view.page = 2
        view.controls()
        assert len(next(x for x in view.children if isinstance(x, PickerSelect)).options) == 11
        assert not await view.interaction_check(current(3))

    asyncio.run(run())


def test_sedation_zero_identities_is_an_explicit_confirmed_heat_reset(ledger):
    svc, _, game, _, identity = ended(ledger)
    with ledger.transaction() as c:
        saved = state(game)
        saved.sheets["3"].identities = []
        saved.sheets["3"].heat = 6
        game.event(c, 1, "synthetic-empty-identities", "synthetic.identities", saved)

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_details(interaction, svc, identity, "sedation")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert "No Identities remain" in form.fields[0].label
        assert state(game).sheets["3"].heat == 6
        form.values["confirm"] = ("yes",)
        await form.confirm.callback(current(1, 9020))
        assert form.completed and state(game).sheets["3"].heat == 0
        assert not state(game).sheets["3"].identities

    asyncio.run(run())


def test_last_asset_native_context_is_a_handler_fact_review(ledger):
    svc, missions, game, _, identity = ended(ledger)
    with ledger.transaction() as c:
        saved = state(game)
        next(x for x in saved.sheets["3"].assets if x.id == "girl:1").damaged = True
        game.event(c, 1, "synthetic-damage", "synthetic.damage", saved)
    submit(svc, ADMIN, identity, Details(kind="beating", asset="girl:0", tag="Bruised"))
    task = next(x for x in missions.owned_work(ADMIN) if x["kind"] == "punishment_helpless")

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_discipline(interaction, svc, task["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = {"piloting": ("no",), "evidence": "Observed outside Frame"}
        await form.confirm.callback(current(1, 9021))
        assert form.completed and state(game).sheets["3"].helpless_against == (1,)

    asyncio.run(run())
