"""A saved High Rebellion takeover releases actual prisoners and transfers one Frame."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical_state import ParkedFrame
from girlframe.engine.m3_rebel_base_capture import RULE, captures
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Faction, Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_saved_rebel_overrun_transfers_parked_frame_and_resolves_real_occupants(ledger):
    strain, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    worlds = WorldService(strain.missions)
    world = initial()
    worlds.initialize(
        ADMIN, "overrun-map", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    for identity, jobs, employment, cell in (
        ("genuine-prisoner", ("prisoner", "civilian"), "unrecorded", (0, 0)),
        ("original-staff", ("guard",), "foundation", (0, 0)),
        ("unaffected-staff", ("doctor",), "foundation", (2, 0)),
    ):
        worlds.npc(
            ADMIN,
            "overrun-npc-" + identity,
            state(game).revision,
            Npc(
                id=identity,
                name=identity,
                jobs=jobs,
                employment=employment,
                cell=cell,
                controller=1,
                detail="Synthetic original NPC",
                revealed=True,
            ),
        )
    faction = Faction(
        id="overrun-faction", name="Original Rebel Group", kind="rebel", cells=((0, 0),)
    )
    worlds.faction(ADMIN, "overrun-faction", state(game).revision, faction)
    assailant = AdversaryPilot(
        id="original-overrun-pilot",
        kind="rebel",
        girl="MOCKINGBIRD",
        frame="JANUS",
        name="Rebel Lead",
        controller=3,
        faction=faction.id,
        cell=(0, 0),
        assets=(
            Asset(
                id="overrun-asset",
                name="Frame Asset",
                description="Synthetic combat capability",
                family="frame",
            ),
        ),
    )
    retired = str(uuid4())
    with ledger.transaction() as c:
        canon = state(game)
        handler = active_handler(canon)
        assert handler is not None
        canon.world = canon.world.model_copy(update=dict(pilots=(assailant,)))
        original = canon.sheets["2"].model_copy(
            update=dict(character_id=retired, frame_runtime=None)
        )
        parked = ParkedFrame(
            owner=ActorRef(kind="pilot", entity="2", incarnation=retired),
            frame_instance="initial:" + retired,
            cell=(0, 0),
            source_event="fixture-storage-source",
            prior_event="fixture-original-frame-use",
            frame_json=original.model_dump_json(),
        )
        canon.parked_frames = [
            parked,
            parked.model_copy(update=dict(frame_instance="other-base-frame", cell=(2, 0))),
        ]
        canon.facts.append(
            dict(
                kind="ordinary_handler_movement",
                actor=handler.model_dump_json(),
                cell="[0,0]",
                event="fixture-handler-local",
            )
        )
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(
            c,
            1,
            "original-overrun-prereqs",
            "synthetic.proved_parked_frame",
            canon,
            event_id=parked.source_event,
        )
    cast = CastService(ActorService(strain.missions))
    staff = ActorRef(kind="npc", entity="original-staff")
    change(cast, ADMIN, "join", staff)
    period = prepared(strain, game, high=frozenset({"rebellion"}))
    effects = EffectService(strain)
    for track, face, column, choice in (
        (
            "void",
            2,
            1,
            Choice(
                rule_id="strain.void.low.2.1",
                account="A Gorgon arrives.",
                gorgon=gorgon("dormant", "outside-overrun-base", (0, 1)),
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="Rooms reassigned.", rooms=((2, 3),)),
        ),
        ("rebellion", 2, 1, None),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "overrun-die-" + track, request.id, 1, state(game).revision)
        selected = strain.choose(
            ADMIN, "overrun-column-" + track, request.id, 2, state(game).revision, column
        )
        identity = request.id + ":effect"
        if choice:
            effects.apply(
                ADMIN, "overrun-effect-" + track, identity, 1, state(game).revision, choice
            )
    assert selected["rule_id"] == RULE
    chosen = Choice(
        rule_id=RULE,
        target="base0",
        victim=assailant.id,
        captured_frame=parked.frame_instance,
        account="The Rebels seize the unoccupied Frame and open the prison.",
    )
    stale = state(game).revision
    with pytest.raises(WorkflowError, match="actually away"):
        effects.apply(ADMIN, "handler-present", identity, 1, stale, chosen)
    with ledger.transaction() as c:
        canon = state(game)
        canon.facts.append(
            dict(
                kind="ordinary_handler_movement",
                actor=handler.model_dump_json(),
                cell=json.dumps((2, 0)),
                event="fixture-handler-away",
            )
        )
        game.event(c, 1, "accepted-handler-position", "synthetic.handler-away", canon)
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        effects.apply(ADMIN, "stale-overrun", identity, 1, stale, chosen)
    with pytest.raises(WorkflowError):
        effects.apply(PLAYER, "wrong-overrun-owner", identity, 1, revision, chosen)
    ledger.safety(PLAYER, "pause-overrun", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        effects.apply(ADMIN, "paused-overrun", identity, 1, revision, chosen)
    ledger.safety(PLAYER, "resume-overrun", ledger.status(PLAYER)["revision"], pause=False)
    revision = state(game).revision
    original_girls = state(game).sheets

    async def submit_native():
        click = current(1, 40500)
        await click.response.defer(ephemeral=True)
        await open_effect(click, effects, identity)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            overrun_base=("base0",),
            overrun_rebel=(assailant.id,),
            overrun_frame=(parked.frame_instance,),
            account=chosen.account,
        )
        submitted = current(1, 40501)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args

    asyncio.run(submit_native())
    assert effects.apply(ADMIN, "40501", identity, 1, revision, chosen)["state"] == "resolved"
    ledger.engine.dispose()
    canon = state(game)
    (report,) = captures(canon)
    assert report.faction == faction.id and report.frame == parked
    assert [x.id for x in report.released] == ["genuine-prisoner"]
    assert [x.id for x in report.killed] == ["original-staff"]
    assert [x.frame_instance for x in canon.parked_frames] == ["other-base-frame"]
    by_id = {x.id: x for x in canon.world.npcs}
    assert (
        by_id["genuine-prisoner"].jobs == ("civilian",)
        and by_id["genuine-prisoner"].custody_event is None
    )
    assert not by_id["original-staff"].alive and by_id["unaffected-staff"].alive
    assert not any(role.actor == staff for scene in canon.scene_casts for role in scene.roles)
    location = next(x for x in canon.world.locations if x.id == "base0")
    assert (
        not location.foundation_operational and location.control_loss.threat.entity == assailant.id
    )
    assert original_girls == canon.sheets
    with pytest.raises(WorkflowError):
        effects.get(OTHER, identity)
    assert effects.get(ADMIN, identity)["captured_base"]["freed"] == 1
    assert activate(CycleService(strain.periods), game, period)["phase"] == "active"
