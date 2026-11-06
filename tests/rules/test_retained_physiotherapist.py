"""Original accepted NPC relationship survives paid Swap and real Off-Duty treatment."""

import asyncio
import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_strain_effect_service
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_off_duty_cycle import prepared as prepared_period
from test_physical_operations import place
from test_privileges import change as restore_choice
from test_strain_service import ready as strain_ready

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_physiotherapist import open_purchase, open_request
from girlframe.engine import m3_class_retention as retention
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine import m3_physiotherapist as rules
from girlframe.engine import m3_privileges as privileges
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_world_state import Npc
from girlframe.engine.rules_registry import Registry
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_physiotherapist import PhysiotherapistService
from girlframe.services.m3_privileges import PrivilegeService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_world import WorldService
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
        trigger="SYNTHETIC retained Physiotherapist actual NPC therapy on paid replacement Frame",
        actor_type="Original Pilot with exact native/graft acquisition and4P Swap",
        pre_roll_sources=["Current paid chain, original NPC and real Off-Duty scene"],
        roll_kind="diceless",
        allowed_modifiers=["Only eligible permanent Void removal; actual damage unchanged"],
        tier_options={"normal": ["Actual NPC-given Tag and nondestructive treatment"]},
        choice_ownership="Original patient chooses; actual NPC controller treats",
        target_policy="Original owner and current replacement Frame only",
        post_roll_effects=["Same Asset without Void, exact NPC Tag and closed treatment work"],
        mandatory_followups=["Actual NPC attendance and treatment response"],
        handler_or_gm_intervention="Actual printed Handler outcome authority",
        test_fixture_ids=["tests/rules/test_retained_physiotherapist.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_physiotherapist.py"],
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
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame="CONSUME"),
    )
    cycle, game, period = prepared_period(store)
    production, registry = synthetic_registry()
    path = tmp_path / "SYNTHETIC-only-five-retained-physiotherapist-sources.json"
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
                    beneath_private_choices="affected_owner",
                    privilege_restoration="inflictor_condition_owner_restores",
                )
            ),
        )
    )
    cycle.missions.access = Access(store)
    world = WorldService(cycle.missions)
    npc = ActorRef(kind="npc", entity="real-retained-physiotherapist")
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Actual original physiotherapist",
            jobs=("doctor",),
            detail="Knowledgeable about Void leakage",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    world.claim_npc(ADMIN, str(uuid4()), state(game).revision, npc.entity)
    with store.transaction() as c:
        actual = state(game)
        actual = place(place(actual, 2, mode="outside_frame"), 3)
        actual.order = (3, 2)
        sheet = actual.sheets["2"]
        sheet.permissions = 10
        sheet.identities[0].marked = True
        sheet.tags.append(
            TagState(id="PRIVATE_THERAPY_TAG", label="PRIVATE_ORIGINAL_THERAPY_MEMORY", giver=2)
        )
        target = next(x for x in sheet.assets if x.family == "girl")
        target.void = target.damaged = True
        original_asset = copy.deepcopy(target)
        kept = next(x for x in sheet.assets if x.family == "frame" and x.intrinsic is None)
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_therapy_resources", actual)
    source = PhysiotherapistService(game)
    offered = source.menu(PLAYER)

    async def acquire_and_accept():
        own = current(2, 958001)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "2 Permissions" in form.text()
        form.values.update(
            npc=(npc.entity,), account="PRIVATE_ORIGINAL_PHYSIOTHERAPIST_RELATIONSHIP"
        )
        await form.confirm.callback(current(2, 958002))
        assert form.completed
        paid = rules.held(state(game), current_ref(state(game), 2))
        assert paid and depth(state(game), paid.actor, npc) == 0
        assert source.buy(
            PLAYER,
            "958002",
            offered["revision"],
            npc.entity,
            "PRIVATE_ORIGINAL_PHYSIOTHERAPIST_RELATIONSHIP",
        ) == {"id": paid.id, "cost": 2}
        controller = current(1, 958003)
        await controller.response.defer(ephemeral=True)
        await open_request(controller, source, paid.id)
        form = controller.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Actual NPC controller accepts original Bond and expertise")
        await form.confirm.callback(current(1, 958004))
        assert form.completed
        return paid

    paid = asyncio.run(acquire_and_accept())
    original = state(game)
    assert paid.price == 2 and depth(original, paid.actor, npc) == 1
    relationship = source.get(PLAYER, paid.id)["therapy"]
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
        account="PRIVATE_PHYSIOTHERAPIST_SWAP",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=selection)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    return (
        game,
        source,
        cycle,
        period,
        paid,
        npc,
        original,
        original_asset,
        relationship,
        production,
    )


def test_retained_physiotherapist_same_bond_real_off_duty_scene_treatment_and_restore(
    ledger, tmp_path, monkeypatch
):
    game, source, cycle, period, paid, npc, original, asset, relationship, production = prepared(
        ledger, tmp_path, monkeypatch
    )
    actor = paid.actor
    canon = state(game)
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    assert rules.held(canon, actor) == paid and source.menu(PLAYER)["owned"]
    assert canon.sheets["2"].permissions == 4
    assert canon.sheets["2"].tags == original.sheets["2"].tags
    assert canon.sheets["2"].identities == original.sheets["2"].identities
    assert canon.sheets["3"] == original.sheets["3"]
    assert source.get(PLAYER, paid.id)["therapy"] == relationship
    assert depth(canon, actor, npc) == 1
    assert next(x for x in canon.sheets["2"].assets if x.id == asset.id) == asset
    with ledger.engine.connect() as c:
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
    with pytest.raises(WorkflowError, match="original humans"):
        source.get(OTHER, paid.id)
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="rather than buy twice"):
        source.buy(
            PLAYER,
            str(uuid4()),
            menu["revision"],
            npc.entity,
            "No duplicate relationship",
            "CONSUME",
        )
    assert state(game) == canon
    activate(cycle, game, period)

    # A genuine social source produces the real owned revocation and trusted restoration.
    game.dice.faces = (6, 6)
    worker, gateway = GameWorker(game), Gateway()
    social = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=2,
            heat=0,
            piloting=True,
            context="Actual confrontation",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("tag", "punish"),
        fields={"tag": "Actual discipline"},
        text="Actual discipline",
    )
    work = game.decision(OTHER, game.choices(OTHER)[0]["id"])["body"]["work_id"]
    punish = PunishmentService(ledger)
    data = punish.get(OTHER, work)
    punish.apply(
        OTHER,
        str(uuid4()),
        work,
        data["revision"],
        data["game_revision"],
        Details(
            kind="revoked_privileges",
            requisition=paid.id,
            restoration="Actual original inflictor condition",
        ),
    )
    assert game.inspect(OTHER, social)["state"] == "complete"
    tick(worker, gateway, 5)
    suspended = state(game)
    assert rules.held(suspended, actor) is None and source.menu(PLAYER)["suspended"]
    assert (
        depth(suspended, actor, npc) == 1 and source.get(PLAYER, paid.id)["therapy"] == relationship
    )
    data = source.get(PLAYER, paid.id)
    with pytest.raises(WorkflowError, match="Restore.*original paid"):
        source.respond(
            PLAYER,
            str(uuid4()),
            paid.id,
            data["revision"],
            data["game_revision"],
            operation="scene",
            account="Cannot use suspended source",
            channel=900,
            location="base0",
            asset=asset.id,
        )
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="rather than buy twice"):
        source.buy(
            PLAYER, str(uuid4()), menu["revision"], npc.entity, "No suspended rebuy", "CONSUME"
        )
    assert state(game) == suspended
    gate = next(x for x in suspended.obligations if x.kind == privileges.KIND)
    assert gate.details["frame"] == swap.new_frame
    assert (
        gate.details["physiotherapist_receipt"]
        == gate.details["implemented_class_receipt"]
        == paid.model_dump_json()
    )
    restoration = PrivilegeService(ledger)
    restore_choice(restoration, OTHER, gate.id, allow=True)
    restore_choice(restoration, PLAYER, gate.id, allow=False)
    restored = state(game)
    assert restored.sheets == suspended.sheets and restored.requisitions == suspended.requisitions
    assert rules.held(restored, actor) == paid and depth(restored, actor, npc) == 1

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
    fake_swap = swap.model_copy(update=dict(source_event="SYNTHETIC_MISSING_PAID_SOURCE"))
    forged.requisitions = [fake_swap if x.id == swap.id else x for x in forged.requisitions]
    link = retention.links(forged)[0]
    forged.facts = [
        dict(x, body=link.model_copy(update=dict(event=fake_swap.source_event)).model_dump_json())
        if x.get("kind") == "class_rule_retained"
        else x
        for x in forged.facts
    ]
    with (
        ledger.engine.connect() as c,
        pytest.raises(WorkflowError, match="SOURCE_REQUISITION_MISSING"),
    ):
        _, value = source._source(c, forged, paid.id)
        source._current(c, forged, value)

    casts = CastService(ActorService(cycle.missions))
    data = casts.view(ADMIN, 900)
    casts.change(
        ADMIN, str(uuid4()), 900, data["game_revision"], data["cast_revision"], "join", npc
    )
    before_treatment = state(game)

    async def native_scene_and_treatment():
        own = current(2, 958005)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_request(own, source, paid.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            location=("base0",), asset=(asset.id,), account="PRIVATE_ACTUAL_RETAINED_THERAPY_SCENE"
        )
        await form.confirm.callback(current(2, 958006))
        assert form.completed
        with ledger.engine.connect() as c:
            scene_id = source._tasks(c, ADMIN)[0]["id"]
        assert next(x for x in state(game).sheets["2"].assets if x.id == asset.id) == asset
        data = source.get(ADMIN, scene_id)
        assert data["therapy"]["scene"]["location"] == "base0"
        assert data["therapy"]["purchase"] == paid.id
        assert data["therapy"]["source_event"] == paid.source_event
        controller = current(1, 958007)
        controller.channel_id = 901
        await controller.response.defer(ephemeral=True)
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_physiotherapist" and x.identity == scene_id
        )
        await InboxView(inbox, 1).route(controller, item)
        form = controller.edit_original_response.call_args.kwargs["view"]
        assert asset.name in form.text()
        form.values.update(
            tag="Steadier with my original therapist",
            account="Actual NPC attendance and nondestructive Void treatment",
        )
        await form.confirm.callback(current(1, 958008))
        assert form.completed and controller.channel_id == 901
        assert (
            source.respond(
                ADMIN,
                "958008",
                scene_id,
                data["revision"],
                data["game_revision"],
                operation="treat",
                account="Actual NPC attendance and nondestructive Void treatment",
                tag="Steadier with my original therapist",
            )["phase"]
            == "closed"
        )
        return scene_id

    scene_id = asyncio.run(native_scene_and_treatment())
    final = state(game)
    actual = next(x for x in final.sheets["2"].assets if x.id == asset.id)
    assert actual == asset.model_copy(update=dict(void=False)) and actual.damaged
    tags = [x for x in final.sheets["2"].tags if x.label == "Steadier with my original therapist"]
    assert len(tags) == 1 and tags[0].giver_actor == npc and tags[0].giver == 1
    assert final.sheets["2"].identities == before_treatment.sheets["2"].identities
    assert final.sheets["2"].heat == before_treatment.sheets["2"].heat
    assert (
        final.sheets["2"].permissions == 4 and final.requisitions == before_treatment.requisitions
    )
    assert final.sheets["3"] == before_treatment.sheets["3"]
    assert depth(final, actor, npc) == 1 and source.get(PLAYER, paid.id)["therapy"] == relationship
    assert source.get(PLAYER, scene_id)["therapy"]["scene"]["acknowledgements"] == [1, 2]
    with ledger.engine.connect() as c:
        row, value = source._source(c, final, scene_id)
        assert (
            row["state"] == "resolved" and row["off_duty_id"] == period and value.phase == "closed"
        )
        assert not source._tasks(c, ADMIN)
        assert cycle.periods.get(ADMIN, period)["phase"] == "active"
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert game.rebuild() > 0 and state(game) == final
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
