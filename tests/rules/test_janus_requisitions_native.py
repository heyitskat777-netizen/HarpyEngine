"""One normal native JANUS acquisition → treatment → owned training scene."""

import asyncio
from uuid import uuid4

from test_enforcer_requisitions import approved
from test_janus_core_service import admitted
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_janus import open_janus
from girlframe.discord_adapter.m3_janus_requisitions import open_training, open_treatment
from girlframe.discord_adapter.m3_punishments import PickerSelect
from girlframe.engine.m3_janus import BATTERY, CORE
from girlframe.engine.m3_janus_requisitions import TRAINING
from girlframe.services.m3_janus import JanusService
from girlframe.services.m3_janus_requisitions import JanusRequisitionService


def test_native_owned_janus_purchase_treatment_and_training_preserve_next_screen(
    ledger, tmp_path, monkeypatch
):
    _, game, _, _ = admitted(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(CORE, BATTERY, TRAINING))
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_permissions", actual)
    service = JanusRequisitionService(game)

    async def pick(view, value, identity):
        selector = next(x for x in view.children if isinstance(x, PickerSelect))
        selector._values = [value]
        interaction = current(2, identity)
        await selector.callback(interaction)
        return interaction.edit_original_response.call_args.kwargs["view"]

    async def run():
        interaction = current(2, 996001)
        await interaction.response.defer(ephemeral=True)
        await open_janus(interaction, JanusService(game))
        hub = interaction.edit_original_response.call_args.kwargs["view"]
        menu = await pick(hub, "requisitions", 996002)
        form = await pick(menu, "buy", 996003)
        assert isinstance(form, NativeForm) and state(game).sheets["2"].permissions == 2
        form.values.update(
            rule=(TRAINING,), account="Actual source-authorized training", payment=("yes",)
        )
        await form.confirm.callback(current(2, 996004))
        assert form.completed and state(game).sheets["2"].permissions == 0
        treatment = current(2, 996005)
        await treatment.response.defer(ephemeral=True)
        await open_treatment(treatment, service)
        remove = treatment.edit_original_response.call_args.kwargs["view"]
        tag = next(x["id"] for x in service.tags(PLAYER)["tags"] if x["label"] == "Drugged")
        remove.values.update(tag=(tag,), account="Actual source-authorized sedative treatment ends")
        await remove.confirm.callback(current(2, 996006))
        assert remove.completed and len(state(game).janus_cores[-1].tags) == 3
        training = current(2, 996007)
        await training.response.defer(ephemeral=True)
        await open_training(training, service)
        start = training.edit_original_response.call_args.kwargs["view"]
        start.values.update(account="Actual Core training scene", confirm=("yes",))
        next_step = current(2, 996008)
        await start.confirm.callback(next_step)
        assert start.completed
        assert next_step.edit_original_response.call_args.kwargs["view"] is not start
        assert state(game).role_punishments[-1].source_kind == "janus_training"

    asyncio.run(run())


def test_actual_pandora_native_multistep_confirm_preserves_new_forms(ledger, tmp_path, monkeypatch):
    from test_ledger import ADMIN
    from test_m2_game import Gateway, pass_tags, tick
    from test_off_duty_cycle import activate, prepared

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.discord_adapter.m3_janus_requisitions import open_pandora, open_pandora_child
    from girlframe.engine.m3_janus_pandora import pregnancies
    from girlframe.engine.m3_janus_requisitions import PANDORA
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.m3_off_duty_cycle import CycleService

    _, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(PANDORA,))
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_pandora_funds", actual)
    purchases = JanusRequisitionService(game)
    menu = purchases.menu(PLAYER)
    purchases.buy_rule(
        PLAYER, str(uuid4()), menu["source_sha256"], PANDORA, "Actual PANDORA acquisition"
    )
    activate(CycleService(OffDutyService(MissionService(ledger))), game, period)
    game.dice.faces = (4, 5)

    async def prepare():
        interaction = current(2, 996101)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_pandora(interaction, game)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(heat=("0",), account="The actual Inseminated Frame gives birth")
        confirmed = current(2, 996102)
        confirmed.channel_id = 900
        await form.confirm.callback(confirmed)
        assert form.completed

    asyncio.run(prepare())
    tick(GameWorker(game), Gateway(), 3)
    pass_tags(game)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "janus_pandora_child")

    async def describe():
        interaction = current(1, 996103)
        await interaction.response.defer(ephemeral=True)
        await open_pandora_child(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            name="Actual newborn",
            type=("growth",),
            class_=("benevolent",),
            account="Actual obedient vicious child",
        )
        form.values["class"] = ("benevolent",)
        confirm = current(1, 996104)
        await form.confirm.callback(confirm)
        assets = confirm.edit_original_response.call_args.kwargs["view"]
        assert isinstance(assets, NativeForm) and assets is not form
        assets.values.update(assets=("Overgrown Musculature", "Infectious Flagella"))
        next_confirm = current(1, 996105)
        await assets.confirm.callback(next_confirm)
        details = next_confirm.edit_original_response.call_args.kwargs["view"]
        assert isinstance(details, NativeForm) and details is not assets
        details.values.update(
            asset0="Actual muscle",
            asset1="Actual flagella",
            core=("0",),
            weakness="Actual exposed Core weakness",
        )
        await details.confirm.callback(current(1, 996106))
        assert details.completed

    asyncio.run(describe())
    assert pregnancies(state(game))[-1].child is not None and game.dice.calls == 1
