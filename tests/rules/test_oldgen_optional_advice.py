"""Low advice preserves the recipient's optional-unmark agency and real maxim use."""

from uuid import uuid4

from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_oldgen import advice, native_choice, ready

from girlframe.engine import m3_oldgen as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_oldgen import OldgenService, prove_advice


def test_low_advice_declined_unmark_still_creates_and_uses_owned_maxim(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    assert before.sheets["3"].identities[0].marked
    action = advice(game, worker, gateway, (1, 1))
    receipt = game.inspect(PLAYER, action)["receipt"]
    native_choice(game, OTHER, "oldgen_low_maxim", "Only trust advice earned in the field")
    tick(worker, gateway, 5)
    actual = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert actual.sheets["3"].identities == before.sheets["3"].identities
    assert actual.order == before.order
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1
    maxim = rules.records(actual, rules.Maxim)[-1]
    assert maxim.owner == current_ref(actual, OTHER.user_id)
    assert maxim.subject == current_ref(actual, PLAYER.user_id)
    with ledger.engine.connect() as c:
        assert prove_advice(game, c, actual, action).maxim == maxim.id
    key = str(uuid4())
    args = (
        OTHER,
        key,
        maxim.id,
        maxim.subject,
        "reinforce",
        900,
        actual.revision,
        "The original adviser actually reinforces the recipient's maxim",
    )
    result = controls.use(*args)
    saved = state(game)
    assert saved.sheets["2"].heat == actual.sheets["2"].heat + 2
    assert saved.sheets["3"].identities == before.sheets["3"].identities
    assert not controls.view(OTHER, maxim.id)["available"]
    assert OldgenService(game).use(*args) == result
    assert state(game) == saved
    assert game.dice.calls == 1
