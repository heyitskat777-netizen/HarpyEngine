"""Actual Handler Feedback reprisals use Engage, never a proxy Flirt performer."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou import current as ankou_current
from test_ankou import feedback_source
from test_ankou import ready as relay_ready
from test_ankou_handler_feedback import actual_handler_source, finish_handler_engage
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_ankou import open_ankou
from girlframe.discord_adapter.m3_ankou_feedback import open_choice
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services import m3_ankou_feedback_sequences as sequences
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ankou_feedback import handler_reprisal, prove
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_collateral import latest
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def actual_maneuvers(game, worker, gateway, child, target, *, high=False):
    tick(worker, gateway, 3)
    for viewer in (PLAYER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    assert any(x["kind"] == "engage_maneuvers" for x in game.choices(PLAYER))
    used = next(x for x in state(game).sheets["2"].assets if x.family == "girl" and not x.damaged)
    moves = ("pin", "cover", "advance") if high else ("pin", "cover")
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=moves,
        fields={x: used.id for x in moves},
        denied=(used.id,) if high else (),
        text="PRIVATE_HANDLER_REPRISAL: I pin the actual Handler and take cover",
    )
    assert game.inspect(PLAYER, child)["state"] == "complete"
    effects = [
        json.loads(x["body"])
        for x in state(game).facts
        if x.get("kind") == "engage_maneuver" and json.loads(x["body"])["source_action"] == child
    ]
    assert {x["kind"] for x in effects} == set(moves)
    assert all(x["opponent"] == target.model_dump(mode="json") for x in effects)
    assert all(
        x["actor"] == current_ref(state(game), PLAYER.user_id).model_dump(mode="json")
        for x in effects
    )
    assert next(x for x in state(game).sheets["2"].assets if x.id == used.id).damaged == high


def test_native_handler_feedback_tear_engage_and_original_roll(ledger, tmp_path, monkeypatch):
    game, worker, gateway, service, action, source, target = actual_handler_source(
        ledger, tmp_path, monkeypatch
    )
    before = state(game)
    lost = next(x for x in before.sheets["2"].assets if x.family == "frame" and not x.void)
    # A supported recipient is not permission to tear away the only usable Engage Asset.
    with ledger.engine.connect() as c:
        unusable = before.model_copy(deep=True)
        for asset in unusable.sheets["2"].assets:
            if asset.id != lost.id:
                asset.damaged = True
        with pytest.raises(WorkflowError, match="undamaged Asset"):
            handler_reprisal(
                game, c, unusable, source.actor, target, source.cast, torn_asset=lost.id
            )
    assert state(game) == before and game.dice.calls == 0

    async def native(kind, number, **values):
        row = next(x for x in game.choices(PLAYER) if x["kind"] == kind)
        opened = current(PLAYER.user_id, number)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        if kind == "ankou_feedback_child":
            assert "Engage" in str(form.fields)
        form.values.update(values)
        submitted = current(PLAYER.user_id, number + 1)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(
        native(
            "ankou_feedback_choice",
            99701,
            effect=("tear",),
            target=(target.token,),
            asset=(lost.id,),
            account="PRIVATE_HANDLER_TEAR: I tear this actual Frame Asset away",
        )
    )
    assert not any(x.id == lost.id for x in state(game).sheets["2"].assets)
    assert state(game).sheets["2"].heat == 5 and game.dice.calls == 0
    assert game.inspect(PLAYER, action)["receipt"] is None
    prepared = PlayInput(
        play="flirt",
        parent=action,
        source_work=source.id,
        target_actor=target,
        heat=5,
        context="No fabricated Handler Flirt",
        trigger_confirmed=True,
    )
    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="source-owned reprisal"):
        game.begin(PLAYER, str(uuid4()), 900, state(game).sheets["2"].revision, prepared)
    assert state(game).model_dump_json() == snapshot and game.dice.calls == 0
    with pytest.raises(WorkflowError):
        service.view(OTHER, source.id)
    assert "prepared" not in service.view(ADMIN, source.id)

    game.dice.faces = (1, 2)
    asyncio.run(
        native(
            "ankou_feedback_child",
            99703,
            context="PRIVATE_HANDLER_REPRISAL: I engage the original Handler",
        )
    )
    child = feedback.get(state(game), source.id).child
    assert child is not None
    with ledger.engine.connect() as c:
        saved = game.action(c, child)
        assert saved["parent_id"] == action and saved["actor_id"] == source.actor.entity
        assert saved["data"]["prepared"]["play"] == "engage"
        assert saved["data"]["engage"]["target"] == target.model_dump(mode="json")
        assert not saved["data"].get("npc_flirt") and not saved["data"].get("actor_basic")
    actual_maneuvers(game, worker, gateway, child, target)
    result = game.inspect(PLAYER, child)["receipt"]
    assert result["heat"] == 5 and result["pre_total"] == 8
    assert game.dice.calls == 1 and state(game).sheets["2"].heat == 0
    assert game.roll(PLAYER, str(uuid4()), child)["receipt"] == result
    with ledger.engine.connect() as c:
        resolved = prove(game, c, state(game), source.id)
        assert resolved.phase == "resolved" and resolved.child == child
        assert resolved.resolved_event is not None
    assert game.inspect(PLAYER, action)["state"] == "ready_to_roll"
    assert game.inspect(PLAYER, action)["receipt"] is None
    game.dice.faces = (4, 4)
    finish_handler_engage(game, worker, gateway, action, expected_calls=2)
    after = state(game)
    assert after.handler_heat == before.handler_heat and after.handler_tags == before.handler_tags
    assert after.handler_persona == before.handler_persona
    assert after.sheets["2"].identities == before.sheets["2"].identities
    assert "PRIVATE_HANDLER" not in json.dumps(gateway.messages)


def test_native_relay_handler_reprisal_keeps_real_high_damage_and_completes_source(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = relay_ready(ledger, tmp_path, monkeypatch)
    # Real CastService joins require their own scoped world approval. Keep the
    # existing synthetic registry/digest and actual Handler/other-Pilot operations.
    approval = ledger.policy.m3_approval
    assert approval is not None
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    target = active_handler(state(game))
    assert target is not None
    casts = CastService(ActorService(MissionService(ledger)))
    change(casts, ADMIN, "join", target)
    change(casts, OTHER, "withdraw", current_ref(state(game), OTHER.user_id))
    game.dice = Dice((1, 1))
    sequence = feedback_source(game, controls, gateway)
    step = ankou.get(state(game), ankou.FeedbackStep, sequence.steps[0])
    before = state(game)
    lost = next(x for x in before.sheets["2"].assets if x.family == "frame" and not x.void)
    heat = before.sheets["2"].heat + 5

    async def native(operation, **values):
        opened = ankou_current()
        await opened.response.defer(ephemeral=True)
        await open_ankou(opened, controls, step.id)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values.update(operation=(operation,))
        selected = ankou_current()
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        if operation == "choose":
            assert any(
                token == target.token and "Bond/Purpose only" not in label
                for field in form.fields
                if field.key == "target"
                for token, label in field.options
            )
        form.values.update(values)
        submitted = ankou_current()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(
        native(
            "choose",
            choice=("tear",),
            target=(target.token,),
            asset=(lost.id,),
            opponent=("none",),
            replace=("none",),
            name="",
            battle=("yes",),
            account="PRIVATE_HANDLER_RELAY: tear a real Frame Asset for this reprisal",
        )
    )
    assert not any(x.id == lost.id for x in state(game).sheets["2"].assets)
    assert state(game).sheets["2"].heat == heat and game.dice.calls == 0
    asyncio.run(
        native(
            "child",
            play=("engage",),
            target=(),
            engage_target=(),
            heat=(str(heat),),
            identity=(),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            context="PRIVATE_HANDLER_RELAY: the actual fixed-Handler Engage",
            trigger=("yes",),
        )
    )
    child = ankou.get(state(game), ankou.FeedbackStep, step.id).child
    assert child is not None
    stale_before_child = state(game).model_copy(deep=True)
    actual_maneuvers(game, worker, gateway, child, target, high=True)
    receipt = game.inspect(PLAYER, child)["receipt"]
    assert receipt["heat"] == heat and receipt["pre_total"] == heat + 2
    assert game.roll(PLAYER, str(uuid4()), child)["receipt"] == receipt
    assert game.dice.calls == 1 and state(game).sheets["2"].heat == 0
    final = ankou.get(state(game), ankou.FeedbackStep, step.id)
    assert final.completed_event is not None
    assert (
        ankou.get(state(game), ankou.FeedbackSequence, sequence.id).completed_event
        == final.completed_event
    )
    completion_query = (
        sa.select(t.events.c.id)
        .where(
            t.events.c.campaign_id == ledger.campaign_id,
            t.events.c.kind == "m3.ankou_child_completed",
            sa.func.json_extract(t.events.c.payload_json, "$.source") == step.id,
        )
        .order_by(t.events.c.seq)
    )
    canonical_json = state(game).model_dump_json()
    with ledger.transaction() as c:
        # The ordinary respond path reaches completion from Engage and again
        # from its later source hook. They must share exactly one canonical event.
        assert list(c.scalars(completion_query)) == [final.completed_event]
        work = latest(game, c, sequence.id)
        assert work["state"] == "resolved" and work["event_id"] == final.completed_event
        assert json.loads(work["body_json"])["completed_event"] == final.completed_event
        actual_child = game.action(c, child)
        # Explicitly replay the same real completion with a pre-roll snapshot.
        # It contains neither the actual maneuvers nor the resulting Asset damage,
        # and still has all pre-roll Heat. None of it may overwrite current canon.
        assert stale_before_child.sheets["2"].heat == heat
        sequences.complete_child(
            game, c, stale_before_child, actual_child, actual_child["data"]["response_event"]
        )
        assert load_state(c, ledger.campaign_id).model_dump_json() == canonical_json
        assert list(c.scalars(completion_query)) == [final.completed_event]
        assert latest(game, c, sequence.id) == work
    assert state(game).model_dump_json() == canonical_json
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    tick(worker, gateway, 3)
    assert state(game).handler_heat == before.handler_heat
    assert state(game).handler_tags == before.handler_tags
    assert "PRIVATE_HANDLER" not in json.dumps(gateway.messages)
