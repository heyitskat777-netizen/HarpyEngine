"""Actual circuits transfer, real new-body damage, and same-AM hooked return."""

import asyncio
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
        assert set(dict(next(x for x in form.fields if x.key == "operation").options)) == {"return"}
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
