"""Genuine learned Bonded use of the native Pair Newgirl source and actual Mentor result."""

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
from test_newgirl_sex import choose
from test_vatgrown_plays import _learned_sex_interaction, native_choice

from girlframe.discord_adapter.m3_bonded_support import open_delegated
from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
from girlframe.discord_adapter.m3_newgirl_sex import open_newgirl_sex
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_learned_play_state import learned_sex_links
from girlframe.engine.m3_mentorship import active_mentors, current_set
from girlframe.services.m3_bonded import pair_lineage
from girlframe.services.m3_learned_sex import lessons, prove
from girlframe.services.m3_newgirl_sex import NewgirlSexService, prove_mentor_set
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("group", [False, True], ids=["single", "group"])
def test_native_pair_newgirl_learned_delegation_decline_cancel_and_once_receipt(
    ledger, tmp_path, monkeypatch, group
):
    game, worker, gateway, controls, original_pair = actual_retained_pair_vatgrown(
        ledger, tmp_path, monkeypatch, native_pair_book="NEWGIRL"
    )
    approved(ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, vat.SEX, newgirl.RULE))
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
            gain=1,
            trigger_confirmed=True,
            context="Actual earned lesson",
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
    source.send_away(
        FOUR, str(uuid4()), proposal, state(game).revision, "End the actual source stay"
    )
    tick(worker, gateway, 6)
    assert not has_rule(state(game).sheets["2"], bonded.SEX, "BONDED")
    assert not has_rule(state(game).sheets["2"], bonded.PAIR, "BONDED")

    assert active_mentors(state(game), original_pair[0]) == (teacher,)
    assert not active_mentors(state(game), actor)
    service = NewgirlSexService(game)
    assert state(game).sheets["3"].girl == "NEWGIRL"
    assert state(game).sheets["3"].review.creation.girl_playbook == "NEWGIRL"
    assert not has_rule(state(game).sheets["2"], newgirl.RULE, "NEWGIRL")

    async def invite():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_learned_sex(opened, game, identity=lesson.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            nonpair=(teacher.token,),
            pair_rule=("newgirl",),
            account="PRIVATE_LEARNED_NEWGIRL: my actual original Pair's rule",
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
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["source"] = ("invite",)
        selected = _learned_sex_interaction()
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            partners=(teacher.token, original_pair[0].token) if group else (teacher.token,),
            account="PRIVATE_GROUP: Each original participant answers independently",
        )
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        delegation = next(
            x for x in bonded.records(state(game), bonded.Delegation) if x.source == link.session
        )
        return link, delegation.session

    async def operate(child, owner, operation, **values):
        opened = _learned_sex_interaction(owner)
        await opened.response.defer(ephemeral=True)
        await open_newgirl_sex(opened, service, child)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = (operation,)
        selected = _learned_sex_interaction(owner)
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        response = _learned_sex_interaction(owner)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    async def consent(child, accept):
        await operate(
            child,
            4,
            "confirm",
            accept=("yes" if (accept or group) else "no",),
            account="My separate original child answer",
        )
        if group:
            assert service.view(PLAYER, child)["phase"] == "invited"
            await operate(
                child,
                3,
                "confirm",
                accept=("yes" if accept else "no",),
                account="My separate additional-participant answer",
            )

    refused, child = asyncio.run(invite())
    asyncio.run(consent(child, False))
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), refused.id).released_kind == "delegation_declined"
        assert lessons(game, c, state(game), actor, bonded.SEX)
    assert service.view(PLAYER, child)["phase"] == "declined"
    withdrawn, child = asyncio.run(invite())
    with pytest.raises(WorkflowError):
        service.withdraw(OTHER, str(uuid4()), child, state(game).revision)
    service.withdraw(PLAYER, str(uuid4()), child, state(game).revision)
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), withdrawn.id).released_kind == "delegation_withdrawn"

    async def start(child):
        available = state(game).sheets["2"].heat
        spend = available if available >= 5 else 0
        total = 8 - spend
        assert 2 <= total <= 12
        game.dice.faces = (max(1, total - 6), min(6, total - 1))
        await operate(
            child,
            2,
            "roll",
            heat=(str(spend),),
            account="My actual delegated Newgirl Play",
        )
        return newgirl.get(state(game), child).action

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
    assert service.view(PLAYER, child)["phase"] == "cancelled"
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), abandoned.id).released_kind == "owner_cancelled"
        assert lessons(game, c, state(game), actor, bonded.SEX)

    final, child = asyncio.run(invite())
    before_consent = state(game)
    with pytest.raises(WorkflowError):
        service.confirm(ADMIN, str(uuid4()), child, before_consent.revision, True, "Not my answer")
    assert state(game) == before_consent
    asyncio.run(consent(child, True))
    assert not active_mentors(state(game), actor)
    actual_child = newgirl.get(state(game), child)
    assert not actual_child.mentors_before
    assert actual_child.mentor_source == bonded.get(state(game), final.session).event
    action = asyncio.run(start(child))
    tick(worker, gateway, 3)
    pass_tags(game)
    choose(
        game,
        PLAYER,
        "newgirl_sex_ask",
        4,
        text="PRIVATE_ACTUAL_RESPECT do you respect me?",
        native=True,
    )
    choose(
        game,
        FOUR,
        "newgirl_sex_respect",
        4,
        options=("no",),
        text="My own actual lack of respect",
        native=True,
    )
    if group:
        choose(game, PLAYER, "newgirl_sex_ask", 3, text="My separate actual question", native=True)
        choose(
            game,
            OTHER,
            "newgirl_sex_respect",
            3,
            options=("no",),
            text="My own answer",
            native=True,
        )
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert controls.view(PLAYER, final.session)["phase"] == "complete"
    result = newgirl.get(state(game), child)
    assert result.tier == "mid" and result.completed_event
    relation = current_set(state(game), actor)
    expected_mentors = (teacher, original_pair[0]) if group else (teacher,)
    assert relation and relation.learner == actor and set(relation.mentors) == set(expected_mentors)
    assert relation.session == child and relation.reason == (
        "newgirl_sex_group" if group else "newgirl_sex_replacement"
    )
    assert set(active_mentors(state(game), actor)) == set(expected_mentors)
    assert {str(x) for x in service.view(PLAYER, child)["mentors"]} == {
        str(x.model_dump(mode="json")) for x in relation.mentors
    }
    with ledger.engine.connect() as c:
        assert pair_lineage(game, c, state(game), actor) == original_pair
        prove_mentor_set(game, c, state(game), relation)
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
        assert actual_action["data"]["newgirl_sex"]["bonded_lesson"] == final.id
        assert "learned_source" not in actual_action["data"]["newgirl_sex"]
    with pytest.raises(WorkflowError):
        service.view(ADMIN, child)
    assert game.dice.calls == calls + 1
    assert not has_rule(state(game).sheets["2"], newgirl.RULE, "NEWGIRL")
    assert not has_rule(state(game).sheets["2"], "girl.newgirl.trainee", "NEWGIRL")
    assert not has_rule(state(game).sheets["2"], "girl.newgirl.mentor", "NEWGIRL")
    assert "PRIVATE_LEARNED_NEWGIRL" not in json.dumps(gateway.messages)
    assert "PRIVATE_ACTUAL_RESPECT" not in json.dumps(gateway.messages)
