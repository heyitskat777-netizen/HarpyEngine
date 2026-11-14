"""One native Newgirl nomination episode; worker-authored, root-run only."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_newgirl_sex import choose
from test_physical_operations import place
from test_required_plays import native, submit
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_required_plays import open_required
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine import m3_required_plays as rules
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.engine.m3_mentorship import active_mentors
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_newgirl_sex import NewgirlSexService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_required_plays import RequiredPlayService, prove
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection


def test_native_newgirl_nomination_consent_cancel_relink_real_mentor_and_restore(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="NEWGIRL", frame=ankou.FRAME)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(ankou.RELAY, newgirl.RULE, "girl.newgirl.mentor", "girl.newgirl.trainee"),
    )
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        event = str(uuid4())
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
        game.event(c, 1, event, "synthetic.initial_newgirl_ankou_intense_relationship", actual)
    worker, gateway = GameWorker(game), Gateway()
    controls, sex, required = AnkouService(game), NewgirlSexService(game), RequiredPlayService(game)
    relay = controls.activate_relay(
        PLAYER, str(uuid4()), 900, state(game).revision, ("speech", "touch"), "Actual relay"
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "Actual Intense partners nominate",
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate"
    )
    assert newgirl.PLAY in controls.view(OTHER, nomination.id)["nomination_options"]
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        newgirl.PLAY,
        "Nominate her own source without consenting for anyone",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "held"
    source_menu = native(lambda i: open_required(i, game, task.id), operation=("invite_newgirl",))
    invitation = submit(source_menu, source=("invite",))
    submit(
        invitation,
        partners=(current_ref(state(game), 3).token,),
        account="PRIVATE_OWN_NEWGIRL actual voluntary source",
    )
    recipe = newgirl.records(state(game), newgirl.Session)[-1]
    assert not required.menu(PLAYER, task.id)["accepted"]
    with pytest.raises(WorkflowError):
        required.link(PLAYER, str(uuid4()), task.id, recipe.id, state(game).revision)
    sex.confirm(
        OTHER,
        str(uuid4()),
        recipe.id,
        state(game).revision,
        True,
        "My independent voluntary answer",
    )
    native(lambda i: open_required(i, game, task.id), operation=("link:" + recipe.id,))
    selected = rules.records(state(game))[-1]
    assert selected.rule == newgirl.RULE
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)

    def start():
        form = native(lambda i: open_required(i, game, task.id), operation=("play",))
        submit(
            form,
            heat=("0",),
            gain=("1",),
            share=("0",),
            context="PRIVATE_OWN_NEWGIRL actually confirmed nominated performance",
        )
        with ledger.engine.connect() as c:
            action = game.action(c, game.lock(c, 900)["action_id"])
        assert action["data"]["newgirl_sex"]["session"] == recipe.id
        assert action["data"]["ankou_effect_child"]["id"] == task.id
        assert action["data"]["prepared"]["target_actor"] is None
        return action["id"]

    abandoned = start()
    before, calls = state(game), game.dice.calls
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    args = PLAYER, str(uuid4()), abandoned, saved["revision"]
    result = recovery.recover(*args, cancel=True)
    assert recovery.recover(*args, cancel=True) == result
    restored = newgirl.get(state(game), recipe.id)
    assert restored.phase == "accepted" and restored.action is None and restored.bound_event is None
    assert newgirl.records(state(game), newgirl.Consent) == newgirl.records(before, newgirl.Consent)
    assert game.dice.calls == calls and state(game).sheets["2"].heat == before.sheets["2"].heat
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), selected.id).retired_event
    linked = required.link(PLAYER, str(uuid4()), task.id, recipe.id, state(game).revision)
    action = start()
    game.dice.faces = (4, 5)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    choose(game, PLAYER, "newgirl_sex_ask", 3, text="Do you respect me?", native=True)
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    choose(game, OTHER, "newgirl_sex_respect", 3, options=("no",), text="No", native=True)
    final = state(game)
    assert current_ref(final, 3) in active_mentors(final, current_ref(final, 2))
    assert newgirl.get(final, recipe.id).phase == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert ankou.get(final, ankou.Task, task.id).completed_event
    with ledger.engine.connect() as c:
        assert prove(game, c, final, linked["id"]).completed_event
    assert game.dice.calls == calls + 1
    tick(worker, gateway, 7)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original
    assert "PRIVATE_OWN_NEWGIRL" not in json.dumps(gateway.messages)
