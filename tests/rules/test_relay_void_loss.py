"""Genuine Relay Feedback can remove nonlast Dive-corrupted hardware."""

from uuid import uuid4

from test_ankou import feedback_source, ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick

from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services import m3_ankou_feedback_sequences as sequences
from girlframe.services.m3_asset_loss import snapshots


def test_actual_relay_feedback_removes_nonlast_void_asset_with_real_reprisal(
    ledger, tmp_path, monkeypatch
):
    # Existing fixture declares synthetic prior body/world/resources; all sources below are real.
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    original = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    game.dice = Dice((4, 4))
    dive = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            heat=1,
            piloting=True,
            context="Actual communion changes this original hardware",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("void_and_unmark_all",),
        text="I connect to my original Frame and let the Void rewrite its hardware",
    )
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"asset": original.id},
        text="Actual Void-grown hardware",
    )
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, dive)["state"] == "complete"
    changed = next(x for x in state(game).sheets["2"].assets if x.id == original.id)
    assert changed.void and changed.description == "Actual Void-grown hardware"
    sequence = feedback_source(game, controls, gateway)
    step = rules.get(state(game), rules.FeedbackStep, sequence.steps[0])
    target = current_ref(state(game), 3)
    before = state(game)
    remaining = [
        x for x in before.sheets["2"].assets if x.family == "frame" and x.id != original.id
    ]
    assert any(not x.damaged for x in remaining) and any(not x.void for x in remaining)
    calls = game.dice.calls
    sequences.choose(
        game,
        PLAYER,
        str(uuid4()),
        step.id,
        before.revision,
        "tear",
        target,
        "Actual whole Void Asset offered as Feedback",
        asset=original.id,
        in_battle=False,
    )
    after = state(game)
    torn = rules.get(after, rules.FeedbackStep, step.id)
    assert after.sheets["2"].assets == [x for x in before.sheets["2"].assets if x.id != original.id]
    assert after.sheets["2"].heat == before.sheets["2"].heat + 5
    assert game.dice.calls == calls
    with ledger.engine.connect() as c:
        old, born = snapshots(game, c, torn.choice_event)
        assert next(x for x in old.sheets["2"].assets if x.id == original.id) == changed
        sequences.prove_loss_source(game, c, born, torn.choice_event, torn.id, torn.actor)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        after.sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=3,
            heat=after.sheets["2"].heat,
            source_work=step.id,
            context="Actual original target reprisal",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    with ledger.engine.connect() as c:
        tier = game.action(c, child)["data"]["result"]["tier"]
    assert tier == "high"
    answer(
        game,
        PLAYER,
        "actor_flirt",
        options=("name",),
        fields={"extra": "owe"},
        text="I go too far in proving my devotion after tearing away the actual hardware",
    )
    answer(game, OTHER, "target_flirt", text="Actual original person's answer")
    answer(game, OTHER, "flirt_owe_tag", text="Actual reprisal noticed")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.dice.calls == calls + 1
    final = state(game)
    assert rules.get(final, rules.FeedbackSequence, sequence.id).completed_event
    assert not any(x.id == original.id for x in final.sheets["2"].assets)
