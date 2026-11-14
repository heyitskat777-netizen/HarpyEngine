"""Feedback Bond rewrite preserves free slots and the authoritative Asset cap."""

import asyncio

from test_ankou_feedback import last_source, ready
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_ankou_feedback import open_choice
from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_core import install
from girlframe.engine.m3_janus_link_state import BatteryAsset
from girlframe.services.m3_ankou_feedback import _bond_replaceable, _bond_target_blocker


def test_actual_bond_rewrite_preserves_free_slot_and_replacement_contract(
    ledger, tmp_path, monkeypatch
):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    _, source = last_source(game, worker, gateway)
    before = state(game)
    actor, target = current_ref(before, 2), current_ref(before, 3)
    assert depth(before, actor, target) > 0
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")
    data = game.decision(PLAYER, row["id"])["ankou_feedback"]
    assert data["assets"] and not any(x["bond_replaceable"] for x in data["assets"])

    async def submit():
        opened = current(2, 98901)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert next(x for x in form.fields if x.key == "replace").options == ()
        assert target.token in dict(next(x for x in form.fields if x.key == "bond_target").options)
        form.values.update(
            effect=("bond",),
            bond_target=(target.token,),
            replace=(),
            name="My chosen emotional distance",
            account="I rewrite this actual Bond as my own psychological Asset",
        )
        response = current(2, 98902)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(submit())
    after = state(game)
    assert depth(after, actor, target) == 0
    assert _bond_target_blocker(after, actor, target) is not None
    assert rules.get(after, source.id).phase == "resolved"
    assert {x.id for x in before.sheets["2"].assets} < {x.id for x in after.sheets["2"].assets}
    assert any(x.id == source.id + ":bond" for x in after.sheets["2"].assets)

    # Synthetic eligibility contract only: no invented saved battery transition.
    sheet = before.sheets["2"].model_copy(deep=True)
    sheet.assets = [AssetState(id=f"slot-{i}", family="girl", name=f"Slot {i}") for i in range(4)]
    eligible = sheet.assets[0]
    assert _bond_replaceable(sheet, eligible)
    new = AssetState(id="new-bond", family="girl", name="Rewritten Bond")
    assert len(install(sheet, new, replace=eligible.id).sheet.assets) == 4
    eligible.void = True
    assert not _bond_replaceable(sheet, eligible)
    eligible.void = False
    battery = BatteryAsset(link="synthetic-contract-only", choice="cognition")
    temporary = AssetState(
        id=battery.asset_id, family="girl", name=battery.name, battery_asset=battery
    )
    sheet.assets.append(temporary)
    assert _bond_replaceable(sheet, eligible)
    assert not _bond_replaceable(sheet, temporary)
    sheet.assets.remove(eligible)
    assert not any(_bond_replaceable(sheet, x) for x in sheet.assets)
