"""One genuine learned non-Pair performance: no fabricated Action, roll, receipt or resources."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_bonded import pass_tags
from test_intracadre_marriage import FOUR
from test_learned_bonded_sex import actual_retained_pair_vatgrown
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_vatgrown_plays import _learned_sex_interaction, native_choice

from girlframe.discord_adapter.m3_bonded_support import open_delegated
from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_learned_play_state import learned_sex_links
from girlframe.services.m3_learned_sex import lessons, prove
from girlframe.services.m3_mockingbird_plays import MockingbirdService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("group", (False, True), ids=("single", "group"))
def test_real_learned_bonded_pair_rule_decline_withdraw_cancel_and_child_receipt(
    ledger, tmp_path, monkeypatch, group
):
    game, worker, gateway, controls, original_pair = actual_retained_pair_vatgrown(
        ledger, tmp_path, monkeypatch
    )
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

    service = MockingbirdService(game)
    assert state(game).sheets["3"].girl == "MOCKINGBIRD"

    async def invite():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_learned_sex(opened, game, identity=lesson.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            nonpair=(teacher.token,),
            pair_rule=("mockingbird",),
            account="PRIVATE_LEARNED_DELEGATION: my actual Pair's rule",
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
            "My own parent participation, no child answer inferred",
        )
        child_ui = _learned_sex_interaction()
        await child_ui.response.defer(ephemeral=True)
        await open_delegated(child_ui, game, link.session)
        child_form = child_ui.edit_original_response.call_args.kwargs["view"]
        child_form.values.update(
            extras=(original_pair[0].token,) if group else (),
            account="My separately proposed original child group",
        )
        submitted = _learned_sex_interaction()
        await child_form.confirm.callback(submitted)
        assert child_form.completed, (
            submitted.response.events,
            submitted.edit_original_response.call_args_list,
        )
        child = state(game).mockingbird.triggers[-1].id
        return link, child

    refused, child = asyncio.run(invite())
    service.attest(
        OTHER if group else FOUR, str(uuid4()), child, original_pair[0] if group else teacher, False
    )
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), refused.id).released_kind == "delegation_declined"
        assert lessons(game, c, state(game), actor, bonded.SEX)
    withdrawn, child = asyncio.run(invite())
    with pytest.raises(WorkflowError):
        service.withdraw(OTHER, str(uuid4()), child)
    service.withdraw(PLAYER, str(uuid4()), child)
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), withdrawn.id).released_kind == "delegation_withdrawn"

    def start(child):
        available = state(game).sheets["2"].heat
        spend = available if available >= 5 else 0
        total = 8 - spend
        assert 2 <= total <= 12
        game.dice.faces = (max(1, total - 6), min(6, total - 1))
        return game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="mockingbird_sex",
                source_work=child,
                heat=spend,
                target_actor=teacher,
                context="Actual delegated child",
                trigger_confirmed=True,
            ),
        )["action_id"]

    abandoned, child = asyncio.run(invite())
    service.attest(FOUR, str(uuid4()), child, teacher, True)
    calls = game.dice.calls
    if group:
        service.attest(OTHER, str(uuid4()), child, original_pair[0], True)
    action = start(child)
    game.abort(ADMIN, str(uuid4()), action)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == action)
    assert saved["cancellable"] and not saved["rolled"]
    recovery.recover(PLAYER, str(uuid4()), action, saved["revision"], cancel=True)
    assert game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), abandoned.id).released_kind == "owner_cancelled"
        assert lessons(game, c, state(game), actor, bonded.SEX)
    assert service.get(PLAYER, child)["lesson_cancelled"]

    final, child = asyncio.run(invite())
    with pytest.raises(WorkflowError):
        service.attest(OTHER, str(uuid4()), child, teacher, True)
    service.attest(FOUR, str(uuid4()), child, teacher, True)
    if group:
        service.attest(OTHER, str(uuid4()), child, original_pair[0], True)
    action = start(child)
    tick(worker, gateway, 3)
    pass_tags(game)
    from test_m2_game import answer

    answer(
        game,
        PLAYER,
        "mockingbird_sex_select",
        options=("starry",),
        fields={"capability": "deception"},
    )
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert controls.view(PLAYER, final.session)["phase"] == "complete"
    with ledger.engine.connect() as c:
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
    assert any(x.label == "Starry-Eyed" for x in state(game).sheets["4"].tags)
    assert game.dice.calls == calls + 1
    assert not has_rule(state(game).sheets["2"], "girl.mockingbird.sex-play", "MOCKINGBIRD")
    assert not has_rule(
        state(game).sheets["2"], "girl.mockingbird.bad-at-being-a-person", "MOCKINGBIRD"
    )
    assert "PRIVATE_LEARNED_DELEGATION" not in json.dumps(gateway.messages)
