"""Original-person Easy Target reactions and their source-backed consequences."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "girl.newgirl.easy-target"
PLAY = "easy_target"
BASE = ("hurt", "use", "request", "protect")
EXTRA = ("contempt", "cohort")
Urge = Literal["hurt", "use", "request", "protect", "contempt", "cohort", "other", "pass"]


class Session(Model):
    id: str
    actor: ActorRef
    caster: int
    handler: ActorRef
    handler_controller: int
    cast: SceneCast
    total: int
    roll_event: str
    event: str
    selected: ActorRef | None = None
    tag: str | None = None
    tag_event: str | None = None


class Reaction(Model):
    id: str
    session: str
    actor: ActorRef
    controller: int
    choice: str
    event: str
    urge: Urge
    account: str
    primary: str | None = None
    rechoosing: bool = False
    performer: ActorRef | None = None
    play: str | None = None
    context: str = ""
    validation_event: str | None = None
    child: str | None = None
    bound_event: str | None = None
    children: tuple[str, ...] = ()
    performance_event: str | None = None
    harm: str | None = None
    protection_event: str | None = None
    failure: str | None = None
    departure_event: str | None = None
    exemption: str | None = None
    consequence: str | None = None
    consequence_event: str | None = None
    completed_event: str | None = None


class Harm(Model):
    id: str
    target: ActorRef
    opponent: ActorRef | None
    event: str
    source_action: str | None
    source_work: str | None
    before: str
    after: str


class NpcHurt(Model):
    """One actual NPC bodily performance, followed by a real owned injury choice."""

    id: str
    reaction: str
    session: str
    actor: ActorRef
    controller: int
    target: ActorRef
    handler: ActorRef
    cast: SceneCast
    choice: str
    account: str
    event: str
    asset: str | None = None
    asset_choice: str | None = None
    damage_event: str | None = None
    work: tuple[str, ...] = ()
    completed_event: str | None = None


class NpcProtection(Model):
    id: str
    reaction: str
    session: str
    actor: ActorRef
    controller: int
    target: ActorRef
    handler: ActorRef
    cast: SceneCast
    choice: str
    account: str = Field(min_length=1, max_length=1200)
    event: str
    actor_position: str | None
    target_position: str | None
    actor_vessel: str | None
    target_vessel: str | None


class NpcProtectionFailure(Model):
    id: str
    protection: str
    reaction: str
    ward: ActorRef
    npc: ActorRef
    handler: ActorRef
    scene: SceneCast
    event: str
    attempt: str = Field(min_length=1, max_length=1200)
    occurred: str = Field(min_length=1, max_length=1200)


KINDS: dict[type[Model], str] = {
    Session: "easy_target_session",
    Reaction: "easy_target_reaction",
    Harm: "easy_target_harm",
    NpcHurt: "easy_target_npc_hurt",
    NpcProtection: "easy_target_npc_protection",
    NpcProtectionFailure: "easy_target_npc_protection_failure",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def get[T: Model](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in records(state, model) if x.model_dump()["id"] == identity), None)
    if value is None:
        raise ValueError("Recover the actual original Easy Target source")
    return value


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], value.model_dump()["id"]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def identity(session: str, actor: ActorRef) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:easy-target:" + session + ":" + actor.token))


def choices(value: Session) -> tuple[str, ...]:
    return (
        BASE if 8 <= value.total <= 10 else BASE + EXTRA + (("other",) if value.total <= 7 else ())
    )


def settled(state: GameState, value: Session) -> bool:
    return (
        all(
            any(
                x.session == value.id and x.actor == role.actor and not x.rechoosing
                for x in records(state, Reaction)
            )
            for role in value.cast.roles
            if role.actor != value.actor
        )
        if value.total >= 11 or value.total <= 7
        else any(
            x.session == value.id and x.actor == value.selected and not x.rechoosing
            for x in records(state, Reaction)
        )
    )
