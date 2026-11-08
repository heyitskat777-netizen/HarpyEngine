"""Native Girl Flirt with an actual ordinary NPC; no invented NPC resources."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, Model, SceneCast

RULE = "play.basic.flirt"
KINDS = (
    "npc_flirt_actor",
    "npc_flirt_target",
    "npc_flirt_answer",
    "npc_flirt_escape",
    "npc_flirt_play",
    "npc_flirt_owe",
)


class Session(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    controller: int
    actor_label: str
    target_label: str
    cast: SceneCast
    registry: str
    target_json: str
    target_sha256: str
    target_position: str | None
    event: str
    princess_direction: str | None = Field(default=None, exclude_if=lambda value: value is None)
    effect_event: str | None = None
    phase: str = "active"
    tier: Literal["low", "mid", "high"] | None = None
    question: str | None = None
    question_event: str | None = None
    extra: Literal["escape", "handler", "owe"] | None = None
    wanted: str | None = None
    wanted_event: str | None = None
    damage: str | None = None
    completed_event: str | None = None
    cancelled_event: str | None = None


class Performance(Model):
    id: str
    action: str
    kind: Literal["escape", "followthrough"]
    actor: ActorRef
    controller: int
    cast: SceneCast
    recipients: tuple[CastRole, ...] = Field(min_length=1)
    rendition: str = Field(min_length=1, max_length=1800)
    event: str
    job: str | None = None
    move: str | None = None
    choice: str | None = None
    performed_action: str | None = None


class Judgment(Model):
    id: str
    performance: str
    action: str
    npc: ActorRef
    controller: int
    accepted: bool
    account: str = Field(min_length=1, max_length=1800)
    event: str
    before_depth: int
    after_depth: int


class Damage(Model):
    id: str
    action: str
    npc: ActorRef
    controller: int
    choice: str
    event: str
    work: tuple[str, ...] = ()


class TagGrant(Model):
    id: str
    action: str
    actor: ActorRef
    npc: ActorRef
    controller: int
    label: str
    event: str
    choice: str
    obligation: str


class Completion(Model):
    id: str
    action: str
    trigger: str
    work: tuple[str, ...]
    receipt: str
    event: str
    handler: str | None = None


FACTS = {
    Session: "npc_flirt_session",
    Performance: "npc_flirt_performance",
    Judgment: "npc_flirt_judgment",
    Damage: "npc_flirt_escape_damage",
    TagGrant: "npc_flirt_tag_grant",
    Completion: "npc_flirt_completion",
}


def identity(kind: str, source: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:npc-flirt:" + kind + ":" + source))


def records[T: (Session, Performance, Judgment, Damage, TagGrant, Completion)](
    state: GameState, model: type[T]
) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == FACTS[model]
    )


def get[T: (Session, Performance, Judgment, Damage, TagGrant, Completion)](
    state: GameState, model: type[T], key: str
) -> T:
    value = next((x for x in records(state, model) if x.id == key), None)
    if value is None:
        raise ValueError("Recover the actual original NPC Flirt source")
    return value


def put(
    state: GameState, value: Session | Performance | Judgment | Damage | TagGrant | Completion
) -> None:
    kind = FACTS[type(value)]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))
