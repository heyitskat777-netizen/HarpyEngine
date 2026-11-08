"""Actual non-Dog accusation and innocence ownership; no fabricated prison position."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_personal_firearm import reviewed_registry
from test_requisition_service import ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_enforcer import open_enforcer_task
from girlframe.engine import m3_enforcer as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_enforcer import EnforcerService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def setup(store, tmp_path, monkeypatch, *, reviewed=True):
    _, game = ready(store, frame="THE ENFORCER")
    data = reviewed_registry().model_dump(mode="json")
    contract = next(x["contract"] for x in data["entries"] if x["id"].endswith("personal-firearm"))
    entry = next(x for x in data["entries"] if x["id"] == rules.OBEDIENCE)
    entry.update(
        implementation="implemented",
        source_audit="audited",
        independent_review="approved" if reviewed else "pending",
        reviewer="SYNTHETIC CONDITIONING TEST ONLY" if reviewed else None,
        review_reference="Fixture; no actual source certification" if reviewed else None,
        contract=contract,
        test_evidence=["tests/rules/test_enforcer_conditioning.py"],
    )
    registry = Registry.model_validate_json(json.dumps(data))
    path = tmp_path / "synthetic-conditioning-review.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    policy = store.policy
    store.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={
                    "registry_sha256": digest(registry),
                    "subsystems": policy.m3_approval.subsystems | {"playbooks"},
                }
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        world = initial()
        canon.world = world.model_copy(
            update={
                "npcs": (
                    Npc(
                        id="known-guard",
                        name="Known actual guard",
                        jobs=("guard",),
                        detail="Actual Foundation NPC",
                        controller=1,
                        cell=(0, 0),
                        revealed=True,
                    ),
                    Npc(
                        id="hidden-npc",
                        name="PRIVATE_HIDDEN_TARGET",
                        jobs=("civilian",),
                        detail="Private NPC",
                        controller=1,
                        cell=(1, 0),
                    ),
                )
            }
        )
        game.event(c, 1, "synthetic-enforcer-world", "synthetic.state", canon)
    return EnforcerService(game), game


def rank(service, *, superior=False):
    work = service.request_rank(PLAYER, str(uuid4()), "known-guard")["id"]
    data = service.get(ADMIN, work)
    service.rank(ADMIN, str(uuid4()), work, data["revision"], superior, "Actual relative rank")
    return service.preview(PLAYER)


def accuse(service, *, data=None, key=None):
    data = data or service.preview(PLAYER)
    target = data["targets"][0]
    return service.accuse(
        PLAYER,
        key or str(uuid4()),
        target["id"],
        target["rank"],
        data["expected"],
        "PRIVATE_CONCRETE_REBEL_ALLEGATION",
    )


def test_actual_non_superior_accusation_detains_until_current_handler_proves_innocence(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, game = setup(ledger, tmp_path, monkeypatch)
    preview = rank(service)
    result = accuse(service, data=preview, key="actual-arrest-once")
    assert accuse(service, data=preview, key="actual-arrest-once") == result
    target = ActorRef(kind="npc", entity="known-guard")
    assert rules.detention(state(game), target) is not None
    data = service.get(ADMIN, result["id"])
    with pytest.raises(WorkflowError):
        service.release(
            PLAYER, str(uuid4()), result["id"], data["revision"], "Not the actual Handler"
        )
    service.release(
        ADMIN,
        "actual-proved-innocence",
        result["id"],
        data["revision"],
        "Actual evidence establishes the allegation false",
    )
    assert rules.detention(state(game), target) is None
    assert any(x["kind"] == "enforcer_release_position_unknown" for x in state(game).facts)
    fresh = service.get(ADMIN, result["id"])
    service.record_released_position(
        ADMIN,
        "actual-released-location",
        result["id"],
        fresh["revision"],
        (2, 0),
        "The original released NPC is actually observed here",
    )
    assert next(x for x in state(game).world.npcs if x.id == target.entity).cell == (2, 0)
    assert state(game).enforcer_accusations[-1].position_event is not None
    with pytest.raises(WorkflowError):
        service.record_released_position(
            ADMIN,
            str(uuid4()),
            result["id"],
            state(game).revision,
            (4, 0),
            "No repeated map relocation through the release confirmation",
        )
    with ledger.engine.connect() as c:
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))


def test_superior_officer_unknown_rank_hidden_npc_and_dog_cannot_be_arrested(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, game = setup(ledger, tmp_path, monkeypatch)
    assert "PRIVATE_HIDDEN" not in str(service.preview(PLAYER))
    with pytest.raises(WorkflowError):
        service.request_rank(PLAYER, str(uuid4()), "hidden-npc")
    with pytest.raises(WorkflowError, match="rank"):
        accuse(service)
    rank(service, superior=True)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="superior"):
        accuse(service)
    assert state(game).model_dump_json() == before
    with ledger.transaction() as c:
        canon = state(game)
        canon.order = tuple(reversed(canon.order))
        game.event(c, 1, "actual-status-change", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="non-Dog"):
        service.preview(PLAYER)


def test_native_rank_declaration_and_innocence_use_owned_real_sources(
    ledger, tmp_path, monkeypatch
):
    service, game = setup(ledger, tmp_path, monkeypatch)
    identity = service.request_rank(PLAYER, "actual-rank-request", "known-guard")["id"]

    async def decide(work, values, callback_id):
        caller = current(1, callback_id)
        await caller.response.defer(ephemeral=True)
        await open_enforcer_task(caller, service, work)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(values)
        await form.confirm.callback(current(1, callback_id + 1))
        assert form.completed

    asyncio.run(decide(identity, dict(superior=("no",), account="Actual rank facts"), 21801))
    case = accuse(service)["id"]
    asyncio.run(decide(case, dict(evidence="Actual proved innocence", confirm=("yes",)), 21803))
    assert not state(game).enforcer_accusations[-1].detained
    with pytest.raises(WorkflowError):
        service.get(OTHER, case)


def test_real_review_gate_safety_pause_and_rebuild_preserve_actual_custody(
    ledger, tmp_path, monkeypatch
):
    service, game = setup(ledger, tmp_path, monkeypatch)
    rank(service)
    case = accuse(service)["id"]
    data = service.get(ADMIN, case)
    ledger.safety(OTHER, "pause-innocence", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.release(ADMIN, str(uuid4()), case, data["revision"], "Actual evidence")
    assert state(game).enforcer_accusations[-1].detained
    original = state(game)
    game.rebuild()
    assert state(game) == original


def test_unreviewed_real_rule_cannot_create_rank_requests_or_custody(ledger, tmp_path, monkeypatch):
    service, game = setup(ledger, tmp_path, monkeypatch, reviewed=False)
    original = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="implementation and review"):
        service.preview(PLAYER)
    with pytest.raises(WorkflowError, match="implementation and review"):
        service.request_rank(PLAYER, str(uuid4()), "known-guard")
    assert state(game).model_dump_json() == original


def test_saved_actual_case_reads_survive_missing_registry_without_enabling_release(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, _ = setup(ledger, tmp_path, monkeypatch)
    rank(service)
    identity = accuse(service)["id"]
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "missing-registry.json"))
    assert service.get(ADMIN, identity)["case"]["detained"]
    assert any(x["id"] == identity for x in service.tasks(ADMIN))
    data = service.get(ADMIN, identity)
    with pytest.raises(WorkflowError):
        service.release(ADMIN, str(uuid4()), identity, data["revision"], "Actual evidence")
