"""Real past mission cleanup scene or single original exposure and Void continuation."""

import asyncio
from uuid import uuid4

import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_punishment_service import ended, submit
from test_strain_service import D6, prepared
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_budget_cleanup import get
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_void import VoidService
from girlframe.services.m3_world import WorldService


class Draw:
    calls = 0

    def choose(self, upper):
        assert upper == 2
        self.calls += 1
        return 0


def ready(store, *, threshold=False, existing=None):
    if existing is None:
        discipline, missions, game, mission, _ = ended(store)
        while work := missions.get(ADMIN, mission["id"])["work"]:
            submit(
                discipline, ADMIN, work[0]["id"], Details(kind="stimulant_injection"), str(uuid4())
            )
        missions.complete(ADMIN, str(uuid4()), mission["id"], mission["revision"])
    else:
        missions, game, mission = existing
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "subsystems": approval.subsystems | {"world", "plays", "playbooks", "strain"}
                },
            )
        }
    )
    world = initial()
    if state(game).world is None:
        WorldService(missions).initialize(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            world.board,
            world.locations,
            world.gorgons[0],
        )
    physical = PhysicalService(store)
    for viewer in (PLAYER, OTHER):
        if any(
            x.actor.kind == "pilot" and x.actor.entity == str(viewer.user_id)
            for x in state(game).placements
        ):
            continue
        data = physical.preview(viewer)
        proposal = physical.propose(
            viewer,
            str(uuid4()),
            data["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(data["actor"]),
                frame_instance=data["frame_instance"],
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="piloting" if threshold and viewer == PLAYER else "outside_frame",
                account="My actual existing physical mode at the past mission site",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN,
            str(uuid4()),
            proposal["id"],
            1,
            "accept",
            "The actual Handler confirms these original physical facts",
        )
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    if threshold:
        with store.transaction() as c:
            actual = state(game)
            for x in actual.sheets["2"].assets:
                if x.family == "frame" and x.id != asset.id:
                    x.void = True
            game.event(c, 1, str(uuid4()), "synthetic.prior_partial_frame_corruption", actual)
    strain = StrainService(OffDutyService(missions), dice=D6(4))
    prepared(strain, game)
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
    strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 1)
    draw = Draw()
    return (
        EffectService(strain, selector=draw),
        game,
        mission["id"],
        request.id + ":effect",
        asset.id,
        draw,
    )


def select(effects, mission, work, mode):
    async def action():
        interaction = current(1, 28700)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, work)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = dict(
            mission=(mission,),
            site=("base0",),
            cleanup_mode=(mode,),
            account="The Cadre's actual cleanup duty at this completed mission site",
        )
        await form.confirm.callback(current(1, 28701))
        assert form.completed

    asyncio.run(action())


def respond(store, viewer, identity, number, values):
    async def action():
        inbox = InboxService(store)
        item = next(
            x
            for x in inbox.items(viewer)
            if x.identity == identity and x.task == "m3_budget_cleanup"
        )
        interaction = current(viewer.user_id, number)
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(interaction, item)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = values
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    asyncio.run(action())


def resolved(store, identity):
    work = t.m3["m3_required_work"]
    with store.engine.connect() as c:
        return c.scalar(
            sa.select(work.c.state)
            .where(
                work.c.campaign_id == store.campaign_id,
                work.c.id == identity,
            )
            .order_by(work.c.revision.desc())
            .limit(1)
        )


def test_cleanup_actual_past_mission_native_scene_attendance_and_real_ending(ledger):
    effects, game, mission, work, _, draw = ready(ledger)
    original = state(game).sheets.copy()
    select(effects, mission, work, "scene")
    identity = work + ":cleanup"
    assert draw.calls == 0 and get(state(game), identity).scene.acknowledgements == ()
    for viewer in (ADMIN, PLAYER, OTHER):
        respond(
            ledger,
            viewer,
            identity,
            28710 + viewer.user_id * 2,
            dict(action=("attend",), account="I actually took part in this cleanup scene"),
        )
    assert resolved(ledger, identity) == "pending"
    respond(
        ledger,
        ADMIN,
        identity,
        28720,
        dict(action=("end",), account="The played cleanup scene actually ended"),
    )
    assert (
        get(state(game), identity).phase == "complete" and resolved(ledger, identity) == "resolved"
    )
    assert state(game).sheets == original


def test_cleanup_single_draw_native_owned_void_and_real_resistance_closes_source(ledger):
    effects, game, mission, work, asset, draw = ready(ledger, threshold=True)
    select(effects, mission, work, "exposure")
    identity = work + ":cleanup"
    source = get(state(game), identity)
    assert source.selected == 0 and draw.calls == 1 and source.people[0].entity == "2"
    respond(
        ledger,
        PLAYER,
        identity,
        28730,
        dict(asset=(asset,), account="The actual selected Frame hardware becomes Void-altered"),
    )
    source = get(state(game), identity)
    assert source.phase == "threshold" and resolved(ledger, identity) == "pending"
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset).void
    threshold = source.thresholds[0]
    assert VoidService(ledger).get(PLAYER, threshold)["stage"] == "resist_pending"
    worker = GameWorker(game)
    gateway = Gateway()
    game.dice.faces = (1, 1)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            source_work=threshold,
            heat=state(game).sheets["2"].heat,
            context="Actual resistance to the cleanup-corrupted Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("in_control", "tough"), denied=("sexy",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="The actual source Handler rules this resistance sufficient",
    )
    tick(worker, gateway, 4)
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert VoidService(ledger).get(PLAYER, threshold)["stage"] == "prevented"
    assert (
        get(state(game), identity).phase == "complete" and resolved(ledger, identity) == "resolved"
    )
    assert draw.calls == 1


def test_cleanup_actual_single_draw_can_store_owned_void_in_genuinely_connected_janus(
    ledger, tmp_path, monkeypatch
):
    from test_enforcer_requisitions import approved
    from test_janus_battery import connected
    from test_janus_battery import start as start_battery

    from girlframe.engine import m3_janus_storage as stored
    from girlframe.engine.m3_janus import BATTERY, CORE
    from girlframe.engine.m3_janus_requisitions import STORAGE
    from girlframe.services.m3_janus_requisitions import JanusRequisitionService
    from girlframe.services.m3_janus_storage import StorageService
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_punishments import PunishmentService

    game, worker, gateway, core, _ = connected(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(CORE, BATTERY, STORAGE))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"missions", "discipline", "strain"}},
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.existing_storage_funds", canon)
    purchase = JanusRequisitionService(game)
    purchase.buy_rule(
        PLAYER,
        str(uuid4()),
        purchase.menu(PLAYER)["source_sha256"],
        STORAGE,
        "Actual native Void Storage acquisition",
    )
    battery = start_battery(game, core)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, battery)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), battery)
    pass_tags(game)
    answer(game, PLAYER, "janus_select", options=("cognition", "offset"))
    tick(worker, gateway, 4)
    missions = MissionService(ledger)
    mission = missions.offer(
        ADMIN, str(uuid4()), "An actual completed mission before cleanup", (2, 3)
    )
    missions.respond(PLAYER, str(uuid4()), mission["id"], 1, "accept")
    missions.respond(OTHER, str(uuid4()), mission["id"], 2, "accept")
    missions.start(ADMIN, str(uuid4()), mission["id"], 3)
    result = missions.end(ADMIN, str(uuid4()), mission["id"], 4, True)
    discipline = PunishmentService(ledger)
    while work := missions.get(ADMIN, mission["id"])["work"]:
        submit(discipline, ADMIN, work[0]["id"], Details(kind="stimulant_injection"), str(uuid4()))
    missions.complete(ADMIN, str(uuid4()), mission["id"], result["revision"])
    effects, game, past, work, asset, draw = ready(ledger, existing=(missions, game, mission))
    original = next(x for x in state(game).sheets["2"].assets if x.id == asset).model_copy(
        deep=True
    )
    select(effects, past, work, "exposure")
    identity = work + ":cleanup"
    respond(
        ledger,
        PLAYER,
        identity,
        28740,
        dict(
            asset=(asset,),
            storage=("yes",),
            account="This actual cleanup alteration is stored only while the same Core is linked",
        ),
    )
    point = StorageService(game).view(PLAYER)["points"][-1]
    assert point["active"] and stored.points(state(game))[-1].source_kind == "budget_cleanup"
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset) == original
    assert next(x for x in game.sheet(PLAYER)["assets"] if x["id"] == asset)["void"]
    assert (
        get(state(game), identity).phase == "complete" and resolved(ledger, identity) == "resolved"
    )
    assert draw.calls == 1
