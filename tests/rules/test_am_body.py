"""Actual circuits transfer, real new-body damage, and same-AM hooked return."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_creation_review
from test_am_code import rolled
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_physical_operations import place

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_am_body import open_prepare
from girlframe.discord_adapter.m3_am_code import open_choice
from girlframe.engine import m3_am_body as bodies
from girlframe.engine import m3_am_code as code
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_am_body import BodyService, prove, prove_preparation
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

CANARY = "PRIVATE_ORIGINAL_AM_OOC_MEMORY"


def test_real_code_body_swap_new_asset_damage_and_private_hooked_return(
    ledger, tmp_path, monkeypatch
):
    selected = test_creation_review.selected

    def actual_assets(girl="MOCKINGBIRD", frame="JANUS-B"):
        value = selected(girl, frame)
        if girl == "AM":
            return value.model_copy(
                update=dict(
                    girl_assets=(
                        AssetChoice(
                            name="Doll-Joints", description="Actual original puppet hardware"
                        ),
                        AssetChoice(
                            name="Perfect Affect", description="Actual persistent expression skill"
                        ),
                    )
                )
            )
        return value

    monkeypatch.setattr(test_creation_review, "selected", actual_assets)
    game, maintenance, root, action, worker, gateway, _ = rolled(
        ledger, tmp_path, monkeypatch, (4, 5), marked=True, choose_identity=False
    )
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            owner_m3_rulings=ledger.policy.owner_m3_rulings.model_copy(
                update=dict(beneath_private_choices="affected_owner")
            )
        )
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon = place(canon, 3)
        physical = next(x for x in canon.sheets["2"].assets if x.name == "Doll-Joints")
        physical.damaged = physical.void = True
        canon.facts.append(dict(kind="synthetic_private_memory", body=CANARY))
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_body_condition", canon)
    original = state(game)
    actor = current_ref(original, 2)
    mind = next(x for x in original.sheets["2"].assets if x.name == "Perfect Affect")
    old_physical = next(x for x in original.sheets["2"].assets if x.name == "Doll-Joints")
    old_pose = next(x for x in original.placements if x.actor == actor)
    service = BodyService(game)

    async def prepare_hardware():
        own = current(1, 961001)
        await own.response.defer(ephemeral=True)
        await open_prepare(own, service, maintenance)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(
            vessel="actual-spare-AM-body",
            label="Actual prepared puppet",
            source="PRIVATE_ACTUAL_LOCAL_HARDWARE_AND_PROCESSING_PROVENANCE",
            processing=("yes",),
            unoccupied=("yes",),
            medical=("fit",),
            mind_assets=(mind.id,),
            assets=(
                "Prepared arm | Actual installed actuator | intact | clear\n"
                "Prepared skin | Actual supplied covering | intact | clear"
            ),
        )
        confirmation = current(1, 961002)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(prepare_hardware())
    before = state(game)
    (prepared,) = bodies.preparations(before)
    assert before.sheets == original.sheets and before.placements == original.placements
    with ledger.engine.connect() as c:
        assert prove_preparation(game, c, before, prepared.id) == prepared
    forged = before.model_copy(deep=True)
    wrong = prepared.model_copy(
        update=dict(spec=prepared.spec.model_copy(update=dict(label="Unproved hardware")))
    )
    bodies.put(forged, "am_body_prepared", prepared.id, wrong)
    with ledger.engine.connect() as c, pytest.raises(WorkflowError, match="original hardware"):
        prove_preparation(game, c, forged, prepared.id)
    calls = game.dice.calls

    async def performed_choice():
        choice = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_options")
        own = current(1, 961003)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, choice["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "body" in dict(next(x for x in form.fields if x.key == "options").options)
        form.values.update(options=("body", "backup"))
        await form.confirm.callback(current(1, 961004))
        assert form.completed
        body = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_body")
        own = current(1, 961005)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, body["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        assert prepared.id in dict(next(x for x in form.fields if x.key == "body").options)
        form.values.update(
            body=(prepared.id,), account="The actual NPC performs this same-AM transfer"
        )
        await form.confirm.callback(current(1, 961006))
        assert form.completed
        assert game.respond(
            ADMIN,
            "961006",
            body["id"],
            body["revision"],
            ChoiceAnswer(
                options=(prepared.id,), text="The actual NPC performs this same-AM transfer"
            ),
        )

    asyncio.run(performed_choice())
    forward = state(game)
    source = code.session(forward, maintenance)
    assert source.body_swap and source.backup and source.selected_options == ("body", "backup")
    changed = bodies.swap(forward, source.body_swap)
    assert changed.actor == actor and changed.original_vessel == old_pose.vessel_id
    assert changed.new_vessel == prepared.spec.vessel and game.dice.calls == calls
    assert set(forward.sheets) == set(original.sheets) and forward.order == original.order
    assert forward.sheets["2"].identities == original.sheets["2"].identities
    assert forward.sheets["2"].tags == original.sheets["2"].tags
    assert forward.sheets["2"].heat == original.sheets["2"].heat
    assert forward.sheets["2"].permissions == original.sheets["2"].permissions
    assert forward.actor_bonds == original.actor_bonds and forward.bonds == original.bonds
    assert [
        x
        for x in forward.facts
        if x.get("kind") in ("am_limiter", "am_memory_erasure", "synthetic_private_memory")
    ] == [
        x
        for x in original.facts
        if x.get("kind") in ("am_limiter", "am_memory_erasure", "synthetic_private_memory")
    ]
    assert {x.id for x in forward.sheets["2"].assets if x.family == "girl"} == {
        mind.id,
        *(x.id for x in prepared.spec.assets),
    }
    assert [x for x in forward.sheets["2"].assets if x.family == "frame"] == [
        x for x in original.sheets["2"].assets if x.family == "frame"
    ]
    parked = next(x for x in bodies.bodies(forward) if x.vessel == old_pose.vessel_id)
    assert parked.assets == (old_physical,) and parked.occupant is None
    with ledger.engine.connect() as c:
        actual = resolve(forward, actor, profiles(c, ledger.campaign_id))
        assert (
            actual.controller == 2
            and actual.vessel_id == prepared.spec.vessel
            and actual.girl == "AM"
        )
        assert prove(game, c, forward, changed.id) == changed
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, root)["state"] == "complete"

    # The real operator leaves the cast; hardware remains physically hooked at this location.
    casts = CastService(ActorService(MissionService(ledger)))
    cast = casts.view(ADMIN, 900)
    casts.change(
        ADMIN,
        str(uuid4()),
        900,
        cast["game_revision"],
        cast["cast_revision"],
        "withdraw",
        changed.operator,
    )

    # Real native source damages the new body, not the saved original hardware.
    game.dice.faces = (1, 1)
    social = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            context="Actual interaction from my new body",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="Actual counterattack")
    damaged = prepared.spec.assets[0]
    answer(game, PLAYER, "beneath_details", denied=(damaged.id,))
    assert game.inspect(PLAYER, social)["state"] == "complete"
    tick(worker, gateway, 5)
    active = state(game)
    assert next(x for x in active.sheets["2"].assets if x.id == damaged.id).damaged
    assert bodies.current(active, actor).assets[0].damaged
    assert game.dice.calls == calls + 1
    with pytest.raises(WorkflowError, match="original humans"):
        service.view(OTHER, changed.id)
    source_view = service.view(ADMIN, changed.id)
    disconnected = service.connection(
        ADMIN,
        "actual-body-disconnect",
        changed.id,
        source_view["revision"],
        False,
        "The actual pair is temporarily unplugged",
    )
    assert disconnected["connected"] is False
    disconnected_state = state(game)
    with pytest.raises(ValueError, match="still hooked up"):
        service.return_body(PLAYER, str(uuid4()), changed.id, disconnected_state.revision)
    assert state(game) == disconnected_state and game.dice.calls == calls + 1
    service.connection(
        ADMIN,
        "actual-body-reconnect",
        changed.id,
        state(game).revision,
        True,
        "The actual same bodies are physically hooked back up",
    )

    async def own_return():
        own = current(2, 961007)
        own.channel_id = 901
        await own.response.defer(ephemeral=True)
        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(PLAYER) if x.task == "m3_am_body" and x.identity == changed.id
        )
        assert not item.incoming and item.state == "established"
        await InboxView(inbox, 2).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "Prepared arm [damaged]" in form.text()
        # The integrated owner menu also opens the independently source-proved
        # spinal controls; this does not create or replace a body hookup.
        assert set(dict(next(x for x in form.fields if x.key == "operation").options)) == {
            "return",
            "spinal",
        }
        expected = service.view(PLAYER, changed.id)["revision"]
        form.values.update(operation=("return",), account="")
        await form.confirm.callback(current(2, 961008))
        assert form.completed
        assert (
            service.return_body(PLAYER, "961008", changed.id, expected)["vessel"]
            == old_pose.vessel_id
        )

    asyncio.run(own_return())
    final = state(game)
    returned = bodies.swap(final, changed.id)
    assert returned.returned_event and game.dice.calls == calls + 1
    assert next(x for x in final.placements if x.actor == actor).vessel_id == old_pose.vessel_id
    assert bodies.current(final, actor).vessel == old_pose.vessel_id
    assert bodies.current(final, actor).assets == (old_physical,)
    assert {x.id: x for x in final.sheets["2"].assets} == {
        x.id: x for x in original.sheets["2"].assets
    }
    assert final.sheets["2"].identities == active.sheets["2"].identities
    assert final.sheets["2"].tags == active.sheets["2"].tags
    assert final.sheets["2"].heat == active.sheets["2"].heat
    assert final.sheets["2"].permissions == active.sheets["2"].permissions
    assert final.actor_bonds == active.actor_bonds and final.bonds == active.bonds
    inactive = next(x for x in bodies.bodies(final) if x.vessel == prepared.spec.vessel)
    assert inactive.occupant is None
    assert next(x for x in inactive.assets if x.id == damaged.id) == damaged.model_copy(
        update=dict(damaged=True)
    )
    assert next(x for x in final.sheets["2"].assets if x.id == old_physical.id) == old_physical
    assert final.sheets["3"] == active.sheets["3"]
    assert CANARY not in str(service.view(PLAYER, changed.id))

    async def reopen_saved_hardware():
        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(PLAYER) if x.task == "m3_am_body" and x.identity == changed.id
        )
        assert not item.incoming
        own = current(2, 961009)
        own.channel_id = 902
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(own, item)
        assert "Prepared arm [damaged]" in str(own.edit_original_response.call_args)

    asyncio.run(reopen_saved_hardware())
    with ledger.engine.connect() as c:
        assert prove(game, c, final, changed.id) == returned
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert game.lock(c, 900)["state"] == "released"
    assert game.rebuild() > 0 and state(game) == final


def test_actual_carried_tool_conveyance_swap_new_body_effect_and_owned_return(
    ledger, tmp_path, monkeypatch
):
    """Deferred normal: actual existing object custody survives each authored physical move."""
    from test_items import carried_asset

    from girlframe.discord_adapter.m3_am_body import open_body
    from girlframe.services.m3_am_body import prove_conveyance
    from girlframe.services.m3_items import prove_item

    game, maintenance, root, action, worker, gateway, _ = rolled(
        ledger, tmp_path, monkeypatch, (4, 5), marked=True, choose_identity=False
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"discipline"}}
            ),
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            ),
        }
    )
    with ledger.transaction() as c:
        actual = place(state(game), 3)
        game.event(c, 1, str(uuid4()), "synthetic.actual_other_body_presence", actual)
    original = state(game)
    actor = current_ref(original, 2)
    tool = next(x for x in original.sheets["2"].assets if x.family == "girl")
    carried_asset(game, PLAYER, tool)
    original = state(game)
    item = next(x for x in original.held_items if x.asset_id == tool.id)
    service = BodyService(game)

    async def native_prepare():
        own = current(1, 962001)
        await own.response.defer(ephemeral=True)
        await open_prepare(own, service, maintenance)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert item.id in dict(next(x for x in form.fields if x.key == "carried_items").options)
        assert tool.id not in dict(next(x for x in form.fields if x.key == "mind_assets").options)
        form.values.update(
            vessel="actual-tool-carrying-puppet",
            label="Actual prepared local puppet",
            source="Actual supplied empty processor/body; the original tool is not new hardware",
            processing=("yes",),
            unoccupied=("yes",),
            medical=("fit",),
            mind_assets=(),
            carried_items=(item.id,),
            assets="Actual arm | Supplied actuator | intact | clear\n"
            "Actual skin | Supplied covering | intact | clear",
        )
        reply = current(1, 962002)
        await form.confirm.callback(reply)
        assert form.completed, reply.edit_original_response.call_args_list

    asyncio.run(native_prepare())
    prepared = bodies.preparations(state(game))[-1]
    answer(game, ADMIN, "am_code_options", options=("body",))
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_body")
    before = state(game)
    calls = game.dice.calls
    with pytest.raises(WorkflowError, match="select every actual owned held object"):
        game.respond(
            ADMIN,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=(prepared.id,), text="Mind movement alone never moves the actual tool"
            ),
        )
    assert state(game) == before and game.dice.calls == calls

    async def native_swap():
        own = current(1, 962003)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            body=(prepared.id,),
            carried_items=(item.id,),
            account="The original operator physically conveys this same tool into the new hands",
        )
        reply = current(1, 962004)
        await form.confirm.callback(reply)
        assert form.completed, reply.edit_original_response.call_args_list
        await form.confirm.callback(reply)

    asyncio.run(native_swap())
    forward = state(game)
    swap = bodies.swaps(forward)[-1]
    assert swap.carried_items == (item.id,) and forward.held_items == original.held_items
    assert next(x for x in forward.sheets["2"].assets if x.id == tool.id) == tool
    assert all(tool.id not in {x.id for x in b.assets} for b in bodies.bodies(forward))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert prove_item(c, game, forward, item.id) == item
        moved = prove_conveyance(game, c, forward, swap.event)
        assert moved.items == (item.id,) and moved.assets == (tool,) and moved.controller == 1
    assert forward.sheets["2"].identities == original.sheets["2"].identities
    assert forward.sheets["2"].frame_runtime == original.sheets["2"].frame_runtime
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, root)["state"] == "complete"
    casts = CastService(ActorService(MissionService(ledger)))
    cast = casts.view(ADMIN, 900)
    casts.change(
        ADMIN,
        str(uuid4()),
        900,
        cast["game_revision"],
        cast["cast_revision"],
        "withdraw",
        swap.operator,
    )
    game.dice.faces = (1, 1)
    social = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            context="Actual interaction from the new puppet while holding my same tool",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="Actual counterattack")
    damaged = prepared.spec.assets[0]
    answer(game, PLAYER, "beneath_details", denied=(damaged.id,))
    assert game.inspect(PLAYER, social)["state"] == "complete"
    tick(worker, gateway, 5)
    active = state(game)
    with pytest.raises(WorkflowError):
        service.view(OTHER, swap.id)
    with pytest.raises(ValueError):
        service.return_body(PLAYER, str(uuid4()), swap.id, active.revision)
    assert state(game) == active

    async def native_return():
        own = current(2, 962005)
        await own.response.defer(ephemeral=True)
        await open_body(own, service, swap.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            operation=("return",),
            carried_items=(item.id,),
            account="I physically convey my same actual tool back into my original body's hands",
        )
        reply = current(2, 962006)
        await form.confirm.callback(reply)
        assert form.completed, reply.edit_original_response.call_args_list
        await form.confirm.callback(reply)

    asyncio.run(native_return())
    final = state(game)
    returned = bodies.swap(final, swap.id)
    assert returned.returned_event and final.held_items == original.held_items
    assert current_ref(final, 2) == actor
    assert next(x for x in final.sheets["2"].assets if x.id == tool.id) == tool
    assert all(tool.id not in {x.id for x in b.assets} for b in bodies.bodies(final))
    assert next(x for b in bodies.bodies(final) for x in b.assets if x.id == damaged.id).damaged
    assert game.dice.calls == calls + 1
    with ledger.engine.connect() as c:
        assert prove(game, c, final, swap.id) == returned
        assert prove_item(c, game, final, item.id) == item
        assert prove_conveyance(game, c, final, returned.returned_event).controller == 2
    assert len(service.view(PLAYER, swap.id)["conveyances"]) == 2


def test_actual_spinal_unplug_body_move_return_and_reviewed_replug(ledger, tmp_path, monkeypatch):
    import test_requisition_service
    from test_enforcer_requisitions import approved
    from test_frame_control import exposed_core
    from test_janus_battery import start as start_battery
    from test_m2_game import Gateway, start
    from test_mission_service import service as campaign
    from test_world import initial

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.discord_adapter.m3_am_body import open_spinal_controls
    from girlframe.discord_adapter.m3_am_jailbroken import open_jailbroken
    from girlframe.discord_adapter.m3_am_jailbroken import open_prepare as prepare_jailbroken
    from girlframe.engine import m3_am_jailbroken as occupancy
    from girlframe.engine import m3_janus_storage as storage
    from girlframe.engine.m2 import AssetState
    from girlframe.engine.m3_janus import BATTERY, CORE
    from girlframe.engine.m3_janus_requisitions import STORAGE
    from girlframe.services.m3_am_jailbroken import JailbrokenService
    from girlframe.services.m3_frame_control import (
        FrameControlService,
        connection_endpoints,
    )
    from girlframe.services.m3_frame_control import (
        prove as prove_contact,
    )
    from girlframe.services.m3_janus_requisitions import JanusRequisitionService
    from girlframe.services.m3_janus_storage import StorageService

    # Genuine initial AM creation, followed by the existing actual Core request/review.
    monkeypatch.setattr(
        test_requisition_service,
        "service",
        lambda store, frame: campaign(store, girl="AM", frame=frame),
    )
    game, actor, core = exposed_core(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(CORE, BATTERY, STORAGE, occupancy.RULE))
    with ledger.transaction() as c:
        original = state(game)
        original.world = initial()
        original = place(original, 2, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.actual_am_original_body_position", original)
    pose = next(x for x in state(game).placements if x.actor == actor)
    source = FrameControlService(game)

    def connect():
        identity = source.propose(
            PLAYER,
            str(uuid4()),
            900,
            actor,
            core,
            "My original physical neural jack actually reaches this exposed Core's spine",
        )["id"]
        source.decide(
            ADMIN,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            "I review the actual jack, original vessels, spinal access and real reach",
        )
        return identity

    contact = connect()
    original_contact = next(x for x in state(game).neural_connections if x.id == contact)
    assert original_contact.caster_vessel == pose.vessel_id
    assert original_contact.battery_vessel
    service = JailbrokenService(game)
    before = state(game).model_dump_json()
    spec = bodies.BodySpec(
        vessel="actual-spinal-test-spare",
        label="Actual supplied spare puppet",
        source="Actual human-authored empty local processing-capable hardware",
        processing_confirmed=True,
        unoccupied_confirmed=True,
        medical="fit",
        assets=(
            AssetState(
                id="actual-spinal-test-spare:physical:0",
                family="girl",
                name="Actual spare arm",
                description="Supplied mechanical arm",
            ),
        ),
    )
    # Even a connection without any temporary mental Asset requires an actual route/unplug.
    with pytest.raises((ValueError, WorkflowError), match="SOURCE_NEURAL_ROUTE_REQUIRED"):
        service.prepare(PLAYER, str(uuid4()), actor, state(game).revision, spec)
    assert state(game).model_dump_json() == before
    with pytest.raises(WorkflowError):
        BodyService(game).neural_controls(OTHER, actor)

    acquisitions = JanusRequisitionService(game)
    menu = acquisitions.menu(PLAYER)
    acquisitions.buy_rule(
        PLAYER, str(uuid4()), menu["source_sha256"], STORAGE, "Actual owned Void Storage"
    )
    worker, gateway = GameWorker(game), Gateway()

    def battery():
        game.dice.faces = (2, 2)
        identity = start_battery(game, core)
        tick(worker, gateway, 3)
        assert game.inspect(PLAYER, identity)["receipt"]  # genuine worker progression
        pass_tags(game)
        answer(game, PLAYER, "janus_select", options=("cognition", "offset"))
        tick(worker, gateway, 4)
        assert game.inspect(PLAYER, identity)["state"] == "complete"
        return next(x for x in state(game).battery_links if x.source_action == identity)

    first = battery()
    temporary = {x.source.asset_id for x in first.borrowed}
    assert len(temporary) == 2
    frame_asset = next(x for x in state(game).sheets["2"].assets if x.family == "frame")
    game.dice.faces = (4, 5)
    dive = start(game, play="dive_deep")
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, dive)["receipt"]
    pass_tags(game)
    answer(game, PLAYER, "dive_select", options=("void_and_unmark_all",), text="Actual communion")
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"asset": frame_asset.id, "storage": "yes"},
        text="Store this actual same-current-Frame Void point through this real Core",
    )
    tick(worker, gateway, 4)
    (point,) = storage.points(state(game))
    assert StorageService(game).view(PLAYER)["points"][0]["active"]
    connected = state(game)

    async def unplug():
        own = current(2, 984001)
        await own.response.defer(ephemeral=True)
        await open_spinal_controls(own, BodyService(game), actor)
        menu = own.edit_original_response.call_args.kwargs["view"]
        assert not await menu.interaction_check(current(3))
        menu.values.update(source=(contact,))
        select = current(2, 984002)
        await menu.confirm.callback(select)
        form = select.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="I physically remove my own jack from the original Core")
        confirmation = current(2, 984003)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(unplug())
    unplugged = state(game)
    assert not temporary & {x.id for x in unplugged.sheets["2"].assets}
    assert storage.points(unplugged) == (point,)
    assert not StorageService(game).view(PLAYER)["points"][0]["active"]
    assert (
        source.unplug(
            PLAYER,
            "984003",
            contact,
            connected.revision,
            "I physically remove my own jack from the original Core",
        )["phase"]
        == "unplugged"
    )
    with ledger.engine.connect() as c:
        ended = prove_contact(game, c, unplugged, contact)
        assert connection_endpoints(game, c, ended) == (
            original_contact.caster_vessel,
            original_contact.battery_vessel,
        )
        forged = unplugged.model_copy(deep=True)
        forged.neural_connections = [
            x.model_copy(update=dict(caster_vessel="unproved-new-endpoint"))
            if x.id == contact
            else x
            for x in forged.neural_connections
        ]
        with pytest.raises(WorkflowError, match="original bodies"):
            prove_contact(game, c, forged, contact)

    async def actual_move_and_return():
        own = current(2, 984004)
        await own.response.defer(ephemeral=True)
        await prepare_jailbroken(own, service)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            vessel=spec.vessel,
            label=spec.label,
            source=spec.source,
            processing=("yes",),
            empty=("yes",),
            medical=("fit",),
            assets="Actual spare arm | Supplied mechanical arm | intact | clear",
        )
        confirmation = current(2, 984005)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)
        for number, vessel in ((984006, spec.vessel), (984008, pose.vessel_id)):
            own = current(2, number)
            await own.response.defer(ephemeral=True)
            await open_jailbroken(own, service)
            form = own.edit_original_response.call_args.kwargs["view"]
            form.values.update(operation=("occupy:" + vessel,))
            confirmation = current(2, number + 1)
            await form.confirm.callback(confirmation)
            assert form.completed, str(confirmation.edit_original_response.call_args)
            with ledger.engine.connect() as c:
                actual = resolve(state(game), actor, profiles(c, ledger.campaign_id))
                assert actual.vessel_id == vessel and actual.ref == actor
                if vessel == spec.vessel:
                    assert any(x.name == "Actual spare arm" for x in actual.assets)
            assert not bodies.spinal_links(state(game), actor)
            assert storage.points(state(game)) == (point,)
            assert not StorageService(game).view(PLAYER)["points"][0]["active"]

    calls = game.dice.calls
    asyncio.run(actual_move_and_return())
    assert len(occupancy.history(state(game), actor)) == 2 and game.dice.calls == calls
    replacement = connect()
    assert replacement != contact
    second = battery()
    assert second.connection == replacement and second.id != first.id
    assert not temporary & {x.id for x in state(game).sheets["2"].assets}
    assert storage.points(state(game)) == (point,)
    assert StorageService(game).view(PLAYER)["points"][0]["active"]
    readback = BodyService(game).neural_controls(PLAYER, actor)
    assert {x["phase"] for x in readback["connections"]} == {"unplugged", "connected"}
    assert next(x for x in readback["connections"] if x["id"] == replacement)["error"] is None
    assert next(x for x in state(game).neural_connections if x.id == contact).ended_event


def test_actual_native_connected_code_swap_preserves_original_jack_and_hooked_return(
    ledger, tmp_path, monkeypatch
):
    import test_requisition_service
    from test_enforcer_requisitions import approved
    from test_frame_control import exposed_core
    from test_janus_battery import start as start_battery
    from test_m2_game import Gateway, start
    from test_mission_service import service as campaign
    from test_world import initial

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.discord_adapter.m3_am_body import open_body
    from girlframe.discord_adapter.m3_am_neural_route import open_code_route
    from girlframe.discord_adapter.m3_frame_control import open_connection
    from girlframe.engine import m3_am as am
    from girlframe.engine import m3_am_neural_route as routes
    from girlframe.engine import m3_janus_storage as storage
    from girlframe.engine.m3_janus import BATTERY, CORE
    from girlframe.engine.m3_janus_link import has_mental_channel
    from girlframe.engine.m3_janus_requisitions import STORAGE
    from girlframe.services.m3_am_code import CodeService
    from girlframe.services.m3_am_neural_route import RouteService, prove_route
    from girlframe.services.m3_frame_control import FrameControlService
    from girlframe.services.m3_janus_play import BatteryService
    from girlframe.services.m3_janus_requisitions import JanusRequisitionService

    selected = test_creation_review.selected

    def real_assets(girl="MOCKINGBIRD", frame="JANUS-B"):
        actual = selected(girl, frame)
        if girl == "AM":
            return actual.model_copy(
                update=dict(
                    girl_assets=(
                        AssetChoice(
                            name="Doll-Joints", description="Actual original physical joints"
                        ),
                        AssetChoice(
                            name="Perfect Affect", description="Actual original expression hardware"
                        ),
                    )
                )
            )
        return actual

    monkeypatch.setattr(test_creation_review, "selected", real_assets)
    monkeypatch.setattr(
        test_requisition_service,
        "service",
        lambda store, frame: campaign(store, girl="AM", frame=frame),
    )
    game, actor, core = exposed_core(ledger, tmp_path, monkeypatch)
    approved(
        ledger, game, tmp_path, monkeypatch, extra=(CORE, BATTERY, STORAGE, am.RULE, code.RULE)
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.actual_connected_code_bodies", canon)
    service, body = CodeService(game), BodyService(game)
    operator = current_ref(state(game), 3)
    maintenance = service.propose_operator(
        PLAYER,
        "actual-connected-code-proposal",
        900,
        operator,
        state(game).revision,
        "Actual Pilot has physical access to my original circuits",
    )["id"]
    assert code.session(state(game), maintenance).root is None
    original_pose = next(x for x in state(game).placements if x.actor == actor)
    original_asset = next(
        x for x in state(game).sheets["2"].assets if x.family == "girl" and not x.void
    )

    async def prepare():
        owner = current(1, 996001)
        await owner.response.defer(ephemeral=True)
        await open_prepare(owner, body, maintenance)
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            vessel="actual-code-relay-destination",
            label="Actual Code prepared puppet",
            source="Actual supplied local empty puppet with independent requisite processor",
            processing=("yes",),
            unoccupied=("yes",),
            medical=("fit",),
            mind_assets=(),
            assets="Real arm | Actual supplied actuator | intact | clear",
        )
        actual = current(1, 996002)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(prepare())
    preparation = next(x for x in bodies.preparations(state(game)) if x.maintenance == maintenance)
    assert preparation.fact_author and preparation.controller == 3
    contact = FrameControlService(game)
    connection = contact.propose(
        PLAYER,
        "actual-code-spinal-contact",
        900,
        actor,
        core,
        "My actual original jack reaches the same exposed Core",
    )["id"]
    contact.decide(
        ADMIN,
        "actual-code-contact-reviewed",
        connection,
        state(game).revision,
        True,
        "Original actual endpoint and physical neural contact reviewed",
    )
    assert code.session(state(game), maintenance).root is None
    acquisition = JanusRequisitionService(game)
    menu = acquisition.menu(PLAYER)
    acquisition.buy_rule(
        PLAYER,
        "actual-code-relay-storage",
        menu["source_sha256"],
        STORAGE,
        "Actual paid original Frame Void Storage",
    )
    worker, gateway = GameWorker(game), Gateway()
    game.dice.faces = (2, 2)
    battery = start_battery(game, core)
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, battery)["receipt"]
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "janus_select",
        options=("cognition", "question"),
        text="PRIVATE_CODE_RELAY_CORE_QUESTION",
    )
    answer(game, OTHER, "janus_answer", text="PRIVATE_CODE_RELAY_CORE_ANSWER")
    tick(worker, gateway, 4)
    link = next(x for x in state(game).battery_links if x.source_action == battery)
    mental = next(
        x
        for x in state(game).sheets["2"].assets
        if x.battery_asset and x.battery_asset.link == link.id
    )
    game.dice.faces = (4, 5)
    dive = start(game, play="dive_deep")
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, dive)["receipt"]
    pass_tags(game)
    answer(game, PLAYER, "dive_select", options=("void_and_unmark_all",), text="Actual communion")
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"asset": original_asset.id, "storage": "yes"},
        text="Actual stored Void changes this exact original physical component",
    )
    tick(worker, gateway, 4)
    point = storage.points(state(game))[0]
    route_service = RouteService(game)
    before = state(game)
    calls = game.dice.calls

    async def source_fact():
        owner = current(2, 996003)
        await owner.response.defer(ephemeral=True)
        await open_code_route(owner, route_service, preparation.id)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(
            account=(
                "My actual original hardware remains powered at its fixed jack. Its real relay "
                "continues through this already prepared independent processor, "
                "without moving the jack."
            )
        )
        actual = current(2, 996004)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(source_fact())
    route = routes.records(state(game))[0]
    assert route.code_maintenance == maintenance and route.moves == ()
    assert state(game).sheets == before.sheets and game.dice.calls == calls
    service.confirm(
        OTHER,
        "actual-code-real-operator-confirmation",
        maintenance,
        state(game).revision,
        "My actual hands operate the same original AM circuits",
    )
    root = code.session(state(game), maintenance).root
    tick(worker, gateway, 3)
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=code.PLAY,
            parent=root,
            source_work=maintenance,
            target_actor=operator,
            heat=0,
            trigger_confirmed=True,
            context="Actual connected Code body transfer",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for human in (PLAYER, OTHER, ADMIN):
        if any(x["kind"] == "tag_window" for x in game.choices(human)):
            answer(game, human, "tag_window", options=("pass",))
    answer(game, OTHER, "am_code_options", options=("body",))

    async def swap():
        row = next(x for x in game.choices(OTHER) if x["kind"] == "am_code_body")
        owner = current(3, 996005)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            body=(preparation.id,),
            neural_route=(route.id,),
            account="Actual original Pilot performs this real connected Code swap",
        )
        actual = current(3, 996006)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(swap())
    changed = state(game)
    actual_swap = bodies.swap(changed, code.session(changed, maintenance).body_swap)
    assert actual_swap.controller == 3 and actual_swap.neural_route == route.id
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert sum(x.id == mental.id for x in changed.sheets["2"].assets) == 1
    assert original_asset.id not in {x.id for x in changed.sheets["2"].assets}
    assert has_mental_channel(changed, actor, core)
    message = (
        PLAYER,
        "actual-code-relay-message",
        link.id,
        changed.revision,
        actor,
        "PRIVATE_MESSAGE_THROUGH_ACTUAL_CODE_RELAY",
    )
    messages = BatteryService(game)
    assert messages.send(*message) == messages.send(*message)
    parked = next(
        x
        for x in body.view(PLAYER, actual_swap.id)["bodies"]
        if x["vessel"] == original_pose.vessel_id
    )
    assert next(x for x in parked["assets"] if x["id"] == original_asset.id)["void"]
    assert point in storage.active(changed, actor)
    with ledger.engine.connect() as c:
        assert prove_route(game, c, changed, route.id).moves[0].swap == actual_swap.id
        assert prove(game, c, changed, actual_swap.id) == actual_swap
    tick(worker, gateway, 5)

    async def return_and_unplug():
        owner = current(2, 996007)
        await owner.response.defer(ephemeral=True)
        await open_body(owner, body, actual_swap.id)
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(operation=("return",))
        actual = current(2, 996008)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)
        owner = current(2, 996009)
        await owner.response.defer(ephemeral=True)
        await open_connection(owner, contact, connection)
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            account="Returned to my actual original body, I physically unplug my jack"
        )
        actual = current(2, 996010)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(return_and_unplug())
    final = state(game)
    saved = routes.get(final, route.id)
    assert len(saved.moves) == 2 and saved.moves[-1].vessel == original_pose.vessel_id
    assert not bodies.spinal_links(final, actor) and routes.active_route(final, actor) is None
    assert mental.id not in {x.id for x in final.sheets["2"].assets}
    assert storage.points(final) == (point,) and point not in storage.active(final, actor)
    assert not next(x for x in final.sheets["2"].assets if x.id == original_asset.id).void
    assert game.dice.calls == calls + 1
    with ledger.engine.connect() as c:
        assert prove_route(game, c, final, route.id) == saved
    assert "PRIVATE_CODE_RELAY_CORE_ANSWER" not in str(route_service.view(PLAYER, route.id))


def _native_adjusted_processing_body(store, tmp_path, monkeypatch, asset_lines):
    game, maintenance, root, action, worker, gateway, _ = rolled(
        store, tmp_path, monkeypatch, (4, 5), choose_identity=False
    )
    source = BodyService(game)
    original = state(game).model_copy(deep=True)

    async def actual_body():
        handler = current(1, 997001)
        await handler.response.defer(ephemeral=True)
        await open_prepare(handler, source, maintenance)
        form = handler.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            vessel="actual-purpose-built-processor",
            label="Actual supplied processing body",
            source="Actual supplied independent processor and current physical condition, reviewed",
            processing=("yes",),
            unoccupied=("yes",),
            medical=("fit",),
            mind_assets=(),
            assets=asset_lines,
        )
        actual = current(1, 997002)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)
        answer(game, ADMIN, "am_code_options", options=("body",))
        row = next(x for x in game.choices(ADMIN) if x["kind"] == "am_code_body")
        handler = current(1, 997003)
        await handler.response.defer(ephemeral=True)
        await open_choice(handler, game, row["id"])
        form = handler.edit_original_response.call_args.kwargs["view"]
        preparation = next(
            x for x in bodies.preparations(state(game)) if x.maintenance == maintenance
        )
        form.values.update(
            body=(preparation.id,), account="Actual performed circuit/body adjustment"
        )
        actual = current(1, 997004)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(actual_body())
    swap = bodies.swap(state(game), code.session(state(game), maintenance).body_swap)
    return game, source, swap, original, root, action, worker, gateway


def test_native_empty_real_processor_is_not_battle_injury_and_can_keep_then_return(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m3_am_body import open_body
    from girlframe.engine.m3_actor_bonds import is_helpless

    game, source, swap, before, root, action, worker, gateway = _native_adjusted_processing_body(
        ledger, tmp_path, monkeypatch, "none"
    )
    actual = state(game)
    actor = current_ref(actual, 2)
    assert not any(x.family == "girl" for x in actual.sheets["2"].assets)
    assert not is_helpless(actual, actor)
    assert actual.helpless_conditions == before.helpless_conditions
    assert actual.sheets["2"].helpless_against == before.sheets["2"].helpless_against
    assert [x for x in actual.sheets["2"].assets if x.family == "frame"] == [
        x for x in before.sheets["2"].assets if x.family == "frame"
    ]
    assert actual.career_archives == before.career_archives and not actual.void_thresholds
    assert (
        game.inspect(PLAYER, action)["state"] == game.inspect(PLAYER, root)["state"] == "complete"
    )
    tick(worker, gateway, 5)
    casts = CastService(ActorService(MissionService(ledger)))
    cast = casts.view(ADMIN, 900)
    casts.change(
        ADMIN,
        str(uuid4()),
        900,
        cast["game_revision"],
        cast["cast_revision"],
        "withdraw",
        swap.operator,
    )
    game.dice.faces = (4, 5)
    keep = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            trigger_confirmed=True,
            context="The same AM uses this real processor to keep her head",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, ADMIN):
        if any(x["kind"] == "tag_window" for x in game.choices(viewer)):
            answer(game, viewer, "tag_window", options=("pass",))
    answer(game, PLAYER, "actor_keep", options=("sexy", "tough"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual same-mind calm response")
    assert game.inspect(PLAYER, keep)["state"] == "complete"
    tick(worker, gateway, 5)

    async def actual_return():
        owner = current(2, 997005)
        await owner.response.defer(ephemeral=True)
        await open_body(owner, source, swap.id)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert "no physical Assets" in form.instructions
        form.values.update(operation=("return",))
        actual = current(2, 997006)
        await form.confirm.callback(actual)
        assert form.completed, str(actual.edit_original_response.call_args)

    asyncio.run(actual_return())
    final = state(game)
    assert next(x for x in final.placements if x.actor == actor).vessel_id == swap.original_vessel
    assert [x for x in final.sheets["2"].assets if x.family == "girl"] == [
        x for x in before.sheets["2"].assets if x.family == "girl"
    ]
    assert not is_helpless(final, actor)
    with ledger.engine.connect() as c:
        assert prove(game, c, final, swap.id).returned_event


def test_actual_all_void_body_holds_code_until_real_entry_questions_and_rebirth(
    ledger, tmp_path, monkeypatch
):
    from test_void_service import five_no, respond

    from girlframe.services.m3_am_body_consequences import prove_void_source
    from girlframe.services.m3_void import VoidService

    game, _, swap, before, root, action, worker, gateway = _native_adjusted_processing_body(
        ledger,
        tmp_path,
        monkeypatch,
        "Void actuator | Actual supplied already-corrupted physical component | intact | void",
    )
    with ledger.engine.connect() as c:
        rows = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.kind == "void_threshold",
                    t.m3["m3_required_work"].c.revision == 1,
                )
            )
            .mappings()
            .all()
        )
        row = next(
            x for x in rows if json.loads(x["body_json"]).get("reason") == "am_body_adjustment"
        )
        body = json.loads(row["body_json"])
        prove_void_source(game, c, dict(row), body, current_ref(state(game), 2))
        assert body["source_id"] == swap.id and body["adjustment_event"] == swap.event
        assert body["source_action"] == action and body["details"] == dict(family="girl")
        assert game.action(c, action)["data"]["am_body_void"]["work"] == row["id"]
    assert game.inspect(PLAYER, action)["state"] == "awaiting_choices"
    assert game.inspect(PLAYER, root)["state"] != "complete"
    service = VoidService(ledger)
    work = row["id"]
    assert service.get(PLAYER, work)["stage"] == "allured"
    # This performs actual original Frame entry and five independently owned honest answers.
    five_no(service, work)
    inside = state(game)
    assert next(x for x in inside.placements if x.actor == swap.actor).mode == "inside_frame"
    assert game.inspect(PLAYER, action)["state"] == "awaiting_choices"
    data = service.get(PLAYER, work)
    choice = data["rebirth_choice"] | dict(
        retained_identities=[before.sheets["2"].identities[1].id],
        new_identities=["Actual new self"],
        account="Actual owner chooses this real rebirth",
    )
    respond(service, work, "save_rebirth", dict(choice=choice, account="Actual saved own choice"))
    respond(service, work, "rebirth", dict(choice=choice, account="Actual source-owned conversion"))
    final = state(game)
    assert service.get(PLAYER, work)["stage"] == "converted"
    assert "2" not in final.sheets
    assert any(x.actor == swap.actor and x.ending == "harpy" for x in final.career_archives)
    assert final.harpy_states[-1].old_body_vessel == swap.new_vessel
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, root)["state"] == "complete"
    tick(worker, gateway, 6)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
