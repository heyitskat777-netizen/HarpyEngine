"""Actual source assignment survives OffDuty and only real target death earns success."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_punishment_service import submit
from test_strain_effect_service import pending, selected

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_budget_assassination import open_assignment
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_budget_assassination import get
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_battle_npc import NpcDamageService
from girlframe.services.m3_budget_assassination import AssassinationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_assassination_source_period_real_mission_death_rewards_and_closure(ledger):
    effects, game, period, first = pending(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    target = ActorRef(kind="npc", entity="actual-political-target")
    WorldService(effects.strain.missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=target.entity,
            name="Actual local politician",
            jobs=("patron",),
            controller=1,
            detail="An actual politician advocating the source's undesirable political ends",
            cell=(0, 0),
            revealed=True,
        ),
    )
    effects.apply(ADMIN, str(uuid4()), first, 1, state(game).revision, selected())
    for track, face, column in (("rebellion", 1, 2), ("budget", 6, 1)):
        request = next(x for x in state(game).strain.requests if x.track == track)
        effects.strain.dice.face = face
        effects.strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        effects.strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        if track == "rebellion":
            effects.apply(
                ADMIN,
                str(uuid4()),
                request.id + ":effect",
                1,
                state(game).revision,
                Choice(rule_id="strain.rebellion.low.1.2", account="A real control slip"),
            )
    source = request.id + ":effect"
    identity = source + ":assassination"

    async def source_choice():
        interaction = current(1, 29100)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, source)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            visitor=(target.entity,),
            account="The source orders our Cadre to assassinate this politician",
        )
        await form.confirm.callback(current(1, 29101))
        assert form.completed

    asyncio.run(source_choice())
    assert get(state(game), identity).phase == "pending"
    cycle = CycleService(effects.strain.periods)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    assignment = AssassinationService(ledger)
    missions = MissionService(ledger)

    async def offer(number):
        interaction = current(1, number)
        await interaction.response.defer(ephemeral=True)
        await open_assignment(interaction, assignment, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(confirm=("yes",))
        await form.confirm.callback(current(1, number + 1))
        assert form.completed
        return get(state(game), identity).mission

    # Players may decline; cancelling an undispatched offer preserves the assignment.
    attempt = asyncio.run(offer(29110))
    missions.respond(PLAYER, str(uuid4()), attempt, 1, "decline")
    missions.respond(OTHER, str(uuid4()), attempt, 2, "decline")
    missions.cancel(ADMIN, str(uuid4()), attempt, 3)
    assert get(state(game), identity).phase == "pending"
    mission = asyncio.run(offer(29120))
    missions.respond(PLAYER, str(uuid4()), mission, 1, "accept")
    missions.respond(OTHER, str(uuid4()), mission, 2, "accept")
    missions.start(ADMIN, str(uuid4()), mission, 3)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="still alive"):
        missions.end(ADMIN, str(uuid4()), mission, 4, True)
    assert state(game).model_dump_json() == before
    handler = HandlerPlayService(ledger)
    grant = handler.start(ADMIN, str(uuid4()), state(game).revision, (target,))["id"]
    handler.submit(
        ADMIN,
        str(uuid4()),
        grant,
        state(game).revision,
        "mess",
        Effect(
            kind="damage",
            target=target,
            account="An actual on-mission assassination hit is being resolved",
        ),
    )
    with ledger.engine.connect() as c:
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work).where(
                    work.c.campaign_id == ledger.campaign_id, work.c.kind == "npc_damage"
                )
            )
            .mappings()
            .one()
        )
    NpcDamageService(ledger).respond(
        ADMIN,
        str(uuid4()),
        row["id"],
        row["revision"],
        "kill",
        "The actual political target dies from that real hit",
    )
    ended = missions.end(ADMIN, str(uuid4()), mission, 4, True)
    discipline = PunishmentService(ledger)
    while pending_work := missions.get(ADMIN, mission)["work"]:
        submit(
            discipline,
            ADMIN,
            pending_work[0]["id"],
            Details(kind="stimulant_injection"),
            str(uuid4()),
        )
    missions.complete(ADMIN, str(uuid4()), mission, ended["revision"])
    after = state(game)
    result = get(after, identity)
    assert result.phase == "complete" and result.death_event and result.completed_event
    assert result.attempts == (attempt, mission)
    assert not next(x for x in after.world.npcs if x.id == target.entity).alive
    with ledger.engine.connect() as c:
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == ledger.campaign_id, work.c.id == identity)
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert row["campaign_context"] and row["off_duty_id"] is None and row["state"] == "resolved"
