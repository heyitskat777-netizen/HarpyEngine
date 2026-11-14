"""Native Pair Newgirl refusal frees only the unused original parent."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_bonded import FOUR, intimate, ready
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_vatgrown_plays import _learned_sex_interaction

from girlframe.discord_adapter.m3_bonded_support import open_delegated
from girlframe.discord_adapter.m3_newgirl_sex import open_newgirl_sex
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_newgirl_sex import NewgirlSexService
from girlframe.services.onboarding import WorkflowError


def test_native_pair_newgirl_refusal_releases_unused_parent_and_reopens(
    ledger, tmp_path, monkeypatch
):
    game, _, gateway, controls = ready(
        ledger, tmp_path, monkeypatch, three=True, native_pair_book="NEWGIRL"
    )
    approved(ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, newgirl.RULE))
    assert state(game).sheets["2"].girl == "BONDED"
    assert state(game).sheets["3"].review.creation.girl_playbook == "NEWGIRL"
    service = NewgirlSexService(game)
    source = intimate(controls, game, 4, "delegated")
    heat = state(game).sheets["2"].heat

    async def invite():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_delegated(opened, game, source)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["source"] = ("invite",)
        selected = _learned_sex_interaction()
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            partners=(current_ref(state(game), 4).token, current_ref(state(game), 3).token),
            account="PRIVATE_NATIVE_NEWGIRL: each participant answers separately",
        )
        response = _learned_sex_interaction()
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        return next(
            x.session for x in bonded.records(state(game), bonded.Delegation) if x.source == source
        )

    child = asyncio.run(invite())
    # The parent's original consent is not an answer to the actual child.
    assert service.view(PLAYER, child)["phase"] == "invited"
    service.confirm(FOUR, str(uuid4()), child, state(game).revision, True, "My own child answer")
    assert service.view(PLAYER, child)["phase"] == "invited"

    async def decline():
        opened = _learned_sex_interaction(3)
        await opened.response.defer(ephemeral=True)
        await open_newgirl_sex(opened, service, child)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = ("confirm",)
        selected = _learned_sex_interaction(3)
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(accept=("no",), account="My own refusal, no others decide for me")
        response = _learned_sex_interaction(3)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(decline())
    assert service.view(PLAYER, child)["phase"] == "declined"
    assert controls.view(PLAYER, source)["phase"] == "declined"
    assert controls.view(FOUR, source)["phase"] == "declined"
    assert game.dice.calls == 0 and state(game).sheets["2"].heat == heat
    ended = newgirl.get(state(game), child)
    assert ended.action is None and ended.effect_event is None
    with pytest.raises(WorkflowError):
        service.confirm(
            OTHER, str(uuid4()), child, state(game).revision, True, "Cannot undo refusal"
        )
    replacement = intimate(controls, game, 4, "delegated")
    assert replacement != source and controls.view(PLAYER, replacement)["phase"] == "accepted"
    assert "PRIVATE_NATIVE_NEWGIRL" not in json.dumps(gateway.messages)
