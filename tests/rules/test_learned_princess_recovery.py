"""Exact unused Princess lesson recovery without changing printed effects."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_vatgrown_plays import (
    _learn_daily_source,
    _learned_sex_interaction,
    _native_learned_sex_card,
    _native_learned_sex_invitation,
    ready,
)

from girlframe.engine import m3_vatgrown_plays as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def test_actual_contact_withdrawal_preserves_consent_favour_and_one_use(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m3_princess_sex import open_choice, open_princess
    from girlframe.engine import m3_princess_sex as princess
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.services.m3_learned_sex import lessons, prove
    from girlframe.services.m3_princess_sex import SexService
    from girlframe.services.m3_recovery import RecoveryService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="PRINCESS")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, rules.BRUTALIZE, princess.RULE),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, princess.RULE)
    learner, target = current_ref(state(game), 2), current_ref(state(game), 3)
    service = SexService(game)
    physical = PhysicalService(ledger)

    def cockpit(operation):
        with ledger.engine.connect() as c:
            body = resolve(state(game), learner, profiles(c, ledger.campaign_id))
        physical.operate(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            CockpitAction(
                actor=learner,
                operation=operation,
                expected_position=body.position_sha256,
                confirmed=True,
                account="Actual learner changes cockpit contact",
            ),
            channel=900,
        )

    async def withdraw(link):
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_princess(opened, service)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["action"] = ("withdraw:" + link.session,)
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, (sent.response.events, sent.edit_original_response.call_args_list)

    released = []
    for accepted in (False, True):
        unused = _native_learned_sex_invitation(game, lesson, target)
        if accepted:
            service.confirm(
                OTHER,
                str(uuid4()),
                unused.session,
                state(game).revision,
                True,
                "My actual consent stays historical",
            )
        consent = princess.get(state(game), unused.session).consent_event
        cockpit("pilot")
        if not accepted:
            with pytest.raises(WorkflowError):
                service.confirm(
                    OTHER,
                    str(uuid4()),
                    unused.session,
                    state(game).revision,
                    False,
                    "No current contact; preserve the source guard",
                )
        with pytest.raises(WorkflowError):
            service.withdraw(OTHER, str(uuid4()), unused.session, state(game).revision)
        sheets, dice_calls = state(game).sheets, game.dice.calls
        asyncio.run(withdraw(unused))
        assert state(game).sheets == sheets and game.dice.calls == dice_calls
        assert princess.get(state(game), unused.session).consent_event == consent
        assert service.view(OTHER, unused.session)["phase"] == "withdrawn"
        with ledger.engine.connect() as c:
            assert prove(game, c, state(game), unused.id).released_kind == "withdrawn"
            assert lessons(game, c, state(game), learner, princess.RULE)
        released.append(unused)
        cockpit("exit")

    first = _native_learned_sex_invitation(game, lesson, target)
    _native_learned_sex_card(
        game,
        service,
        open_princess,
        first.session,
        OTHER,
        accept=("no",),
        account="I decline only this actual source",
    )
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), first.id).released_kind == "declined"
        assert lessons(game, c, state(game), learner, princess.RULE)[0]["id"] == lesson.id
    assert not has_rule(state(game).sheets["2"], princess.RULE, "PRINCESS")

    second = _native_learned_sex_invitation(game, lesson, target)
    _native_learned_sex_card(
        game,
        service,
        open_princess,
        second.session,
        OTHER,
        accept=("yes",),
        account="My own positive confirmation of this source",
    )
    calls, heat = game.dice.calls, state(game).sheets["2"].heat
    _native_learned_sex_card(
        game,
        service,
        open_princess,
        second.session,
        PLAYER,
        heat=("1",),
        gain=("0",),
        context="Our actual accepted physical interaction",
    )
    with ledger.engine.connect() as c:
        abandoned = game.lock(c, 900)["action_id"]
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    recovery.recover(PLAYER, str(uuid4()), abandoned, saved["revision"], cancel=True)
    assert game.dice.calls == calls and state(game).sheets["2"].heat == heat
    assert service.view(PLAYER, second.session)["lesson_cancelled"]
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), second.id).released_kind == "owner_cancelled"
    tick(worker, gateway, 5)

    third = _native_learned_sex_invitation(game, lesson, target)
    _native_learned_sex_card(
        game,
        service,
        open_princess,
        third.session,
        OTHER,
        accept=("yes",),
        account="Fresh actual invitation, fresh own confirmation",
    )
    game.dice.faces = (3, 4)
    _native_learned_sex_card(
        game,
        service,
        open_princess,
        third.session,
        PLAYER,
        heat=("1",),
        gain=("0",),
        context="Our actual newly confirmed source",
    )
    with ledger.engine.connect() as c:
        action = game.lock(c, 900)["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    raw = game.inspect(PLAYER, action)["receipt"]
    assert state(game).sheets["2"].heat == heat - 1 and game.dice.calls == calls + 1
    with pytest.raises(WorkflowError):
        service.view(ADMIN, third.session)

    async def answer_native(viewer, kind, **values):
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        opened = _learned_sex_interaction(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        sent = _learned_sex_interaction(viewer.user_id)
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list

    asyncio.run(
        answer_native(
            PLAYER, "princess_sex_favour", text="PRIVATE_LEARNED_FAVOUR Please pass the actual note"
        )
    )
    asyncio.run(
        answer_native(
            OTHER, "princess_sex_favour_reply", options=("refuse",), text="My own actual refusal"
        )
    )
    asyncio.run(
        answer_native(
            PLAYER, "princess_sex_optional_tag", options=("give",), text="Refused my actual request"
        )
    )
    actual = state(game)
    source = princess.get(actual, third.session)
    assert source.phase == "complete" and source.tag
    assert any(x.id == source.tag and x.giver_actor == learner for x in actual.sheets["3"].tags)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == raw
    with ledger.engine.connect() as c:
        used = prove(game, c, actual, third.id)
        assert used.action == action and used.roll_event and used.released_event is None
        assert not lessons(game, c, actual, learner, princess.RULE)
    assert actual.sheets["2"].girl == "VATGROWN"
    assert not has_rule(actual.sheets["2"], princess.RULE, "PRINCESS")
    assert service.view(PLAYER, third.session)["favour"].startswith("PRIVATE_LEARNED_FAVOUR")
    assert "PRIVATE_LEARNED_FAVOUR" not in json.dumps(gateway.messages)
    tick(worker, gateway, 6)

    for unused in released:
        assert service.view(PLAYER, unused.session)["phase"] == "withdrawn"
        with ledger.engine.connect() as c:
            assert prove(game, c, state(game), unused.id).released_kind == "withdrawn"
    with pytest.raises(WorkflowError):
        service.withdraw(PLAYER, str(uuid4()), third.session, state(game).revision)
