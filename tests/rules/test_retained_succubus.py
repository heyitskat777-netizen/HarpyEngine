"""Exact paid retained source → scoped original-person Order → actual refusal completion."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_succubus import restore, suspend
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_succubus import open_succubus
from girlframe.engine import m3_class_retention as retention
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine import m3_succubus as rules
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import PlayInput, TagState, higher
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_succubus import SuccubusService
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
        trigger="SYNTHETIC retained Succubus exact bonded-target Order",
        actor_type="Original issuer/recipient with exact paid Class acquisition and4P Swap",
        pre_roll_sources=["Actual personal Bond, original source and current replacement Frame"],
        roll_kind="diceless",
        allowed_modifiers=["Real recipient Disobey uses its own existing printed resources"],
        tier_options={"normal": ["Actual direct Order and recipient-owned refusal"]},
        choice_ownership="Original recipient/Handler retain actual response ownership",
        target_policy="Actual qualifying original Girl or bonded ordinary NPC only",
        post_roll_effects=["Real Order/refusal completion without ordinary Status change"],
        mandatory_followups=["Actual refusal result, original Handler response, chat restoration"],
        handler_or_gm_intervention="Actual source only",
        test_fixture_ids=["tests/rules/test_retained_succubus.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_succubus.py"],
            )
            if not entry.get("contract"):
                entry["contract"] = contract
    candidate = Registry.model_validate_json(json.dumps(raw))
    assert {x.id for x in candidate.entries if x != production.entry(x.id)} == NEEDED
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
    return production, candidate


def prepared(store, tmp_path, monkeypatch):
    _, game = service(store, girl="ALPHA", frame="THE RED QUEEN")
    production, registry = synthetic_registry()
    path = tmp_path / "SYNTHETIC-only-five-retained-succubus-sources.json"
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
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3)
        canon.order = (3, 2)
        sheet = canon.sheets["2"]
        sheet.permissions, sheet.heat = 10, 3
        sheet.identities[0].marked = True
        sheet.tags.append(
            TagState(
                id="original-marked-succubus-tag",
                label="PRIVATE_SUCCUBUS_TAG",
                giver=2,
                marked=True,
            )
        )
        kept = next(x for x in sheet.assets if x.family == "frame" and x.intrinsic is None)
        kept.damaged = kept.void = True
        canon = set_depth(canon, current_ref(canon, 2), current_ref(canon, 3), 2, str(uuid4()))
        game.event(c, 2, str(uuid4()), "synthetic.actual_original_succubus_resources", canon)
    source = SuccubusService(game)

    async def purchase():
        own = current(2, 953001)
        await own.response.defer(ephemeral=True)
        await open_succubus(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and "2 Permissions" in form.text()
        form.values.update(account="PRIVATE_ORIGINAL_SUCCUBUS_SOURCE")
        await form.confirm.callback(current(2, 953002))
        assert form.completed

    asyncio.run(purchase())
    original = state(game)
    actor = current_ref(original, 2)
    paid = rules.held(original, actor)
    assert paid and paid.price == 2 and paid.frame == "THE RED QUEEN"
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
        account="PRIVATE_SUCCUBUS_SWAP",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=selection)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    return game, source, paid, original, production


def test_retained_succubus_real_scoped_order_refusal_source_suspension_and_immutable_chain(
    ledger, tmp_path, monkeypatch
):
    game, source, paid, original, production = prepared(ledger, tmp_path, monkeypatch)
    canon = state(game)
    actor, target = current_ref(canon, 2), current_ref(canon, 3)
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    assert canon.sheets["2"].permissions == 4 and canon.sheets["2"].heat == 3
    assert canon.order == original.order == (3, 2) and not higher(canon, 2, 3)
    assert canon.sheets["2"].tags == original.sheets["2"].tags
    assert canon.sheets["2"].identities == original.sheets["2"].identities
    assert next(x for x in canon.requisitions if x.id == paid.id) == paid
    assert rules.authority(canon, actor, target).frame == swap.new_frame != paid.frame_instance
    with ledger.engine.connect() as c:
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="Restore"):
        source.buy(PLAYER, str(uuid4()), menu["revision"], actor, menu["frame"], "No rebuy")
    assert state(game) == canon
    # Suspend the actual4P chain source; original purchase alone cannot bypass it.
    gate = suspend(game, swap.id)
    suspended = state(game)
    assert rules.held(suspended, actor) is None and source.menu(PLAYER)["suspended"]
    with pytest.raises(WorkflowError, match="active Succubus"):
        game.issue_order(PLAYER, str(uuid4()), 900, 3, "Unavailable source cannot grant authority")
    assert state(game) == suspended and game.dice.calls == 0
    restore(game, gate)
    restored = state(game)
    assert rules.held(restored, actor) == paid and not source.menu(PLAYER)["suspended"]
    assert restored.sheets["2"].tags == canon.sheets["2"].tags
    assert restored.sheets["2"].identities == canon.sheets["2"].identities
    with ledger.transaction() as c:
        personal = set_depth(restored, actor, target, 1, str(uuid4()))
        game.event(c, 2, str(uuid4()), "synthetic.actual_weakened_personal_bond", personal)
    before_denial = state(game)
    with pytest.raises(WorkflowError, match="Intense Bond"):
        game.issue_order(PLAYER, str(uuid4()), 900, 3, "A Personal Bond is insufficient")
    assert state(game) == before_denial and game.dice.calls == 0
    with ledger.transaction() as c:
        intense = set_depth(state(game), actor, target, 2, str(uuid4()))
        game.event(c, 2, str(uuid4()), "synthetic.actual_restored_intense_bond", intense)
    args = (PLAYER, "actual-retained-scoped-order", 900, 3, "Stand with me now")
    issued = game.issue_order(*args)
    assert game.issue_order(*args) == issued
    with ledger.engine.connect() as c:
        body = json.loads(
            c.scalar(
                sa.select(t.m2["m2_orders"].c.body_json).where(
                    t.m2["m2_orders"].c.campaign_id == ledger.campaign_id,
                    t.m2["m2_orders"].c.id == issued["order_id"],
                )
            )
        )
    authority = rules.Authority.model_validate(body["succubus"])
    assert authority == rules.authority(state(game), actor, target)
    assert (
        authority.purchase == paid.id
        and authority.event == paid.source_event
        and authority.frame == swap.new_frame
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)

    async def native_answer(viewer, kind, identity, **values):
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        own = current(viewer.user_id, identity)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        if viewer == OTHER:
            assert not await form.interaction_check(current(2, identity + 1))
        form.values.update(**values)
        response = current(viewer.user_id, identity + 2)
        await form.confirm.callback(response)
        assert form.completed, str(response.edit_original_response.call_args)

    asyncio.run(native_answer(OTHER, "order_response", 953010, options=("disobey",)))
    game.dice.faces = (6, 6)
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="disobey_orders",
            order_id=issued["order_id"],
            parent=issued["action_id"],
            context="I actually refuse this original source Order",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(OTHER, child)["receipt"]
    assert game.dice.calls == 1 and receipt["pre_total"] == 12
    asyncio.run(native_answer(OTHER, "actor_disobey", 953020, flag=("yes",)))
    asyncio.run(native_answer(ADMIN, "handler_disobey", 953030, flag=("no",)))
    final = state(game)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(OTHER, child)["receipt"] == receipt and game.dice.calls == 1
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"
    assert final.order == original.order and not higher(final, 2, 3)
    assert final.sheets["2"] == restored.sheets["2"]
    assert final.sheets["3"].revision > original.sheets["3"].revision
    assert final.sheets["3"].heat == original.sheets["3"].heat + 2
    assert final.sheets["3"].model_dump(exclude={"revision", "heat"}) == original.sheets[
        "3"
    ].model_dump(exclude={"revision", "heat"})
    assert (
        rules.held(final, actor) == paid
        and next(x for x in final.requisitions if x.id == paid.id) == paid
    )
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    forged = final.model_copy(deep=True)
    link = retention.links(forged)[0]
    wrong = link.model_copy(update=dict(event="SYNTHETIC_FORGED_SWAP"))
    forged.facts = [
        dict(x, body=wrong.model_dump_json()) if x.get("kind") == "class_rule_retained" else x
        for x in forged.facts
    ]
    with ledger.engine.connect() as c, pytest.raises(ValueError, match="retention chain"):
        proof(game, c, forged, paid)
    assert game.rebuild() > 0 and state(game) == final
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
