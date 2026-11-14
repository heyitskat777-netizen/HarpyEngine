"""Actual nominated native Princess recipe retains consent, cancellation and real effects."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_physical_operations import place
from test_required_plays import native, submit
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_princess_sex import open_choice
from girlframe.discord_adapter.m3_required_plays import open_required
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_physical as physical
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine import m3_required_plays as required_rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_princess_sex import SexService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_required_plays import RequiredPlayService, prove
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection


def test_native_required_princess_consent_withdraw_cancel_relink_and_owned_favour(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="PRINCESS", frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, princess.RULE))
    with ledger.transaction() as connection:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.sheets["2"].heat = 3
        event = str(uuid4())
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
        game.event(connection, 1, event, "synthetic.initial_princess_ankou_bodies_bond", actual)
    worker, gateway = GameWorker(game), Gateway()
    controls, required, sex = AnkouService(game), RequiredPlayService(game), SexService(game)
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("speech", "touch"),
        "Activate my original Emotional Relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "Actual Handler consequence",
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate"
    )
    assert princess.PLAY in controls.view(OTHER, nomination.id)["nomination_options"]
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        princess.PLAY,
        "Nominate her own Play, without supplying her partner's consent",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)
    menu = native(lambda i: open_required(i, game, task.id), operation=("invite_princess",))
    invitation = submit(menu, action=("invite",))
    submit(
        invitation,
        target=(current_ref(state(game), 3).token,),
        account="PRIVATE required Princess proposal",
    )
    recipe = princess.sessions(state(game))[-1]
    with pytest.raises(WorkflowError):
        required.link(PLAYER, str(uuid4()), task.id, recipe.id, state(game).revision)
    sex.confirm(
        OTHER, str(uuid4()), recipe.id, state(game).revision, True, "My independent consent"
    )
    native(lambda i: open_required(i, game, task.id), operation=("link:" + recipe.id,))
    first = required_rules.records(state(game))[-1]
    assert first.rule == princess.RULE
    with ledger.transaction() as connection:
        moved = physical.cockpit_enter(
            state(game),
            profiles(connection, ledger.campaign_id),
            recipe.target,
            str(uuid4()),
            "Original counterpart sits in her actual cockpit",
            pilot=False,
        )
        game.event(connection, 1, str(uuid4()), "synthetic.contact_changed_before_begin", moved)
    changed = state(game)
    assert required.menu(PLAYER, task.id)["accepted"] == []
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            changed.sheets["2"].revision,
            PlayInput(
                play=princess.PLAY,
                source_work=recipe.id,
                target_actor=recipe.target,
                heat=1,
                context="Stale contact",
                trigger_confirmed=True,
            ),
        )
    assert state(game) == changed
    with pytest.raises(WorkflowError):
        required.withdraw_princess(OTHER, str(uuid4()), first.id, changed.revision)
    native(lambda i: open_required(i, game, task.id), operation=("withdraw_princess",))
    withdrawn = required_rules.get(state(game), first.id)
    assert withdrawn.withdrawn_event and withdrawn.retired_event
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    assert (
        princess.get(state(game), recipe.id).consent_event
        == princess.get(changed, recipe.id).consent_event
    )
    with ledger.transaction() as connection:
        returned = physical.cockpit_exit(
            state(game),
            profiles(connection, ledger.campaign_id),
            recipe.target,
            str(uuid4()),
            "Original counterpart exits her actual cockpit",
        )
        game.event(connection, 1, str(uuid4()), "synthetic.original_contact_restored", returned)
    native(lambda i: open_required(i, game, task.id), operation=("link:" + recipe.id,))
    first = required_rules.records(state(game))[-1]
    assert first.id != withdrawn.id

    def start():
        form = native(lambda i: open_required(i, game, task.id), operation=("play",))
        submit(
            form,
            heat=("1",),
            gain=("1",),
            share=("0",),
            context="PRIVATE actual nominated Princess source",
        )
        with ledger.engine.connect() as connection:
            action = game.action(connection, game.lock(connection, 900)["action_id"])
        assert action["data"]["princess_sex"]["session"] == recipe.id
        assert action["data"]["ankou_effect_child"]["id"] == task.id
        return action["id"]

    abandoned = start()
    before, calls = state(game), game.dice.calls
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    recovery.recover(PLAYER, str(uuid4()), abandoned, saved["revision"], cancel=True)
    restored = princess.get(state(game), recipe.id)
    assert restored.phase == "accepted" and restored.action is None and restored.bound_event is None
    assert restored.consent_event == princess.get(before, recipe.id).consent_event
    assert game.dice.calls == calls and state(game).sheets["2"].heat == before.sheets["2"].heat
    assert princess.get(state(game), recipe.id).effect_event is None
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    args = PLAYER, str(uuid4()), task.id, recipe.id, state(game).revision
    linked = required.link(*args)
    assert required.link(*args) == linked and linked["id"] != first.id
    action = start()
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    favour = next(x for x in game.choices(PLAYER) if x["kind"] == "princess_sex_favour")
    native(lambda i: open_choice(i, game, favour["id"]), text="PRIVATE please deliver my note")
    reply = next(x for x in game.choices(OTHER) if x["kind"] == "princess_sex_favour_reply")
    with pytest.raises(WorkflowError):
        game.decision(PLAYER, reply["id"])
    native(
        lambda i: open_choice(i, game, reply["id"]),
        user=3,
        options=("agree",),
        text="My own agreement, not inferred performance",
    )
    final = state(game)
    assert princess.get(final, recipe.id).phase == "complete"
    assert ankou.get(final, ankou.Task, task.id).completed_event
    assert required.menu(PLAYER, task.id)["completed"]
    assert game.dice.calls == calls + 1
    actual_recipe = princess.get(final, recipe.id)
    assert actual_recipe.favour == "PRIVATE please deliver my note"
    assert actual_recipe.response == "agree" and actual_recipe.response_event
    assert actual_recipe.actor == recipe.actor and actual_recipe.target == recipe.target
    with ledger.engine.connect() as connection:
        assert prove(game, connection, final, withdrawn.id).withdrawn_event
        assert prove(game, connection, final, first.id).retired_event
        assert prove(game, connection, final, linked["id"]).completed_event
        actual = game.action(connection, action)
        assert actual["data"]["receipt"] and actual["state"] == "complete"
    tick(worker, gateway, 7)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as connection:
        assert projection(game, connection, task.id)["state"] == "closed"
    assert "PRIVATE" not in json.dumps(gateway.messages)
