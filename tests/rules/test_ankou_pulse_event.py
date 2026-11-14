"""The actual Pulse move's original event is its genuine canonical roll receipt."""

import json

import sqlalchemy as sa
from test_ankou_handler_pulse import (
    test_native_engage_pulse_preserves_tag_on_actual_handler_and_one_roll as actual_pulse,
)
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.engine import m3_ankou as rules
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou import prove_tag
from girlframe.services.m3_asset_loss import snapshots


def test_actual_pulse_move_binds_original_canonical_roll_event(ledger, tmp_path, monkeypatch):
    actual_pulse(ledger, tmp_path, monkeypatch)
    game = GameService(ledger)
    current = state(game)
    move = next(x for x in rules.records(current, rules.TagUse) if x.kind == "pulse")
    with ledger.engine.connect() as c:
        source = game.action(c, move.source)
        row = c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == ledger.campaign_id, t.events.c.id == move.event
            )
        ).one()
        payload = json.loads(row.payload_json)
        assert row.kind in ("m2.rolled", "m3.rolled")
        assert payload["action_id"] == source["id"]
        assert payload["receipt_id"] == source["data"]["receipt"]["id"]
        before, after = snapshots(game, c, move.event)
        assert not any(x.id == move.id for x in rules.records(before, rules.TagUse))
        assert rules.get(after, rules.TagUse, move.id) == move
        assert prove_tag(game, c, current, move.target, move.tag) == move
