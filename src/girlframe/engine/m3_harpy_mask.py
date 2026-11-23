"""A Harpy's recorded human appearance belongs to a specific real scene."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

KIND = "harpy_human_mask"


class Mask(Model):
    event: str
    scene: str
    channel: int
    actor: ActorRef
    controller: int
    advancement: str
    appearance: str
    account: str
    facilitator: int
    appointment: str
    approval: str | None = None
    review: str | None = None
    ended: str | None = None


def records(state: GameState) -> tuple[Mask, ...]:
    return tuple(Mask.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def active(state: GameState, actor: ActorRef, scene: str) -> Mask | None:
    return next(
        (
            x
            for x in records(state)
            if x.actor == actor and x.scene == scene and x.approval and not x.ended
        ),
        None,
    )


def put(state: GameState, mask: Mask) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, mask.event)]
    state.facts.append(dict(kind=KIND, id=mask.event, body=mask.model_dump_json()))
