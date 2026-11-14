"""One genuine learned non-Pair performance: no fabricated Action, roll, receipt or resources."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_bonded import pass_tags, pause_tick
from test_intracadre_marriage import FOUR
from test_learned_bonded_sex import actual_retained_pair_vatgrown
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_vatgrown_plays import _learned_sex_interaction, native_choice

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_bonded import open_bonded
from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_learned_play_state import learned_sex_links
from girlframe.services.m3_bonded import pair_lineage
from girlframe.services.m3_learned_sex import lessons, prove
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
from girlframe.services.onboarding import WorkflowError


def test_real_earned_bonded_nonpair_actual_performance_no_roll_once_private_stop(
    ledger, tmp_path, monkeypatch
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

    async def invite():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_learned_sex(opened, game, identity=lesson.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            nonpair=(teacher.token,), account="PRIVATE_NONPAIR actual non-Pair7 source"
        )
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, (sent.response.events, sent.edit_original_response.call_args_list)
        return learned_sex_links(state(game))[-1]

    refused = asyncio.run(invite())
    controls.confirm(
        FOUR, str(uuid4()), refused.session, state(game).revision, False, "My own refusal"
    )
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), refused.id).released_kind == "declined"
        assert lessons(game, c, state(game), actor, bonded.SEX)[0]["id"] == lesson.id
    link = asyncio.run(invite())
    assert bonded.get(state(game), link.session).route == "seven"
    assert bonded.get(state(game), link.session).pair == original_pair[0]
    with pytest.raises(WorkflowError):
        controls.confirm(
            OTHER,
            str(uuid4()),
            link.session,
            state(game).revision,
            True,
            "Pair cannot answer for actual counterpart",
        )
    controls.confirm(
        FOUR, str(uuid4()), link.session, state(game).revision, True, "My actual voluntary consent"
    )
    before, calls = state(game), game.dice.calls
    with ledger.engine.connect() as c:
        actions_before = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"]))
        unused = prove(game, c, before, link.id)
        assert unused.used_event is None and unused.action is None and unused.roll_event is None
    resources = {
        key: (value.heat, [x.model_dump() for x in value.identities], value.permissions)
        for key, value in before.sheets.items()
    }
    baseline_permissions = {key: dict(value) for key, value in gateway.values.items()}

    async def activate():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_bonded(opened, controls, link.session)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        options = dict(next(x for x in menu.fields if x.key == "operation").options)
        assert "activate" in options and "roll" not in options
        menu.values["operation"] = ("activate",)
        response = _learned_sex_interaction()
        await menu.confirm.callback(response)
        form = response.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            account="I actually performed this independently confirmed non-Pair source"
        )
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, (sent.response.events, sent.edit_original_response.call_args_list)
        saved = state(game)
        await form.confirm.callback(sent)
        assert state(game) == saved

    asyncio.run(activate())
    with ledger.engine.connect() as c:
        used = prove(game, c, state(game), link.id)
        assert used.used_event and used.action is None and used.bound_event is None
        assert used.roll_event is None and used.receipt_sha256 is None
        grant = next(
            x for x in state(game).sheets["2"].girl_runtime.learned_plays if x.id == lesson.id
        )
        assert grant.claimed_source == link.session and grant.used_event == used.used_event
        assert grant.claimed_action is None and grant.rolled_event is None
        assert not lessons(game, c, state(game), actor, bonded.SEX)
    with pytest.raises(WorkflowError):
        controls.activate(
            PLAYER, str(uuid4()), link.session, state(game).revision, "Cannot perform again"
        )
    with pytest.raises(WorkflowError):
        controls.withdraw_learned(PLAYER, str(uuid4()), link.session, state(game).revision)
    with pytest.raises(WorkflowError):
        controls.view(OTHER, link.session)
    pause_tick(game, gateway)
    controls.choose(
        FOUR,
        str(uuid4()),
        link.session,
        state(game).revision,
        ChoiceAnswer(options=("stop",), text="I independently choose to stop"),
    )
    pause_tick(game, gateway)
    actual = state(game)
    assert controls.view(PLAYER, link.session)["phase"] == "complete"
    assert bonded.get(actual, link.session).action is None
    assert game.dice.calls == calls
    assert {
        key: (value.heat, [x.model_dump() for x in value.identities], value.permissions)
        for key, value in actual.sheets.items()
    } == resources
    assert gateway.values == baseline_permissions
    assert depth(actual, actor, teacher) == max(0, depth(before, actor, teacher) - 1)
    assert depth(actual, actor, original_pair[0]) == depth(before, actor, original_pair[0])
    with ledger.engine.connect() as c:
        assert (
            c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == actions_before
        )
        assert pair_lineage(game, c, actual, actor) == original_pair
        assert prove(game, c, actual, link.id).used_event == used.used_event
        assert prove(game, c, actual, refused.id).released_kind == "declined"
    assert controls.view(PLAYER, refused.session)["phase"] == "declined"
    assert controls.view(FOUR, refused.session)["phase"] == "declined"
    controls.menu(PLAYER, 900)  # Includes historical sources after this lesson's later use.
    assert "PRIVATE_NONPAIR" not in json.dumps(gateway.messages)
