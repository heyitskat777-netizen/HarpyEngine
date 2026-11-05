"""Actual purchased Requisition → temporary removal → owned restoration."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_beneath_service import ready, start
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_requisitions import selected

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_privileges import open_privilege
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService
from girlframe.services.m3_comforts import ComfortService
from girlframe.services.m3_privileges import PrivilegeService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError


def setup(store, kind="asset_installment", *, altered=False, native=False):
    game, worker, gateway = ready(store, (6, 6))
    policy = store.policy
    store.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={
                    "subsystems": policy.m3_approval.subsystems | {"economy"},
                }
            ),
            "owner_m3_rulings": policy.owner_m3_rulings.model_copy(
                update={
                    "privilege_restoration": "inflictor_condition_owner_restores",
                }
            ),
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["3"].permissions = 3
        game.event(c, 1, "fund-revocation-test", "synthetic.funds", canon)
    buyer = RequisitionService(game) if kind == "asset_installment" else ComfortService(game)
    preview = buyer.view(OTHER)
    args = (
        OTHER,
        "actual-revocable-purchase",
        ActorRef.model_validate(preview["actor"]),
        preview["source_sha256"],
    )
    if kind == "asset_installment":
        buyer.buy(*args, selected())
    else:
        buyer.buy_comforts(*args, "PRIVATE_SUSPENDED_COMFORT")
    receipt = state(game).requisitions[-1]
    if altered:
        with store.transaction() as c:
            canon = state(game)
            asset = next(x for x in canon.sheets["3"].assets if x.id == receipt.asset_id)
            asset.damaged = True
            asset.void = True
            asset.description = "Actual prior damage and Void corruption"
            game.event(c, 1, "prior-asset-changes", "synthetic.state", canon)
    identity = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "punish"),
        fields={"tag": "Actual confrontation"},
        text="Actual discipline",
    )
    work = game.decision(PLAYER, game.choices(PLAYER)[0]["id"])["body"]["work_id"]
    svc = PunishmentService(store)
    data = svc.get(PLAYER, work)
    assert data["choices"]["requisitions"] == [
        dict(
            id=receipt.id,
            name=next(x.name for x in state(game).sheets["3"].assets if x.id == receipt.asset_id)
            if kind == "asset_installment"
            else "Creature Comforts",
        )
    ]
    details = Details(
        kind="revoked_privileges", requisition=receipt.id, restoration="PRIVATE_RETURN_CONDITION"
    )
    if native:
        from girlframe.discord_adapter.m3_punishments import open_details

        async def choose_revocation():
            inflictor = current(2, 19301)
            await inflictor.response.defer(ephemeral=True)
            await open_details(inflictor, svc, work, "revoked_privileges")
            form = inflictor.edit_original_response.call_args.kwargs["view"]
            form.values.update(requisition=(receipt.id,), restoration="PRIVATE_RETURN_CONDITION")
            await form.confirm.callback(current(2, 19302))
            assert form.completed

        asyncio.run(choose_revocation())
    else:
        svc.apply(
            PLAYER, "actual-revocation", work, data["revision"], data["game_revision"], details
        )
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    tick(worker, gateway, 5)
    gate = next(x for x in state(game).obligations if x.kind == "revoked_requisition")
    return PrivilegeService(store), game, receipt, gate.id


def change(service, viewer, identity, *, allow, key=None, replace=None, preview=None):
    data = preview or service.get(viewer, identity)
    return service.change(
        viewer,
        key or str(uuid4()),
        identity,
        data["expected"],
        data["game_revision"],
        allow=allow,
        evidence="Actual condition or restoration",
        replace=replace,
    )


def test_real_social_punishment_removes_original_asset_then_restores_exactly_once(ledger):
    svc, game, receipt, identity = setup(ledger)
    canon = state(game)
    assert suspended(canon, receipt.id)
    assert not any(x.id == receipt.asset_id for x in canon.sheets["3"].assets)
    assert canon.sheets["3"].permissions == 2
    with pytest.raises(WorkflowError):
        svc.get(ADMIN, identity)
    with pytest.raises(WorkflowError):
        change(svc, OTHER, identity, allow=True)
    with pytest.raises(WorkflowError):
        change(svc, OTHER, identity, allow=False)
    change(svc, PLAYER, identity, allow=True)
    assert not any(x.id == receipt.asset_id for x in state(game).sheets["3"].assets)
    preview = svc.get(OTHER, identity)
    result = change(svc, OTHER, identity, allow=False, key="restore-once", preview=preview)
    assert (
        change(
            PrivilegeService(ledger),
            OTHER,
            identity,
            allow=False,
            key="restore-once",
            preview=preview,
        )
        == result
    )
    restored = state(game)
    assert not suspended(restored, receipt.id)
    assert len([x for x in restored.sheets["3"].assets if x.id == receipt.asset_id]) == 1
    assert restored.sheets["3"].permissions == 2 and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert "PRIVATE_RETURN" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))


def test_restoration_preserves_damage_and_void_and_original_frame_and_requires_legal_cap_choice(
    ledger,
):
    svc, game, receipt, identity = setup(ledger, altered=True)
    original = state(game)
    asset_snapshot = next(x for x in original.obligations if x.id == identity).details["asset"]
    change(svc, PLAYER, identity, allow=True)
    with ledger.transaction() as c:
        canon = state(game)
        frame = [x for x in canon.sheets["3"].assets if x.family == "frame"]
        for index in range(5 - len(frame)):
            canon.sheets["3"].assets.append(
                AssetState(id="extra-" + str(index), family="frame", name="Actual installed extra")
            )
        game.event(c, 1, "actual-cap-change", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="replace|cap|limit"):
        change(svc, OTHER, identity, allow=False)
    change(svc, OTHER, identity, allow=False, replace="extra-0")
    restored = next(x for x in state(game).sheets["3"].assets if x.id == receipt.asset_id)
    assert restored.model_dump_json() == asset_snapshot
    assert restored.damaged and restored.void


def test_changed_original_frame_cannot_receive_suspended_equipment(ledger):
    svc, game, _, identity = setup(ledger)
    change(svc, PLAYER, identity, allow=True)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].frame_runtime = FrameRuntime(
            id="replacement", generation=2, source_work="actual-replacement"
        )
        game.event(c, 1, "changed-actual-frame", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="original Frame"):
        change(svc, OTHER, identity, allow=False)


def test_native_condition_and_restore_controls_are_owned_and_inbox_contains_no_condition(ledger):
    svc, game, receipt, identity = setup(ledger, "creature_comforts", native=True)
    assert suspended(state(game), receipt.id)
    items = InboxService(ledger).items(PLAYER)
    assert any(x.task == "m3_privilege" for x in items)
    assert "PRIVATE_RETURN" not in str(items)

    async def run():
        inflictor = current(2, 19401)
        await inflictor.response.defer(ephemeral=True)
        await open_privilege(inflictor, svc, identity)
        form = inflictor.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(evidence="The actual condition is met", confirm=("yes",))
        await form.confirm.callback(current(2, 19402))
        assert form.completed
        target = current(3, 19403)
        await target.response.defer(ephemeral=True)
        await open_privilege(target, PrivilegeService(ledger), identity)
        restore = target.edit_original_response.call_args.kwargs["view"]
        restore.values.update(evidence="The original benefit is usable again", confirm=("yes",))
        await restore.confirm.callback(current(3, 19404))
        assert restore.completed

    asyncio.run(run())
    assert not suspended(state(game), receipt.id) and state(game).sheets["3"].permissions == 2


def test_pause_stale_revision_and_changed_character_do_not_restore_resources(ledger):
    svc, game, receipt, identity = setup(ledger)
    change(svc, PLAYER, identity, allow=True)
    preview = svc.get(OTHER, identity)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].character_id = "replacement-girl"
        game.event(c, 1, "replace-girl-no-inheritance", "synthetic.state", canon)
    assert svc.get(OTHER, identity)["stale"]
    with pytest.raises(WorkflowError):
        change(svc, OTHER, identity, allow=False, preview=preview)
    assert not any(x.id == receipt.asset_id for x in state(game).sheets["3"].assets)


def test_paused_missing_policy_and_stale_confirmation_preserve_the_pending_resource(
    ledger, monkeypatch, tmp_path
):
    svc, game, receipt, identity = setup(ledger)
    preview = svc.get(PLAYER, identity)
    ledger.safety(OTHER, "pause-restoration", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        change(svc, PLAYER, identity, allow=True, preview=preview)
    assert svc.get(OTHER, identity)["pending"]
    ledger.safety(OTHER, "resume-restoration", ledger.status(OTHER)["revision"], pause=False)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].heat += 1
        game.event(c, 1, "changed-before-restore", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="STALE_REVOCATION"):
        change(svc, PLAYER, identity, allow=True, preview=preview)
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "missing.json"))
    assert svc.get(PLAYER, identity)["pending"]
    with pytest.raises(WorkflowError, match="registry is unavailable"):
        change(svc, PLAYER, identity, allow=True)
    assert suspended(state(game), receipt.id)


def test_forged_confirmation_and_changed_original_condition_fail_source_proof(ledger):
    svc, game, receipt, identity = setup(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        gate = next(x for x in canon.obligations if x.id == identity)
        gate.details["restoration_allowed"] = "true"
        game.event(c, 1, "forged-restore-confirmation", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="SOURCE_RESTORATION_MISSING"):
        svc.get(OTHER, identity)
    with ledger.transaction() as c:
        canon = state(game)
        gate = next(x for x in canon.obligations if x.id == identity)
        gate.details["restoration_allowed"] = "false"
        gate.details["condition"] = "Substituted condition"
        game.event(c, 1, "forged-original-condition", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="SOURCE_REVOCATION_MISSING"):
        svc.get(PLAYER, identity)
    assert not any(x.id == receipt.asset_id for x in state(game).sheets["3"].assets)


def test_actual_qualified_comfort_benefit_cannot_grant_during_temporary_removal(ledger):
    from test_comfort_service import offered

    from girlframe.services.m3_work import related

    comfort, _, game, period, _, _ = offered(ledger)
    policy = ledger.policy
    ledger.policy = policy.model_copy(
        update={
            "owner_m3_rulings": policy.owner_m3_rulings.model_copy(
                update={
                    "privilege_restoration": "inflictor_condition_owner_restores",
                }
            )
        }
    )
    benefit = comfort.list(PLAYER)[0]
    receipt = state(game).requisitions[0]
    work_id = str(uuid4())
    with ledger.transaction() as c:
        source = game.event(c, 1, "fixture-actual-discipline-cause", "synthetic.discipline")
        related(
            c,
            ledger,
            dict(campaign_id=ledger.campaign_id, off_duty_id=period),
            work_id,
            1,
            2,
            "punishment",
            dict(reason="m2_play", source_pdf=17, immediate=True),
            source,
        )
    svc = PunishmentService(ledger)
    preview = svc.get(ADMIN, work_id)
    svc.apply(
        ADMIN,
        "revoke-qualified-comfort",
        work_id,
        preview["revision"],
        preview["game_revision"],
        Details(
            kind="revoked_privileges",
            requisition=receipt.id,
            restoration="Actual temporary condition",
        ),
    )
    with pytest.raises(WorkflowError, match="REVOKED_PRIVILEGE"):
        comfort.decline(
            PLAYER,
            "decline-while-revoked",
            benefit["id"],
            benefit["revision"],
            "Actual choice cannot spend a suspended benefit",
        )
    assert comfort.list(PLAYER)[0]["state"] == "pending"


def test_concurrent_restore_is_exactly_once_and_failed_history_write_rolls_back(
    ledger, monkeypatch
):
    svc, game, receipt, identity = setup(ledger)
    change(svc, PLAYER, identity, allow=True)
    preview = svc.get(OTHER, identity)
    original = state(game).model_dump_json()
    event = svc.game.event

    def fail_after_history(*args, **kwargs):
        event(*args, **kwargs)
        raise RuntimeError("Synthetic post-history failure")

    monkeypatch.setattr(svc.game, "event", fail_after_history)
    with pytest.raises(RuntimeError, match="post-history"):
        change(svc, OTHER, identity, allow=False, key="retry-restoration", preview=preview)
    assert state(game).model_dump_json() == original
    monkeypatch.setattr(svc.game, "event", event)
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(
            pool.map(
                lambda _: change(
                    svc, OTHER, identity, allow=False, key="retry-restoration", preview=preview
                ),
                range(2),
            )
        )
    assert outcomes[0] == outcomes[1]
    assert sum(x.id == receipt.asset_id for x in state(game).sheets["3"].assets) == 1


def test_suspending_comfort_does_not_repeat_an_existing_all_void_frame_threshold(ledger):
    from girlframe.engine.m2 import GameState
    from girlframe.engine.m3_punishments import apply

    _, _, receipt, _ = setup(ledger, "creature_comforts")
    with ledger.engine.connect() as c:
        history = t.m2["m2_state_history"]
        body = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.event_id == receipt.source_event,
                history.c.campaign_id == ledger.campaign_id,
            )
        )
    canon = GameState.model_validate_json(body)
    for asset in canon.sheets["3"].assets:
        if asset.family == "frame":
            asset.void = True
    result = apply(
        canon,
        3,
        2,
        Details(
            kind="revoked_privileges",
            requisition=receipt.id,
            restoration="Actual temporary removal",
        ),
        entity_id="actual-new-removal",
        source_event="actual-new-source",
        off_duty=False,
        character_ids={2: canon.sheets["2"].character_id, 3: canon.sheets["3"].character_id},
    )
    assert not result.followups
    assert result.state.sheets["3"].assets == canon.sheets["3"].assets
