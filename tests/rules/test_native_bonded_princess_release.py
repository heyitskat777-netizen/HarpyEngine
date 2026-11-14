"""Native Pair Princess refusal frees only the unused original parent."""

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


def test_native_pair_princess_refusal_releases_unused_parent_and_reopens(
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
    with pytest.raises(WorkflowError):
        service.confirm(PLAYER, str(uuid4()), child, state(game).revision, False, "Not my answer")

    async def decline():
        opened = _learned_sex_interaction(4)
        await opened.response.defer(ephemeral=True)
        await open_princess(opened, service, child)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(accept=("no",), account="My own refusal")
        response = _learned_sex_interaction(4)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(decline())
    assert service.view(PLAYER, child)["phase"] == "declined"
    assert controls.view(PLAYER, source)["phase"] == "declined"
    assert controls.view(FOUR, source)["phase"] == "declined"
    assert game.dice.calls == 0 and state(game).sheets["2"].heat == heat
    assert princess.get(state(game), child).action is None
    with pytest.raises(WorkflowError):
        service.confirm(
            FOUR, str(uuid4()), child, state(game).revision, True, "Cannot undo refusal"
        )
    replacement = intimate(controls, game, 4, "delegated")
    assert replacement != source and controls.view(PLAYER, replacement)["phase"] == "accepted"
    assert "PRIVATE_NATIVE_PRINCESS" not in json.dumps(gateway.messages)
