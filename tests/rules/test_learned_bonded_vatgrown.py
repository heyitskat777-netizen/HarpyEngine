"""Genuine learned Bonded use of its original Vatgrown Pair and actual source-owned learning."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_bonded import pass_tags
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR
from test_learned_bonded_sex import actual_retained_pair_vatgrown
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_vatgrown_plays import _learned_sex_interaction, native_choice

from girlframe.discord_adapter.m3_bonded_support import open_delegated
from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_learned_play_state import learned_sex_links
from girlframe.services.m3_bonded import pair_lineage
from girlframe.services.m3_learned_sex import lessons, prove
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
from girlframe.services.m3_vatgrown_plays import prove as prove_child
from girlframe.services.onboarding import WorkflowError


def test_native_pair_vatgrown_learned_delegation_decline_cancel_and_once_receipt(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls, original_pair = actual_retained_pair_vatgrown(
        ledger, tmp_path, monkeypatch, native_pair_book="VATGROWN"
    )
    approved(ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, vat.SEX))
    actor, teacher = current_ref(state(game), 2), current_ref(state(game), 4)
    source = VatgrownPlaysService(game)
    proposal = source.invite(
        PLAYER,
        str(uuid4()),
        900,
        teacher,
        state(game).revision,
        "Actual original teacher, not her Pair or native passives",
    )["id"]
    source.respond(FOUR, str(uuid4()), proposal, state(game).revision, True, "My own participation")
    ordinary = next(
        x for x in state(game).sheets["2"].identities if not x.protected and not x.marked
    )
    game.dice.faces = (5, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=vat.PLAY,
            source_work=proposal,
            heat=1,
            identity=ordinary.id,
            gain=3,
            trigger_confirmed=True,
            context="My actual learning reinforces " + ordinary.name,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    actual = state(game)
    replacement = next(x for x in actual.sheets["2"].identities if not x.protected)
    retained = {x.name.casefold() for x in actual.sheets["2"].identities if x.id != replacement.id}
    taught = next(
        x
        for x in actual.sheets["4"].identities
        if not x.protected and x.name.casefold() not in retained
    )
    native_choice(
        game,
        FOUR,
        "vat_sex_learn",
        identities=(taught.id,),
        replacements=(replacement.id,),
        play=(bonded.SEX,),
        account="My actual Bonded Sex, without copying my Pair",
    )
    lesson = vat.records(state(game), vat.LearnedPlay)[-1]
    assert lesson.rule_id == bonded.SEX and game.inspect(PLAYER, action)["state"] == "complete"
    # The actual ordinary Identity generates 3 Heat; this source spent 1.
    assert state(game).sheets["2"].heat == 2
    source.send_away(
        FOUR, str(uuid4()), proposal, state(game).revision, "End the actual source stay"
    )
    tick(worker, gateway, 6)
    assert not has_rule(state(game).sheets["2"], bonded.SEX, "BONDED")
    assert not has_rule(state(game).sheets["2"], bonded.PAIR, "BONDED")

    service = VatgrownPlaysService(game)
    assert state(game).sheets["3"].girl == "VATGROWN"
    assert state(game).sheets["3"].review.creation.girl_playbook == "VATGROWN"

    async def invite():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_learned_sex(opened, game, identity=lesson.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            nonpair=(teacher.token,),
            pair_rule=("vatgrown",),
            account="PRIVATE_LEARNED_VATGROWN: my actual original Pair's rule",
        )
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, (sent.response.events, sent.edit_original_response.call_args_list)
        link = learned_sex_links(state(game))[-1]
        controls.confirm(
            FOUR,
            str(uuid4()),
            link.session,
            state(game).revision,
            True,
            "My own parent participation, not a child answer",
        )
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_delegated(opened, game, link.session)
        delegation = next(
            x for x in bonded.records(state(game), bonded.Delegation) if x.source == link.session
        )
        return link, delegation.session

    async def consent(child, accept):
        opened = _learned_sex_interaction(4)
        await opened.response.defer(ephemeral=True)
        await open_vatgrown_plays(opened, service, child)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            accept=("yes" if accept else "no",), account="My separate original child answer"
        )
        response = _learned_sex_interaction(4)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    refused, child = asyncio.run(invite())
    asyncio.run(consent(child, False))
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), refused.id).released_kind == "delegation_declined"
        assert lessons(game, c, state(game), actor, bonded.SEX)
    assert service.view(PLAYER, child)["session"]["phase"] == "declined"
    withdrawn, child = asyncio.run(invite())
    with pytest.raises(WorkflowError):
        service.withdraw(OTHER, str(uuid4()), child, state(game).revision)

    async def withdraw():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_vatgrown_plays(opened, service, child)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["operation"] = ("withdraw",)
        response = _learned_sex_interaction()
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(withdraw())
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), withdrawn.id).released_kind == "delegation_withdrawn"

    async def start(child):
        available = state(game).sheets["2"].heat
        assert available >= 1
        spend = min(available, 5)
        total = 8 - spend
        assert 2 <= total <= 12
        game.dice.faces = (max(1, total - 6), min(6, total - 1))
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_delegated(opened, game, vat.get(state(game), child).bonded_source)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            heat=(str(spend),),
            operation=("roll",),
        )
        response = _learned_sex_interaction()
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        return vat.get(state(game), child).action

    abandoned, child = asyncio.run(invite())
    asyncio.run(consent(child, True))
    calls = game.dice.calls
    action = asyncio.run(start(child))
    game.abort(ADMIN, str(uuid4()), action)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == action)
    assert saved["cancellable"] and not saved["rolled"]
    recovery.recover(PLAYER, str(uuid4()), action, saved["revision"], cancel=True)
    assert game.dice.calls == calls
    assert service.view(PLAYER, child)["session"]["phase"] == "cancelled"
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), abandoned.id).released_kind == "owner_cancelled"
        assert lessons(game, c, state(game), actor, bonded.SEX)

    final, child = asyncio.run(invite())
    before_consent = state(game)
    with pytest.raises(WorkflowError):
        service.respond(OTHER, str(uuid4()), child, before_consent.revision, True, "Not my answer")
    assert state(game) == before_consent
    asyncio.run(consent(child, True))
    before_bond = depth(state(game), actor, teacher)
    action = asyncio.run(start(child))
    tick(worker, gateway, 3)
    pass_tags(game)
    native_choice(
        game,
        PLAYER,
        "vat_sex_learn",
        effects=("plans", "good"),
        plans="PRIVATE_VATGROWN_PLAN: what is your actual plan?",
        good="How can I be good for you?",
        account="My owned two learning choices",
    )
    native_choice(
        game, FOUR, "vat_sex_plans", account="PRIVATE_VATGROWN_PLAN: my own actual answer"
    )
    native_choice(game, FOUR, "vat_sex_good", account="My own requested care")
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert controls.view(PLAYER, final.session)["phase"] == "complete"
    result = vat.get(state(game), child)
    assert result.phase == "complete" and result.effect_event
    assert depth(state(game), actor, teacher) == min(before_bond + 1, 2)
    selections = [x for x in vat.records(state(game), vat.Selection) if x.session == child]
    assert len(selections) == 1
    assert selections[0].controller == 2 and selections[0].options == ("plans", "good")
    assert selections[0].fields["plans"].startswith("PRIVATE_VATGROWN_PLAN")
    with ledger.engine.connect() as c:
        assert pair_lineage(game, c, state(game), actor) == original_pair
        assert prove_child(game, c, state(game), child) == result
        used = prove(game, c, state(game), final.id)
        assert used.action == action and used.roll_event and used.receipt_sha256
        grant = next(
            x for x in state(game).sheets["2"].girl_runtime.learned_plays if x.id == lesson.id
        )
        assert grant.claimed_action == action and grant.rolled_event == used.roll_event
        assert not lessons(game, c, state(game), actor, bonded.SEX)
        assert prove(game, c, state(game), refused.id).released_event
        assert prove(game, c, state(game), withdrawn.id).released_event
        assert prove(game, c, state(game), abandoned.id).released_event
        actual_action = game.action(c, action)
        assert actual_action["data"]["vatgrown_sex"]["bonded_lesson"] == final.id
        assert "learned_source" not in actual_action["data"]["vatgrown_sex"]
        assert actual_action["data"]["result"]["tier"] == "mid"
    assert game.dice.calls == calls + 1
    assert not has_rule(state(game).sheets["2"], bonded.SEX, "BONDED")
    assert not has_rule(state(game).sheets["2"], bonded.PAIR, "BONDED")
    assert "PRIVATE_VATGROWN_PLAN" not in json.dumps(gateway.messages)
    assert "PRIVATE_LEARNED_VATGROWN" not in json.dumps(gateway.messages)
    with pytest.raises(WorkflowError):
        service.view(ADMIN, child)
