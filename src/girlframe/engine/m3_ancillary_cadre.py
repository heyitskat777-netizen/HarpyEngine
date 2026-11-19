"""Optional Cadres retain actual actor identities, even for shared controllers."""

from typing import Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, Model
from girlframe.engine.m3_ancillary import find

KIND = "ancillary_cadre"


class Cadre(Model):
    id: str
    scene: str
    channel: int
    facilitator: int
    appointment: str
    handler: ActorRef
    handler_owner: int
    faction: str | None
    order: tuple[CastRole, ...]
    accepted: tuple[str, ...] = ()
    handler_accepted: bool = False
    state: Literal["pending", "active", "declined"] = "pending"
    event: str


def records(state: GameState) -> tuple[Cadre, ...]:
    return tuple(Cadre.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def put(state: GameState, cadre: Cadre) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, cadre.id)]
    state.facts.append(dict(kind=KIND, id=cadre.id, body=cadre.model_dump_json()))


def actual_members(state: GameState, cadre: Cadre) -> tuple[ActorRef, ...]:
    live = (
        {
            row.id: row
            for row in state.world.pilots
            if row.alive and row.faction == cadre.faction and row.custody in ("free", "converted")
        }
        if state.world is not None
        else {}
    )
    return tuple(
        x.actor
        for x in cadre.order
        if x.actor.entity in live
        and live[x.actor.entity].controller == x.controller
        and (body := find(state, x.actor)) is not None
        and body.controller == x.controller
    )


def current(state: GameState, actor: ActorRef) -> Cadre | None:
    matches = tuple(
        x for x in records(state) if x.state == "active" and actor in actual_members(state, x)
    )
    if len(matches) > 1:
        raise ValueError("One living actual member cannot belong to multiple active Cadres.")
    return matches[0] if matches else None


def shift(state: GameState, actor: ActorRef, direction: Literal[-1, 1], event: str) -> bool:
    cadre = current(state, actor)
    if cadre is None:
        raise ValueError("The original actual character needs a confirmed Ancillary Cadre.")
    members = actual_members(state, cadre)
    index = members.index(actor)
    if not 0 <= index + direction < len(members):
        return False
    ordered = list(cadre.order)
    first = next(i for i, role in enumerate(ordered) if role.actor == actor)
    other = members[index + direction]
    second = next(i for i, role in enumerate(ordered) if role.actor == other)
    ordered[first], ordered[second] = ordered[second], ordered[first]
    put(state, cadre.model_copy(update=dict(order=tuple(ordered), event=event)))
    return True
