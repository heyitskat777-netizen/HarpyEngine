"""Synthetic source admission verifies real retained Class mechanics, not production approval."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_privileges import change as restore_choice
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_frame_swap import configure, open_plan
from girlframe.engine import m3_class_grafts as classes
from girlframe.engine import m3_class_retention as rules
from girlframe.engine import m3_dampener as dampener
from girlframe.engine import m3_frame_swap as swap_rules
from girlframe.engine import m3_privileges as privileges
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_frame_swap_state import SwapReceipt
from girlframe.engine.m3_punishments import Details
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_dampener import DampenerService
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_privileges import PrivilegeService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError

NEEDED = frozenset(
    (
        dampener.RULE,
        "core.core.frame-requisitions",
        "frame.enforcer.obedience-conditioning",
        "frame.enforcer.permission-trigger",
        "frame.enforcer.enforcement-initiative",
    )
)


def synthetic_registry():
    raw = json.loads(Path("rules/registry.json").read_text())
    original = Registry.model_validate_json(json.dumps(raw))
    template = dict(
        trigger="SYNTHETIC finite paid Class retention and actual replacement Frame source",
        actor_type="Actual original Pilot and typed paid receipt chain",
        pre_roll_sources=["Exact original paid receipt and actual four-Permission SwapReceipt"],
        roll_kind="2d6",
        allowed_modifiers=["Actual5Heat spent, explicit +2/+3 Dampener basis"],
        tier_options={"normal": ["Real ordinary Keep results"]},
        choice_ownership="Actual printed owner and GM responses",
        target_policy="Own original Frame, source receipt and Asset only",
        post_roll_effects=[
            "Retain original source and actual Asset without creating a fresh purchase"
        ],
        mandatory_followups=["Actual ordinary choices and channel restoration"],
        handler_or_gm_intervention="Actual source GM only",
        test_fixture_ids=["tests/rules/test_class_retention.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC NARROW RETENTION TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_class_retention.py"],
            )
            if not entry.get("contract"):
                entry["contract"] = template
    reviewed = Registry.model_validate_json(json.dumps(raw))
    changed = {x.id for x in reviewed.entries if x != original.entry(x.id)}
    assert changed == NEEDED
    return original, reviewed


def prepared(store, tmp_path, monkeypatch):
    _, game = service(store, girl="ALPHA", frame="WYVERN 0.4")
    production, registry = synthetic_registry()
    with pytest.raises(ValueError, match="review are incomplete"):
        swap_rules.destination(production, "THE ENFORCER")
    path = tmp_path / "SYNTHETIC-only-retained-dampener-and-Enforcer-baseline.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    old = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=old.model_copy(
                update=dict(
                    registry_sha256=digest(registry),
                    subsystems=old.subsystems | {"economy", "plays", "world"},
                )
            ),
            owner_m3_rulings=store.policy.owner_m3_rulings.model_copy(
                update=dict(privilege_restoration="inflictor_condition_owner_restores")
            ),
        )
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3)
        actual.sheets["2"].permissions = 10
        actual.sheets["2"].heat = 5
        actual.sheets["2"].identities[0].marked = True
        retained = next(
            x for x in actual.sheets["2"].assets if x.family == "frame" and x.intrinsic is None
        )
        retained.damaged = retained.void = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_retention_resources", actual)
    source = DampenerService(game)
    data = source.menu(PLAYER)
    source.buy(
        PLAYER,
        str(uuid4()),
        data["revision"],
        ActorRef.model_validate(data["actor"]),
        data["frame"],
        "Actual original native2P Dampener",
    )
    paid = classes.held(state(game), current_ref(state(game), 2), dampener.RULE)
    return game, FrameSwapService(game, registry), source, paid, retained.id, production


def exchange(game, source, retained):
    plan = source.create(PLAYER, str(uuid4()), "THE ENFORCER")["id"]
    original = state(game)

    async def actual_ui():
        owner = current(2, 939001)
        await owner.response.defer(ephemeral=True)
        await configure(owner, source, plan)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        label = dict(next(x for x in form.fields if x.key == "keep_rule").options)[dampener.RULE]
        assert "original" in label and "2P" in label
        form.values.update(
            keep_asset=(retained,),
            keep_rule=(dampener.RULE,),
            assets=("0", "1"),
            first_description="First actual new Frame Asset",
            second_description="Second actual new Frame Asset",
            name="Actual new Enforcer",
            appearance="Actual replacement hardware",
            account="PRIVATE_RETAINED_CLASS_EXCHANGE",
        )
        await form.confirm.callback(current(2, 939002))
        assert form.completed
        owner = current(2, 939003)
        await owner.response.defer(ephemeral=True)
        await open_plan(owner, source, plan)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(3))
        form.values.update(operation=("pay",), delivered=("yes",))
        await form.confirm.callback(current(2, 939004))
        assert form.completed

    asyncio.run(actual_ui())
    assert state(game).sheets["2"].permissions == 4
    return plan, original


def test_actual_retained_dampener_paid_swap_then_new_frame_real_full_heat_roll_and_owned_restore(
    ledger, tmp_path, monkeypatch
):
    game, swap, source, paid, asset, production = prepared(ledger, tmp_path, monkeypatch)
    plan, original = exchange(game, swap, asset)
    actual = state(game)
    actor = current_ref(actual, 2)
    receipt = next(x for x in actual.requisitions if isinstance(x, SwapReceipt))
    assert next(x for x in actual.requisitions if x.id == paid.id) == paid
    assert receipt.selection.retained_receipt == paid.id and receipt.price == 4
    assert receipt.old_frame == paid.frame_instance and receipt.new_frame != paid.frame_instance
    assert classes.held(actual, actor, dampener.RULE) == paid
    assert actual.sheets["2"].identities == original.sheets["2"].identities
    assert actual.sheets["2"].heat == original.sheets["2"].heat == 5
    assert next(x for x in actual.sheets["2"].assets if x.id == asset) == next(
        x for x in original.sheets["2"].assets if x.id == asset
    )
    assert actual.placements[0].vessel_id == original.placements[0].vessel_id
    assert actual.placements[0].girl_cell == original.placements[0].girl_cell
    assert actual.parked_frames[-1].frame_instance == paid.frame_instance
    with ledger.engine.connect() as c:
        assert proof(game, c, actual, paid) == (receipt.new_frame, (paid.id, receipt.id))
        assert "PRIVATE_RETAINED_CLASS" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    with pytest.raises(WorkflowError):
        swap.get(OTHER, plan)
    # One actual paid exchange retry returns the original result, never a second charge/source.
    before = actual.model_dump_json()
    data = swap.get(PLAYER, plan)
    with ledger.engine.connect() as c:
        original_expected = resolve(original, actor, profiles(c, ledger.campaign_id)).source_sha256
    assert (
        swap.change(
            PLAYER,
            "939004",
            plan,
            data["revision"] - 1,
            purchase=True,
            expected=original_expected,
            delivered=True,
        )["paid"]
        is True
    )
    assert state(game).model_dump_json() == before
    new_offer = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="Restore"):
        source.buy(
            PLAYER,
            str(uuid4()),
            new_offer["revision"],
            actor,
            new_offer["frame"],
            "Cannot rebuy retained source",
            "WYVERN 0.4",
        )
    game.dice.faces = (1, 2)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        actual.sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=5,
            dampener_modifier=3,
            context="My actual retained control on the new Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    rolled = game.inspect(PLAYER, action)["receipt"]
    assert rolled["heat"] == 5 and rolled["base_modifier"] == 3 and rolled["pre_total"] == 6
    assert rolled["dampener_purchase"] == paid.id and state(game).sheets["2"].heat == 0
    with ledger.engine.connect() as c:
        assert game.action(c, action)["data"]["dampener"]["frame"] == receipt.new_frame
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual source GM judges sufficient")
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)
    # A genuine ordinary mission discipline source suspends the immutable original purchase.
    missions = MissionService(ledger)
    offered = missions.offer(ADMIN, str(uuid4()), "SYNTHETIC actual mission source", (2, 3))
    missions.respond(PLAYER, str(uuid4()), offered["id"], 1, "accept")
    missions.respond(OTHER, str(uuid4()), offered["id"], 2, "accept")
    missions.start(ADMIN, str(uuid4()), offered["id"], 3)
    missions.end(ADMIN, str(uuid4()), offered["id"], 4, False)
    work = next(
        x
        for x in missions.owned_work(ADMIN)
        if x["subject_id"] == "2" and x["kind"] == "punishment"
    )
    punish = PunishmentService(ledger)
    view = punish.get(ADMIN, work["id"])
    punish.apply(
        ADMIN,
        str(uuid4()),
        work["id"],
        view["revision"],
        view["game_revision"],
        Details(
            kind="revoked_privileges",
            requisition=paid.id,
            restoration="Actual restoration condition",
        ),
    )
    suspended = state(game)
    assert classes.held(suspended, actor, dampener.RULE) is None
    gate = next(x for x in suspended.obligations if x.kind == privileges.KIND)
    assert gate.details["frame"] == receipt.new_frame
    restore = PrivilegeService(ledger)
    restore_choice(restore, ADMIN, gate.id, allow=True)
    restore_choice(restore, PLAYER, gate.id, allow=False)
    restored = state(game)
    assert classes.held(restored, actor, dampener.RULE) == paid
    assert (
        restored.sheets["2"].heat == 0
        and restored.sheets["2"].identities == suspended.sheets["2"].identities
    )
    assert restored.sheets["2"].assets == suspended.sheets["2"].assets
    # The independently paid Swap link can also suspend this same retained rule, without resources.
    isolated = privileges.revoke(
        restored,
        2,
        1,
        receipt.id,
        "Actual source condition",
        "SYNTHETIC_SWAP_GATE",
        "SYNTHETIC_UNIT_SOURCE",
        {2: actor.incarnation},
    )
    assert classes.held(isolated, actor, dampener.RULE) is None
    isolated.obligations[-1].details["restoration_allowed"] = "true"
    isolated = privileges.restore(isolated, "SYNTHETIC_SWAP_GATE", actor.incarnation, None)
    assert (
        classes.held(isolated, actor, dampener.RULE) == paid and isolated.sheets == restored.sheets
    )
    game.rebuild()
    assert state(game) == restored
    with pytest.raises(ValueError, match="review are incomplete"):
        swap_rules.destination(production, "THE ENFORCER")


def test_retained_class_requires_true_original_swap_chain_and_keeps_hardware_out(
    ledger, tmp_path, monkeypatch
):
    game, swap, _, paid, asset, production = prepared(ledger, tmp_path, monkeypatch)
    _, _ = exchange(game, swap, asset)
    canon = state(game)
    assert rules.RULES == {
        dampener.RULE,
        "frame.class.legion.kicked-puppy",
        "frame.class.autocrat.untouchable-frame",
        "frame.class.autocrat.martyr",
        "frame.class.autocrat.succubus-protocol",
        "frame.class.priestess.sup-of-primordial-flesh",
        "frame.class.autocrat.handlers-special-girl",
        "frame.class.legion.modular-build",
        "frame.class.priestess.appearance-matrix",
    }
    with ledger.engine.connect() as c:
        assert "frame.class.autocrat.clone-am" not in swap_rules.retained_rules(
            canon, current_ref(canon, 2), profiles(c, ledger.campaign_id), swap._registry()
        )
    (link,) = rules.links(canon)
    forged = type(canon).model_validate_json(canon.model_dump_json())
    changed = link.model_copy(update=dict(event="SYNTHETIC_FAKE_SWAP_EVENT"))
    forged.facts = [
        dict(x, body=changed.model_dump_json()) if x.get("kind") == "class_rule_retained" else x
        for x in forged.facts
    ]
    assert not classes.eligible(forged, paid)
    with ledger.engine.connect() as c, pytest.raises(ValueError, match="retention chain"):
        proof(game, c, forged, paid)
    missing = type(canon).model_validate_json(canon.model_dump_json())
    missing.requisitions = [x for x in missing.requisitions if x.id != link.swap]
    assert not classes.eligible(missing, paid)
    assert not production.entry("frame.enforcer.enforcement-initiative").verified
