"""A real contact change cannot strand the original unused Oldgen lesson."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_vatgrown_plays import (
    _learn_daily_source,
    _learned_sex_interaction,
    _native_learned_sex_invitation,
    ready,
)

from girlframe.discord_adapter.m3_oldgen_sex import open_oldgen_sex
from girlframe.engine import m3_oldgen_sex as oldgen
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_learned_sex import lessons, prove
from girlframe.services.m3_oldgen_sex import OldgenSexService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def test_real_contact_change_owner_release_preserves_consent_history_and_later_use(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="OLDGEN")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, vat.BRUTALIZE, oldgen.RULE),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, oldgen.RULE)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    service = OldgenSexService(game)
    physical = PhysicalService(ledger)

    def cockpit(operation):
        with ledger.engine.connect() as c:
            body = resolve(state(game), actor, profiles(c, ledger.campaign_id))
        physical.operate(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            CockpitAction(
                actor=actor,
                operation=operation,
                expected_position=body.position_sha256,
                confirmed=True,
                account="My actual source actor changes cockpit contact",
            ),
            channel=900,
        )

    async def withdraw(link):
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_oldgen_sex(opened, service)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert "withdraw:" + link.session in dict(
            next(x for x in form.fields if x.key == "action").options
        )
        form.values.update(action=("withdraw:" + link.session,))
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, (sent.response.events, sent.edit_original_response.call_args_list)
        saved = state(game)
        await form.confirm.callback(sent)
        assert state(game) == saved

    first = _native_learned_sex_invitation(game, lesson, target)
    cockpit("pilot")
    with pytest.raises(WorkflowError):
        service.respond(
            OTHER,
            str(uuid4()),
            first.session,
            state(game).revision,
            False,
            "Contact is gone; do not waive the live source guard",
        )
    before = state(game).sheets["2"].model_dump()
    calls = game.dice.calls
    with pytest.raises(WorkflowError):
        service.withdraw(OTHER, str(uuid4()), first.session, state(game).revision)
    asyncio.run(withdraw(first))
    assert state(game).sheets["2"].model_dump() == before
    assert game.dice.calls == calls
    assert oldgen.get(state(game), first.session).consent_event is None
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), first.id).released_kind == "withdrawn"
        assert lessons(game, c, state(game), actor, oldgen.RULE)
    cockpit("exit")
    second = _native_learned_sex_invitation(game, lesson, target)
    service.respond(
        OTHER,
        str(uuid4()),
        second.session,
        state(game).revision,
        True,
        "My actual independent consent remains historical",
    )
    consent = oldgen.get(state(game), second.session).consent_event
    cockpit("pilot")
    asyncio.run(withdraw(second))
    assert oldgen.get(state(game), second.session).consent_event == consent
    assert service.view(OTHER, second.session)["phase"] == "withdrawn"
    cockpit("exit")
    final = _native_learned_sex_invitation(game, lesson, target)
    service.respond(
        OTHER,
        str(uuid4()),
        final.session,
        state(game).revision,
        True,
        "My fresh independent consent, never copied from earlier invitations",
    )
    available = state(game).sheets["2"].heat
    spend = available if available >= 5 else 0
    assert spend <= 5
    game.dice.faces = (1, 1)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=oldgen.PLAY,
            source_work=final.session,
            target_actor=target,
            heat=spend,
            context="Actual fresh source after owner withdrawal",
            trigger_confirmed=True,
        ),
    )["action_id"]
    with pytest.raises(WorkflowError):
        service.withdraw(PLAYER, str(uuid4()), final.session, state(game).revision)
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "oldgen_sex_rewrite", options=("decline",))
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert oldgen.get(state(game), final.session).phase == "complete"
    assert not oldgen.records(state(game), oldgen.Effect)
    assert game.dice.calls == calls + 1
    with ledger.engine.connect() as c:
        used = prove(game, c, state(game), final.id)
        assert used.action == action and used.roll_event and used.receipt_sha256
        assert not lessons(game, c, state(game), actor, oldgen.RULE)
        assert prove(game, c, state(game), first.id).released_event
        assert prove(game, c, state(game), second.id).released_event
    assert service.view(PLAYER, first.session)["phase"] == "withdrawn"
    assert service.view(OTHER, second.session)["phase"] == "withdrawn"
