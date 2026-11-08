"""Original Show Dog choices, real addressed messages and NPC interests."""

from typing import Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "girl.princess.show-dog"
FIRST = ("trend", "public", "message", "quiet")
DESIRES = ("sex", "own", "kill", "emulate")
Desire = Literal["sex", "own", "kill", "emulate"]


class Show(Model):
    id: str
    period: str
    actor: ActorRef
    controller: int
    handler: ActorRef
    source_action: str
    source_event: str
    first_kind: Literal["trend", "public", "message", "quiet"] | None = None
    first_event: str | None = None
    target: ActorRef | None = None
    tag: str | None = None
    message: str | None = None
    account: str = ""
    second_event: str | None = None
    interest: str | None = None
    risk_event: str | None = None
    risk_decision: bool | None = None
    risk_account: str = ""
    punishment: str | None = None


class Message(Model):
    id: str
    show: str
    sender: ActorRef
    target: ActorRef
    controller: int
    event: str
    text: str


class Interest(Model):
    id: str
    show: str
    actor: ActorRef
    npc: ActorRef
    controller: int
    desire: Desire
    event: str
    appearance: str
    before: int
    after: int


class Exposure(Model):
    id: str
    show: str
    actor: ActorRef
    target: ActorRef
    event: str
    account: str


KINDS: dict[type[Model], str] = {
    Show: "show_dog",
    Message: "show_dog_message",
    Interest: "show_dog_interest",
    Exposure: "show_dog_exposure",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], value.model_dump()["id"]
    if not isinstance(value, Show) and any(
        x.get("kind") == kind and x.get("id") == identity for x in state.facts
    ):
        raise ValueError("Preserve the immutable original Show Dog outcome")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def get(state: GameState, identity: str) -> Show:
    value = next((x for x in records(state, Show) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original Show Dog source")
    return value


def complete(state: GameState, value: Show) -> bool:
    if value.first_event is None or value.second_event is None or value.risk_decision is None:
        return False
    if not value.risk_decision:
        return True
    return any(
        x.id == value.punishment
        and x.effect_event is not None
        and x.completion_event is not None
        and x.ended_event is None
        for x in state.role_punishments
    )
