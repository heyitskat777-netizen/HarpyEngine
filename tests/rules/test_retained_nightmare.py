"""Exact original Nightmare acquisition survives paid Swap and completes real Keep."""

import asyncio
import copy
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
from girlframe.discord_adapter.m2_receipt_text import expression
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.discord_adapter.m3_nightmare import open_purchase
from girlframe.engine import m3_class_retention as retention
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine import m3_nightmare as rules
from girlframe.engine import m3_privileges as privileges
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.m3_punishments import Details
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_nightmare import NightmareService, pre_roll
from girlframe.services.m3_privileges import PrivilegeService
from girlframe.services.m3_punishments import PunishmentService
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
        trigger="SYNTHETIC retained Nightmare actual Keep on paid replacement Frame",
        actor_type="Original Pilot with exact native/graft acquisition and4P Swap",
        pre_roll_sources=["Current paid chain and effective owned Void Assets"],
        roll_kind="2d6",
        allowed_modifiers=["Actual owned Void instead of Heat; zero Heat spent"],
        tier_options={"normal": ["Actual ordinary Keep plus established terrifying"]},
        choice_ownership="Original player trait choice and actual Handler enough ruling",
        target_policy="Original owner and current replacement Frame only",
        post_roll_effects=["Real saved receipt and normal owned Keep result"],
        mandatory_followups=["Actual player/Handler response and chat restoration"],
        handler_or_gm_intervention="Actual printed Handler outcome authority",
        test_fixture_ids=["tests/rules/test_retained_nightmare.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_nightmare.py"],
            )
            if not entry.get("contract"):
                entry["contract"] = contract
    candidate = Registry.model_validate_json(json.dumps(raw))
    assert {x.id for x in candidate.entries if x != production.entry(x.id)} == NEEDED
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
    return production, candidate


def prepared(store, tmp_path, monkeypatch):
    _, game = service(store, girl="ALPHA", frame="CONSUME")
    production, registry = synthetic_registry()
    path = tmp_path / "SYNTHETIC-only-five-retained-nightmare-sources.json"
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
                update=dict(privilege_restoration="inflictor_condition_owner_restores")
            ),
        )
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3)
        actual.order = (3, 2)
        sheet = actual.sheets["2"]
        sheet.permissions, sheet.heat = 10, 5
        sheet.identities[0].marked = True
        sheet.tags.append(
            TagState(id="PRIVATE_NIGHTMARE_TAG", label="PRIVATE_NIGHTMARE_MEMORY", giver=2)
        )
        next(x for x in sheet.assets if x.family == "girl").void = True
        kept = next(x for x in sheet.assets if x.family == "frame" and x.intrinsic is None)
        kept.void = True
        game.event(c, 2, str(uuid4()), "synthetic.actual_original_nightmare_resources", actual)
    source = NightmareService(game)
    offered = source.menu(PLAYER)

    async def purchase():
        own = current(2, 954001)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "2 Permissions" in form.text()
        form.values.update(account="PRIVATE_ORIGINAL_NIGHTMARE_SOURCE")
        await form.confirm.callback(current(2, 954002))
        assert form.completed

    asyncio.run(purchase())
    original = state(game)
    actor = current_ref(original, 2)
    paid = rules.held(original, actor)
    assert paid and paid.price == 2 and paid.frame == "CONSUME"
    assert (
        source.buy(
            PLAYER,
            "954002",
            offered["revision"],
            actor,
            offered["frame"],
            "PRIVATE_ORIGINAL_NIGHTMARE_SOURCE",
        )["id"]
        == paid.id
    )
    swap = FrameSwapService(game, registry)
    plan = swap.create(PLAYER, str(uuid4()), "THE ENFORCER")["id"]
    data = swap.get(PLAYER, plan)
    assert next(x for x in data["class_sources"] if x["rule"] == rules.RULE)["receipt"] == paid.id
    selection = Selection(
        frame="THE ENFORCER",
        name="Actual replacement Enforcer",
        appearance="Actual new Frame",
        assets=tuple(AssetChoice(name=x, description="Actual " + x) for x in data["starting"][:2]),
        retained_asset=kept.id,
        retained_rule=rules.RULE,
        retained_receipt=paid.id,
        account="PRIVATE_NIGHTMARE_SWAP",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=selection)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    return game, source, paid, original, production


def test_retained_nightmare_paid_swap_real_keep_and_original_source_restore(
    ledger, tmp_path, monkeypatch
):
    game, source, paid, original, production = prepared(ledger, tmp_path, monkeypatch)
    canon = state(game)
    actor = current_ref(canon, 2)
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    assert rules.held(canon, actor) == paid and source.menu(PLAYER)["owned"]
    assert canon.sheets["2"].permissions == 4 and canon.sheets["2"].heat == 5
    assert canon.sheets["2"].tags == original.sheets["2"].tags
    assert canon.sheets["2"].identities == original.sheets["2"].identities
    assert canon.sheets["3"] == original.sheets["3"]
    assert sum(x.void for x in canon.sheets["2"].assets) == 2
    assert next(x for x in canon.requisitions if x.id == paid.id) == paid
    with ledger.engine.connect() as c:
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="instead of buying twice"):
        source.buy(
            PLAYER, str(uuid4()), menu["revision"], actor, menu["frame"], "No rebuy", "CONSUME"
        )
    assert state(game) == canon and game.dice.calls == 0

    async def native_keep():
        own = current(2, 954003)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_play(own, game)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "Nightmare Core" in form.text()
        assert "Nightmare Keep uses 0" in next(x for x in form.fields if x.key == "heat").label
        form.values.update(
            play=("keep_your_head",),
            heat=("0",),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="Actual retained source keeps my head on the replacement Frame",
        )
        await form.confirm.callback(current(2, 954004))
        assert form.completed

    asyncio.run(native_keep())
    assert game.dice.calls == 0 and state(game).sheets == canon.sheets
    with ledger.engine.connect() as c:
        action = game.lock(c, 900)["action_id"]
        begun = game.action(c, action)
        meta = begun["data"]["nightmare_core"]
        assert (
            meta["frame"] == swap.new_frame != paid.frame_instance and meta["purchase"] == paid.id
        )
        forged_action = copy.deepcopy(begun)
        forged_action["data"]["nightmare_core"]["frame"] = paid.frame_instance
        with pytest.raises(WorkflowError, match="paid Frame"):
            pre_roll(game, c, PLAYER, state(game), forged_action)
    game.dice.faces = (3, 3)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    raw = copy.deepcopy(game.inspect(PLAYER, action)["receipt"])
    assert raw["heat"] == 0 and raw["base_modifier"] == 2 and raw["pre_total"] == 8
    assert raw["nightmare_purchase"] == paid.id and game.dice.calls == 1
    assert "2 Void Assets (Nightmare Core) (no Heat spent)" in expression(raw)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="Actual Handler accepts terrifying and rules this enough",
    )
    final = game.inspect(PLAYER, action)
    assert final["state"] == "complete" and final["receipt"] == raw
    assert set(final["result"]["positive"]) == {"terrifying", "tough", "in_control", "vicious"}
    assert final["result"]["negative"] == ["desperate"] and final["result"]["enough"]
    tick(worker, gateway, 5)
    completed = state(game)
    assert completed.sheets["2"].heat == 5 and completed.sheets["2"].permissions == 4
    assert completed.sheets["2"].identities == canon.sheets["2"].identities
    assert completed.sheets["2"].assets == canon.sheets["2"].assets
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"

    # Actual mission failure provides ordinary owned Punishment; the original source survives it.
    missions = MissionService(ledger)
    offered = missions.offer(ADMIN, str(uuid4()), "SYNTHETIC real mission source", (2, 3))
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
    args = (
        ADMIN,
        str(uuid4()),
        work["id"],
        view["revision"],
        view["game_revision"],
        Details(
            kind="revoked_privileges",
            requisition=paid.id,
            restoration="Actual original Handler condition",
        ),
    )
    outcome = punish.apply(*args)
    assert punish.apply(*args) == outcome
    suspended = state(game)
    gate = next(x for x in suspended.obligations if x.kind == privileges.KIND)
    assert gate.details["frame"] == swap.new_frame
    assert gate.details["nightmare_receipt"] == paid.model_dump_json()
    assert gate.details["implemented_class_receipt"] == paid.model_dump_json()
    assert rules.held(suspended, actor) is None and source.menu(PLAYER)["suspended"]
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="instead of buying twice"):
        source.buy(
            PLAYER,
            str(uuid4()),
            menu["revision"],
            actor,
            menu["frame"],
            "No suspended rebuy",
            "CONSUME",
        )
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            suspended.sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="Cannot use suspended zero-Heat source",
                trigger_confirmed=True,
            ),
        )
    assert state(game) == suspended and game.dice.calls == 1
    restoration = PrivilegeService(ledger)
    forged_source = suspended.model_copy(deep=True)
    fake_swap = swap.model_copy(update=dict(source_event="SYNTHETIC_MISSING_PAID_SOURCE"))
    forged_source.requisitions = [
        fake_swap if x.id == swap.id else x for x in forged_source.requisitions
    ]
    link = retention.links(forged_source)[0]
    forged_source.facts = [
        dict(x, body=link.model_copy(update=dict(event=fake_swap.source_event)).model_dump_json())
        if x.get("kind") == "class_rule_retained"
        else x
        for x in forged_source.facts
    ]
    with (
        ledger.engine.connect() as c,
        pytest.raises(WorkflowError, match="SOURCE_REQUISITION_MISSING"),
    ):
        restoration._current(c, forged_source, gate)
    restore_choice(restoration, ADMIN, gate.id, allow=True)
    restore_choice(restoration, PLAYER, gate.id, allow=False)
    restored = state(game)
    assert rules.held(restored, actor) == paid and not source.menu(PLAYER)["suspended"]
    assert restored.sheets == suspended.sheets and restored.requisitions == suspended.requisitions

    isolated = privileges.revoke(
        restored,
        2,
        1,
        swap.id,
        "Source condition",
        "SYNTHETIC_SWAP_GATE",
        "SYNTHETIC_UNIT_SOURCE",
        {2: actor.incarnation},
    )
    assert rules.held(isolated, actor) is None
    assert paid.id not in {x.id for x in privileges.available(isolated, 2, actor.incarnation)}
    isolated.obligations[-1].details["restoration_allowed"] = "true"
    isolated = privileges.restore(isolated, "SYNTHETIC_SWAP_GATE", actor.incarnation, None)
    assert rules.held(isolated, actor) == paid and isolated.sheets == restored.sheets
    forged = restored.model_copy(deep=True)
    link = retention.links(forged)[0]
    forged.facts = [
        dict(x, body=link.model_copy(update=dict(event="SYNTHETIC_FORGED_EVENT")).model_dump_json())
        if x.get("kind") == "class_rule_retained"
        else x
        for x in forged.facts
    ]
    assert rules.held(forged, actor) is None
    with ledger.engine.connect() as c, pytest.raises(ValueError, match="retention chain"):
        proof(game, c, forged, paid)
    assert game.rebuild() > 0 and state(game) == restored and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
