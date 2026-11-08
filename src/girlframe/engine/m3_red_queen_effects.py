"""Actual Court command performances and source-attributed Tag births."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast


class Command(Model):
    id: str
    mark: str
    actor: ActorRef
    target: ActorRef
    play: str
    controller: int
    cast: SceneCast
    event: str
    work: str
    action: str | None = None
    bound_event: str | None = None
    completed_event: str | None = None


class TagGift(Model):
    id: str
    giver: ActorRef
    target: ActorRef
    label: str
    source: str
    event: str


KINDS = {Command: "red_queen_command", TagGift: "red_queen_tag_gift"}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], str(value.model_dump()["id"])
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))
