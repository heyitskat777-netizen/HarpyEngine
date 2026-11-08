"""Narrow synthetic source release: original paid rule → Swap → actual Engage costs."""

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
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_untouchable import open_purchase
from girlframe.engine import m3_class_grafts as classes
from girlframe.engine import m3_class_retention as retention
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine import m3_privileges as privileges
from girlframe.engine import m3_untouchable as rules
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
from girlframe.services.m3_privileges import PrivilegeService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_untouchable import UntouchableService, entitlement, tags
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
        trigger="SYNTHETIC retained Untouchable actual Engage damage",
        actor_type="Original Pilot with actual original paid Class and4P Swap chain",
        pre_roll_sources=["Actual new Frame, usable owned Assets and genuine unmarked own Tag"],
        roll_kind="2d6",
        allowed_modifiers=["Ordinary genuine Engage Heat and sources only"],
        tier_options={"normal": ["Mark real own Tag instead of actual Engage Asset damage"]},
        choice_ownership="Original acting human owns actual maneuver and Tag",
        target_policy="Actual native opposing Pilot",
        post_roll_effects=["Actual maneuver, Tag mark, unchanged Asset and real completion"],
        mandatory_followups=["Actual results and restoration of scene chat"],
        handler_or_gm_intervention="Actual source only",
        test_fixture_ids=["tests/rules/test_retained_untouchable.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_untouchable.py"],
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
    path = tmp_path / "SYNTHETIC-only-five-retained-untouchable-sources.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    registry_sha256=digest(registry),
                    subsystems=store.policy.m3_approval.subsystems | {"economy", "plays", "world"},
                ),
            ),
            owner_m3_rulings=store.policy.owner_m3_rulings.model_copy(
                update=dict(privilege_restoration="inflictor_condition_owner_restores")
            ),
        )
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3)
        sheet = canon.sheets["2"]
        sheet.permissions, sheet.heat = 10, 3
        sheet.identities[0].marked = True
        sheet.tags.extend(
            TagState(id=identity, label="PRIVATE_" + identity, giver=2, marked=marked)
            for identity, marked in (
                ("original-marked", True),
                ("first-own", False),
                ("second-own", False),
            )
        )
        kept = next(x for x in sheet.assets if x.family == "frame" and x.intrinsic is None)
        kept.damaged = kept.void = True
        game.event(c, 2, str(uuid4()), "synthetic.actual_original_untouchable_resources", canon)
    source = UntouchableService(game)

    async def purchase():
        own = current(2, 950001)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and "2 Permissions" in form.text()
        form.values.update(account="PRIVATE_ORIGINAL_UNTOUCHABLE")
        await form.confirm.callback(current(2, 950002))
        assert form.completed

    asyncio.run(purchase())
    original = state(game)
    paid = rules.held(original, current_ref(original, 2))
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
        account="PRIVATE_UNTOUCHABLE_SWAP",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=selection)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    return game, source, paid, original, production


def engage(game, worker, gateway, tag, *, repeated=None):
    before = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="engage",
            heat=0,
            target_actor=current_ref(before, 3),
            context="Actual maneuver through the replacement Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["pre_total"] == 3
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.damaged)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "engage_maneuvers")
    if repeated:
        saved = state(game)
        with pytest.raises(WorkflowError, match="currently unmarked"):
            answer(
                game,
                PLAYER,
                "engage_maneuvers",
                options=("cover",),
                fields={"cover": asset.id, "untouchable_tag": repeated},
                text="Already marked Tag cannot pay this actual cost twice",
            )
        assert state(game) == saved and game.inspect(PLAYER, action)["receipt"] == receipt

    async def respond_native():
        own = current(2, 951000 + game.dice.calls * 2)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(3, 951100 + game.dice.calls))
        offered = dict(next(x for x in form.fields if x.key == "untouchable_tag").options)
        assert tag in offered and "original-marked" not in offered
        if repeated:
            assert repeated not in offered
        form.values.update(
            maneuvers=("cover",),
            asset_cover=(asset.id,),
            untouchable_tag=(tag,),
            text="My actual new Frame capability creates cover",
        )
        current_id = 951001 + game.dice.calls * 2
        await form.confirm.callback(current(2, current_id))
        assert form.completed
        saved = state(game)
        await form.confirm.callback(current(2, current_id))
        assert state(game) == saved

    asyncio.run(respond_native())
    result = game.inspect(PLAYER, action)
    assert result["state"] == "complete" and result["receipt"] == receipt
    assert result["result"]["damaged"] == [] and result["result"]["untouchable_tag"] == tag
    assert state(game).sheets["2"].assets == before.sheets["2"].assets
    tick(worker, gateway, 4)
    return action


def test_retained_paid_untouchable_actual_engage_repeat_mark_source_restore_and_production_gate(
    ledger, tmp_path, monkeypatch
):
    game, source, paid, original, production = prepared(ledger, tmp_path, monkeypatch)
    canon = state(game)
    actor = current_ref(canon, 2)
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    assert canon.sheets["2"].permissions == 4 and canon.sheets["2"].heat == 3
    assert canon.sheets["2"].tags == original.sheets["2"].tags
    assert canon.sheets["2"].identities == original.sheets["2"].identities
    assert canon.sheets["2"].frame_runtime.court == {}
    assert canon.sheets["2"].frame_runtime.acquired_rules == (rules.RULE,)
    assert next(x for x in canon.requisitions if x.id == paid.id) == paid
    assert rules.held(canon, actor) == paid and swap.selection.retained_receipt == paid.id
    with ledger.engine.connect() as c:
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="Restore"):
        source.buy(PLAYER, str(uuid4()), menu["revision"], actor, menu["frame"], "No free rebuy")
    assert state(game) == canon
    game.dice.faces = (1, 2)
    worker, gateway = GameWorker(game), Gateway()
    first = engage(game, worker, gateway, "first-own")
    assert game.dice.calls == 1 and state(game).sheets["2"].permissions == 4
    missions = MissionService(ledger)
    offered = missions.offer(ADMIN, str(uuid4()), "Actual ordinary discipline source", (2, 3))
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
            restoration="Actual original retained Untouchable condition",
        ),
    )
    suspended = state(game)
    assert rules.held(suspended, actor) is None and source.menu(PLAYER)["suspended"]
    with ledger.engine.connect() as c:
        assert (
            entitlement(game, c, suspended, actor) is None and tags(game, c, suspended, actor) == []
        )
    gate = next(x for x in suspended.obligations if x.kind == privileges.KIND)
    privilege = PrivilegeService(ledger)
    restore_choice(privilege, ADMIN, gate.id, allow=True)
    restore_choice(privilege, PLAYER, gate.id, allow=False)
    restored = state(game)
    assert (
        rules.held(restored, actor) == paid
        and restored.sheets["2"].tags == suspended.sheets["2"].tags
        and restored.sheets["2"].permissions == suspended.sheets["2"].permissions == 6
    )
    second = engage(game, worker, gateway, "second-own", repeated="first-own")
    final = state(game)
    assert (
        game.dice.calls == 2 and final.sheets["2"].permissions == 6 and final.sheets["2"].heat == 3
    )
    facts = [x for x in final.facts if x.get("kind") == "untouchable_frame_used"]
    assert {x["action"] for x in facts} == {first, second}
    assert all(x["frame"] == swap.new_frame and x["receipt"] == paid.id for x in facts)
    forged = final.model_copy(deep=True)
    link = retention.links(forged)[0]
    wrong = link.model_copy(update=dict(event="SYNTHETIC_FORGED_SWAP"))
    forged.facts = [
        dict(x, body=wrong.model_dump_json()) if x.get("kind") == "class_rule_retained" else x
        for x in forged.facts
    ]
    assert not classes.eligible(forged, paid)
    with ledger.engine.connect() as c:
        assert entitlement(game, c, forged, actor) is None
        with pytest.raises(ValueError, match="retention chain"):
            proof(game, c, forged, paid)
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert game.rebuild() > 0 and state(game) == final
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
