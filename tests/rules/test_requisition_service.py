import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, start, state, tick
from test_mission_service import service
from test_requisitions import selected

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_requisition_state import Installation
from girlframe.services.m2_game import GameService
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store):
    missions, game = service(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"economy"}}
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 3
        game.event(c, 1, "synthetic-purchase-funds", "synthetic.permissions", canon)
    return RequisitionService(game), game


def buy(svc, *, viewer=PLAYER, key=None, data=None, choice=None):
    view = data or svc.view(viewer)
    return svc.buy(
        viewer,
        key or str(uuid4()),
        ActorRef.model_validate(view["actor"]),
        view["source_sha256"],
        choice or selected(),
    )


def test_source_payment_acquisition_and_private_receipt_are_atomic_durable_and_replay_safe(ledger):
    svc, game = ready(ledger)
    view = svc.view(PLAYER)
    before = state(game)
    outcome = buy(svc, key="pay-once", data=view)
    assert buy(svc, key="pay-once", data=view) == outcome
    after = state(game)
    assert after.sheets["2"].permissions == 2 and len(after.requisitions) == 1
    assert after.sheets["3"] == before.sheets["3"] and after.bonds == before.bonds
    receipt = after.requisitions[0]
    assert receipt.actor.incarnation == before.sheets["2"].character_id
    with ledger.engine.connect() as c:
        saved = (
            c.execute(sa.select(t.events).where(t.events.c.id == receipt.source_event))
            .mappings()
            .one()
        )
        history = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.event_id == receipt.source_event
            )
        )
        assert json.loads(history)["requisitions"][0]["id"] == receipt.id
        assert "Actual installation" not in saved["payload_json"]
        assert "gear" not in saved["payload_json"]
        assert game.dice.calls == 0
    restarted = RequisitionService(GameService(ledger))
    assert restarted.view(PLAYER) == svc.view(PLAYER)
    game.rebuild()
    assert state(game) == after
    assert not svc.view(OTHER)["purchases"]
    assert receipt.id not in str(svc.view(OTHER))


def test_wrong_owner_policy_revocation_and_stale_native_form_do_not_charge(ledger):
    svc, game = ready(ledger)
    data = svc.view(PLAYER)
    ref = ActorRef.model_validate(data["actor"])
    with pytest.raises(WorkflowError, match="owned"):
        svc.buy(OTHER, "wrong-owner", ref, data["source_sha256"], selected())
    buy(svc, data=data, key="actual-purchase")
    with pytest.raises(WorkflowError, match="STALE_REQUISITION"):
        buy(svc, data=data)
    assert state(game).sheets["2"].permissions == 2
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        buy(svc, data=data, key="actual-purchase")
    assert state(game).sheets["2"].permissions == 2


def test_pause_pending_play_and_unrestored_chat_block_purchase_without_resource_effects(ledger):
    svc, game = ready(ledger)
    data = svc.view(PLAYER)
    before = state(game)
    ledger.safety(OTHER, "pause-buy", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        buy(svc, data=data)
    ledger.safety(OTHER, "resume-buy", ledger.status(OTHER)["revision"], pause=False)
    action = start(game)
    with pytest.raises(WorkflowError, match="pending Plays"):
        buy(svc, data=data)
    game.abort(ADMIN, "abort-before-installation", action)
    with pytest.raises(WorkflowError, match="restore chat"):
        buy(svc, data=data)
    tick(GameWorker(game), Gateway(), 5)
    assert state(game) == before and game.dice.calls == 0
    assert buy(svc, data=data)


@pytest.mark.parametrize("change", ("frame", "body", "profile"))
def test_changed_frame_body_or_profile_cannot_reuse_purchase_preview(ledger, change):
    svc, game = ready(ledger)
    data = svc.view(PLAYER)
    with ledger.transaction() as c:
        if change == "frame":
            canon = state(game)
            canon.sheets["2"].frame_runtime = FrameRuntime(
                id="replacement-frame", generation=1, source_work="synthetic-source"
            )
            game.event(c, 1, "synthetic-frame-change", "synthetic.frame", canon)
        else:
            c.execute(
                t.characters.update()
                .where(
                    t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2"
                )
                .values(
                    **(
                        {"id": str(uuid4())}
                        if change == "body"
                        else {"revision": t.characters.c.revision + 1}
                    )
                )
            )
    with pytest.raises(WorkflowError, match="STALE"):
        buy(svc, data=data)
    assert state(game).sheets["2"].permissions == 3 and not state(game).requisitions


def test_rollback_after_history_event_restores_payment_asset_receipt_and_command(
    ledger, monkeypatch
):
    svc, game = ready(ledger)
    data, before = svc.view(PLAYER), state(game)
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic installation failure after history")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        buy(svc, data=data, key="retry-installation")
    assert state(game) == before
    with ledger.engine.connect() as c:
        assert (
            c.scalar(
                sa.select(t.commands.c.interaction_key).where(
                    t.commands.c.interaction_key == "retry-installation"
                )
            )
            is None
        )
    monkeypatch.setattr(game, "event", original)
    assert buy(svc, data=data, key="retry-installation")
    assert len(state(game).requisitions) == 1 and state(game).sheets["2"].permissions == 2


def test_concurrent_same_purchase_is_exactly_once_and_distinct_stale_purchase_does_not_charge(
    ledger,
):
    svc, game = ready(ledger)
    data = svc.view(PLAYER)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: buy(svc, data=data, key="concurrent-installation"), range(2))
        )
    assert results[0] == results[1]
    assert len(state(game).requisitions) == 1 and state(game).sheets["2"].permissions == 2
    with pytest.raises(WorkflowError, match="STALE_REQUISITION"):
        buy(svc, data=data)


def test_native_asset_catalog_is_paginated_owner_bound_and_requires_explicit_payment(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_requisitions import open_requisitions

    svc, game = ready(ledger)

    async def run():
        owner = current(2, 15801)
        await owner.response.defer(ephemeral=True)
        await open_requisitions(owner, svc)
        picker = owner.edit_original_response.call_args.kwargs["view"]
        assert not await picker.interaction_check(current(3))
        sources = current(2, 15802)
        await sources.response.defer(ephemeral=True)
        await picker.open_item(sources, "install")
        catalog = sources.edit_original_response.call_args.kwargs["view"]
        assert len(catalog.options) > 25 and len(catalog.children[-1].options) <= 25
        chosen = current(2, 15803)
        await chosen.response.defer(ephemeral=True)
        await catalog.open_item(chosen, "THE RED QUEEN:3")
        form = chosen.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        assert not state(game).requisitions and state(game).sheets["2"].permissions == 3
        form.values.update(
            description="PRIVATE_INSTALLED_DESCRIPTION",
            account="PRIVATE_INSTALLATION_ACCOUNT",
            confirm=("yes",),
        )
        await form.confirm.callback(current(2, 15804))
        assert form.completed and state(game).sheets["2"].permissions == 2
        assert state(game).sheets["2"].assets[-1].name == "The Crown"

    asyncio.run(run())


def test_custom_native_purchase_preserves_private_details_and_new_assets_are_ordinary(ledger):
    svc, game = ready(ledger)
    before = state(game)
    outcome = buy(
        svc,
        choice=Installation(
            name="PRIVATE_CUSTOM_NAME",
            description="PRIVATE_CUSTOM_DESCRIPTION",
            account="PRIVATE_CUSTOM_INSTALLATION",
            trigger_confirmed=True,
        ),
    )
    after = state(game)
    assert after.sheets["2"].assets[-1].name == "PRIVATE_CUSTOM_NAME"
    assert not after.sheets["2"].assets[-1].void and not after.sheets["2"].assets[-1].damaged
    assert (
        after.sheets["2"].girl == before.sheets["2"].girl
        and after.sheets["2"].frame == before.sheets["2"].frame
    )
    assert "PRIVATE_" not in json.dumps(outcome)
    with ledger.engine.connect() as c:
        bodies = c.scalars(
            sa.select(t.events.c.payload_json).where(t.events.c.campaign_id == ledger.campaign_id)
        )
        assert "PRIVATE_CUSTOM_" not in str(list(bodies))
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_outbox"])) == 0
