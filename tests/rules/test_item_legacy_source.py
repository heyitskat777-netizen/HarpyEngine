"""Old physical-object JSON keeps its signed shape and real source custody proof."""

import hashlib
import json

import sqlalchemy as sa
from test_handler_items import held
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.engine.m3_item_state import HeldItem
from girlframe.services.m2_game import GameService
from girlframe.services.m3_items import prove_item, prove_transfer


def test_old_default_item_json_roundtrip_keeps_fingerprint_and_actual_source_replay(
    ledger, tmp_path, monkeypatch
):
    game, _, _, _, item = held(ledger, tmp_path, monkeypatch)
    table = t.m2["m2_state_history"]
    with ledger.engine.connect() as c:
        old = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == ledger.campaign_id, table.c.event_id == item.source_event
            )
        )
    original = json.loads(old)
    physical = next(x for x in original["held_items"] if x["id"] == item.id)
    assert not {"location_mode", "scene_id", "location_event", "condition"} & set(physical)
    before = json.dumps(physical, sort_keys=True)
    loaded = HeldItem.model_validate_json(before)
    after = json.dumps(loaded.model_dump(mode="json"), sort_keys=True)
    assert after == before
    assert hashlib.sha256(after.encode()).hexdigest() == hashlib.sha256(before.encode()).hexdigest()
    assert loaded.location_mode == "carried" and loaded.condition == "intact"
    restarted = GameService(ledger)
    canonical = state(restarted)
    with ledger.engine.connect() as c:
        assert prove_item(c, restarted, canonical, item.id) == item
        assert (
            prove_transfer(c, restarted, canonical.item_transfers[-1].id)[2]
            == canonical.item_transfers[-1]
        )
    restarted.rebuild()
    assert state(restarted).held_items == canonical.held_items
    with ledger.engine.connect() as c:
        assert (
            c.scalar(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == ledger.campaign_id, table.c.event_id == item.source_event
                )
            )
            == old
        )
    located = loaded.model_copy(
        update=dict(
            location_mode="scene", scene_id="actual-room", location_event="actual-storage-source"
        )
    )
    assert json.loads(located.model_dump_json())["location_mode"] == "scene"
