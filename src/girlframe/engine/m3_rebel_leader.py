"""Actual source-bound opportunity, living leader and later group destruction."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world import update

RULE = "strain.rebellion.endgame.1"


class Opportunity(Model):
    id: str
    source_event: str
    named_event: str
    group: str
    handler: ActorRef
    leader: ActorRef
    account: str = Field(min_length=1, max_length=1200)
    phase: Literal["available", "destroyed", "forgone"] = "available"
    death_event: str | None = None
    completed_event: str | None = None
    response: str = Field(default="", max_length=1200)


def opportunities(state: GameState) -> tuple[Opportunity, ...]:
    return tuple(
        Opportunity.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "rebel_leader_opportunity"
    )


def put(state: GameState, value: Opportunity) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "rebel_leader_opportunity" and x.get("id") == value.id)
    ]
    state.facts.append(
        dict(kind="rebel_leader_opportunity", id=value.id, body=value.model_dump_json())
    )


def identify(state: GameState, value: Opportunity) -> GameState:
    changed = GameState.model_validate_json(state.model_dump_json())
    world = changed.world
    if world is None or any(x.id == value.id for x in opportunities(state)):
        raise ValueError("Use the actual new leader opportunity")
    group = next(
        (x for x in world.factions if x.id == value.group and x.kind == "rebel" and x.active), None
    )
    leader = next((x for x in world.npcs if x.id == value.leader.entity and x.alive), None)
    if (
        value.leader.kind != "npc"
        or group is None
        or leader is None
        or group.leader is not None
        and group.leader != leader.id
        or group.leader is None
        and leader.faction != group.id
        and group.id not in leader.secret_factions
    ):
        raise ValueError("Identify the actual existing leader or an actual living group member")
    changed.world = update(
        world,
        factions=tuple(
            x.model_copy(update=dict(leader=leader.id)) if x.id == group.id else x
            for x in world.factions
        ),
    )
    put(changed, value)
    return changed


def finish(
    state: GameState, value: Opportunity, event: str, death: str | None, account: str
) -> GameState:
    changed = GameState.model_validate_json(state.model_dump_json())
    if value.phase != "available" or not event:
        raise ValueError("This original opportunity is already settled")
    if death:
        world = changed.world
        group = next((x for x in world.factions if x.id == value.group), None) if world else None
        leader = (
            next((x for x in world.npcs if x.id == value.leader.entity), None) if world else None
        )
        if (
            not world
            or not group
            or not group.active
            or group.leader != value.leader.entity
            or not leader
            or leader.alive
        ):
            raise ValueError(
                "Destroy only the actual active group after its current leader's death"
            )
        cancelled = [x.id for x in world.npc_recruitment if x.faction == group.id]
        changed.world = update(
            world,
            factions=tuple(
                x.model_copy(update=dict(active=False)) if x.id == group.id else x
                for x in world.factions
            ),
            npc_recruitment=tuple(x for x in world.npc_recruitment if x.faction != group.id),
        )
        changed.facts.append(
            dict(
                kind="rebel_group_destroyed",
                group=group.id,
                opportunity=value.id,
                event=event,
                death=death,
                cancelled_recruitment=",".join(cancelled),
            )
        )
    put(
        changed,
        value.model_copy(
            update=dict(
                phase="destroyed" if death else "forgone",
                death_event=death,
                completed_event=event,
                response=account,
            )
        ),
    )
    return changed
