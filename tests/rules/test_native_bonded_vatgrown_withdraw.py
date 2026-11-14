"""Native Pair Vatgrown owner withdrawal frees only the unused original parent."""

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

from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_vatgrown_plays as vatgrown
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
from girlframe.services.onboarding import WorkflowError


def test_native_pair_vatgrown_owner_withdraws_unused_accepted_child_and_reopens(
    ledger, tmp_path, monkeypatch
):
    game, _, gateway, controls = ready(
        ledger, tmp_path, monkeypatch, three=True, native_pair_book="VATGROWN"
    )
    approved(ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, vatgrown.SEX))
    service = VatgrownPlaysService(game)
    source = intimate(controls, game, 4, "delegated")
    heat = state(game).sheets["2"].heat
    child = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 4),
        state(game).revision,
        "PRIVATE_NATIVE_VATGROWN independent child consent",
        bonded_source=source,
    )["id"]
    assert service.view(PLAYER, child)["session"]["phase"] == "invited"
    service.respond(FOUR, str(uuid4()), child, state(game).revision, True, "My actual consent")
    accepted = vatgrown.get(state(game), child)
    with pytest.raises(WorkflowError):
        service.withdraw(FOUR, str(uuid4()), child, state(game).revision)

    async def withdraw():
        opened = _learned_sex_interaction(2)
        await opened.response.defer(ephemeral=True)
        await open_vatgrown_plays(opened, service, child)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert any(x[0] == "withdraw" for x in form.fields[0].options)
        form.values.update(operation=("withdraw",))
        response = _learned_sex_interaction(2)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(withdraw())
    assert service.view(PLAYER, child)["session"]["phase"] == "withdrawn"
    assert controls.view(PLAYER, source)["phase"] == "withdrawn"
    assert controls.view(FOUR, source)["phase"] == "withdrawn"
    assert game.dice.calls == 0 and state(game).sheets["2"].heat == heat
    withdrawn = vatgrown.get(state(game), child)
    assert withdrawn.action is None
    assert withdrawn.consent_event == accepted.consent_event
    assert withdrawn.consent_account == accepted.consent_account
    with pytest.raises(WorkflowError):
        service.respond(
            FOUR, str(uuid4()), child, state(game).revision, True, "Cannot undo withdrawal"
        )
    replacement = intimate(controls, game, 4, "delegated")
    assert replacement != source and controls.view(PLAYER, replacement)["phase"] == "accepted"
    assert "PRIVATE_NATIVE_VATGROWN" not in json.dumps(gateway.messages)
