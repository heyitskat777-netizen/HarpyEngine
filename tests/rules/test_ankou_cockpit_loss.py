"""Native last ordinary Girl tear requires proven original cockpit occupancy."""

from uuid import uuid4

import pytest
from test_ankou_feedback import choose, finish_keep, last_source, ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_ankou_feedback import prove_loss_source
from girlframe.services.m3_asset_loss import last_frame, snapshots
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("context", ("inside", "outside", "unknown"))
def test_last_ordinary_girl_feedback_tear_requires_original_cockpit(
    ledger, tmp_path, monkeypatch, context
):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    original = next(x for x in state(game).sheets["2"].assets if x.family == "girl")
    # Explicit synthetic prior loss, not a claim that this test earned earlier losses.
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].assets = [
            x for x in actual.sheets["2"].assets if x.family != "girl" or x.id == original.id
        ]
        if context == "unknown":
            actual.placements = [x for x in actual.placements if x.actor != actor]
        game.event(c, 1, str(uuid4()), "synthetic.prior_single_girl_asset", actual)
    if context == "inside":
        physical = PhysicalService(ledger)
        preview = physical.preview(PLAYER)
        physical.operate(
            PLAYER,
            str(uuid4()),
            preview["game_revision"],
            CockpitAction(
                actor=actor,
                operation="sit",
                expected_position=preview["position_sha256"],
                account="I enter my actual original Frame before the final mark",
                confirmed=True,
            ),
        )
    parent, source = last_source(game, worker, gateway)
    before = state(game)
    assert not original.void
    assert [x.id for x in before.sheets["2"].assets if x.family == "girl"] == [original.id]
    if context != "inside":
        with pytest.raises(WorkflowError, match="SOURCE_ANKOU_LOSS_REQUIRED"):
            choose(game, "tear", target, asset=original.id)
        assert state(game).model_dump_json() == before.model_dump_json()
        return
    choose(game, "tear", target, asset=original.id)
    after = state(game)
    assert not is_helpless(after, actor, target)
    assert not last_frame(before, after, actor)
    assert after.harpy_defeats == before.harpy_defeats
    torn = rules.get(after, source.id)
    assert torn.lost_asset == original.id and torn.phase == "child"
    assert after.sheets["2"].assets == [x for x in before.sheets["2"].assets if x.id != original.id]
    assert after.sheets["2"].heat == before.sheets["2"].heat + 5
    with ledger.engine.connect() as c:
        old, born = snapshots(game, c, torn.choice_event)
        assert next(x for x in old.sheets["2"].assets if x.id == original.id) == original
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
