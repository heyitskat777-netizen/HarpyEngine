"""Real Emotional Relay Feedback, NPC reprisal and source-owned sequence completion."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_ankou import current, feedback_source, ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick

from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_ankou import open_ankou
from girlframe.engine import m3_ankou as rules
from girlframe.engine import m3_npc_flirt as flirt
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_native_relay_feedback_npc_tear_real_child_and_source_completion(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            rules.RELAY,
            *rules.REQUISITIONS,
            flirt.RULE,
            "core.core.npcs",
            "core.core.npc-assets",
            "core.core.npc-tags",
        ),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    target = ActorRef(kind="npc", entity="actual-relay-feedback-person")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=target.entity,
            name="Actual Relay Person",
            jobs=("doctor",),
            cell=(0, 0),
            detail="A real human-controlled person in this Relay scene",
            controller=1,
            revealed=True,
            employment="foundation",
        ),
    )
    cast = CastService(ActorService(missions))
    view = cast.view(ADMIN, 900)
    cast.change(
        ADMIN, str(uuid4()), 900, view["game_revision"], view["cast_revision"], "join", target
    )
    view = cast.view(OTHER, 900)
    cast.change(
        OTHER,
        str(uuid4()),
        900,
        view["game_revision"],
        view["cast_revision"],
        "withdraw",
        current_ref(state(game), 3),
    )
    game.dice = Dice((1, 1))
    sequence = feedback_source(game, controls, gateway)
    step = rules.get(state(game), rules.FeedbackStep, sequence.steps[0])
    before = state(game)
    asset = next(x.id for x in before.sheets["2"].assets if x.family == "frame" and not x.void)
    heat = before.sheets["2"].heat

    async def native_operation(operation, **values):
        opened = current()
        await opened.response.defer(ephemeral=True)
        await open_ankou(opened, controls, step.id)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values.update(operation=(operation,))
        selected = current()
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
        submitted = current()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(
        native_operation(
            "choose",
            choice=("tear",),
            target=(target.token,),
            asset=(asset,),
            opponent=("none",),
            replace=("none",),
            name="",
            battle=("no",),
            account="PRIVATE_RELAY_TEAR: actual Frame Asset offered against this person",
        )
    )
    assert not any(x.id == asset for x in state(game).sheets["2"].assets)
    assert state(game).sheets["2"].heat == heat + 5
    assert game.dice.calls == 0
    prepared = PlayInput(
        play="flirt",
        target_actor=target,
        heat=heat + 5,
        source_work=step.id,
        context="Actual source-owned NPC reprisal",
        trigger_confirmed=True,
    )
    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            prepared.model_copy(update={"source_work": "forged-feedback-step"}),
        )
    assert state(game).model_dump_json() == snapshot and game.dice.calls == 0

    # Synthetic independent pending work tests the admission guard itself; it is
    # not a fictional gameplay source or a way to complete the actual sequence.
    from girlframe.services.m3_collateral import append, latest
    from girlframe.services.m3_work import related

    unrelated = str(uuid4())
    with ledger.transaction() as c:
        event = str(uuid4())
        game.event(
            c, 1, str(uuid4()), "synthetic.unrelated_immediate_work", state(game), event_id=event
        )
        related(
            c,
            ledger,
            dict(campaign_id=ledger.campaign_id, campaign_context=True),
            unrelated,
            2,
            2,
            "synthetic_unrelated_guard",
            dict(immediate=True),
            event,
        )
    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="REQUIRED_FOLLOWUP"):
        game.begin(PLAYER, str(uuid4()), 900, state(game).sheets["2"].revision, prepared)
    assert state(game).model_dump_json() == snapshot and game.dice.calls == 0
    with ledger.transaction() as c:
        row = latest(game, c, unrelated)
        assert row["state"] == "pending"
        assert latest(game, c, sequence.id)["state"] == "pending"
        event = str(uuid4())
        game.event(
            c,
            1,
            str(uuid4()),
            "synthetic.unrelated_guard_fixture_completed",
            state(game),
            event_id=event,
        )
        append(c, row, event, json.loads(row["body_json"]), "resolved")
    asyncio.run(
        native_operation(
            "child",
            play=("flirt",),
            target=(),
            heat=(str(heat + 5),),
            identity=(),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            context="PRIVATE_RELAY_REPRISAL: a real source-owned NPC Flirt",
            trigger=("yes",),
        )
    )
    child = rules.get(state(game), rules.FeedbackStep, step.id).child
    assert child is not None
    with ledger.engine.connect() as c:
        actual = game.action(c, child)
        assert actual["parent_id"] is None
        assert actual["data"]["ankou_effect_child"]["id"] == step.id
        assert actual["data"]["prepared"]["target_actor"] == target.model_dump(mode="json")
        assert actual["data"]["prepared"]["heat"] == heat + 5
    tick(worker, gateway, 3)
    for viewer in (PLAYER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    with ledger.engine.connect() as c:
        assert game.action(c, child)["data"]["result"]["tier"] == "high"
        assert game.action(c, child)["data"]["receipt"]["pre_total"] == 11
    answer(
        game,
        PLAYER,
        "npc_flirt_actor",
        options=("name",),
        fields={"extra": "owe"},
        text="I actually press my question too far",
    )
    answer(game, ADMIN, "npc_flirt_target", text="PRIVATE_RELAY_NAME: the actual NPC answer")
    answer(game, ADMIN, "npc_flirt_owe", text="PRIVATE_RELAY_TAG: answer my real request")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert state(game).sheets["2"].heat == 0 and game.dice.calls == 1
    final = rules.get(state(game), rules.FeedbackStep, step.id)
    assert final.completed_event and final.asset == asset
    assert rules.get(state(game), rules.FeedbackSequence, sequence.id).completed_event
    receipt = game.inspect(PLAYER, child)["receipt"]
    assert game.roll(PLAYER, str(uuid4()), child)["receipt"] == receipt
    assert game.dice.calls == 1
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    tick(worker, gateway, 3)
    assert not any(
        secret in json.dumps(gateway.messages)
        for secret in (
            "PRIVATE_RELAY_TEAR",
            "PRIVATE_RELAY_REPRISAL",
            "PRIVATE_RELAY_NAME",
            "PRIVATE_RELAY_TAG",
        )
    )
