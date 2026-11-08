"""Actual human Sessions and legal starting-Identity chains create one spendable award."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import open_advancement
from girlframe.discord_adapter.m3_handler_ordinary import open_ordinary
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService, evidence
from girlframe.services.onboarding import WorkflowError


def setup(store, tmp_path, monkeypatch):
    creation, game = ready(store)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    save(creation, complete(creation, "Scientist"))
    agree(creation)
    data = creation.view(ADMIN)
    creation.activate(ADMIN, str(uuid4()), data["revision"], data["game_revision"], True)
    return game, HandlerOrdinaryService(store), GameWorker(game), Gateway()


def session_native(service, name, number):
    async def run():
        own = current(1, number)
        await own.response.defer(ephemeral=True)
        await open_ordinary(own, service)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            name=name, actual=("began",), account="Actual authorized human campaign Session begins"
        )
        await form.confirm.callback(current(1, number + 1))
        assert form.completed

    asyncio.run(run())
    return next(x.id for x in rules.sessions(state(service.game)) if x.end_event is None)


def finish_keep(game, worker, gateway, action, *, high=False, label=""):
    if high:
        answer(game, PLAYER, "actor_keep", text=label)
    else:
        answer(game, PLAYER, "actor_keep", options=("tough", "sexy"), denied=("in_control",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual source-owned sufficient result")
    tick(worker, gateway, 4)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def mark(game, worker, gateway, channel, tag):
    game.dice = Dice((4, 4))
    from girlframe.engine.m2 import PlayInput

    action = game.begin(
        PLAYER,
        str(uuid4()),
        channel,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Actual meaningful action witnessed by the original Handler",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for person in (PLAYER, OTHER):
        answer(game, person, "tag_window", options=("pass",))
    answer(
        game,
        ADMIN,
        "tag_window",
        options=("tag",),
        denied=(tag,),
        number=1,
        text="This actual self-description is relevant",
    )
    return action


def replace_starting(game, worker, gateway, identity, index, channel):
    from girlframe.engine.m2 import PlayInput

    game.dice = Dice((6, 6))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        channel,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Actual danger and changed self-description",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    label = "PRIVATE_USEFUL_REPLACEMENT_" + str(index)
    finish_keep(game, worker, gateway, action, high=True, label=label)
    tag = next(x.id for x in state(game).sheets["2"].tags if x.label == label)
    action = mark(game, worker, gateway, channel, tag)
    finish_keep(game, worker, gateway, action)
    game.close_scene(ADMIN, str(uuid4()), channel)
    channel += 1
    game.bind_scene(ADMIN, str(uuid4()), channel)
    for viewer in (ADMIN, PLAYER, OTHER):
        game.join_scene(viewer, str(uuid4()), channel)
    action = mark(game, worker, gateway, channel, tag)
    answer(game, PLAYER, "tag_resolution", options=("embrace",), denied=(identity,))
    finish_keep(game, worker, gateway, action)
    return channel


def test_actual_sessions_prior_replacements_owned_disclosure_award_spend_replay(
    ledger, tmp_path, monkeypatch
):
    game, ordinary, worker, gateway = setup(ledger, tmp_path, monkeypatch)
    starting = tuple(x.id for x in state(game).sheets["2"].identities)
    first = session_native(ordinary, "Actual first campaign Session", 36000)
    with pytest.raises(WorkflowError, match="Every actual starting"):
        ordinary.request_review(
            ADMIN,
            str(uuid4()),
            first,
            state(game).revision,
            current_ref(state(game), 2),
            "Not yet replaced",
        )
    assert not awards.awards(state(game))
    channel = 900
    for index, identity in enumerate(starting[:2]):
        channel = replace_starting(game, worker, gateway, identity, index, channel)
        assert next(x.id for x in rules.sessions(state(game)) if x.end_event is None) == first
    ordinary.end_session(
        ADMIN,
        "actual-session-one-end",
        first,
        state(game).revision,
        "The real facilitator records actual end; no other human acknowledgment",
    )
    assert not awards.awards(state(game))
    second = session_native(ordinary, "Actual second campaign Session", 36010)
    for index, identity in enumerate(starting[2:], 2):
        channel = replace_starting(game, worker, gateway, identity, index, channel)
    actual = state(game)
    with ledger.engine.connect() as c:
        proof = evidence(game, c, actual, current_ref(actual, 2))
    assert len(proof.chains) == 4 and all(x.current not in starting for x in proof.chains)
    review = ordinary.request_review(
        ADMIN,
        "actual-useful-identity-review",
        second,
        actual.revision,
        current_ref(actual, 2),
        "Actual original Handler requests useful replacement review",
    )["id"]
    assert ordinary.menu(ADMIN, review)["identities"] == []
    with pytest.raises(WorkflowError, match="original participants"):
        ordinary.menu(OTHER, review)

    async def disclosure():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(PLAYER)
            if x.task == "m3_handler_ordinary" and x.identity == review
        )
        assert item.incoming
        own = current(2, 36020)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            share=("yes",), account="I disclose these actual replacements only for this review"
        )
        await form.confirm.callback(current(2, 36021))
        assert form.completed

    asyncio.run(disclosure())
    assert not awards.awards(state(game))
    data = ordinary.menu(ADMIN, review)
    reasons = {
        x["id"]: "This actual replacement supports my Handler's real teaching"
        for x in data["identities"]
    }
    args = (
        ADMIN,
        "36031",
        review,
        data["revision"],
        reasons,
        "Actual useful replacement accomplishment",
    )

    async def judge():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_handler_ordinary" and x.identity == review
        )
        own = current(1, 36030)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update({"reason:" + key: value for key, value in reasons.items()})
        form.values.update(account=args[-1])
        await form.confirm.callback(current(1, 36031))
        assert form.completed

    asyncio.run(judge())
    value = awards.awards(state(game))[0]
    assert (
        value.phase == "held"
        and value.source_work is None
        and value.ordinary_source.session == second
    )
    assert ordinary.grant_identity_award(*args) == dict(id=value.id, phase="held")
    assert len(awards.awards(state(game))) == len(rules.marks(state(game))) == 1
    with pytest.raises(WorkflowError):
        ordinary.grant_identity_award(
            ADMIN,
            str(uuid4()),
            review,
            state(game).revision,
            reasons,
            "No duplicate actual ordinary award",
        )
    before = state(game).sheets["2"].permissions

    async def spend():
        service = HandlerAdvancementService(ledger)
        own = current(1, 36040)
        await own.response.defer(ephemeral=True)
        await open_advancement(own, service, value.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(girls=(current_ref(state(game), 2).token,))
        next_step = current(1, 36041)
        await form.confirm.callback(next_step)
        amounts = next_step.edit_original_response.call_args.kwargs["view"]
        amounts.values.update(
            {current_ref(state(game), 2).token: ("2",)},
            account="Actual ordinary award grants two Permissions",
        )
        await amounts.confirm.callback(current(1, 36042))
        assert amounts.completed
        await open_advancement(own, service, value.id)
        assert (
            "Ordinary starting-Identity" in own.edit_original_response.call_args.kwargs["content"]
        )

    asyncio.run(spend())
    assert state(game).sheets["2"].permissions == before + 2
    ordinary.end_session(
        ADMIN, str(uuid4()), second, state(game).revision, "Actual second session end"
    )
    third = session_native(ordinary, "Actual later Session", 36050)
    with pytest.raises(WorkflowError, match="marked off"):
        ordinary.request_review(
            ADMIN,
            str(uuid4()),
            third,
            state(game).revision,
            current_ref(state(game), 2),
            "New session cannot reset permanent criterion",
        )
    assert len(awards.awards(state(game))) == 1 and len(rules.marks(state(game))) == 1
    assert HandlerAdvancementService(ledger).view(ADMIN, value.id)["phase"] == "spent"
