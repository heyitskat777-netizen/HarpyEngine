"""Actual destroyed Harpy objects retain provenance without a repairable ghost Asset."""

from uuid import uuid4

import pytest
from test_harpy_item_resources import carried
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.m3_harpy_resources import assets, destroy_asset, set_assets
from girlframe.engine.m3_items import actual_asset
from girlframe.services.m3_items import prove_item


@pytest.mark.parametrize("converted", [False, True])
def test_real_paid_and_transferred_asset_destruction_retains_wreckage_and_source(
    ledger, tmp_path, monkeypatch, converted
):
    _, game, actor, item = carried(ledger, tmp_path, monkeypatch, converted=converted)
    before = state(game)
    resources = assets(before, actor)
    source = before.sheets["3"].model_dump_json()
    event = str(uuid4())
    changed = destroy_asset(before, actor, item.asset_id, event=event)
    ruined = next(x for x in changed.held_items if x.id == item.id)
    assert actual_asset(changed, ruined) is None and ruined.condition == "ruined"
    assert ruined.asset_id is None and ruined.asset_owner is None
    assert (
        ruined.origin_asset_json == item.origin_asset_json
        and ruined.source_event == item.source_event
    )
    assert ruined.holder == item.holder and ruined.state_event == event
    assert item.asset_id not in {x.id for x in assets(changed, actor)}
    assert changed.sheets["3"].model_dump_json() == source and before.held_items[-1] == item
    with ledger.transaction() as c:
        game.event(
            c, 2, str(uuid4()), "synthetic.actual_contest_destruction", changed, event_id=event
        )
        assert prove_item(c, game, changed, item.id) == ruined
    with pytest.raises(ValueError, match="exactly the existing"):
        set_assets(changed, actor, resources, event=str(uuid4()))
    with pytest.raises(ValueError, match="actual original Harpy Asset"):
        destroy_asset(changed, actor, item.asset_id, event=str(uuid4()))
