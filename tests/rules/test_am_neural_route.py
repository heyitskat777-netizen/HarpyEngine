"""One actual continuous AM move, mental channel and exact parked bodily Void point.

Authored for parent integration/final P1; no worker pytest or collection.
"""

import asyncio
from uuid import uuid4

import pytest
import test_creation_review
import test_requisition_service
from test_enforcer_requisitions import approved
from test_frame_control import exposed_core
from test_janus_battery import start as start_battery
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, start, state, tick
from test_mission_service import service as campaign
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_am_neural_route import open_neural_route
from girlframe.discord_adapter.m3_frame_control import open_connection
from girlframe.engine import m3_am_body as hardware
from girlframe.engine import m3_am_jailbroken as occupancy
from girlframe.engine import m3_am_neural_route as rules
from girlframe.engine import m3_janus_storage as storage
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_janus import BATTERY, CORE
from girlframe.engine.m3_janus_link import has_mental_channel
from girlframe.engine.m3_janus_requisitions import STORAGE
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_am_jailbroken import JailbrokenService
from girlframe.services.m3_am_neural_route import RouteService, prove_route
from girlframe.services.m3_frame_control import FrameControlService
from girlframe.services.m3_janus_play import BatteryService
from girlframe.services.m3_janus_requisitions import JanusRequisitionService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_actual_continuous_route_preserves_mental_ids_parked_void_and_physical_unplug(
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
                            name="Doll-Joints", description="Actual original puppet joints"
                        ),
                        AssetChoice(
                            name="Perfect Affect",
                            description="Actual original physical expression hardware",
                        ),
                    )
                )
            )
            if girl == "AM"
            else value
        )

    monkeypatch.setattr(test_creation_review, "selected", actual_assets)
    monkeypatch.setattr(
        test_requisition_service,
        "service",
        lambda store, frame: campaign(store, girl="AM", frame=frame),
    )
    game, actor, core = exposed_core(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(CORE, BATTERY, STORAGE, occupancy.RULE))
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.actual_continuous_route_baseline", actual)
    before = state(game)
    pose = next(x for x in before.placements if x.actor == actor)
    original_asset = next(x for x in before.sheets["2"].assets if x.family == "girl" and not x.void)
    source = JailbrokenService(game)
    spec = hardware.BodySpec(
        vessel="actual-neural-route-spare",
        label="Actual prepared processing puppet",
        source="Actual supplied empty puppet with independent requisite processing hardware",
        processing_confirmed=True,
        unoccupied_confirmed=True,
        medical="fit",
        assets=(
            AssetState(
                id="actual-neural-route-arm",
                family="girl",
                name="Actual new arm",
                description="The supplied new body's mechanical arm",
            ),
        ),
    )
    # Genuine preparation precedes spinal contact; no source/prepare-guard bypass.
    source.prepare(PLAYER, "actual-prior-route-preparation", actor, before.revision, spec)
    contact = FrameControlService(game)
    identity = contact.propose(
        PLAYER,
        "actual-route-contact",
        900,
        actor,
        core,
        "My actual original jack reaches this Core's exposed spine",
    )["id"]
    contact.decide(
        ADMIN,
        "actual-route-contact-review",
        identity,
        state(game).revision,
        True,
        "Original hardware, jack, reach and actual spinal contact reviewed",
    )
    acquisitions = JanusRequisitionService(game)
    menu = acquisitions.menu(PLAYER)
    acquisitions.buy_rule(
        PLAYER,
        "actual-route-storage",
        menu["source_sha256"],
        STORAGE,
        "Actual paid original JANUS Void Storage",
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
        text="PRIVATE_ACTUAL_CORE_QUESTION",
    )
    answer(game, OTHER, "janus_answer", text="PRIVATE_ACTUAL_ORIGINAL_CORE_ANSWER")
    tick(worker, gateway, 4)
    link = next(x for x in state(game).battery_links if x.source_action == battery)
    (mental,) = tuple(
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
        text="The exact physical original-body component bears this stored Void change",
    )
    tick(worker, gateway, 4)
    (point,) = storage.points(state(game))
    assert point.family == "girl" and point.asset == original_asset.id
    assert point in storage.active(state(game), actor)
    service = RouteService(game)
    calls = game.dice.calls

    async def actual_route():
        own = current(2, 993001)
        await own.response.defer(ephemeral=True)
        await open_neural_route(own, service)
        menu = own.edit_original_response.call_args.kwargs["view"]
        assert not await menu.interaction_check(current(3))
        menu.values.update(operation=("propose",))
        choose = current(2, 993002)
        await menu.confirm.callback(choose)
        form = choose.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            destination=(spec.vessel,),
            account=(
                "The actual original AM interface remains powered and jacked into this same Core; "
                "my nanomechanical interface continues through that real hardware while I occupy "
                "the already prepared independent processor. No jack is moved or body copied."
            ),
        )
        confirmation = current(2, 993003)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)
        move = confirmation.edit_original_response.call_args.kwargs["view"]
        move.values.update(destination=(spec.vessel,))
        perform = current(2, 993004)
        await move.confirm.callback(perform)
        assert move.completed, str(perform.edit_original_response.call_args)

    asyncio.run(actual_route())
    forward = state(game)
    (route,) = rules.records(forward)
    assert route.actor == actor and route.endpoints[0].vessel == pose.vessel_id
    assert route.moves[0].vessel == spec.vessel and route.moves[0].previous == pose.vessel_id
    assert hardware.spinal_links(forward, actor) == (identity,)
    assert rules.active_route(forward, actor, identity) == route
    assert has_mental_channel(forward, actor, core)
    assert next(x for x in forward.sheets["2"].assets if x.id == mental.id) == mental
    assert original_asset.id not in {x.id for x in forward.sheets["2"].assets}
    assert all(mental.id not in {a.id for a in body.assets} for body in hardware.bodies(forward))
    effective = storage.effective_body_assets(forward, actor, pose.vessel_id)
    assert next(x for x in effective if x.id == original_asset.id).void
    assert next(x for x in hardware.bodies(forward) if x.vessel == pose.vessel_id).occupant is None
    with ledger.engine.connect() as c:
        assert prove_route(game, c, forward, route.id) == route
        actual = resolve(forward, actor, profiles(c, ledger.campaign_id))
        assert actual.vessel_id == spec.vessel and any(
            x.id == spec.assets[0].id for x in actual.assets
        )
        assert original_asset.id not in {x.id for x in actual.assets}
    with pytest.raises(WorkflowError):
        service.view(OTHER, route.id)
    snapshot = forward.model_dump_json()
    with pytest.raises(WorkflowError, match="physical endpoint"):
        contact.unplug(
            PLAYER,
            "no-remote-limb",
            identity,
            forward.revision,
            "I have not returned to my original physical endpoint",
        )
    assert state(game).model_dump_json() == snapshot
    messages = BatteryService(game)
    message_args = (
        PLAYER,
        "actual-routed-message",
        link.id,
        state(game).revision,
        actor,
        "PRIVATE_MESSAGE_FROM_ACTUAL_NEW_BODY",
    )
    assert messages.send(*message_args) == messages.send(*message_args)
    assert state(game).battery_links[-1].messages[-1].actor == actor
    assert game.dice.calls == calls

    async def actual_return_and_unplug():
        own = current(2, 993005)
        await own.response.defer(ephemeral=True)
        await open_neural_route(own, service, route.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(destination=(pose.vessel_id,))
        confirmation = current(2, 993006)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)
        own = current(2, 993007)
        await own.response.defer(ephemeral=True)
        await open_connection(own, contact, identity)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Back in my actual original body, I physically remove my jack")
        confirmation = current(2, 993008)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(actual_return_and_unplug())
    final = state(game)
    (saved,) = rules.records(final)
    assert len(saved.moves) == 2 and saved.moves[-1].vessel == pose.vessel_id
    assert not hardware.spinal_links(final, actor) and rules.active_route(final, actor) is None
    assert not has_mental_channel(final, actor, core)
    assert mental.id not in {x.id for x in final.sheets["2"].assets}
    assert storage.points(final) == (point,) and point not in storage.active(final, actor)
    assert not next(x for x in final.sheets["2"].assets if x.id == original_asset.id).void
    assert all(mental.id not in {a.id for a in body.assets} for body in hardware.bodies(final))
    assert game.dice.calls == calls and service.view(PLAYER, route.id)["phase"] == "ended"
    with ledger.engine.connect() as c:
        assert prove_route(game, c, final, route.id) == saved
    assert "PRIVATE_ACTUAL_ORIGINAL_CORE_ANSWER" not in str(service.view(PLAYER, route.id))
