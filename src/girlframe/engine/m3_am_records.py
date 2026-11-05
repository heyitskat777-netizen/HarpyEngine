"""A complete fictional Foundation dossier and one actual source-bound question."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model


class Access(Model):
    id: str
    maintenance: str
    subject: ActorRef
    label: str = Field(min_length=1, max_length=120)
    learner: ActorRef
    controller: int
    requested_event: str
    phase: Literal["requested", "prepared", "granted", "answered", "not_granted"] = "requested"
    prepared_event: str | None = None
    gm: int | None = None
    appointment: str | None = None
    reference: str = Field(default="", max_length=1200)
    document: str = Field(default="", max_length=1200)
    granted_event: str | None = None
    question: str = Field(default="", max_length=1200)
    question_event: str | None = None
    answer: str = Field(default="", max_length=1200)
    answer_event: str | None = None
    closed_event: str | None = None


def records(state: GameState) -> tuple[Access, ...]:
    return tuple(
        Access.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "am_foundation_records"
    )


def access(state: GameState, identity: str) -> Access:
    value = next((x for x in records(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original Foundation record source")
    return value


def put(state: GameState, value: Access) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "am_foundation_records" and x.get("id") == value.id)
    ]
    state.facts.append(
        dict(kind="am_foundation_records", id=value.id, body=value.model_dump_json())
    )
