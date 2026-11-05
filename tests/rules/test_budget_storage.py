"""Two ordinary storage flows with real source, physical and Budget evidence."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_physical_operations import place
from test_punishment_service import submit
from test_strain import facts
from test_strain_effect_service import selected
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_budget_storage import open_storage
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import QUESTIONS, PlayInput
from girlframe.engine.m3_budget_storage import get
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_storage import StorageService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def setup(store, *, prior_success=False):
    strain, game = ready(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    if prior_success:
        mission = strain.missions.offer(
            ADMIN, str(uuid4()), "Actual prior successful mission", (2, 3)
        )
        for viewer in (PLAYER, OTHER):
            mission = strain.missions.respond(
                viewer, str(uuid4()), mission["id"], mission["revision"], "accept"
            )
        mission = strain.missions.start(ADMIN, str(uuid4()), mission["id"], mission["revision"])
        mission = strain.missions.end(ADMIN, str(uuid4()), mission["id"], mission["revision"], True)
        discipline = PunishmentService(store, strain.missions.access.registry)
        for work in strain.missions.get(ADMIN, mission["id"])["work"]:
            submit(
                discipline,
                ADMIN,
                work["id"],
                Details(
                    kind="strict_regulations",
                    regulation="Observe this actual assigned duty regulation",
                ),
                str(uuid4()),
            )
        strain.missions.complete(ADMIN, str(uuid4()), mission["id"], mission["revision"])
    with store.transaction() as c:
        placed = place(place(state(game), 2, mode="outside_frame"), 3, mode="outside_frame")
        for sheet in placed.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.prior_actual_poses", placed)
    WorldService(strain.missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="regional-superior",
            name="Actual regional superior",
            controller=1,
            jobs=("handler",),
            cell=(0, 0),
            revealed=True,
            detail="The actual ordinary higher-up who issues this order",
        ),
    )
    period = prepared(strain, game, high=frozenset({"budget"}))
    effects = EffectService(strain)
    for track, face, column in (("void", 1, 1), ("rebellion", 1, 2), ("budget", 6, 1)):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        if track != "budget":
            choice = (
                selected()
                if track == "void"
                else Choice(rule_id="strain.rebellion.low.1.2", account="Actual control slip")
            )
            effects.apply(
                ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice
            )
    source = request.id + ":effect"

    async def native_source():
        own = current(1, 78100)
        await own.response.defer(ephemeral=True)
        await open_effect(own, effects, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            storage_owner=("2",),
            storage_base=("base0",),
            storage_superior=("regional-superior",),
            account="Our actual regional superior orders this ordinary Frame stored empty",
        )
        await form.confirm.callback(current(1, 78101))
        assert form.completed

    asyncio.run(native_source())
    return StorageService(store), strain, game, period, source + ":storage"


def native(service, user, identity, action, *, label=""):
    async def run():
        own = current(user, int(uuid4()) % 10000000 + 80000)
        await own.response.defer(ephemeral=True)
        if action == "store":
            own.channel_id = 999
            inbox = InboxService(service.store)
            item = next(x for x in inbox.items(PLAYER) if x.identity == identity)
            assert item.task == "m3_budget_storage"
            await InboxView(inbox, user).route(own, item)
            assert own.channel_id == 999
        else:
            await open_storage(own, service, identity)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            action=(action,),
            label=label,
            account="Actual owned " + action + " of this original storage order",
        )
        confirmation = current(user, int(uuid4()) % 10000000 + 80000)
        await form.confirm.callback(confirmation)
        assert form.completed
        return str(confirmation.id)

    return asyncio.run(run())


def cockpit(store, game, action):
    service = PhysicalService(store)
    data = service.preview(PLAYER)
    return service.operate(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        CockpitAction(
            actor=data["actor"],
            operation=action,
            expected_position=data["position_sha256"],
            account="I actually " + action + " my original cockpit",
            confirmed=True,
        ),
    )


def test_native_empty_storage_actual_later_preparation_releases_without_body_changes(ledger):
    service, strain, game, period, identity = setup(ledger, prior_success=True)
    before = state(game)
    native(service, 2, identity, "store")
    stored = state(game)
    assert stored.placements == before.placements and stored.frame_locks == before.frame_locks == []
    assert stored.sheets == before.sheets and stored.world == before.world
    assert get(stored, identity).entries[-1].actor == 2
    with pytest.raises(WorkflowError, match="No actual later canonical"):
        service.act(
            ADMIN, str(uuid4()), identity, stored.revision, "release", "Budget remains High"
        )
    with pytest.raises(WorkflowError, match="Only"):
        service.act(
            OTHER, str(uuid4()), identity, stored.revision, "store", "I cannot store her Frame"
        )
    cycle = CycleService(strain.periods)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    next_period = strain.periods.begin(ADMIN, str(uuid4()))["id"]
    actual = state(game)
    strain.prepare(
        ADMIN,
        str(uuid4()),
        next_period,
        1,
        actual.revision,
        facts(
            no_girl_void=True,
            last_mission_success_no_frame_death_infrastructure_loss=True,
            budget_contributor_moderately_punished=True,
        ),
    )
    assert state(game).strain.levels["budget"] == "low"
    native(service, 2, identity, "release")
    after = state(game)
    released = get(after, identity)
    assert released.phase == "released" and after.placements == before.placements
    with ledger.engine.connect() as c:
        assert (
            c.scalar(sa.select(t.events.c.kind).where(t.events.c.id == released.entries[-1].proof))
            == "m3.strain_start_prepared"
        )
        assert not service.available(c, PLAYER)


def test_actual_piloting_owned_warning_distinct_postwarning_refusal_fires_alive_handler(ledger):
    service, _, game, _, identity = setup(ledger)
    before = state(game)
    native(service, 1, identity, "refuse")
    refusal = get(state(game), identity).entries[-1]
    cockpit(ledger, game, "pilot")
    with pytest.raises(WorkflowError, match="prior warning|warning before"):
        service.act(ADMIN, str(uuid4()), identity, state(game).revision, "fire", "No warning yet")
    native(service, 1, identity, "warn", label="Storage order ignored")
    warned = state(game)
    warning = get(warned, identity).entries[-1]
    assert warning.proof == refusal.event
    assert warned.handler_tags[-1].giver_actor == get(warned, identity).superior
    assert warned.handler_tags[-1].label == "Storage order ignored"
    with pytest.raises(WorkflowError, match="distinct post-order or post-warning"):
        service.act(ADMIN, str(uuid4()), identity, warned.revision, "fire", "Same old breach")
    game.dice = Dice((4, 5))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="check_sensors",
            piloting=True,
            heat=0,
            context="I continue piloting the ordered Frame to check its sensors",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    with pytest.raises(WorkflowError, match="distinct post-order or post-warning"):
        service.act(
            ADMIN, str(uuid4()), identity, state(game).revision, "fire", "Unfinished sensor Play"
        )
    pass_tags(game)
    answer(game, PLAYER, "actor_sensors", options=QUESTIONS[:2])
    answer(
        game,
        ADMIN,
        "handler_sensors",
        fields={"a1": "Actual human answer", "a2": "Second human answer"},
    )
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    firing_revision = state(game).revision
    firing_key = native(service, 1, identity, "fire")
    service.act(
        ADMIN,
        firing_key,
        identity,
        firing_revision,
        "fire",
        "Actual owned fire of this original storage order",
    )
    after = state(game)
    order = get(after, identity)
    assert order.phase == "fired"
    with ledger.engine.connect() as c:
        proof = c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.id == order.entries[-1].proof
            )
        ).one()
        assert proof.kind in ("m2.rolled", "m3.rolled")
        assert json.loads(proof.payload_json)["action_id"] == action
    assert order.handler == get(before, identity).handler
    assert after.handler_archives[-1].ending == "fired" and after.handler_archives[-1].alive
    assert after.handler_departures[-1].source_work == identity
    assert len(after.handler_archives) == len(after.handler_departures) == 1
    assert after.placements == warned.placements and after.frame_locks == before.frame_locks == []
    assert after.sheets["2"].assets == warned.sheets["2"].assets
    assert after.world == warned.world
    assert not after.handler_persona and not after.handler_tags
