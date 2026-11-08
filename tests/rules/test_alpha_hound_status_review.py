"""A real Hound mark expires when the actual end-OffDuty review changes The Dog."""

from uuid import uuid4

from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, state, tick
from test_off_duty_cycle import activate, finish_routine, prepared, recover_both

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_girl_runtime_state import change_playbook_runtime


def test_hound_genuine_mark_ends_when_actual_off_duty_review_changes_dog(ledger):
    cycle, game, identity = prepared(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"], _ = change_playbook_runtime(
            canon.sheets["3"], "ALPHA", "synthetic-current-alpha-baseline"
        )
        game.event(c, 1, str(uuid4()), "synthetic.current_native_alpha_context", canon)
    game.dice = Dice((4, 4))
    from girlframe.engine.m2 import PlayInput

    action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Actual Hound keeps her head",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(game, OTHER, "tag_window", options=("pass",), fields={"status": "1"})
    answer(game, ADMIN, "tag_window", options=("pass",))
    assert state(game).sheets["3"].status_marked
    answer(game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual Hound Keep source adjudication")
    assert game.inspect(OTHER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    activate(cycle, game, identity)
    recover_both(cycle, game, identity)
    assert state(game).order[-1] == 3 and state(game).sheets["3"].status_marked
    finish_routine(cycle, game, identity)
    assert state(game).order == (3, 2)
    assert not state(game).sheets["3"].status_marked
