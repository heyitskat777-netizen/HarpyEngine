"""Actual custody/escape failure and genuine Initiative dealing; authored, not run."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, state, tick
from test_physical_operations import place
from test_strain_service import prepared
from test_strain_service import ready as strain_ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter import m3_movement as movement_native
from girlframe.discord_adapter import m3_prisoner_escape as native
from girlframe.engine import m3_prisoner_escape as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_prisoner_escape import PrisonerEscapeService, prove, prove_movement
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ledger = ledger_fixture
UNRELATED = GuildViewer(9, 200, True, False)
PEOPLE = {1: ADMIN, 2: PLAYER, 3: OTHER}


def ready(store, tmp_path, monkeypatch):
    strain, game = strain_ready(store, frame="THE ENFORCER", face=4)
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.RULE, "frame.enforcer.enforcement-initiative"),
    )
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    strain.missions.access.registry = load_registry()
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        for sheet in actual.sheets.values():
            sheet.heat = 0
            for asset in sheet.assets:
                asset.void = False
                asset.damaged = False
        game.event(c, 1, str(uuid4()), "synthetic.actual_prisoner_context", actual)
    world = WorldService(strain.missions)
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="real-held-prisoner",
            name="Actual held prisoner",
            jobs=("prisoner",),
            detail="Existing actual Foundation prisoner at this actual base",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    world.claim_npc(OTHER, str(uuid4()), state(game).revision, "real-held-prisoner")
    actor = ActorRef(kind="npc", entity="real-held-prisoner")
    casts = CastService(ActorService(strain.missions))
    shown = casts.view(OTHER, 900)
    casts.change(
        OTHER, str(uuid4()), 900, shown["game_revision"], shown["cast_revision"], "join", actor
    )
    store.join(UNRELATED, "actual-unrelated-source-reader")
    prepared(strain, game)
    request = next(x for x in state(game).strain.requests if x.track == "rebellion")
    strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
    strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    assert next(x for x in state(game).strain.events if x.id == request.id).rule_id == rules.RULE
    return game, PrisonerEscapeService(strain), actor, request.id + ":effect"


def work(store, identity):
    with store.engine.connect() as c:
        table = t.m3["m3_required_work"]
        return (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )


def capture_native(monkeypatch):
    captured = []
    for module in (native, movement_native):
        monkeypatch.setattr(
            module, "viewer_from_interaction", lambda current: PEOPLE[current.user.id]
        )

    async def reply(interaction, text, view=None):
        captured.append(view)

    monkeypatch.setattr(native, "reply", reply)
    monkeypatch.setattr(movement_native, "reply", reply)
    return captured


def test_genuine_npc_custody_native_breakout_actual_movement_then_factual_failure_escalates_once(
    ledger, tmp_path, monkeypatch
):
    game, service, actor, identity = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    old = next(x for x in before.world.npcs if x.id == actor.entity)
    assert old.custody_event and old.controller == OTHER.user_id
    with pytest.raises(WorkflowError):
        MovementService(game).move(
            OTHER,
            str(uuid4()),
            before.revision,
            900,
            actor,
            (1, 0),
            account="Still actually held; this cannot move the prisoner",
        )
    assert state(game).model_dump_json() == before.model_dump_json()
    captured = capture_native(monkeypatch)
    handler = SimpleNamespace(id=91001, user=SimpleNamespace(id=1), channel_id=900)
    npc_human = SimpleNamespace(id=91002, user=SimpleNamespace(id=3), channel_id=900)
    asyncio.run(native.open_prisoner_escape(handler, service, identity))
    start_form = captured[-1]
    values = dict(
        prisoner=(actor.token,), account="The real prisoner breaks out and attempts escape"
    )
    result = asyncio.run(start_form.submit_action(handler, values))
    assert asyncio.run(start_form.submit_action(handler, values)) == result
    source = rules.records(state(game), rules.Attempt)[0]
    released = next(x for x in state(game).world.npcs if x.id == actor.entity)
    assert released == old.model_copy(update=dict(custody_event=None))
    assert source.before == old and work(ledger, identity)["state"] == "pending"
    with pytest.raises(WorkflowError):
        service.view(UNRELATED, identity)
    asyncio.run(native.open_prisoner_escape(npc_human, service, identity))
    asyncio.run(captured[-1].submit_action(npc_human, dict(operation=("move",))))
    movement_form = captured[-1]
    movement = dict(
        actor=(actor.token,),
        mode=("body",),
        x=("1",),
        y=("0",),
        account="I actually leave this base as the original escaping prisoner",
    )
    asyncio.run(movement_form.submit_action(npc_human, movement))
    evidence = rules.records(state(game), rules.MovementEvidence)[0]
    assert next(x for x in state(game).world.npcs if x.id == actor.entity).cell == (1, 0)
    assert state(game).strain.levels["rebellion"] == "low"
    assert work(ledger, identity)["state"] == "pending"  # Movement is not automatic failure.
    unchanged = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        service.resolve_failure(
            OTHER,
            str(uuid4()),
            identity,
            state(game).revision,
            evidence.id,
            "The NPC controller cannot adjudicate the Handler's finding",
        )
    with pytest.raises(WorkflowError):
        service.resolve_failure(
            ADMIN,
            str(uuid4()),
            identity,
            before.revision,
            evidence.id,
            "Stale finding must not increase Strain",
        )
    assert state(game).model_dump_json() == unchanged
    handler.id = 91003
    asyncio.run(native.open_prisoner_escape(handler, service, identity))
    finding = captured[-1]
    answer = dict(
        operation=("failed:" + evidence.id,),
        account="The actual escape attempt has ended; the Girls did not deal with it",
    )
    outcome = asyncio.run(finding.submit_action(handler, answer))
    assert asyncio.run(finding.submit_action(handler, answer)) == outcome
    assert state(game).strain.levels["rebellion"] == "high"
    assert work(ledger, identity)["state"] == "resolved"
    assert len(rules.records(state(game), rules.Resolution)) == 1
    assert game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), identity) == source
        assert prove_movement(game, c, state(game), evidence.id) == evidence
    handler.channel_id = 999
    asyncio.run(native.open_prisoner_escape(handler, service, identity))
    readback = "".join(page.body for page in captured[-1].pages)
    assert "State: failed" in readback and native.clean(answer["account"]) in readback


def test_actual_completed_initiative_and_still_held_original_npc_resolve_without_escalation(
    ledger, tmp_path, monkeypatch
):
    game, service, actor, identity = ready(ledger, tmp_path, monkeypatch)
    service.start(
        ADMIN,
        "actual-breakout-before-intervention",
        identity,
        1,
        state(game).revision,
        900,
        actor,
        "The prisoner actually breaks out at this base",
    )
    source = rules.records(state(game), rules.Attempt)[0]
    game.dice.faces = (4, 5)
    gateway, worker = Gateway(), GameWorker(game)
    action = game.begin(
        PLAYER,
        "actual-girl-initiative",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="enforcement_initiative",
            target_actor=actor,
            piloting=False,
            heat=0,
            context="I actually take hold of the original escaping prisoner here",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, ADMIN):
        for row in game.choices(viewer):
            if row["kind"] == "tag_window":
                game.respond(
                    viewer,
                    str(uuid4()),
                    row["id"],
                    row["revision"],
                    ChoiceAnswer(options=("pass",)),
                )
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    grip = next(x for x in state(game).enforcer_grasps if x.action == action)
    assert grip.held and grip.target == actor and is_helpless(state(game), actor)
    assert work(ledger, identity)["state"] == "pending"
    with pytest.raises(WorkflowError):
        MovementService(game).move(
            OTHER,
            str(uuid4()),
            state(game).revision,
            900,
            actor,
            (1, 0),
            account="The actual held prisoner cannot walk away",
        )
    captured = capture_native(monkeypatch)
    girl = SimpleNamespace(id=91010, user=SimpleNamespace(id=2), channel_id=900)
    asyncio.run(native.open_prisoner_escape(girl, service, identity))
    form = captured[-1]
    values = dict(
        operation=("held:" + grip.id,),
        account="My genuine completed performance and live grip have dealt with this escape",
    )
    asyncio.run(form.submit_action(girl, values))
    assert state(game).strain.levels["rebellion"] == "low"
    assert work(ledger, identity)["state"] == "resolved"
    result = rules.resolution(state(game), source)
    assert result.kind == "dealt" and result.action == action and result.grip == grip.id
    assert next(x for x in state(game).enforcer_grasps if x.id == grip.id).held
    assert next(x for x in state(game).world.npcs if x.id == actor.entity).custody_event is None
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert game.action(c, action)["data"]["prepared"].get("source_work") is None
        assert game.lock(c, 900)["state"] == "released"
    girl.channel_id = 999
    asyncio.run(native.open_prisoner_escape(girl, service, identity))
    assert "State: dealt" in "".join(page.body for page in captured[-1].pages)
