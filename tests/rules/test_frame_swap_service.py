"""Synthetic destination review verifies payment/coordination/physical exchange only."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_frame_swap import selection, synthetic_registry
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_personal_firearm_service import purchase
from test_personal_firearm_service import setup as firearm_setup
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_frame_swap import open_plan
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical import initial as place
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services.m3_access import digest
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_personal_firearm import proof
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def setup(store, tmp_path, monkeypatch, *, mode="outside_frame"):
    service, _, game, _ = firearm_setup(store, tmp_path, monkeypatch)
    registry = synthetic_registry()
    service.registry = registry
    path = tmp_path / "SYNTHETIC-swap-registry.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    policy = store.policy
    store.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={"registry_sha256": digest(registry)}
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon.sheets["2"].permissions = 10
        actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
        placement = InitialPlacement(
            actor=actor,
            frame_instance="initial:" + actor.incarnation,
            girl_cell=(0, 0),
            frame_cell=(0, 0),
            mode=mode,
            account="Actual location",
            facts_confirmed=True,
        )
        canon = place(
            canon,
            profiles(c, store.campaign_id),
            placement,
            "actual-original-vessel",
            "synthetic-owned-position",
            "synthetic-reviewed-position",
        )
        game.event(c, 1, "synthetic-source-position", "synthetic.state", canon)
    purchase(service)
    return FrameSwapService(game, registry), game


def configured(service, game, frame="THE ENFORCER"):
    identity = service.create(PLAYER, str(uuid4()), frame)["id"]
    service.change(PLAYER, str(uuid4()), identity, 1, selection=selection(state(game), frame))
    return identity


def pay(service, identity, *, key=None, data=None):
    data = data or service.get(PLAYER, identity)
    return service.change(
        PLAYER,
        key or str(uuid4()),
        identity,
        data["revision"],
        purchase=True,
        expected=data["expected"],
        delivered=True,
    )


def test_actual_paid_exchange_preserves_original_body_archives_old_frame_and_rebuilds_once(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, game = setup(ledger, tmp_path, monkeypatch)
    identity = configured(service, game)
    original, data = state(game), service.get(PLAYER, identity)
    result = pay(service, identity, key="pay-exchange-once", data=data)
    assert pay(service, identity, key="pay-exchange-once", data=data) == result
    changed = state(game)
    assert changed.sheets["2"].permissions == 3
    assert changed.placements[0].vessel_id == original.placements[0].vessel_id
    assert changed.placements[0].girl_cell == original.placements[0].girl_cell == (0, 0)
    assert changed.parked_frames[0].frame_instance == original.placements[0].frame_instance
    assert json.loads(changed.parked_frames[0].frame_json) == original.sheets["2"].model_dump(
        mode="json"
    )
    assert changed.personal_firearms[0].issues == original.personal_firearms[0].issues
    with ledger.engine.connect() as c:
        proof(c, ledger, changed.personal_firearms[0])
        assert "PRIVATE_EXCHANGE" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    game.rebuild()
    assert state(game) == changed


def test_red_queen_requires_exact_original_other_girl_then_reconfiguration_clears_consent(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, game = setup(ledger, tmp_path, monkeypatch)
    identity = configured(service, game, "THE RED QUEEN")
    with pytest.raises(WorkflowError, match="accept"):
        pay(service, identity)
    data = service.get(OTHER, identity)
    assert "account" not in str(data)
    service.change(OTHER, "actual-court-accept", identity, data["revision"], accept=True)
    data = service.get(PLAYER, identity)
    assert data["accepted"]
    service.change(
        PLAYER,
        "actual-change-plan",
        identity,
        data["revision"],
        selection=selection(state(game), "THE RED QUEEN"),
    )
    assert not service.get(PLAYER, identity)["accepted"]
    data = service.get(OTHER, identity)
    service.change(OTHER, "new-exact-court-accept", identity, data["revision"], accept=True)
    pay(service, identity)
    assert state(game).sheets["2"].frame_runtime.court["The Knight"] == 3


def test_inside_cockpit_payment_failure_rolls_back_currency_new_frame_and_history(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, game = setup(ledger, tmp_path, monkeypatch, mode="piloting")
    identity = configured(service, game)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="outside|cockpit"):
        pay(service, identity)
    assert state(game).model_dump_json() == before
    assert service.get(PLAYER, identity)["state"] == "pending"


def test_native_exact_saved_choices_payment_is_owner_bound_and_stale_safe(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, game = setup(ledger, tmp_path, monkeypatch)
    identity = configured(service, game)

    async def run():
        caller = current(2, 21701)
        await caller.response.defer(ephemeral=True)
        await open_plan(caller, service, identity)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(operation=("pay",), delivered=("yes",))
        await form.confirm.callback(current(2, 21702))
        assert form.completed

    asyncio.run(run())
    assert state(game).sheets["2"].permissions == 3
