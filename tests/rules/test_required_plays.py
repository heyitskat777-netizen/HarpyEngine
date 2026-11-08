"""Deferred P1 normal: real Ankou nomination and separately accepted own Alpha source.

Authored only. Do not treat this as executed gameplay evidence.
"""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current as native_current
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_alpha_sex import open_consent
from girlframe.discord_adapter.m3_required_plays import open_required
from girlframe.engine import m3_alpha_sex as alpha
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_required_plays as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_alpha_sex import SexService
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_required_plays import RequiredPlayService, prove, source_for_play
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection

ledger = ledger_fixture


def current(user=2):
    value = native_current(user, int(uuid4().int % 1000000000))
    value.channel_id = 900
    return value


def native(callback, *, user=2, **values):
    async def run():
        interaction = current(user)
        await interaction.response.defer(ephemeral=True)
        await callback(interaction)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1 if user == 2 else 2))
        form.values.update(values)
        response = current(user)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        return response.edit_original_response.call_args.kwargs.get("view")

    return asyncio.run(run())


def submit(form, user=2, **values):
    async def run():
        form.values.update(values)
        response = current(user)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        return response.edit_original_response.call_args.kwargs.get("view")

    return asyncio.run(run())


def finish_mid(game, worker, gateway, action):
    game.dice.faces = (4, 5)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_actual_nomination_native_alpha_consent_cancel_retry_effects_and_pause_restore(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="ALPHA", frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, alpha.RULE))
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_alpha_ankou_bodies", actual)
    worker, gateway = GameWorker(game), Gateway()
    sex, controls, required = SexService(game), AnkouService(game), RequiredPlayService(game)

    # Earn the real Intense Bond through an actual completed own Alpha Play.
    first = sex.invite(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 3),
        state(game).revision,
        "My actual voluntary interaction with this original counterpart",
    )["id"]
    sex.respond(
        OTHER,
        str(uuid4()),
        first,
        state(game).revision,
        True,
        "I confirm only my own actual voluntary source",
    )
    prior = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=alpha.PLAY,
            source_work=first,
            target_actor=current_ref(state(game), 3),
            heat=0,
            context="Our actual confirmed voluntary source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    finish_mid(game, worker, gateway, prior)
    tick(worker, gateway, 5)
    actual = state(game)
    assert depth(actual, current_ref(actual, 2), current_ref(actual, 3)) == 2

    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        actual.revision,
        ("speech", "touch"),
        "I activate my actual Emotional Relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "The actual Intense partners nominate actual Plays",
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate" and x.actor == current_ref(state(game), 3)
    )
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        alpha.PLAY,
        "I nominate her actual own Alpha Sex Play, without authoring anyone's consent",
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
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)

    # The source pause creates no fake Action: actual invite and answer still work.
    alpha_menu = native(lambda i: open_required(i, game, task.id), operation=("invite",))
    invite = submit(alpha_menu, action=("invite",))
    submit(
        invite,
        target=(current_ref(state(game), 3).token,),
        account="My actual voluntary source during this paused nominated performance",
    )
    recipe = alpha.sessions(state(game))[-1]
    assert recipe.phase == "invited" and recipe.id != task.id
    native(
        lambda i: open_consent(i, sex, recipe.id),
        user=3,
        accept=("yes",),
        account="My own actual voluntary answer; no performance is inferred",
    )
    assert alpha.get(state(game), recipe.id).consent_event
    stale = state(game).revision - 1
    with pytest.raises(WorkflowError, match="STALE"):
        required.link(PLAYER, str(uuid4()), task.id, recipe.id, stale)
    native(lambda i: open_required(i, game, task.id), operation=("link:" + recipe.id,))
    selected = rules.records(state(game))[-1]
    assert selected.source == task.id and selected.recipe == recipe.id

    def start():
        form = native(lambda i: open_required(i, game, task.id), operation=("play",))
        submit(
            form,
            heat=("0",),
            gain=("1",),
            share=("0",),
            context="My actual confirmed voluntary Alpha interaction",
        )
        with ledger.engine.connect() as c:
            action = game.action(c, game.lock(c, 900)["action_id"])
        assert action["data"]["prepared"]["source_work"] == recipe.id
        assert action["data"]["ankou_effect_child"]["id"] == task.id
        return action["id"]

    abandoned = start()
    before = state(game)
    calls = game.dice.calls
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    key = str(uuid4())
    restored = recovery.recover(PLAYER, key, abandoned, saved["revision"], cancel=True)
    assert recovery.recover(PLAYER, key, abandoned, saved["revision"], cancel=True) == restored
    cancelled = state(game)
    assert rules.get(cancelled, selected.id).retired_event
    assert alpha.get(cancelled, recipe.id).action is None
    assert (
        alpha.get(cancelled, recipe.id).consent_event == alpha.get(before, recipe.id).consent_event
    )
    assert game.dice.calls == calls and cancelled.sheets["2"].heat == before.sheets["2"].heat
    with ledger.engine.connect() as c:
        prove(game, c, cancelled, selected.id)
        prepared = PlayInput(
            play=alpha.PLAY,
            source_work=recipe.id,
            context="Reopen the original accepted source",
            trigger_confirmed=True,
            heat=1,
            target_actor=recipe.target,
        )
        assert source_for_play(game, c, cancelled, prepared) is None
        forged = cancelled.model_copy(deep=True)
        old = rules.get(forged, selected.id)
        rules.put(forged, old.model_copy(update={"retired_event": str(uuid4())}))
        with pytest.raises(WorkflowError):
            source_for_play(game, c, forged, prepared)

    revision = cancelled.revision
    link_key = str(uuid4())
    linked = required.link(PLAYER, link_key, task.id, recipe.id, revision)
    assert required.link(PLAYER, link_key, task.id, recipe.id, revision) == linked
    assert linked["id"] != selected.id
    action = start()
    finish_mid(game, worker, gateway, action)
    completed = state(game)
    assert alpha.get(completed, recipe.id).phase == "complete"
    assert ankou.get(completed, ankou.Task, task.id).completed_event
    assert required.menu(PLAYER, task.id)["completed"]
    with ledger.engine.connect() as c:
        link = prove(game, c, completed, linked["id"])
        receipt = game.action(c, action)["data"]["receipt"]
        assert link.completed_event and link.action == action and receipt
    assert game.dice.calls == calls + 1
    tick(worker, gateway, 5)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == json.loads(
        json.dumps(gateway.original)
    )
