"""Mid shaping still works when the actual unmark benefit is exhausted."""

from test_bonded import intimate, native_choice, ready, roll
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_bonded as rules
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_bonded import BondedService, prove


def test_mid_pair_without_marks_requests_actual_tag_and_preserves_bond(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    source = intimate(controls, game)
    action = roll(game, worker, gateway, source, (4, 4))
    before = state(game)
    assert not any(x.marked for x in before.sheets["2"].identities)
    receipt = game.inspect(PLAYER, action)["receipt"]
    calls = game.dice.calls
    native_choice(
        game,
        PLAYER,
        "bonded_mid",
        {"options": ("tag",), "account": "I ask her for a Tag without inventing a marked Identity"},
        number=97700,
    )
    pending = state(game)
    assert pending.sheets["2"].identities == before.sheets["2"].identities
    assert pending.sheets["2"].heat == before.sheets["2"].heat
    assert game.inspect(PLAYER, action)["state"] != "complete"
    native_choice(
        game,
        OTHER,
        "bonded_reply",
        {"options": ("give",), "account": "I choose my own answer", "content": "Steady together"},
        number=97701,
    )
    after = state(game)
    assert any(x.label == "Steady together" for x in after.sheets["2"].tags)
    assert depth(after, current_ref(after, 2), current_ref(after, 3)) == 2
    assert after.sheets["2"].identities == before.sheets["2"].identities
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.dice.calls == calls
    selected = next(
        x
        for x in rules.records(after, rules.Selection)
        if x.source == source and x.kind == "bonded_mid"
    )
    assert selected.options == ("tag",) and selected.identities == ()
    with ledger.engine.connect() as connection:
        assert prove(game, connection, after, source).phase == "complete"
    assert BondedService(game).view(PLAYER, source)["phase"] == "complete"
