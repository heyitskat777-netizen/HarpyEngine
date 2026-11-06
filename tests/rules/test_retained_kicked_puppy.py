"""One narrowly source-enabled retained Kicked Puppy, never production approval."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_privileges import change as restore_choice
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice, open_play
from girlframe.engine import m3_class_grafts as classes
from girlframe.engine import m3_class_retention as retention
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine import m3_kicked_puppy as rules
from girlframe.engine import m3_privileges as privileges
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.m3_punishments import Details
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_kicked_puppy import KickedPuppyService, entitlement
from girlframe.services.m3_missions import MissionService
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
    original = Registry.model_validate_json(Path("rules/registry.json").read_text())
    raw = original.model_dump(mode="json")
    contract = dict(
        trigger="SYNTHETIC retained Kicked Puppy actual Flirt",
        actor_type="Actual original Girl and original paid acquisition plus actual4P swap",
        pre_roll_sources=[
            "Exact paid chain/current Frame, actual damaged Girl Assets and original target giver"
        ],
        roll_kind="2d6",
        allowed_modifiers=["Actual damaged Girl count instead of Heat, original-target-given Tag"],
        tier_options={"normal": ["Ordinary Flirt choices and extra care question"]},
        choice_ownership="Original actor, target and actual human Tag response",
        target_policy="Actual other original Pilot",
        post_roll_effects=["Original target answers; actual follow-through deepens real Bond"],
        mandatory_followups=["Real question/answer and target-confirmed follow-through"],
        handler_or_gm_intervention="Actual source only",
        test_fixture_ids=["tests/rules/test_retained_kicked_puppy.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review/production approval",
                test_evidence=["tests/rules/test_retained_kicked_puppy.py"],
            )
            if not entry.get("contract"):
                entry["contract"] = contract
    candidate = Registry.model_validate_json(json.dumps(raw))
    assert {x.id for x in candidate.entries if x != original.entry(x.id)} == NEEDED
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(original, "THE ENFORCER")
    return original, candidate


def prepared(store, tmp_path, monkeypatch):
    _, game = service(store, girl="ALPHA", frame="WYVERN 0.4")
    production, registry = synthetic_registry()
    path = tmp_path / "SYNTHETIC-only-five-retained-kicked-sources.json"
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
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3)
        sheet = canon.sheets["2"]
        sheet.permissions = 10
        sheet.heat = 5
        sheet.identities[0].marked = True
        for asset in sheet.assets:
            if asset.family == "girl":
                asset.damaged = True
        kept = next(x for x in sheet.assets if x.family == "frame" and x.intrinsic is None)
        kept.damaged = kept.void = True
        giver = current_ref(canon, 3)
        sheet.tags.append(
            TagState(
                id="actual-retained-target-gift",
                label="PRIVATE_RETAINED_TARGET_GIFT",
                giver=3,
                giver_actor=giver,
                giver_character=giver.incarnation,
                observers=(2, 3),
            )
        )
        game.event(c, 3, str(uuid4()), "synthetic.actual_prior_kicked_resources_and_gift", canon)
    source = KickedPuppyService(game)
    menu = source.menu(PLAYER)
    source.buy(
        PLAYER,
        str(uuid4()),
        menu["revision"],
        ActorRef.model_validate(menu["actor"]),
        menu["frame"],
        "Actual original native2P Kicked Puppy",
    )
    paid = rules.held(state(game), current_ref(state(game), 2))
    swap = FrameSwapService(game, registry)
    plan = swap.create(PLAYER, str(uuid4()), "THE ENFORCER")["id"]
    data = swap.get(PLAYER, plan)
    assert data["class_sources"][0]["receipt"] == paid.id
    pick = Selection(
        frame="THE ENFORCER",
        name="Actual replacement Enforcer",
        appearance="Actual replacement hardware",
        assets=tuple(AssetChoice(name=x, description="Actual " + x) for x in data["starting"][:2]),
        retained_asset=kept.id,
        retained_rule=rules.RULE,
        retained_receipt=paid.id,
        account="PRIVATE_KICKED_SWAP",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=pick)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    original = state(game)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    return game, source, paid, original, production


def test_retained_kicked_real_flirt_gift_care_followthrough_and_source_suspension(
    ledger, tmp_path, monkeypatch
):
    game, source, paid, before, production = prepared(ledger, tmp_path, monkeypatch)
    canon = state(game)
    actor, target = current_ref(canon, 2), current_ref(canon, 3)
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    assert (
        rules.held(canon, actor) == paid
        and next(x for x in canon.requisitions if x.id == paid.id) == paid
    )
    assert swap.selection.retained_receipt == paid.id and swap.new_frame != paid.frame_instance
    assert canon.sheets["2"].permissions == 4 and canon.sheets["2"].heat == 5
    assert (
        canon.sheets["2"].identities == before.sheets["2"].identities
        and canon.sheets["2"].tags == before.sheets["2"].tags
    )
    assert [x for x in canon.sheets["2"].assets if x.family == "girl"] == [
        x for x in before.sheets["2"].assets if x.family == "girl"
    ]
    damaged = sum(x.family == "girl" and x.damaged for x in canon.sheets["2"].assets)
    assert sum(x.damaged for x in canon.sheets["2"].assets) > damaged
    with ledger.engine.connect() as c:
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
    offer = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="Restore"):
        source.buy(
            PLAYER,
            str(uuid4()),
            offer["revision"],
            actor,
            offer["frame"],
            "Cannot buy retained original again",
            "WYVERN 0.4",
        )

    async def actual_flirt():
        owner = current(2, 949001)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_play(owner, game)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            play=("flirt",),
            target=("3",),
            heat=("0",),
            kicked_puppy_basis=("damaged",),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="Actual original target-gift Flirt from replacement Frame",
        )
        await form.confirm.callback(current(2, 949002))
        assert form.completed and game.dice.calls == 0

    asyncio.run(actual_flirt())
    worker, gateway = GameWorker(game), Gateway()
    game.dice.faces = (3, 3)
    tick(worker, gateway, 3)
    action = game.choices(PLAYER)[0]["action_id"]
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert (
        receipt["heat"] == 0
        and receipt["base_modifier"] == damaged
        and receipt["pre_total"] == 6 + damaged
    )
    assert receipt["kicked_purchase"] == paid.id and state(game).sheets["2"].heat == 5
    with ledger.engine.connect() as c:
        assert game.action(c, action)["data"]["kicked_puppy"]["frame"] == swap.new_frame

    async def gift_and_care():
        tag = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
        owner = current(2, 949003)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, tag["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            options=("tag",),
            denied=("actual-retained-target-gift",),
            number=("1",),
            text="Her actual original gift expresses my need for care",
        )
        await form.confirm.callback(current(2, 949004))
        assert form.completed
        for viewer in (ADMIN, OTHER):
            answer(game, viewer, "tag_window", options=("pass",))
        question = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_flirt")
        owner = current(2, 949005)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, question["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert rules.QUESTION in dict(next(x for x in form.fields if x.key == "options").options)
        form.values.update(options=(rules.QUESTION,))
        await form.confirm.callback(current(2, 949006))
        assert form.completed
        request = next(x for x in game.choices(OTHER) if x["kind"] == "target_flirt")
        other = current(3, 949007)
        await other.response.defer(ephemeral=True)
        await open_choice(other, game, request["id"])
        form = other.edit_original_response.call_args.kwargs["view"]
        assert rules.QUESTION_TEXT in form.text()
        form.values.update(text="I want to care for you with actual shared rest")
        await form.confirm.callback(current(3, 949008))
        assert form.completed

    asyncio.run(gift_and_care())
    final = game.inspect(PLAYER, action)
    assert final["state"] == "complete" and final["receipt"] == receipt and game.dice.calls == 1
    assert final["result"]["question"] == rules.QUESTION and final["result"]["target_answer"]
    assert final["modifiers"][-1]["amount"] == 1
    marked = next(x for x in state(game).sheets["2"].tags if x.id == "actual-retained-target-gift")
    assert marked.marked and marked.giver_actor == target and marked.scene_used
    tick(worker, gateway, 5)
    obligation = next(
        x for x in state(game).obligations if x.kind == "flirt_followthrough" and x.action == action
    )
    old_bond = depth(state(game), actor, target)
    args = (PLAYER, str(uuid4()), 900, obligation.id, "I actually share the rest she asked for")
    follow = game.fulfill(*args)["action_id"]
    assert game.fulfill(*args)["action_id"] == follow
    tick(worker, gateway, 3)
    answer(
        game,
        OTHER,
        "followthrough_confirm",
        flag=True,
        text="She actually provided the care I asked for",
    )
    assert game.inspect(PLAYER, follow)["state"] == "complete" and depth(
        state(game), actor, target
    ) == min(2, old_bond + 1)
    assert game.dice.calls == 1 and state(game).sheets["2"].heat == 5
    tick(worker, gateway, 5)
    missions = MissionService(ledger)
    offered = missions.offer(ADMIN, str(uuid4()), "SYNTHETIC actual discipline source", (2, 3))
    missions.respond(PLAYER, str(uuid4()), offered["id"], 1, "accept")
    missions.respond(OTHER, str(uuid4()), offered["id"], 2, "accept")
    missions.start(ADMIN, str(uuid4()), offered["id"], 3)
    missions.end(ADMIN, str(uuid4()), offered["id"], 4, False)
    work = next(
        x
        for x in missions.owned_work(ADMIN)
        if x["subject_id"] == "2" and x["kind"] == "punishment"
    )
    discipline = PunishmentService(ledger)
    view = discipline.get(ADMIN, work["id"])
    discipline.apply(
        ADMIN,
        str(uuid4()),
        work["id"],
        view["revision"],
        view["game_revision"],
        Details(
            kind="revoked_privileges",
            requisition=paid.id,
            restoration="Actual Kicked restoration condition",
        ),
    )
    suspended = state(game)
    assert rules.held(suspended, actor) is None
    with ledger.engine.connect() as c:
        assert entitlement(game, c, suspended, actor) is None
    before_denial = suspended.model_dump_json()
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            suspended.sheets["2"].revision,
            PlayInput(
                play="flirt",
                target=3,
                heat=0,
                kicked_puppy_basis=True,
                context="Unavailable original retained source cannot roll",
                trigger_confirmed=True,
            ),
        )
    assert state(game).model_dump_json() == before_denial and game.dice.calls == 1
    gate = next(x for x in suspended.obligations if x.kind == privileges.KIND)
    privilege = PrivilegeService(ledger)
    restore_choice(privilege, ADMIN, gate.id, allow=True)
    restore_choice(privilege, PLAYER, gate.id, allow=False)
    restored = state(game)
    assert rules.held(restored, actor) == paid and restored.sheets["2"].heat == 5
    assert next(x for x in restored.sheets["2"].tags if x.id == marked.id) == marked
    # Corrupt or missing source cannot become a new current-Frame purchase authority.
    forged = type(restored).model_validate_json(restored.model_dump_json())
    (link,) = retention.links(forged)
    wrong = link.model_copy(update=dict(event="SYNTHETIC_FORGED_SWAP"))
    forged.facts = [
        dict(x, body=wrong.model_dump_json()) if x.get("kind") == "class_rule_retained" else x
        for x in forged.facts
    ]
    assert not classes.eligible(forged, paid)
    with ledger.engine.connect() as c, pytest.raises(ValueError, match="retention chain"):
        proof(game, c, forged, paid)
    with ledger.engine.connect() as c:
        assert "PRIVATE_RETAINED" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert (
            resolve(restored, actor, profiles(c, ledger.campaign_id)).frame_instance
            == swap.new_frame
        )
    game.rebuild()
    assert state(game) == restored
    assert not production.entry("frame.enforcer.enforcement-initiative").verified
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
