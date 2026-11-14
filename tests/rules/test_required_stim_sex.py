"""Actual nominated native Stim recipe retains consent, cancellation and real effects."""

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
from test_stim_sex import choose
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_required_plays import open_required
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_physical as physical
from girlframe.engine import m3_required_plays as required_rules
from girlframe.engine import m3_stim_sex as stim
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_required_plays import RequiredPlayService, prove
from girlframe.services.m3_stim_sex import SexService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection


def test_native_required_stim_consent_cancel_relink_drug_effect_and_task_completion(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="STIM-BLISSED", frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, stim.RULE))
    with ledger.transaction() as connection:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.sheets["2"].heat = 3
        event = str(uuid4())
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
        game.event(connection, 1, event, "synthetic.initial_stim_ankou_bodies_bond", actual)
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
    assert stim.PLAY in controls.view(OTHER, nomination.id)["nomination_options"]
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        stim.PLAY,
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
    menu = native(lambda i: open_required(i, game, task.id), operation=("invite_stim",))
    invitation = submit(menu, source=("invite",))
    submit(
        invitation,
        target=(current_ref(state(game), 3).token,),
        account="PRIVATE required Stim proposal",
    )
    recipe = stim.records(state(game), stim.Session)[-1]
    with pytest.raises(WorkflowError):
        required.link(PLAYER, str(uuid4()), task.id, recipe.id, state(game).revision)
    sex.respond(
        OTHER, str(uuid4()), recipe.id, state(game).revision, True, "My independent consent"
    )
    native(lambda i: open_required(i, game, task.id), operation=("link:" + recipe.id,))
    first = required_rules.records(state(game))[-1]
    assert first.rule == stim.RULE
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
                play=stim.PLAY,
                source_work=recipe.id,
                target_actor=recipe.target,
                heat=1,
                context="Stale contact",
                trigger_confirmed=True,
            ),
        )
    assert state(game) == changed
    with pytest.raises(WorkflowError):
        required.withdraw_stim(OTHER, str(uuid4()), first.id, changed.revision)
    native(lambda i: open_required(i, game, task.id), operation=("withdraw_stim",))
    withdrawn = required_rules.get(state(game), first.id)
    assert withdrawn.withdrawn_event and withdrawn.retired_event
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    assert (
        stim.get(state(game), recipe.id).consent_event == stim.get(changed, recipe.id).consent_event
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
            context="PRIVATE actual nominated Stim source",
        )
        with ledger.engine.connect() as connection:
            action = game.action(connection, game.lock(connection, 900)["action_id"])
        assert action["data"]["stim_sex"]["session"] == recipe.id
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
    restored = stim.get(state(game), recipe.id)
    assert restored.phase == "accepted" and restored.action is None and restored.bound_event is None
    assert restored.consent_event == stim.get(before, recipe.id).consent_event
    assert game.dice.calls == calls and state(game).sheets["2"].heat == before.sheets["2"].heat
    assert not stim.records(state(game), stim.Drug)
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
    choose(game, PLAYER, "stim_sex_drug", ("quick",), native=True)
    choose(
        game,
        PLAYER,
        "stim_sex_effects",
        ("orders",),
        native=True,
    )
    final = state(game)
    assert stim.get(final, recipe.id).phase == "complete"
    assert ankou.get(final, ankou.Task, task.id).completed_event
    assert required.menu(PLAYER, task.id)["completed"]
    assert game.dice.calls == calls + 1
    drug = next(x for x in stim.records(final, stim.Drug) if x.session == recipe.id)
    assert drug.target == recipe.target and drug.giver == recipe.actor
    assert any(x.action == action and x.kind == "orders" for x in stim.records(final, stim.Effect))
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
