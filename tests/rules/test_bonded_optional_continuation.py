"""A real low Pair result can continue without claiming optional benefits."""

import json
from uuid import uuid4

import pytest
from test_bonded import intimate, native_choice, ready, roll
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_bonded as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_bonded import BondedService, prove
from girlframe.services.onboarding import WorkflowError


def test_low_pair_unmarked_counterpart_can_continue_without_optional_benefits(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    source = intimate(controls, game)
    action = roll(game, worker, gateway, source, (1, 1))
    before = state(game)
    assert not any(x.marked for x in before.sheets["3"].identities)
    receipt = game.inspect(PLAYER, action)["receipt"]
    calls = game.dice.calls
    row = next(x for x in game.choices(OTHER) if x["kind"] == "bonded_low")
    response = ChoiceAnswer(
        options=("continue_without_benefits",),
        text=json.dumps({"account": "I choose to continue without claiming either benefit"}),
    )
    frozen = before.model_dump_json()
    for viewer, answer in (
        (PLAYER, response),
        (OTHER, response.model_copy(update={"denied": (before.sheets["3"].identities[0].id,)})),
    ):
        with pytest.raises(WorkflowError):
            game.respond(viewer, str(uuid4()), row["id"], row["revision"], answer)
        assert state(game).model_dump_json() == frozen

    native_choice(
        game,
        OTHER,
        "bonded_low",
        {
            "options": ("continue_without_benefits",),
            "account": "I choose to continue without claiming either benefit",
        },
        number=97690,
    )
    after = state(game)
    assert after.order == before.order
    assert after.sheets["3"].identities == before.sheets["3"].identities
    assert depth(after, current_ref(after, 2), current_ref(after, 3)) == depth(
        before, current_ref(before, 2), current_ref(before, 3)
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.dice.calls == calls
    selections = [x for x in rules.records(after, rules.Selection) if x.source == source]
    assert len(selections) == 1
    assert selections[0].options == ("continue_without_benefits",)
    assert selections[0].identities == ()
    assert selections[0].person == current_ref(after, 3)
    with ledger.engine.connect() as connection:
        assert prove(game, connection, after, source).phase == "complete"
    assert BondedService(game).view(OTHER, source)["phase"] == "complete"
