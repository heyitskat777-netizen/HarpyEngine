"""Paid economy resources survive actual temporary removal without free replacement."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_off_duty_cycle import activate, roll_for
from test_personal_firearm_service import lose, purchase
from test_personal_firearm_service import setup as firearm_setup
from test_personal_firearm_service import sync as firearm_sync
from test_privileges import change
from test_scene_requisition_service import pay, propose
from test_scene_requisition_service import setup as scene_setup
from test_scene_requisition_service import sync as scene_sync

from girlframe.database import tables as t
from girlframe.engine import m3_privileges as rules
from girlframe.services.m3_privileges import (
    PrivilegeService,
    resume_restored_benefits,
    suspend_benefits,
)
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def revoke(game, receipt):
    """Synthetic disciplined source; real paid purchase and owned restoration services."""
    identity, event = str(uuid4()), str(uuid4())
    with game.store.transaction() as c:
        original = state(game)
        chars = {
            u: game.character_binding(c, original, u, require_current_profile=False) for u in (2, 3)
        }
        removed = rules.revoke(
            original, 2, 3, receipt.id, "Until the next mission", identity, event, chars
        )
        game.event(c, 3, str(uuid4()), "m3.punishment_applied", removed, event_id=event)
        suspend_benefits(c, game.store, removed, event)
    policy = game.store.policy
    game.store.policy = policy.model_copy(
        update={
            "owner_m3_rulings": policy.owner_m3_rulings.model_copy(
                update={
                    "privilege_restoration": "inflictor_condition_owner_restores",
                }
            ),
        }
    )
    return PrivilegeService(game.store), identity


def latest(store, identity):
    work = t.m3["m3_required_work"]
    with store.engine.connect() as c:
        return (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == store.campaign_id, work.c.id == identity)
                .order_by(work.c.revision.desc())
            )
            .mappings()
            .first()
        )


@pytest.mark.parametrize("kind", ["privacy", "visiting_home"])
def test_scene_suspension_preserves_paid_qualification_and_resets_old_consent(ledger, kind):
    service, cycle, game, period = scene_setup(ledger)
    pay(service, kind)
    activate(cycle, game, period)
    if kind == "visiting_home":
        roll_for(cycle, game, period, PLAYER, (2, 2))
    scene_sync(service, period)
    old = service.scene_tasks(PLAYER)[0]["id"]
    propose(service, old, kind=kind)
    receipt = state(game).requisitions[-1]
    original = json.loads(latest(ledger, old)["body_json"])["benefit"]
    svc, gate = revoke(game, receipt)
    saved = service.scene_get(PLAYER, old)
    assert saved["state"] == "resolved" and saved["deferred"]
    assert not saved["benefit"]["declined"]
    change(svc, OTHER, gate, allow=True)
    change(svc, PLAYER, gate, allow=False)
    after = service.scene_get(PLAYER, old)
    assert after["resolution"] == "requisition_benefit_transferred"
    fresh = service.scene_get(PLAYER, after["transfer_work"])
    assert fresh["state"] == "pending" and fresh["benefit"]["scene"] is None
    assert fresh["benefit"]["purchase"] == original["purchase"]
    assert fresh["benefit"]["source_event"] == original["source_event"]
    assert fresh["benefit"]["qualification_event"] == original["qualification_event"]
    with ledger.transaction() as c:
        resume_restored_benefits(c, ledger, service.periods._get(c, period), str(uuid4()))
    assert len(service.scene_tasks(PLAYER)) == 2
    assert state(game).sheets["2"].permissions == (3 if kind == "privacy" else 2)


@pytest.mark.parametrize("lost", [False, True])
def test_personal_firearm_revoke_restore_preserves_actual_item_or_actual_loss(
    ledger,
    tmp_path,
    monkeypatch,
    lost,
):
    service, _, game, _ = firearm_setup(ledger, tmp_path, monkeypatch)
    purchase(service)
    grant = state(game).personal_firearms[-1]
    asset = next(x for x in state(game).sheets["2"].assets if x.id == grant.issues[-1].asset)
    if lost:
        lose(service)
    svc, gate = revoke(game, state(game).requisitions[-1])
    assert not any(x.id == asset.id for x in state(game).sheets["2"].assets)
    change(svc, OTHER, gate, allow=True)
    change(svc, PLAYER, gate, allow=False)
    held = [x for x in state(game).sheets["2"].assets if x.id == asset.id]
    assert len(held) == (0 if lost else 1)
    if held:
        assert held[0] == asset
    assert state(game).personal_firearms[-1] == grant
    assert state(game).sheets["2"].permissions == 2


def test_earned_lost_firearm_return_is_deferred_then_owned_retrieval_keeps_original_roll(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, cycle, game, period = firearm_setup(ledger, tmp_path, monkeypatch, period=True)
    purchase(service)
    lose(service)
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    firearm_sync(service, period)
    old = service.return_tasks(PLAYER)[0]["id"]
    original = json.loads(latest(ledger, old)["body_json"])
    svc, gate = revoke(game, state(game).requisitions[-1])
    assert service.return_get(PLAYER, old)["deferred"]
    change(svc, OTHER, gate, allow=True)
    change(svc, PLAYER, gate, allow=False)
    saved = service.return_get(PLAYER, old)
    identity = saved["transfer_work"]
    transferred = json.loads(latest(ledger, identity)["body_json"])
    assert (transferred["action"], transferred["raw_event"], transferred["total"]) == (
        original["action"],
        original["raw_event"],
        original["total"],
    )
    assert len(state(game).personal_firearms[-1].issues) == 1
    fresh = service.return_get(PLAYER, identity)
    service.claim(
        PLAYER,
        str(uuid4()),
        identity,
        fresh["revision"],
        take=True,
        account="Actual retrieved original entitlement",
        expected=fresh["expected"],
    )
    assert len(state(game).personal_firearms[-1].issues) == 2
    with pytest.raises(WorkflowError):
        service.claim(
            PLAYER,
            str(uuid4()),
            identity,
            fresh["revision"],
            take=True,
            account="No duplicate issue",
            expected=fresh["expected"],
        )


@pytest.mark.parametrize("complete_scene", [False, True])
def test_unspent_comforts_keeps_actual_qualification_and_only_completed_attendance(
    ledger,
    complete_scene,
):
    from test_comfort_service import grant, offered, record

    service, _, game, _, receipts, _ = offered(ledger)
    identity = service.list(PLAYER)[0]["id"]
    if complete_scene:
        record(service, identity)
    original = json.loads(latest(ledger, identity)["body_json"])["benefit"]
    svc, gate = revoke(game, state(game).requisitions[-1])
    assert service.get(PLAYER, identity)["deferred"]
    change(svc, OTHER, gate, allow=True)
    change(svc, PLAYER, gate, allow=False)
    fresh_id = service.get(PLAYER, identity)["transfer_work"]
    fresh = service.get(PLAYER, fresh_id)
    assert fresh["ready"] is complete_scene
    saved = json.loads(latest(ledger, fresh_id)["body_json"])["benefit"]
    assert saved["action"] == original["action"] and saved["raw_event"] == original["raw_event"]
    assert saved["purchase"] == receipts[0]["id"] and saved["taken"] is None
    if complete_scene:
        assert saved["scene"] == original["scene"]
        grant(service, fresh_id)
        assert service.get(PLAYER, fresh_id)["taken"] is True
