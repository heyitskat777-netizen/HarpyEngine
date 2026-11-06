"""Paid replacement transfers the same copy, then real Identity and Clone Flirt work."""

import asyncio
import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_actor_play_service import pass_tags
from test_clone_am import cast_copy, finish_keep, flirt
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_succubus import restore, suspend
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.discord_adapter.m3_clone_am import open_purchase
from girlframe.engine import m3_clone_am as rules
from girlframe.engine import m3_clone_residency as residency
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_clone_am import CloneService, prepare_transfer, prove_copy
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.onboarding import WorkflowError

CANARY = "PRIVATE_ORIGINAL_NOTES_NEVER_COPIED"
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
        trigger="SYNTHETIC retained Clone same-copy actual residency and owned Plays",
        actor_type="Original Pilot with exact native/graft acquisition and4P Swap",
        pre_roll_sources=["Original born copy and exact paid carrier transfer"],
        roll_kind="2d6",
        allowed_modifiers=["Original shared Heat, ordinary source roll basis"],
        tier_options={"normal": ["Native additional Identity and actual clone Flirt"]},
        choice_ownership="Actual copy controller, original target and source adjudicator",
        target_policy="Original owner and current replacement Frame only",
        post_roll_effects=["Same copy and actual saved source outcomes"],
        mandatory_followups=["Actual player/Handler response and chat restoration"],
        handler_or_gm_intervention="Actual printed Handler outcome authority",
        test_fixture_ids=["tests/rules/test_retained_clone_am.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_clone_am.py"],
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
    path = tmp_path / "SYNTHETIC-only-five-retained-clone-sources.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    registry_sha256=digest(registry),
                    subsystems=store.policy.m3_approval.subsystems
                    | {"economy", "plays", "world", "playbooks"},
                )
            )
        )
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3)
        canon.sheets["2"].permissions = 10
        canon.sheets["2"].heat = 1
        canon.facts.append(dict(kind="synthetic_private_memory", body=CANARY))
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_clone_resources", canon)
    source = CloneService(game)
    offered = source.menu(PLAYER)

    async def purchase():
        own = current(2, 959001)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "2 Permissions" in form.text()
        form.values.update(account="PRIVATE_ORIGINAL_CLONE_ACQUISITION")
        await form.confirm.callback(current(2, 959002))
        assert form.completed

    asyncio.run(purchase())
    original = state(game)
    (born,) = rules.copies(original)
    paid = next(x for x in original.requisitions if x.id == born.receipt)
    assert born.identity.name == "Perfect Copy" and CANARY not in born.model_dump_json()
    assert (
        source.buy(
            PLAYER,
            "959002",
            offered["revision"],
            born.original,
            offered["frame"],
            "PRIVATE_ORIGINAL_CLONE_ACQUISITION",
        )["id"]
        == paid.id
    )
    # Real saved mutable copy resources are distinct from immutable birth and original OOC history.
    with store.transaction() as c:
        saved = state(game)
        rules.add_tag(saved, born.ref, "My own earlier identity", (2, 3))
        tag = rules.tags(saved, born.ref)[0]
        rules.tag(saved, born.ref, tag.id, marked=True)
        rules.embrace(saved, born.ref, tag.id, (born.identity.id,))
        rules.add_tag(saved, born.ref, "My own saved marked Tag", (2, 3))
        rules.tag(saved, born.ref, rules.tags(saved, born.ref)[0].id, marked=True)
        saved = set_depth(saved, born.ref, born.original, 1, str(uuid4()))
        game.event(c, 2, str(uuid4()), "synthetic.actual_prior_saved_clone_state", saved)
    before = state(game)
    with store.engine.connect() as c:
        assert prepare_transfer(game, c, before, paid) == before
    kept = next(x for x in before.sheets["2"].assets if x.family == "frame" and x.intrinsic is None)
    swap = FrameSwapService(game, registry)
    plan = swap.create(PLAYER, str(uuid4()), "THE ENFORCER")["id"]
    data = swap.get(PLAYER, plan)
    assert next(x for x in data["class_sources"] if x["rule"] == rules.RULE)["receipt"] == paid.id
    selection = Selection(
        frame="THE ENFORCER",
        name="Actual replacement Enforcer",
        appearance="Actual new carrier",
        assets=tuple(AssetChoice(name=x, description="Actual " + x) for x in data["starting"][:2]),
        retained_asset=kept.id,
        retained_rule=rules.RULE,
        retained_receipt=paid.id,
        account="PRIVATE_SAME_COPY_TRANSFER",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=selection)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    return game, source, born, paid, before, production


def test_retained_clone_same_resident_native_identity_and_real_flirt_bond_endpoint(
    ledger, tmp_path, monkeypatch
):
    game, source, born, paid, before, production = prepared(ledger, tmp_path, monkeypatch)
    canon = state(game)
    ref, actor = born.ref, born.original
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    (change,) = residency.transfers(canon, ref)
    saved_copy = rules.current(before, ref)
    assert rules.current(canon, ref) == saved_copy and len(rules.copies(canon)) == 1
    assert change.event == swap.source_event and change.old_frame == born.frame
    assert change.frame == residency.residence(canon, ref) == swap.new_frame
    assert canon.actor_bonds == before.actor_bonds and canon.obligations == before.obligations
    assert canon.sheets["2"].heat == 1 and canon.sheets["2"].permissions == 4
    assert canon.sheets["2"].identities == before.sheets["2"].identities
    assert canon.sheets["2"].tags == before.sheets["2"].tags
    assert canon.sheets["3"] == before.sheets["3"]
    assert source.view(PLAYER)["frame"] == swap.new_frame
    assert source.view(PLAYER)["birth_frame"] == born.frame
    assert source.view(PLAYER)["actor"] == ref.model_dump(mode="json")
    assert CANARY not in str(source.view(PLAYER)) and not source.view(OTHER)["owned"]
    with ledger.engine.connect() as c:
        prove_copy(game, c, canon, ref)
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
        actual = resolve(canon, ref, profiles(c, ledger.campaign_id))
        assert actual.controller == 2 and actual.frame_instance == swap.new_frame
        assert actual.cell == (0, 0) and actual.inside_frame is True and not actual.piloting
    assert (
        next(x for x in canon.parked_frames if x.frame_instance == born.frame).source_event
        == swap.source_event
    )
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="instead of buying twice"):
        source.buy(
            PLAYER,
            str(uuid4()),
            menu["revision"],
            actor,
            menu["frame"],
            "No rebirth",
        )
    assert state(game) == canon and game.dice.calls == 0

    gate = suspend(game, swap.id)
    suspended = state(game)
    assert source.menu(PLAYER)["suspended"] and not source.view(PLAYER)["owned"]
    assert rules.find(suspended, ref) == saved_copy and residency.transfers(suspended, ref) == (
        change,
    )
    restore(game, gate)
    restored = state(game)
    assert rules.current(restored, ref) == saved_copy and restored.sheets == suspended.sheets
    assert residency.transfers(restored, ref) == (change,)

    missing = restored.model_copy(deep=True)
    missing.facts = [x for x in missing.facts if x.get("kind") != residency.KIND]
    with pytest.raises(ValueError, match="residency transfer"):
        rules.current(missing, ref)
    forged = restored.model_copy(deep=True)
    forged.facts = [
        dict(x, body=change.model_copy(update=dict(copy_sha256="0" * 64)).model_dump_json())
        if x.get("kind") == residency.KIND
        else x
        for x in forged.facts
    ]
    with ledger.engine.connect() as c, pytest.raises(WorkflowError, match="residence snapshot"):
        prove_copy(game, c, forged, ref)
    with pytest.raises(ValueError, match="actual paid delivered replacement"):
        residency.transfer(before, restored, paid, swap)

    identity = saved_copy.identity.id
    assert game.sheet(PLAYER, 2)["additional_identities"][0]["id"] == identity
    assert "additional_identities" not in game.sheet(OTHER, 2)

    async def native_selector():
        own = current(2, 959003)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_play(own, game, _pilot=True)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert identity in dict(next(x for x in form.fields if x.key == "identity").options)

    asyncio.run(native_selector())
    cast_copy(game, ref)
    prior = state(game)
    game.dice.faces = (2, 3)
    args = (
        PLAYER,
        str(uuid4()),
        900,
        prior.sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            identity=identity,
            gain=3,
            heat=3,
            context="Actual retained copy Identity supports my original action",
            trigger_confirmed=True,
        ),
    )
    action = game.begin(*args)["action_id"]
    assert game.begin(*args)["action_id"] == action
    assert rules.current(state(game), ref) == saved_copy and state(game).sheets == prior.sheets
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    receipt = copy.deepcopy(game.inspect(PLAYER, action)["receipt"])
    assert receipt["heat"] == 3 and receipt["pre_total"] == 8
    assert rules.current(state(game), ref).identity.marked and state(game).sheets["2"].heat == 1
    assert game.dice.calls == 1
    pass_tags(game)
    finish_keep(game, mid=True)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    target = current_ref(state(game), 3)
    owner_bond = depth(state(game), actor, target)
    flirt_action = flirt(game, ref, worker, gateway)
    assert game.inspect(PLAYER, flirt_action)["state"] == "complete"
    tick(worker, gateway, 5)
    owed = next(x for x in state(game).obligations if x.kind == "clone_flirt_followthrough")
    follow = source.fulfill_followthrough(
        PLAYER, str(uuid4()), owed.id, "I actually use her chosen name", channel=900
    )["action_id"]
    tick(worker, gateway, 3)
    answer(
        game,
        OTHER,
        "clone_flirt_followthrough_confirm",
        flag=True,
        text="The same original copy actually followed through",
    )
    assert game.inspect(PLAYER, follow)["state"] == "complete"
    tick(worker, gateway, 5)
    final = state(game)
    assert game.dice.calls == 2 and depth(final, ref, target) == 1
    assert depth(final, actor, target) == owner_bond and depth(final, ref, actor) == 1
    assert (
        rules.current(final, ref).identity.id == identity
        and rules.current(final, ref).identity.marked
    )
    assert rules.current(final, ref).tags == saved_copy.tags
    assert (rules.current(final, ref).frame, rules.current(final, ref).source_event) == (
        born.frame,
        born.source_event,
    )
    assert residency.transfers(final, ref) == (change,)
    assert final.sheets["2"].identities == before.sheets["2"].identities
    assert final.sheets["2"].permissions == 4 and final.sheets["2"].heat == 1
    assert next(x for x in final.requisitions if x.id == paid.id) == paid
    actor_plays = ActorPlayService(game)
    preview = actor_plays.preview(PLAYER, 900, ref)
    with pytest.raises(ValueError, match="cannot Dive"):
        actor_plays.begin(
            PLAYER,
            str(uuid4()),
            900,
            ref,
            preview["actor"]["source_sha256"],
            None,
            preview["cast_revision"],
            PlayInput(
                play="dive_deep",
                heat=0,
                context="Forbidden retained-copy Dive",
                trigger_confirmed=True,
            ),
        )
    assert state(game) == final and game.dice.calls == 2
    with ledger.engine.connect() as c:
        prove_copy(game, c, final, ref)
        assert game.lock(c, 900)["state"] == "released"
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert game.rebuild() > 0 and state(game) == final
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
