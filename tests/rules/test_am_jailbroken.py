"""Intrinsic AM movement uses actual hardware, independent of discovery/circuit Plays."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_creation_review
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_personal_firearm import reviewed_registry
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_am import open_am
from girlframe.discord_adapter.m3_am_jailbroken import open_jailbroken
from girlframe.engine import m3_am as am
from girlframe.engine import m3_am_body as hardware
from girlframe.engine import m3_am_jailbroken as rules
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest, load_registry
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_am_jailbroken import JailbrokenService, prove, prove_preparation
from girlframe.services.m3_am_scrutinized import ScrutinyService
from girlframe.services.onboarding import WorkflowError

CANARY = "PRIVATE_ORIGINAL_AM_OOC_HISTORY"


def test_voluntary_occupancy_real_new_body_damage_and_same_ability_moveback(
    ledger, tmp_path, monkeypatch
):
    selected = test_creation_review.selected

    def actual_assets(girl="MOCKINGBIRD", frame="JANUS-B"):
        value = selected(girl, frame)
        return (
            value.model_copy(
                update=dict(
                    girl_assets=(
                        AssetChoice(
                            name="Doll-Joints", description="Actual original puppet hardware"
                        ),
                        AssetChoice(
                            name="Perfect Affect",
                            description="Actual persistent expression software",
                        ),
                    )
                )
            )
            if girl == "AM"
            else value
        )

    monkeypatch.setattr(test_creation_review, "selected", actual_assets)
    _, game = service(ledger, girl="AM", frame="THE ENFORCER")
    production = load_registry()
    with pytest.raises(ValueError, match="UNSUPPORTED_RULE"):
        production.require_available(rules.RULE)
    data = production.model_dump(mode="json")
    prototype = reviewed_registry().entry("frame.enforcer.personal-firearm").model_dump(mode="json")
    target = next(x for x in data["entries"] if x["id"] == rules.RULE)
    for field in (
        "implementation",
        "source_audit",
        "independent_review",
        "reviewer",
        "review_reference",
        "contract",
        "test_evidence",
    ):
        target[field] = prototype[field]
    fixture = Registry.model_validate_json(json.dumps(data))
    path = tmp_path / "synthetic-jailbroken-only.json"
    path.write_text(fixture.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(
                    registry_sha256=digest(fixture), subsystems=approval.subsystems | {"plays"}
                )
            ),
            owner_m3_rulings=ledger.policy.owner_m3_rulings.model_copy(
                update=dict(beneath_private_choices="affected_owner")
            ),
        )
    )
    assert not fixture.entry(am.RULE).verified
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        physical = next(x for x in actual.sheets["2"].assets if x.name == "Doll-Joints")
        physical.damaged = physical.void = True
        actual.facts.append(dict(kind="synthetic_private_memory", body=CANARY))
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_am_hardware", actual)
    before = state(game)
    assert (
        not am.discoveries(before)
        and not hardware.preparations(before)
        and not hardware.swaps(before)
    )
    original = current_ref(before, 2)
    sheet = before.sheets["2"].model_copy(deep=True)
    pose = next(x for x in before.placements if x.actor == original)
    mind = next(x for x in sheet.assets if x.name == "Perfect Affect")
    service_ = JailbrokenService(game)
    calls = game.dice.calls

    async def preparation_and_move():
        owner = current(2, 973001)
        await owner.response.defer(ephemeral=True)
        await open_am(owner, ScrutinyService(game))
        entry = owner.edit_original_response.call_args.kwargs["view"]
        assert "your actual body occupancy" in entry.title
        entry.values.update(operation=("prepare",))
        launch = current(2, 973000)
        await entry.confirm.callback(launch)
        form = launch.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(
            vessel="actual-independent-puppet",
            label="Actual spare AM puppet",
            source="PRIVATE_ACTUAL_SUPPLIED_PUPPET_AND_PROCESSOR",
            processing=("yes",),
            empty=("yes",),
            medical=("fit",),
            mind_assets=(mind.id,),
            assets=(
                "Prepared arm | Supplied actuator | intact | clear\n"
                "Prepared skin | Supplied covering | intact | clear"
            ),
        )
        confirmation = current(2, 973002)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)
        owner = current(2, 973003)
        await owner.response.defer(ephemeral=True)
        await open_jailbroken(owner, service_)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert "near-instant calculations" in form.instructions
        form.values.update(operation=("occupy:actual-independent-puppet",))
        confirmation = current(2, 973004)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(preparation_and_move())
    forward = state(game)
    (move,) = rules.history(forward)
    (prepared,) = rules.preparations(forward)
    assert not hardware.swaps(forward) and not am.discoveries(forward)
    assert game.dice.calls == calls and current_ref(forward, 2) == original
    assert forward.sheets["2"].identities == sheet.identities
    assert forward.sheets["2"].tags == sheet.tags
    assert (
        forward.sheets["2"].heat == sheet.heat
        and forward.sheets["2"].permissions == sheet.permissions
    )
    assert forward.sheets["2"].frame_runtime == sheet.frame_runtime
    assert forward.actor_bonds == before.actor_bonds and forward.bonds == before.bonds
    assert hardware.current(forward, original).vessel == prepared.spec.vessel
    assert next(x for x in hardware.bodies(forward) if x.vessel == pose.vessel_id).occupant is None
    assert not rules.available(forward, original) == ()
    with ledger.engine.connect() as c:
        assert prove(game, c, forward, move.id) == move
        assert prove_preparation(game, c, forward, prepared.id) == prepared
        assert (
            resolve(forward, original, profiles(c, ledger.campaign_id)).vessel_id
            == prepared.spec.vessel
        )
        forged = forward.model_copy(deep=True)
        hardware.put(
            forged,
            "am_jailbroken_prepared",
            prepared.id,
            prepared.model_copy(
                update=dict(spec=prepared.spec.model_copy(update=dict(source="Unproved source")))
            ),
        )
        with pytest.raises(WorkflowError, match="hardware preparation"):
            prove_preparation(game, c, forged, prepared.id)
    with pytest.raises(WorkflowError):
        service_.occupy(OTHER, str(uuid4()), original, forward.revision, pose.vessel_id)
    with pytest.raises(ValueError):
        rules.occupy(forward.model_copy(deep=True), original, prepared.spec.vessel, "not-empty")
    assert (
        service_.occupy(PLAYER, "973004", original, before.revision + 1, prepared.spec.vessel)["id"]
        == move.id
    )
    worker, gateway = GameWorker(game), Gateway()
    game.dice.faces = (1, 1)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        forward.sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            trigger_confirmed=True,
            context="Actual same AM interacts from newly occupied hardware",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="Actual new-body counterattack")
    damaged = prepared.spec.assets[0]
    answer(game, PLAYER, "beneath_details", denied=(damaged.id,))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    active = state(game)
    assert next(x for x in active.sheets["2"].assets if x.id == damaged.id).damaged

    async def moveback_and_read():
        owner = current(2, 973005)
        await owner.response.defer(ephemeral=True)
        await open_jailbroken(owner, service_, move.id)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert "Prepared arm [damaged]" in form.instructions
        form.values.update(operation=("occupy:" + pose.vessel_id,))
        confirmation = current(2, 973006)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(moveback_and_read())
    final = state(game)
    assert current_ref(final, 2) == original and game.dice.calls == calls + 1
    assert len(rules.history(final)) == 2 and not hardware.swaps(final)
    assert {x.id: x for x in final.sheets["2"].assets} == {x.id: x for x in sheet.assets}
    assert final.sheets["2"].identities == sheet.identities and final.sheets["2"].tags == sheet.tags
    assert final.sheets["2"].heat == active.sheets["2"].heat
    assert final.sheets["2"].permissions == active.sheets["2"].permissions
    assert final.sheets["2"].frame_runtime == sheet.frame_runtime
    assert final.sheets["3"] == active.sheets["3"]
    parked = next(x for x in hardware.bodies(final) if x.vessel == prepared.spec.vessel)
    assert parked.occupant is None and next(x for x in parked.assets if x.id == damaged.id).damaged
    assert hardware.current(final, original).vessel == pose.vessel_id
    assert CANARY not in str(service_.view(PLAYER, move.id))
    assert CANARY in str(final.facts)

    async def reopen_saved_controls():
        from girlframe.discord_adapter.inbox import InboxView
        from girlframe.services.inbox import InboxService

        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(PLAYER) if x.task == "m3_am_jailbroken" and x.identity == move.id
        )
        assert not item.incoming
        assert not any(x.task == "m3_am_jailbroken" for x in inbox.items(OTHER))
        owner = current(2, 973007)
        owner.channel_id = 902
        await owner.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(owner, item)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert pose.vessel_id in form.instructions
        assert "Saved empty hardware" in form.instructions
        assert "Prepared arm [damaged]" in form.instructions
        assert CANARY not in form.instructions
        assert not await form.interaction_check(current(3))

    asyncio.run(reopen_saved_controls())
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert game.rebuild() > 0 and state(game) == final
