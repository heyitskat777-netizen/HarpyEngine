"""Previously stale tear fixture continued through real high Flirt fields."""

from uuid import uuid4

from test_ankou import feedback_source, ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services import m3_ankou_feedback_sequences as sequences

ledger = ledger_fixture


def test_tear_reprisal_completes_real_high_flirt_and_original_sequence(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    sequence = feedback_source(game, controls, gateway)
    step = rules.get(state(game), rules.FeedbackStep, sequence.steps[0])
    before = state(game)
    asset = next(x.id for x in before.sheets["2"].assets if x.family == "frame" and not x.void)
    sequences.choose(
        game,
        PLAYER,
        str(uuid4()),
        step.id,
        before.revision,
        "tear",
        current_ref(before, 3),
        "My original source-owned tear",
        asset=asset,
        in_battle=False,
    )
    assert not any(x.id == asset for x in state(game).sheets["2"].assets)
    assert state(game).sheets["2"].heat == before.sheets["2"].heat + 5
    assert game.dice.calls == 0
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            context="The actual required reprisal",
            trigger_confirmed=True,
            heat=state(game).sheets["2"].heat,
            target=3,
            source_work=step.id,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    game.dice.faces = (1, 1)
    receipt = game.roll(PLAYER, str(uuid4()), child)["receipt"]
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_flirt",
        options=("name",),
        fields={"extra": "owe"},
        text="I press the real question too far",
    )
    answer(game, OTHER, "target_flirt", text="The counterpart's actual owned answer")
    answer(game, OTHER, "flirt_owe_tag", text="Actual reprisal noticed")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.dice.calls == 1
    assert state(game).sheets["2"].heat == 0
    assert rules.get(state(game), rules.FeedbackSequence, sequence.id).completed_event
    assert rules.get(state(game), rules.FeedbackStep, step.id).child == child
    with ledger.engine.connect() as c:
        saved = game.action(c, child)["data"]
        assert saved["receipt"] == receipt
        assert saved["result"]["tier"] == "high"
