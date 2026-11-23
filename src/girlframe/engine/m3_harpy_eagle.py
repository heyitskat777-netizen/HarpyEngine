"""The original removed cockpit and living Girl remain tied to one Harpy."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

KIND = "harpy_eagle_cockpit"


class Cockpit(Model):
    event: str
    scene: str
    harpy: ActorRef
    controller: int
    girl: ActorRef
    frame: str
    exposure: str
    tag: str
    advancement: str
    released: str | None = None
    restored: str | None = None


def records(state: GameState) -> tuple[Cockpit, ...]:
    return tuple(
        Cockpit.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def put(state: GameState, value: Cockpit) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.event)]
    state.facts.append(dict(kind=KIND, id=value.event, body=value.model_dump_json()))


def holding(state: GameState, harpy: ActorRef) -> Cockpit | None:
    return next((x for x in records(state) if x.harpy == harpy and not x.released), None)


def held(state: GameState, girl: ActorRef) -> Cockpit | None:
    return next((x for x in records(state) if x.girl == girl and not x.released), None)


def missing(state: GameState, owner: ActorRef, frame: str) -> bool:
    return any(x.girl == owner and x.frame == frame and not x.restored for x in records(state))
