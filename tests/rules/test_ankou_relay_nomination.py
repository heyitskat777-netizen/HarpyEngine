"""Bounded genuine Relay nomination to owned ordinary Play; synthetic starting Bond."""

import asyncio
from uuid import uuid4

import pytest
from test_ankou import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick

from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_relay_intense_nomination_requires_actual_owned_play(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        actual = state(game)
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, str(uuid4()))
        game.event(c, 1, str(uuid4()), "synthetic.starting_intense_bond", actual)
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("speech", "sense"),
        "I activate the real Relay for this scene",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "The actual Intense partner may nominate a Play",
    )
    nomination = next(
        x
        for x in rules.records(state(game), rules.Task)
        if x.source == relay and x.kind == "nominate"
    )
    assert nomination.controller == OTHER.user_id
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        controls.choose_task(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            nomination.id,
            "keep_your_head",
            "Not my nomination",
        )
    assert state(game).model_dump_json() == before
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        "keep_your_head",
        "Keep your head through this actual danger",
    )
    performance = next(
        x
        for x in rules.records(state(game), rules.Task)
        if x.source == relay and x.kind == "perform"
    )
    assert performance.actor == current_ref(state(game), 2)
    assert performance.options == ("keep_your_head",)
    assert not performance.completed_event and performance.child is None
    with pytest.raises(WorkflowError):
        controls.choose_task(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            performance.id,
            "keep_your_head",
            "I cannot merely acknowledge a required Play",
        )
    # Deliver the real source pause through the normal worker before starting its child.
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    game.dice.faces = (3, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=1,
            context="Actual danger under the relay",
            trigger_confirmed=True,
            source_work=performance.id,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    receipt = game.roll(PLAYER, str(uuid4()), action)["receipt"]
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The real performance is sufficient")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    actual = rules.get(state(game), rules.Task, performance.id)
    assert actual.child == action and actual.completed_event
    assert rules.get(state(game), rules.Task, nomination.id).completed_event
    with ledger.engine.connect() as c:
        assert game.action(c, action)["data"]["receipt"] == receipt
    reopened = AnkouService(game).view(PLAYER, performance.id)
    assert not reopened["can_choose"]
    assert rules.get(state(game), rules.Relay, relay).ended_event is None
