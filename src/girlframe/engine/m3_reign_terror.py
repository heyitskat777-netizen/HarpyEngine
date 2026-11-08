"""Genuine execution effects and ordinary subject-owned Underfunded Tags."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "handler-advancement.handler-advancement.reign-of-terror"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Execution(Model):
    id: str
    acquisition: str
    handler: ActorRef
    prisoner: ActorRef
    custody_event: str
    prisoner_json: str
    event: str
    account: str = Field(min_length=1, max_length=1200)
    choice: Literal["rebellion_low", "underfunded", "girl_tag"]
    group: str | None = None
    condition: str | None = None
    target: ActorRef | None = None
    tag: str | None = None
    rebellion_before: str | None = None


class Condition(Model):
    id: str
    execution: str
    group: str
    event: str


class MemberTag(Model):
    id: str
    condition: str
    group: str
    target: ActorRef
    event: str
    tag: TagState
    phase: Literal["live", "reject_pending", "embraced", "rejected"] = "live"
    mark_event: str | None = None
    resolution_event: str | None = None
    identity: str | None = None


class PCExecutionSource(Model):
    acquisition: str
    handler: ActorRef
    appointment: str
    prisoner: ActorRef
    label: str
    archive: str
    execution_event: str
    grasp: str
    custody_event: str
    works: tuple[str, ...]
    cell: tuple[int, int]
    handler_position_event: str


class PCExecutionClaim(PCExecutionSource):
    id: str
    event: str
    choice: Literal["rebellion_low", "girl_tag"]
    account: str = Field(min_length=1, max_length=1200)
    target: ActorRef | None = None
    tag: str | None = None
    rebellion_before: str | None = None


def values[T: Model](state: GameState, kind: str, cls: type[T]) -> tuple[T, ...]:
    return tuple(cls.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == kind)


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return values(state, "reign_acquisition", Acquisition)


def executions(state: GameState) -> tuple[Execution, ...]:
    return values(state, "reign_execution", Execution)


def conditions(state: GameState) -> tuple[Condition, ...]:
    return values(state, "reign_condition", Condition)


def member_tags(state: GameState) -> tuple[MemberTag, ...]:
    return values(state, "reign_member_tag", MemberTag)


def pc_claims(state: GameState) -> tuple[PCExecutionClaim, ...]:
    return values(state, "reign_pc_execution_claim", PCExecutionClaim)


def put(
    state: GameState, value: Acquisition | Execution | Condition | MemberTag | PCExecutionClaim
) -> None:
    kind = {
        Acquisition: "reign_acquisition",
        Execution: "reign_execution",
        Condition: "reign_condition",
        MemberTag: "reign_member_tag",
        PCExecutionClaim: "reign_pc_execution_claim",
    }[type(value)]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))
