"""Actual native Pair's Mockingbird rule uses one original consenting child receipt."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_bonded import FOUR, intimate, pass_tags, ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_vatgrown_plays import _learned_sex_interaction

from girlframe.discord_adapter.m3_bonded_support import open_delegated
from girlframe.engine import m3_bonded as bonded
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m3_bonded_mockingbird import prove_native_child
from girlframe.services.m3_mockingbird_plays import MockingbirdService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("group", [False, True], ids=["single", "group"])
def test_native_actual_pair_mockingbird_child_consent_receipt_effect_and_reopen(
    ledger, tmp_path, monkeypatch, group
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, three=True)
    assert state(game).sheets["2"].girl == "BONDED"
    assert state(game).sheets["3"].girl == "MOCKINGBIRD"  # Genuine reviewed Pair creation.
    target = current_ref(state(game), 4)
    source = intimate(controls, game, 4, "delegated")
    service = MockingbirdService(game)

    async def propose_child():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_delegated(opened, game, source)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            extras=(current_ref(state(game), 3).token,) if group else (),
            account="PRIVATE_NATIVE_PAIR_RULE: actual original source, no copied person",
        )
        submitted = _learned_sex_interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        return state(game).mockingbird.triggers[-1].id

    child = asyncio.run(propose_child())
    if group:
        service.attest(OTHER, str(uuid4()), child, current_ref(state(game), 3), False)
        assert controls.view(PLAYER, source)["phase"] == "declined"
        assert game.dice.calls == 0
        source = intimate(controls, game, 4, "delegated")
        child = asyncio.run(propose_child())
    with pytest.raises(WorkflowError):
        service.attest(OTHER, str(uuid4()), child, target, True)
    service.attest(FOUR, str(uuid4()), child, target, True)
    if group:
        assert service.get(PLAYER, child)["body"]["state"] == "proposed"
        service.attest(OTHER, str(uuid4()), child, current_ref(state(game), 3), True)
    calls = game.dice.calls
    heat = state(game).sheets["2"].heat
    spend = heat if heat >= 5 else 0
    total = 8 - spend
    assert 2 <= total <= 12
    game.dice.faces = (max(1, total - 6), min(6, total - 1))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="mockingbird_sex",
            heat=spend,
            source_work=child,
            target_actor=target,
            context="Actual native Pair-rule performance",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    answer(
        game,
        PLAYER,
        "mockingbird_sex_select",
        options=("starry",),
        fields={"capability": "deception"},
    )
    tick(worker, gateway, 6)
    actual = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert controls.view(PLAYER, source)["phase"] == "complete"
    assert controls.view(FOUR, source)["phase"] == "complete"
    assert service.get(PLAYER, child)["body"]["action"] == action
    assert any(x.label == "Starry-Eyed" for x in actual.sheets["4"].tags)
    assert not any(x.label == "Starry-Eyed" for x in actual.sheets["3"].tags)
    assert actual.sheets["2"].heat == heat - spend and game.dice.calls == calls + 1
    assert has_rule(actual.sheets["2"], bonded.SEX, "BONDED")
    assert not has_rule(actual.sheets["2"], "girl.mockingbird.sex-play", "MOCKINGBIRD")
    assert not has_rule(actual.sheets["2"], "girl.mockingbird.bad-at-being-a-person", "MOCKINGBIRD")
    with ledger.engine.connect() as c:
        trigger = next(x for x in actual.mockingbird.triggers if x.id == child)
        assert prove_native_child(game, c, actual, trigger, game.action(c, action))
    with pytest.raises(WorkflowError):
        service.withdraw(PLAYER, str(uuid4()), child)
    assert "PRIVATE_NATIVE_PAIR_RULE" not in json.dumps(gateway.messages)
