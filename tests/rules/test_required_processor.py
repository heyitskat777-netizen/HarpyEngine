"""One source-owned Processor nomination episode; root runs the authored minimum."""

import asyncio
from uuid import uuid4

import pytest
from test_ankou import buy, native_result, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_required_plays import native, submit

from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_ankou import _child
from girlframe.discord_adapter.m3_required_plays import open_required
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_physical as physical
from girlframe.engine import m3_required_plays as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_required_plays import RequiredPlayService, nomination_options, prove
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection


def test_native_processor_nomination_actual_purchase_cancel_relink_effects_and_restore(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    with ledger.engine.connect() as c:
        assert ankou.PLAY not in nomination_options(
            game, c, state(game), current_ref(state(game), 2)
        )
    buy(controls, ankou.PROCESSOR)
    with ledger.transaction() as c:
        actual = state(game)
        event = str(uuid4())
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
        game.event(c, 1, event, "synthetic.original_processor_nomination_relationship", actual)
    relay = controls.activate_relay(
        PLAYER, str(uuid4()), 900, state(game).revision, ("speech", "touch"), "Actual relay"
    )["id"]
    controls.choose_consequence(
        ADMIN, str(uuid4()), state(game).revision, relay, "nominees", "Actual nominations"
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate"
    )
    assert ankou.PLAY in controls.view(OTHER, nomination.id)["nomination_options"]
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        ankou.PLAY,
        "Nominate her purchased Processor Core without selecting minds or costs for her",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "held"
    required = RequiredPlayService(game)
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)

    async def entry(interaction):
        await _child(
            interaction, game, {"body": {"allowed": (ankou.PLAY,), "source_work": task.id}}
        )

    form = native(entry, operation=("processor",))
    submit(
        form,
        heat=("1",),
        identity=("none",),
        gain=("1",),
        cadre=("no",),
        exempt=("none",),
        account="Actual nominated use of nearby living minds",
    )
    first = rules.records(state(game))[-1]
    assert first.rule == ankou.PROCESSOR and first.actor == first.target
    with ledger.engine.connect() as c:
        abandoned = game.lock(c, 900)["action_id"]
        actual = game.action(c, abandoned)
        assert actual["data"]["ankou"]["proposal"] == first.recipe
        assert actual["data"]["ankou_effect_child"]["id"] == task.id
    before, calls = state(game), game.dice.calls
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    recovery.recover(PLAYER, str(uuid4()), abandoned, saved["revision"], cancel=True)
    assert rules.get(state(game), first.id).retired_event
    proposal = ankou.get(state(game), ankou.Proposal, first.recipe)
    assert proposal.action is None and proposal.bound_event is None
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert not ankou.records(state(game), ankou.Processor) and game.dice.calls == calls
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    key, revision = str(uuid4()), state(game).revision
    linked = required.link(PLAYER, key, task.id, first.recipe, revision)
    assert required.link(PLAYER, key, task.id, first.recipe, revision) == linked
    # Simulate a concurrent, genuine body-position change after linking and
    # before begin. This exercises the gap between separate transactions.
    with ledger.transaction() as c:
        changed = state(game)
        event = str(uuid4())
        changed = physical.cockpit_enter(
            changed,
            profiles(c, ledger.campaign_id),
            current_ref(changed, 3),
            event,
            "Actual counterpart enters their own cockpit",
            pilot=False,
        )
        game.event(c, 3, event, "synthetic.concurrent_cockpit_entry", changed)
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play=ankou.PLAY,
                trigger_confirmed=True,
                heat=1,
                context="Try the stale original range",
                source_work=first.recipe,
            ),
        )
    with pytest.raises(WorkflowError):
        from girlframe.services.m3_required_processor import withdraw

        withdraw(game, OTHER, str(uuid4()), linked["id"], state(game).revision)
    native(lambda i: open_required(i, game, task.id), operation=("withdraw_processor",))
    assert rules.get(state(game), linked["id"]).withdrawn_event
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    assert first.recipe not in {x["id"] for x in required.menu(PLAYER, task.id)["accepted"]}
    with pytest.raises(WorkflowError):
        required.link(PLAYER, str(uuid4()), task.id, first.recipe, state(game).revision)
    form = native(entry, operation=("processor",))
    submit(
        form,
        heat=("1",),
        identity=("none",),
        gain=("1",),
        cadre=("no",),
        exempt=("none",),
        account="Use the actual changed original minds",
    )
    linked = {"id": rules.records(state(game))[-1].id}
    with ledger.engine.connect() as c:
        action = game.lock(c, 900)["action_id"]
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    native_result(game, benefit0=("champion",), benefit1=("eyes",), replace1=("none",))
    final = state(game)
    processor = ankou.get(final, ankou.Processor, action)
    assert processor.completed_event and processor.total == 8
    assert processor.minds == proposal.minds
    assert final.sheets["2"].heat == before.sheets["2"].heat - 1
    assert any(
        x.id in processor.assets and x.name == "Eyes Everywhere" for x in final.sheets["2"].assets
    )
    assert ankou.get(final, ankou.Task, task.id).completed_event
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == calls + 1
    with ledger.engine.connect() as c:
        assert prove(game, c, final, linked["id"]).completed_event
    tick(worker, gateway, 7)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original
