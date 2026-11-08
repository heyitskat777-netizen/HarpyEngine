"""A real source Harpy interrupts a no-RNG Gorgon without using its human's PC."""

import json
from uuid import uuid4

from test_gorgon_runtime import candidate_source_gate as candidate_source_gate
from test_gorgon_runtime import gorgon_source
from test_harpy_actor_plays import begin, pass_tags
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_recovery import RecoveryService


def test_actual_harpy_keep_interrupts_gorgon_without_borrowing_same_humans_pc(ledger):
    game, worker, gateway, parent, _ = gorgon_source(ledger, kind="collateral", harpy=True)
    before = state(game).sheets["2"].model_dump_json()
    actor = ActorRef(kind="external_pilot", entity="actual-pitted-harpy")
    answer(
        game,
        ADMIN,
        "gorgon_collateral",
        options=("structure",),
        fields={"structure": "base0"},
        text="This actual Gorgon threatens the existing Base",
    )
    answer(
        game,
        ADMIN,
        "gorgon_interrupt",
        options=("play",),
        fields={"actor": json.dumps(actor.model_dump(mode="json"))},
        text="The actually present Harpy gets her own interruption",
    )
    game.dice.faces = (6, 6)
    child = begin(ActorPlayService(game), actor, parent=parent, heat=5)
    tick(worker, gateway, 3)
    receipt = game.inspect(PLAYER, child)["receipt"]
    committed = state(game).model_dump_json()
    game.abort(ADMIN, str(uuid4()), parent)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(ADMIN) if x["id"] == parent)
    assert saved["rolled"] and saved["descendants"] == 1
    recovery.recover(ADMIN, str(uuid4()), parent, saved["revision"])
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, child)["receipt"] == receipt and game.dice.calls == 1
    assert state(game).model_dump_json() == committed
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", text="Actual interruption poise")
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="The real source judge confirms the actual response saves this Base",
    )
    assert game.inspect(PLAYER, child)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert game.action(c, parent)["state"] == "complete"
    assert state(game).sheets["2"].model_dump_json() == before
    assert next(x for x in state(game).world.locations if x.id == "base0").condition == "intact"
    assert game.dice.calls == 1
    # A repeated actual no-RNG control returns its already-started action unchanged.
    assert game.roll(ADMIN, str(uuid4()), parent)["receipt"] is None
    assert game.dice.calls == 1
