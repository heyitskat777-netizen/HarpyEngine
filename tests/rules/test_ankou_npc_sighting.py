"""Actual owner-authored NPC sighting during a genuine complete Off-Duty period."""

from uuid import uuid4

import pytest
import test_strain_effect_service
from test_ankou import buy, native
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_off_duty_cycle import activate, call, finish_routine, movement, prepared, recover_both
from test_physical_operations import place
from test_strain_service import ready as strain_ready
from test_world_service import transfer_npc

from girlframe.engine import m3_ankou as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_ankou import AnkouService, prove_encounter
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_npc_obsession_sighting_prevents_false_whole_period_feedback(
    ledger, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame=rules.FRAME),
    )
    cycle, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RELAY, *rules.REQUISITIONS))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = place(place(state(game), 2, mode="outside_frame"), 3, mode="outside_frame")
        canon.sheets["2"].permissions = 10
        game.event(c, 1, str(uuid4()), "synthetic.prior_obsession_resources_positions", canon)
    cycle.missions.access = Access(ledger)
    controls = AnkouService(game)
    missions = MissionService(ledger)
    world = WorldService(missions)
    target = ActorRef(kind="npc", entity="actual-seen-obsession")
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=target.entity,
            name="Original NPC Obsession",
            jobs=("guard",),
            controller=1,
            detail="Actual person physically present during this Off-Duty",
            cell=(0, 0),
            revealed=True,
        ),
    )
    buy(controls, rules.OBSESSIVE)
    actor = current_ref(state(game), 2)
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "withdraw", actor)
    change(cast, PLAYER, "join", actor)
    obsession = controls.choose_obsession(
        PLAYER, str(uuid4()), state(game).revision, target, "My original NPC Obsession"
    )["id"]
    activate(cycle, game, period)
    before = state(game)
    with pytest.raises(WorkflowError, match="actual observer"):
        controls.encounter(
            ADMIN,
            str(uuid4()),
            900,
            before.revision,
            actor,
            target,
            "seen",
            "Cannot author the observer's sighting",
            period=period,
        )
    assert state(game) == before
    assert not rules.records(before, rules.Encounter)
    native(
        controls,
        "encounter",
        person=(target.token,),
        kind=("seen",),
        private=("no",),
        period=period,
        account="I actually see this original NPC during my active Off-Duty",
    )
    sighting = rules.records(state(game), rules.Encounter)[-1]
    assert sighting.actor == actor and sighting.target == target and sighting.period == period
    assert sighting.author == PLAYER.user_id and sighting.kind == "seen"
    with ledger.engine.connect() as c:
        assert prove_encounter(game, c, state(game), sighting.id) == sighting
        view = resolve(state(game), target, profiles(c, ledger.campaign_id))
        assert view.position_sha256 is None and sighting.target_position == view.source_sha256
    # Later genuine custody changes do not erase an already-authored historical sighting.
    transfer_npc(world, ADMIN, OTHER, target.entity)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    result = call(cycle, game, ADMIN, period, "finish", movement(game))
    assert result["phase"] == "complete"
    after = state(game)
    assert not rules.get(after, rules.Obsession, obsession).ended_event
    assert not any(
        x.kind == "missed_obsession" and x.source == obsession
        for x in rules.records(after, rules.Task)
    )
    assert not any(x.source == obsession for x in rules.records(after, rules.FeedbackSequence))
    assert rules.get(after, rules.Encounter, sighting.id) == sighting
