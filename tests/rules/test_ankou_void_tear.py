"""Actual Dive-created non-last Void hardware can be torn off for real Feedback reprisal."""

from uuid import uuid4

from test_ankou_feedback import choose, finish_keep, last_source, ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick

from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_ankou_feedback import prove_loss_source
from girlframe.services.m3_asset_loss import snapshots


def test_actual_nonlast_void_asset_feedback_tear_preserves_loss_heat_and_reprisal(
    ledger, tmp_path, monkeypatch
):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    original = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    game.dice = Dice((4, 5))
    dive = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            heat=0,
            context="Actual link communion before the final mark",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "dive_select", options=("void_and_unmark_all",), text="Actual Void choice")
    answer(
        game, PLAYER, "dive_effect", fields={"asset": original.id}, text="Real Void-grown hardware"
    )
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, dive)["state"] == "complete"
    void_asset = next(x for x in state(game).sheets["2"].assets if x.id == original.id)
    assert void_asset.void and void_asset.description == "Real Void-grown hardware"
    parent, source = last_source(game, worker, gateway)
    before = state(game)
    remaining = [
        x for x in before.sheets["2"].assets if x.family == "frame" and x.id != original.id
    ]
    assert any(not x.damaged for x in remaining) and any(not x.void for x in remaining)
    choose(game, "tear", target, asset=original.id)
    after = state(game)
    torn = rules.get(after, source.id)
    assert torn.lost_asset == original.id and torn.phase == "child"
    assert after.sheets["2"].assets == [x for x in before.sheets["2"].assets if x.id != original.id]
    assert after.sheets["2"].heat == before.sheets["2"].heat + 5
    with ledger.engine.connect() as c:
        old, born = snapshots(game, c, torn.choice_event)
        assert next(x for x in old.sheets["2"].assets if x.id == original.id) == void_asset
        proof = prove_loss_source(game, c, born, torn.choice_event, torn.id, actor)
        assert proof["source_action"] == parent
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        after.sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=int(target.entity),
            heat=after.sheets["2"].heat,
            parent=parent,
            source_work=source.id,
            context="Actual reprisal to this original person",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="My original actual name")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    tick(worker, gateway, 3)
    finish_keep(game, worker, gateway, parent)
    final = state(game)
    assert rules.get(final, source.id).rolled_event
    assert game.dice.calls == 2
    assert not any(x.id == original.id for x in final.sheets["2"].assets)
