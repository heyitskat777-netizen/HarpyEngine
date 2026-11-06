"""Paid retained Modular slot/rule repairs new hardware without reissuing old hardware."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_strain_effect_service
import test_strain_service
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service as mission_service
from test_mission_ui import current
from test_off_duty_cycle import activate, call, roll_for
from test_off_duty_cycle import prepared as prepared_period
from test_physical_operations import place
from test_strain_service import ready as strain_ready
from test_succubus import restore, suspend

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_modular import open_purchase
from girlframe.discord_adapter.m3_off_duty_cycle import open_action
from girlframe.engine import m3_class_retention as retention
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine import m3_modular as rules
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import PilotSheet
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_assets import frame_capacity
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.m3_modular import Replacement
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_modular import ModularService, entitlement, repair_options
from girlframe.services.onboarding import WorkflowError

NEEDED = frozenset(
    (
        rules.RULE,
        "core.core.frame-requisitions",
        "frame.enforcer.obedience-conditioning",
        "frame.enforcer.permission-trigger",
        "frame.enforcer.enforcement-initiative",
    )
)


def synthetic_registry():
    production = Registry.model_validate_json(Path("rules/registry.json").read_text())
    raw = production.model_dump(mode="json")
    contract = dict(
        trigger="SYNTHETIC retained Modular actual newFrame repair",
        actor_type="Original Girl with exact original paid Class and4P Swap",
        pre_roll_sources=["Current newFrame, original receipt, actual damaged/repaired Asset"],
        roll_kind="diceless",
        allowed_modifiers=["Original real GoOffDuty retains its normal roll"],
        tier_options={"normal": ["Real capacity6 and replacement instead of actual repair"]},
        choice_ownership="Actual original owner chooses its current repaired Asset/replacement",
        target_policy="Current original owned newFrame, no old hardware migration",
        post_roll_effects=["Real new Asset/current recovery, original old hardware not reissued"],
        mandatory_followups=["Actual recovery endpoint; other period duties remain pending"],
        handler_or_gm_intervention="Actual source only",
        test_fixture_ids=["tests/rules/test_retained_modular.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_modular.py"],
            )
            if not entry.get("contract"):
                entry["contract"] = contract
    candidate = Registry.model_validate_json(json.dumps(raw))
    assert {x.id for x in candidate.entries if x != production.entry(x.id)} == NEEDED
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
    return production, candidate


def prepared(store, tmp_path, monkeypatch):
    monkeypatch.setattr(
        test_strain_service,
        "service",
        lambda store, frame: mission_service(store, girl="ALPHA", frame=frame),
    )
    monkeypatch.setattr(
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame="WYVERN 0.4"),
    )
    cycle, game, period = prepared_period(store)
    production, registry = synthetic_registry()
    path = tmp_path / "SYNTHETIC-only-five-retained-modular-sources.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    registry_sha256=digest(registry),
                    subsystems=store.policy.m3_approval.subsystems | {"economy", "plays", "world"},
                )
            )
        )
    )
    cycle.missions.access = Access(store)
    with store.transaction() as c:
        canon = state(game)
        canon = place(place(canon, 2, mode="outside_frame"), 3)
        canon.sheets["2"].permissions = 10
        canon.sheets["2"].identities[0].marked = True
        game.event(c, 2, str(uuid4()), "synthetic.actual_original_modular_resources", canon)
    source = ModularService(game)

    async def purchase():
        own = current(2, 956001)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and "2 Permissions" in form.text()
        form.values.update(
            name="Original acquisition-written module",
            description="PRIVATE_ORIGINAL_MODULAR_HARDWARE",
            account="PRIVATE_ORIGINAL_MODULAR_SOURCE",
        )
        await form.confirm.callback(current(2, 956002))
        assert form.completed

    asyncio.run(purchase())
    original = state(game)
    actor = current_ref(original, 2)
    paid = rules.held(original, actor)
    assert paid and paid.price == 2 and paid.frame == "WYVERN 0.4"
    assert frame_capacity(original.sheets["2"], original) == 6
    written = next(x for x in original.sheets["2"].assets if x.id == "modular:" + paid.id)
    kept = next(
        x
        for x in original.sheets["2"].assets
        if x.family == "frame" and x.intrinsic is None and x.id != written.id
    )
    swap = FrameSwapService(game, registry)
    plan = swap.create(PLAYER, str(uuid4()), "THE ENFORCER")["id"]
    data = swap.get(PLAYER, plan)
    assert next(x for x in data["class_sources"] if x["rule"] == rules.RULE)["receipt"] == paid.id
    selection = Selection(
        frame="THE ENFORCER",
        name="Actual replacement Enforcer",
        appearance="Actual new body",
        assets=tuple(AssetChoice(name=x, description="Actual " + x) for x in data["starting"][:2]),
        retained_asset=kept.id,
        retained_rule=rules.RULE,
        retained_receipt=paid.id,
        account="PRIVATE_MODULAR_SWAP",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=selection)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    return game, source, cycle, period, paid, original, written, production


def test_retained_modular_actual_new_frame_slot_recovery_replacement_without_old_hardware_regrant(
    ledger, tmp_path, monkeypatch
):
    game, source, cycle, period, paid, original, written, production = prepared(
        ledger, tmp_path, monkeypatch
    )
    actor = paid.actor
    canon = state(game)
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    assert canon.sheets["2"].permissions == 4 and rules.held(canon, actor) == paid
    assert frame_capacity(canon.sheets["2"], canon) == 6
    assert written.id not in {x.id for x in canon.sheets["2"].assets}
    parked = next(x for x in canon.parked_frames if x.frame_instance == paid.frame_instance)
    assert written in PilotSheet.model_validate_json(parked.frame_json).assets
    assert not any(x.intrinsic for x in canon.sheets["2"].assets if x.family == "frame")
    assert canon.sheets["2"].identities == original.sheets["2"].identities
    with ledger.engine.connect() as c:
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="Restore"):
        source.buy(
            PLAYER,
            str(uuid4()),
            menu["revision"],
            actor,
            menu["frame"],
            "No regift/rebuy",
            "Duplicate hardware",
            "Cannot recreate original hardware",
            "WYVERN 0.4",
        )
    gate = suspend(game, swap.id)
    suspended = state(game)
    assert frame_capacity(suspended.sheets["2"], suspended) == 5
    assert (
        source.menu(PLAYER)["suspended"]
        and suspended.sheets["2"].assets == canon.sheets["2"].assets
    )
    with ledger.engine.connect() as c:
        assert entitlement(game, c, suspended, actor) is None
        assert repair_options(game, c, suspended, actor) == []
    restore(game, gate)
    assert frame_capacity(state(game).sheets["2"], state(game)) == 6
    assert not source.menu(PLAYER)["suspended"]
    assert state(game).sheets["2"].assets == canon.sheets["2"].assets
    with ledger.transaction() as c:
        damaged = state(game)
        selected = next(
            x
            for x in damaged.sheets["2"].assets
            if x.family == "frame" and x.id.startswith(swap.new_frame)
        )
        selected.damaged = True
        game.event(c, 2, str(uuid4()), "synthetic.actual_new_frame_damage", damaged)
    before = state(game)
    assert selected.id in rules.replaceable(before, actor)
    activate(cycle, game, period)
    action = roll_for(cycle, game, period, PLAYER, (2, 2))
    receipt = game.inspect(PLAYER, action)["receipt"]
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    review = cycle.review(PLAYER, period)
    replacement = Replacement(
        asset=selected.id,
        name="Actual new replacement component",
        description="PRIVATE_NEW_MODULAR_REPAIR",
    )

    async def recover():
        own = current(2, 956010)
        await own.response.defer(ephemeral=True)
        await open_action(own, cycle, period, "recover")
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(3, 956011))
        form.values.update(repairs=("yes",), modular_assets=(selected.id,))
        form.values["modular_name:" + selected.id] = replacement.name
        form.values["modular_description:" + selected.id] = replacement.description
        response = current(2, 956012)
        await form.confirm.callback(response)
        assert form.completed, str(response.edit_original_response.call_args)

    asyncio.run(recover())
    saved = state(game)
    replay = cycle.recover(
        PLAYER,
        "956012",
        period,
        review["revision"],
        review["game_revision"],
        RecoveryChoice(repair_assets=True, modular_replacements=(replacement,)),
    )
    assert replay and state(game) == saved
    assert selected.id not in {x.id for x in saved.sheets["2"].assets}
    new = next(x for x in saved.sheets["2"].assets if x.name == replacement.name)
    assert new.id != written.id and not new.damaged and not new.void
    assert written.id not in {x.id for x in saved.sheets["2"].assets}
    assert len(saved.sheets["2"].assets) == len(before.sheets["2"].assets)
    assert frame_capacity(saved.sheets["2"], saved) == 6
    fact = next(x for x in saved.facts if x.get("kind") == "modular_repair")
    assert fact["purchase"] == paid.id and fact["period"] == period
    assert fact["old"] == selected.id and fact["new"] == new.id
    assert cycle.review(PLAYER, period)["own"]["recovered"]
    other = cycle.review(OTHER, period)["own"]
    assert other is None or not other["recovered"]
    assert cycle.periods.get(ADMIN, period)["phase"] == "active"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    assert next(x for x in saved.requisitions if x.id == paid.id) == paid
    assert saved.sheets["2"].permissions == 4
    forged = saved.model_copy(deep=True)
    link = retention.links(forged)[0]
    wrong = link.model_copy(update=dict(event="SYNTHETIC_FORGED_SWAP"))
    forged.facts = [
        dict(x, body=wrong.model_dump_json()) if x.get("kind") == "class_rule_retained" else x
        for x in forged.facts
    ]
    with ledger.engine.connect() as c:
        with pytest.raises(ValueError, match="retention chain"):
            proof(game, c, forged, paid)
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert game.lock(c, 900)["state"] == "released"
    assert game.rebuild() > 0 and state(game) == saved
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
