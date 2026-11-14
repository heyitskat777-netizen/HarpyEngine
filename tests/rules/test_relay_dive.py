"""Authored P1 normal: actual Relay nomination through real native Dive and table answers."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_physical_operations import place
from test_required_plays import native, submit
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_ankou import open_ankou
from girlframe.discord_adapter.m3_dive import open_dive
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_required_plays as required
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection

ledger = ledger_fixture


def test_native_relay_dive_cancel_retry_owned_identity_table_answers_and_restore(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, "play.basic.dive_deep"))
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.sheets["2"].heat = 3
        event = str(uuid4())
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
        game.event(c, 1, event, "synthetic.original_ankou_intense_relationship", actual)
    controls = AnkouService(game)
    worker, gateway = GameWorker(game), Gateway()
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("speech", "touch"),
        "I activate the original emotional relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "Original Intense partners nominate actual Plays",
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate"
    )
    assert "dive_deep" in controls.view(OTHER, nomination.id)["nomination_options"]
    choice = native(lambda i: open_ankou(i, controls, nomination.id), user=3, operation=("choose",))
    submit(
        choice,
        user=3,
        choice=("dive_deep",),
        account="I nominate her own Frame communion, not any result or table answer",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "held"
        assert not game.pending_actions(c)
    before = state(game)
    with pytest.raises(WorkflowError):
        game.begin(
            OTHER,
            str(uuid4()),
            900,
            before.sheets["3"].revision,
            PlayInput(
                play="dive_deep",
                source_work=task.id,
                heat=0,
                context="An incorrect actor cannot perform her nominated Dive",
                trigger_confirmed=True,
            ),
        )
    assert state(game).model_dump_json() == before.model_dump_json()
    assert game.dice.calls == 0

    def start():
        form = native(lambda i: open_ankou(i, controls, task.id), operation=("child",))
        submit(
            form,
            play=("dive_deep",),
            heat=("1",),
            identity=(),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="I actually commune with my own Vital Frame as nominated",
        )
        with ledger.engine.connect() as c:
            action = game.action(c, game.lock(c, 900)["action_id"])
        assert action["data"]["prepared"]["source_work"] == task.id
        assert action["data"]["ankou_effect_child"]["id"] == task.id
        assert action["data"]["dive"]["actor"] == task.actor.model_dump(mode="json")
        assert not required.records(state(game))
        return action["id"]

    abandoned = start()
    before = state(game)
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    key = str(uuid4())
    restored = recovery.recover(PLAYER, key, abandoned, saved["revision"], cancel=True)
    assert recovery.recover(PLAYER, key, abandoned, saved["revision"], cancel=True) == restored
    pending = ankou.get(state(game), ankou.Task, task.id)
    assert pending.child is None and pending.completed_event is None
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert game.dice.calls == 0

    action = start()
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] == "ready_to_roll":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_select")
    native(
        lambda i: open_dive(i, game, row["id"]),
        option=("erase_identity_and_table_question",),
        account="My actual communion",
    )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_effect")
    old = state(game).sheets["2"].identities[1]
    question = "PRIVATE_NOMINATED_DIVE_QUESTION"
    native(lambda i: open_dive(i, game, row["id"]), identity=(old.id,), text=question)
    assert old.id not in {x.id for x in state(game).sheets["2"].identities}
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    for viewer in (PLAYER, OTHER, ADMIN):
        assert game.inspect(PLAYER, action)["state"] != "complete"
        assert not ankou.get(state(game), ankou.Task, task.id).completed_event
        row = next(x for x in game.choices(viewer) if x["kind"] == "dive_table_answer")
        native(
            lambda i, row=row: open_dive(i, game, row["id"], reviewed=True),
            user=viewer.user_id,
            text="My own actual answer " + str(viewer.user_id),
        )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert ankou.get(state(game), ankou.Task, task.id).completed_event
    assert state(game).sheets["2"].heat == before.sheets["2"].heat - 1
    assert game.dice.calls == 1
    assert (
        game.roll(PLAYER, str(uuid4()), action)["receipt"]
        == game.inspect(PLAYER, action)["receipt"]
    )
    assert game.dice.calls == 1
    tick(worker, gateway, 5)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == json.loads(
        json.dumps(gateway.original)
    )
    assert question not in json.dumps(gateway.messages)
