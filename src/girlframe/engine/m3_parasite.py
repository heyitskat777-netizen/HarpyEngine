"""An original Parasite can ride a living ordinary NPC through their actual movements."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model
from girlframe.engine.m3_world_state import Cell

RULE = "gorgon-type.parasite.parasite-type"
KIND = "parasite_ride"
PLAYS = ("parasite_hitch", "parasite_detach")


class Ride(Model):
    actor: ActorRef
    host: ActorRef
    action: str
    scene: str
    event: str
    cell: Cell
    position_event: str
    ended: str | None = Field(default=None, exclude_if=lambda value: value is None)


def records(state: GameState) -> tuple[Ride, ...]:
    return tuple(Ride.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def active(state: GameState, actor: ActorRef) -> Ride | None:
    return next((x for x in records(state) if x.actor == actor and x.ended is None), None)


def _save(state: GameState, ride: Ride) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, ride.event)]
    state.facts.append(dict(kind=KIND, id=ride.event, body=ride.model_dump_json()))


def present(state: GameState, actor: ActorView, host: ActorView) -> bool:
    return (
        actor.ref.kind == "gorgon"
        and host.rules == "npc"
        and host.ref.kind == "npc"
        and actor.alive
        and host.alive
        and actor.offstage_source is None
        and host.offstage_source is None
        and actor.cell is not None
        and actor.cell == host.cell
        and state.world is not None
        and any(
            npc.id == host.ref.entity and npc.source_kind is None and npc.cell == host.cell
            for npc in state.world.npcs
        )
    )


def hitch(
    state: GameState, actor: ActorView, host: ActorView, *, action: str, scene: str, event: str
) -> None:
    if (
        not present(state, actor, host)
        or actor.cell is None
        or active(state, actor.ref) is not None
    ):
        raise ValueError("Use an actual present ordinary NPC and a Parasite without another host")
    _save(
        state,
        Ride(
            actor=actor.ref,
            host=host.ref,
            action=action,
            scene=scene,
            event=event,
            cell=actor.cell,
            position_event=event,
        ),
    )


def detach(state: GameState, actor: ActorRef, event: str) -> None:
    current = active(state, actor)
    if current is None:
        raise ValueError("Use the actual original Parasite with an active host")
    _save(state, current.model_copy(update=dict(ended=event)))


def follow_hosts(state: GameState, event: str) -> None:
    """Update only each attached Gorgon's position after a canonical host changes."""
    world = state.world
    if world is None:
        return
    hosts = {x.id: x for x in world.npcs if x.alive}
    living = {x.id: x for x in world.gorgons if x.alive and "parasite" in x.types}
    for ride in records(state):
        if ride.ended:
            continue
        host = hosts.get(ride.host.entity)
        gorgon = living.get(ride.actor.entity)
        if host is None or gorgon is None or gorgon.cell not in (ride.cell, host.cell):
            _save(state, ride.model_copy(update=dict(ended=event)))
        elif host.cell != ride.cell:
            _save(state, ride.model_copy(update=dict(cell=host.cell, position_event=event)))
            world = world.model_copy(
                update=dict(
                    gorgons=tuple(
                        x.model_copy(update=dict(cell=host.cell)) if x.id == gorgon.id else x
                        for x in world.gorgons
                    )
                )
            )
            state.world = world
