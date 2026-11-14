"""Ordinary printed Processor repeated-Identity benefit, not registry approval."""

from uuid import uuid4

from test_ankou import native_result, processor, ready
from test_ledger import PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state

from girlframe.engine import m3_ankou as rules

ledger = ledger_fixture


def test_mid_processor_repeated_identity_results_survive_unlink(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    # Synthetic starting marks only. All result mutations below go through the
    # real Play and original owner's native choice callback, not direct writes.
    with ledger.transaction() as c:
        initial = state(game)
        eligible = [
            x
            for x in initial.sheets["2"].identities
            if not (x.protected or x.paired or x.am_limiter)
        ]
        assert len(eligible) == 4
        erased = (eligible[0].id, eligible[1].id)
        unmarked = (eligible[2].id, eligible[3].id)
        eligible[2].marked = eligible[3].marked = True
        game.event(c, 1, str(uuid4()), "synthetic.processor_starting_identity_marks", initial)
    before = state(game)
    action = processor(game, worker, gateway, controls, faces=(3, 4))
    native_result(
        game,
        benefit0=("identity",),
        erase0=(erased[0],),
        unmark0=(unmarked[0],),
        gain0=("1",),
        benefit1=("identity",),
        erase1=(erased[1],),
        unmark1=(unmarked[1],),
        gain1=("3",),
    )
    actual = state(game)
    source = rules.get(actual, rules.Processor, action)
    assert source.total == 8 and source.completed_event
    assert source.benefits == ("identity", "identity")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert not source.assets and not source.tags and not source.symptoms
    assert {x.id for x in actual.sheets["2"].identities} == set(unmarked)
    assert not any(x.marked for x in actual.sheets["2"].identities)
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1 + 1 + 3
    assert actual.sheets["3"].identities == before.sheets["3"].identities
    controls.unlink(
        PLAYER,
        str(uuid4()),
        actual.revision,
        action,
        "I stop using the actual original minds as processors",
    )
    after = state(game)
    assert after.sheets["2"].identities == actual.sheets["2"].identities
    assert after.sheets["2"].heat == actual.sheets["2"].heat
    assert rules.get(after, rules.Processor, action).unlinked_event
