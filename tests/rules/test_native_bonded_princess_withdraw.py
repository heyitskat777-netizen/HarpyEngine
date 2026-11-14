"""Native Pair Princess owner withdrawal frees only the unused original parent."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_bonded import FOUR, intimate, ready
from test_enforcer_requisitions import approved
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_vatgrown_plays import _learned_sex_interaction

from girlframe.discord_adapter.m3_princess_sex import open_princess
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_princess_sex import SexService
from girlframe.services.onboarding import WorkflowError


def test_native_pair_princess_owner_withdraws_unused_accepted_child_and_reopens(
    ledger, tmp_path, monkeypatch
):
    game, _, gateway, controls = ready(
        ledger, tmp_path, monkeypatch, three=True, native_pair_book="PRINCESS"
    )
    approved(ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, princess.RULE))
    service = SexService(game)
    source = intimate(controls, game, 4, "delegated")
    heat = state(game).sheets["2"].heat
    child = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 4),
        state(game).revision,
        "PRIVATE_NATIVE_PRINCESS independent child consent",
        bonded_source=source,
    )["id"]
    assert service.view(PLAYER, child)["phase"] == "invited"
    service.confirm(FOUR, str(uuid4()), child, state(game).revision, True, "My actual consent")
    accepted = princess.get(state(game), child)
    with pytest.raises(WorkflowError):
        service.withdraw(FOUR, str(uuid4()), child, state(game).revision)

    async def withdraw():
        opened = _learned_sex_interaction(2)
        await opened.response.defer(ephemeral=True)
        await open_princess(opened, service)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert any(x[0] == "withdraw:" + child for x in form.fields[0].options)
        form.values.update(action=("withdraw:" + child,))
        response = _learned_sex_interaction(2)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(withdraw())
    assert service.view(PLAYER, child)["phase"] == "withdrawn"
    assert controls.view(PLAYER, source)["phase"] == "withdrawn"
    assert controls.view(FOUR, source)["phase"] == "withdrawn"
    assert game.dice.calls == 0 and state(game).sheets["2"].heat == heat
    withdrawn = princess.get(state(game), child)
    assert withdrawn.action is None
    assert withdrawn.consent_event == accepted.consent_event
    assert withdrawn.consent_account == accepted.consent_account
    with pytest.raises(WorkflowError):
        service.confirm(
            FOUR, str(uuid4()), child, state(game).revision, True, "Cannot undo closure"
        )
    replacement = intimate(controls, game, 4, "delegated")
    assert replacement != source and controls.view(PLAYER, replacement)["phase"] == "accepted"
    assert "PRIVATE_NATIVE_PRINCESS" not in json.dumps(gateway.messages)
