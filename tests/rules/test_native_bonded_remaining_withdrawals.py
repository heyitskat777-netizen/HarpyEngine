"""Exact unused native Pair children may be withdrawn without undoing consent."""

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

from girlframe.discord_adapter.m3_alpha_sex import open_alpha
from girlframe.discord_adapter.m3_newgirl_sex import open_newgirl_sex
from girlframe.engine import m3_alpha_sex as alpha
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_alpha_sex import SexService
from girlframe.services.m3_newgirl_sex import NewgirlSexService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("book", ("NEWGIRL", "ALPHA"))
def test_native_pair_unused_accepted_child_owner_withdrawal(ledger, tmp_path, monkeypatch, book):
    game, _, gateway, controls = ready(
        ledger, tmp_path, monkeypatch, three=True, native_pair_book=book
    )
    rules = newgirl if book == "NEWGIRL" else alpha
    approved(ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, rules.RULE))
    service = NewgirlSexService(game) if book == "NEWGIRL" else SexService(game)
    source = intimate(controls, game, 4, "delegated")
    heat = state(game).sheets["2"].heat
    target = current_ref(state(game), 4)
    child = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        (target,) if book == "NEWGIRL" else target,
        state(game).revision,
        "PRIVATE_NATIVE_WITHDRAW actual child consent",
        bonded_source=source,
    )["id"]
    if book == "NEWGIRL":
        service.confirm(FOUR, str(uuid4()), child, state(game).revision, True, "My own answer")
        consents = tuple(newgirl.records(state(game), newgirl.Consent))
    else:
        service.respond(FOUR, str(uuid4()), child, state(game).revision, True, "My own answer")
        consents = (
            alpha.get(state(game), child).consent_event,
            alpha.get(state(game), child).consent_account,
        )
    assert service.view(PLAYER, child)["phase"] == "accepted"
    with pytest.raises(WorkflowError):
        service.withdraw(FOUR, str(uuid4()), child, state(game).revision)

    async def withdraw():
        opened = _learned_sex_interaction(2)
        await opened.response.defer(ephemeral=True)
        if book == "NEWGIRL":
            await open_newgirl_sex(opened, service)
        else:
            await open_alpha(opened, service)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert any(x[0] == "withdraw:" + child for x in form.fields[0].options)
        form.values["source" if book == "NEWGIRL" else "action"] = ("withdraw:" + child,)
        response = _learned_sex_interaction(2)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(withdraw())
    assert service.view(PLAYER, child)["phase"] == "withdrawn"
    assert controls.view(PLAYER, source)["phase"] == "withdrawn"
    assert controls.view(FOUR, source)["phase"] == "withdrawn"
    assert rules.get(state(game), child).action is None
    if book == "NEWGIRL":
        assert tuple(newgirl.records(state(game), newgirl.Consent)) == consents
    else:
        assert (
            alpha.get(state(game), child).consent_event,
            alpha.get(state(game), child).consent_account,
        ) == consents
    assert game.dice.calls == 0 and state(game).sheets["2"].heat == heat
    with pytest.raises(WorkflowError):
        service.withdraw(PLAYER, str(uuid4()), child, state(game).revision)
    replacement = intimate(controls, game, 4, "delegated")
    assert replacement != source and controls.view(PLAYER, replacement)["phase"] == "accepted"
    assert "PRIVATE_NATIVE_WITHDRAW" not in json.dumps(gateway.messages)
