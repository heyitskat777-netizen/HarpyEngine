"""Mixed Home possessions and actual new comforts survive paid delivery and real use."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_home import rescue_guest
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_succubus import restore, suspend
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_frame_swap import configure, open_plan
from girlframe.discord_adapter.m3_home import open_effect, open_home
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine import m3_home as rules
from girlframe.engine import m3_home_objects as hardware
from girlframe.engine.m2 import Obligation, TagState
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frame_swap_state import SwapReceipt
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_home import HomeService, prepare_transfer, prove_prepared
from girlframe.services.onboarding import WorkflowError

ITEMS = ("book", "napping", "bottle")
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
        trigger="SYNTHETIC retained Home same possessions and prepared structural comforts",
        actor_type="Original Pilot with exact native/graft acquisition and4P Swap",
        pre_roll_sources=["Original installation and true paid newFrame preparation"],
        roll_kind="diceless",
        allowed_modifiers=["No new Assets, action or roll from Home use"],
        tier_options={"normal": ["Same-frame Bond and owned Tag rejection"]},
        choice_ownership="Actual original owner and same-Frame co-occupant",
        target_policy="Original owner and current replacement Frame only",
        post_roll_effects=["Canonical Bond/Tag changes, same objects and new realizations"],
        mandatory_followups=["Actual player/Handler response and chat restoration"],
        handler_or_gm_intervention="Actual printed Handler outcome authority",
        test_fixture_ids=["tests/rules/test_retained_home.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_home.py"],
            )
            if not entry.get("contract"):
                entry["contract"] = contract
    candidate = Registry.model_validate_json(json.dumps(raw))
    assert {x.id for x in candidate.entries if x != production.entry(x.id)} == NEEDED
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
    return production, candidate


def prepared(store, tmp_path, monkeypatch):
    _, game = service(store, girl="ALPHA", frame="WYVERN 0.4")
    production, registry = synthetic_registry()
    path = tmp_path / "SYNTHETIC-only-five-retained-home-sources.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    registry_sha256=digest(registry),
                    subsystems=store.policy.m3_approval.subsystems | {"economy", "plays", "world"},
                )
            ),
            owner_m3_rulings=store.policy.owner_m3_rulings.model_copy(
                update=dict(
                    privilege_restoration="inflictor_condition_owner_restores",
                    beneath_private_choices="affected_owner",
                )
            ),
        )
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3)
        actor, other = current_ref(canon, 2), current_ref(canon, 3)
        canon = set_depth(canon, actor, other, 0, str(uuid4()))
        canon.order = (3, 2)
        sheet = canon.sheets["2"]
        sheet.permissions = 10
        sheet.identities[0].marked = True
        sheet.tags.append(
            TagState(
                id="actual-home-tag",
                label="Actual unwanted Tag",
                giver=3,
                giver_actor=other,
                giver_character=other.incarnation,
                observers=(2, 3),
                marked=True,
                rejection_pending=True,
            )
        )
        canon.obligations.append(
            Obligation(
                id="actual-home-rejection",
                kind="reject_tag",
                owner=2,
                action="actual-prior-tag",
                details={"tag": "actual-home-tag"},
            )
        )
        kept = next(x for x in sheet.assets if x.family == "frame" and x.intrinsic is None)
        kept.damaged = kept.void = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_home_resources", canon)
    home = HomeService(game)
    offered = home.menu(PLAYER)

    async def purchase():
        own = current(2, 960001)
        await own.response.defer(ephemeral=True)
        await open_home(own, home)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "2 Permissions" in form.text()
        form.values.update(items=ITEMS, account="PRIVATE_ORIGINAL_MIXED_HOME")
        await form.confirm.callback(current(2, 960002))
        assert form.completed

    asyncio.run(purchase())
    original = state(game)
    actor = current_ref(original, 2)
    paid = rules.held(original, actor)
    assert paid and paid.price == 2
    assert (
        home.buy(
            PLAYER,
            "960002",
            offered["revision"],
            actor,
            offered["frame"],
            ITEMS,
            "PRIVATE_ORIGINAL_MIXED_HOME",
        )["id"]
        == paid.id
    )
    with store.engine.connect() as c:
        assert prepare_transfer(game, c, original, paid) == original
    swap = FrameSwapService(game, registry)
    plan = swap.create(PLAYER, str(uuid4()), "THE ENFORCER")["id"]

    async def configure_actual():
        own = current(2, 960003)
        await own.response.defer(ephemeral=True)
        await configure(own, swap, plan)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert (
            "2P" in dict(next(x for x in form.fields if x.key == "keep_rule").options)[rules.RULE]
        )
        form.values.update(
            keep_asset=(kept.id,),
            keep_rule=(rules.RULE,),
            assets=("0", "1"),
            first_description="Actual new Frame Asset",
            second_description="Second actual new Frame Asset",
            name="Actual replacement Enforcer",
            appearance="Actual new Frame",
            account="PRIVATE_MIXED_HOME_REINSTALLATION",
        )
        await form.confirm.callback(current(2, 960004))
        assert form.completed

    asyncio.run(configure_actual())
    data = swap.get(PLAYER, plan)
    no_confirmation = state(game)
    with pytest.raises(WorkflowError, match="Confirm.*Home"):
        swap.change(
            PLAYER,
            str(uuid4()),
            plan,
            data["revision"],
            purchase=True,
            expected=data["expected"],
            delivered=True,
        )
    assert state(game) == no_confirmation and game.dice.calls == 0

    async def pay_actual():
        own = current(2, 960005)
        await own.response.defer(ephemeral=True)
        await open_plan(own, swap, plan)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "home_reinstalled" in {x.key for x in form.fields}
        assert not await form.interaction_check(current(3))
        form.values.update(operation=("pay",), delivered=("yes",), home_reinstalled=("yes",))
        await form.confirm.callback(current(2, 960006))
        assert form.completed

    asyncio.run(pay_actual())
    assert swap.change(
        PLAYER,
        "960006",
        plan,
        data["revision"],
        purchase=True,
        expected=data["expected"],
        delivered=True,
        home_reinstalled=True,
    )["paid"]
    return game, home, paid, original, kept, production


def test_retained_home_mixed_preparation_native_effects_and_source_integrity(
    ledger, tmp_path, monkeypatch
):
    game, home, paid, original, kept, production = prepared(ledger, tmp_path, monkeypatch)
    canon = state(game)
    actor, other = paid.actor, current_ref(canon, 3)
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    old = hardware.prepared(original, paid)
    installed = hardware.prepared(canon, paid)
    (change,) = hardware.transfers(canon, paid)
    assert old.choices == installed.choices == ITEMS
    assert old.objects == installed.objects and {x.choice for x in installed.objects} == {
        "book",
        "bottle",
    }
    assert installed.frame == swap.new_frame != old.frame
    assert installed.purchase == paid.id and change.confirmed_by == 2
    assert change.event == swap.source_event and change.confirmed
    assert {x.id for x in old.realizations}.isdisjoint({x.id for x in installed.realizations})
    for fixture in installed.realizations:
        previous = next(x for x in old.realizations if x.choice == fixture.choice)
        assert fixture.prior_realization == previous.id and fixture.frame == swap.new_frame
        assert fixture.event == swap.source_event
    bottle = next(x for x in installed.objects if x.choice == "bottle")
    vent = next(x for x in installed.realizations if x.choice == "bottle")
    assert vent.object_ids == (bottle.id,)
    assert rules.installed(canon, paid) == rules.installed(original, paid)
    assert canon.sheets["2"].permissions == 4
    assert canon.sheets["2"].identities == original.sheets["2"].identities
    assert canon.sheets["2"].tags == original.sheets["2"].tags
    assert canon.sheets["3"] == original.sheets["3"]
    assert next(x for x in canon.sheets["2"].assets if x.id == kept.id) == kept
    assert {x.id for x in original.sheets["2"].assets if x.family == "frame"} & {
        x.id for x in canon.sheets["2"].assets if x.family == "frame"
    } == {kept.id}
    assert len([x for x in canon.sheets["2"].assets if x.family == "frame"]) == 3
    with ledger.engine.connect() as c:
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
        assert prove_prepared(game, c, canon, paid) == installed
    assert home.menu(OTHER)["items"] == [] and home.menu(OTHER)["prepared"] is None
    menu = home.menu(PLAYER)
    with pytest.raises(WorkflowError, match="instead of buying twice"):
        home.buy(
            PLAYER,
            str(uuid4()),
            menu["revision"],
            actor,
            menu["frame"],
            ITEMS,
            "No new installation",
            "WYVERN 0.4",
        )
    assert state(game) == canon
    gate = suspend(game, swap.id)
    suspended = state(game)
    assert home.menu(PLAYER)["suspended"] and home.menu(PLAYER)["items"] == list(ITEMS)
    assert hardware.prepared(suspended, paid) == installed and rules.held(suspended, actor) is None
    restore(game, gate)
    restored = state(game)
    assert rules.held(restored, actor) == paid and hardware.prepared(restored, paid) == installed
    assert restored.sheets == suspended.sheets
    missing = restored.model_copy(deep=True)
    missing.facts = [x for x in missing.facts if x.get("kind") != hardware.KIND]
    with pytest.raises(ValueError, match="reinstallation"):
        hardware.prepared(missing, paid)
    forged = restored.model_copy(deep=True)
    wrong = change.model_copy(update=dict(confirmed_by=3))
    forged.facts = [
        dict(x, body=wrong.model_dump_json()) if x.get("kind") == hardware.KIND else x
        for x in forged.facts
    ]
    with ledger.engine.connect() as c, pytest.raises(ValueError, match="same Home possessions"):
        prove_prepared(game, c, forged, paid)
    duplicate = restored.model_copy(deep=True)
    duplicate.facts.append(dict(kind=hardware.KIND, body=change.model_dump_json()))
    with pytest.raises(ValueError, match="One actual Home"):
        hardware.prepared(duplicate, paid)

    # Existing actual Defeat/rescue supplies both real original people in the new Home.
    rescue_guest(game)
    aboard = state(game)
    assert depth(aboard, actor, other) == 1
    co = home.menu(PLAYER)["others"][0]
    assert ActorRef.model_validate(co["actor"]) == other

    async def native_bond(item, interaction):
        own = current(2, interaction)
        await own.response.defer(ephemeral=True)
        await open_effect(own, home, "bond")
        form = own.edit_original_response.call_args.kwargs["view"]
        assert item in dict(next(x for x in form.fields if x.key == "item").options)
        form.values.update(other=("3",), item=(item,), account="Actual prepared Home use together")
        await form.confirm.callback(current(2, interaction + 1))
        assert form.completed

    calls = game.dice.calls
    asyncio.run(native_bond("napping", 960007))
    assert depth(state(game), actor, other) == 2
    fixture_use = next(x for x in reversed(state(game).facts) if x.get("kind") == "home_used")
    assert json.loads(fixture_use["object_ids"]) == []
    assert json.loads(fixture_use["realization_ids"]) == [
        next(x.id for x in installed.realizations if x.choice == "napping")
    ]
    before_book = state(game)
    asyncio.run(native_bond("book", 960009))
    used = state(game)
    assert used.sheets["2"].heat == before_book.sheets["2"].heat + 2
    assert used.sheets["3"].heat == before_book.sheets["3"].heat + 2
    object_use = next(x for x in reversed(used.facts) if x.get("kind") == "home_used")
    assert json.loads(object_use["object_ids"]) == [
        next(x.id for x in installed.objects if x.choice == "book")
    ]
    assert json.loads(object_use["realization_ids"]) == []
    menu = home.menu(PLAYER)
    co = menu["others"][0]
    args = (PLAYER, "actual-retained-home-rejection", menu["revision"], other, co["physical"])
    kwargs = dict(
        operation="reject",
        account="Actual owner rejects this Tag without taking another action",
        tag="actual-home-tag",
    )
    result = home.use(*args, **kwargs)
    assert home.use(*args, **kwargs) == result
    final = state(game)
    assert not any(x.id == "actual-home-tag" for x in final.sheets["2"].tags)
    assert (
        next(x for x in final.obligations if x.id == "actual-home-rejection").state == "fulfilled"
    )
    assert hardware.prepared(final, paid) == installed and final.sheets["2"].permissions == 4
    assert final.placements == aboard.placements and game.dice.calls == calls
    assert final.requisitions == canon.requisitions
    assert next(x for x in final.requisitions if x.id == paid.id) == paid
    with ledger.engine.connect() as c:
        assert prove_prepared(game, c, final, paid) == installed
        visible = str(list(c.scalars(sa.select(t.events.c.payload_json)))) + str(
            list(c.scalars(sa.select(t.m2["m2_outbox"].c.body_json)))
        )
        assert "PRIVATE_" not in visible
        assert all(dict(rules.ITEMS)[item] not in visible for item in ITEMS)
    assert game.rebuild() > 0 and state(game) == final
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
