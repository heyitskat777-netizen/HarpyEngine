"""Stored mechanical objects stay outside a Harpy's carried resource and update authority."""

from uuid import uuid4

import pytest
from test_harpy_item_resources import carried
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_resources import assets, set_assets
from girlframe.services.m3_actors import profiles


@pytest.mark.parametrize("converted", [False, True])
def test_real_acquired_object_stored_in_scene_does_not_grant_carried_harpy_assets(
    ledger, tmp_path, monkeypatch, converted
):
    _, game, actor, item = carried(ledger, tmp_path, monkeypatch, converted=converted)
    original = state(game)
    assert any(x.id == item.asset_id for x in assets(original, actor))
    event = str(uuid4())
    # A factual storage fixture exercises the new existing-object location model;
    # acquisition and transfer above are genuine source-owned paid workflows.
    with ledger.transaction() as c:
        scene = game.scene(c, 900)["id"]
        original.held_items = [
            x.model_copy(
                update=dict(
                    location_mode="scene", scene_id=scene, location_event=event, state_event=event
                )
            )
            if x.id == item.id
            else x
            for x in original.held_items
        ]
        game.event(c, 2, str(uuid4()), "synthetic.actual_object_storage", original, event_id=event)
    stored = state(game)
    assert item.asset_id not in {x.id for x in assets(stored, actor)}
    with ledger.engine.connect() as c:
        assert item.asset_id not in {
            x.id for x in resolve(stored, actor, profiles(c, ledger.campaign_id)).assets
        }
    changed = set_assets(stored, actor, assets(stored, actor), event=str(uuid4()))
    assert changed.held_items == stored.held_items
    assert changed.sheets == stored.sheets
