"""Exact paid personal Secretary and four source-owned Plays through that real NPC."""

from typing import Any, Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, Model, SceneCast
from girlframe.engine.m3_world_state import Cell

RULE = "handler-advancement.handler-advancement.secretary"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Secretary(Model):
    id: str
    acquisition: str
    actor: ActorRef
    handler: ActorRef
    appointment: str
    event: str
    branch: Literal["promoted", "created"]
    original_npc_json: str
    style: Literal["am", "military", "clone", "competent"]


class Performed(Model):
    id: str
    secretary: str
    actor: ActorRef
    principal: ActorRef
    play: Literal["authority", "appear", "competence"]
    event: str
    account: str = Field(min_length=1, max_length=1800)
    scene: str | None = None
    destination: Cell | None = None
    order: str | None = None
    mission: str | None = None
    mission_event: str | None = None
    mission_json: str | None = None
    recipients: tuple[ActorRef, ...] = ()
    recipient_roles: tuple[CastRole, ...] = Field(default=(), exclude_if=lambda value: not value)
    recipient_labels: dict[str, str] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )
    statement_channel: int | None = Field(default=None, exclude_if=lambda value: value is None)
    statement_cast_revision: int | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class Gunpoint(Model):
    id: str
    secretary: str
    actor: ActorRef
    principal: ActorRef
    attacker: ActorRef
    action: str
    cast: SceneCast
    weapon: str
    event: str
    account: str = Field(min_length=1, max_length=1200)
    phase: Literal[
        "awaiting_attacker",
        "responding",
        "awaiting_resolution",
        "withdrawn",
        "released",
        "proceeded",
    ] = "awaiting_attacker"
    response_event: str | None = None
    response_account: str | None = None
    response_action: str | None = None
    response_started: str | None = None
    resolution_event: str | None = None
    resolution_account: str | None = None


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "secretary_acquisition"
    )


def secretaries(state: GameState) -> tuple[Secretary, ...]:
    return tuple(
        Secretary.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "personal_secretary"
    )


def performances(state: GameState) -> tuple[Performed, ...]:
    return tuple(
        Performed.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "secretary_performed"
    )


def gunpoints(state: GameState) -> tuple[Gunpoint, ...]:
    return tuple(
        Gunpoint.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "secretary_gunpoint"
    )


def put(state: GameState, value: Acquisition | Secretary | Performed | Gunpoint) -> None:
    kind = {
        Acquisition: "secretary_acquisition",
        Secretary: "personal_secretary",
        Performed: "secretary_performed",
        Gunpoint: "secretary_gunpoint",
    }[type(value)]
    if not isinstance(value, Gunpoint) and any(
        x.get("kind") == kind and x.get("id") == value.id for x in state.facts
    ):
        raise ValueError("Preserve this immutable original Secretary source event")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def held(state: GameState, actor: ActorRef) -> Secretary | None:
    return next((x for x in secretaries(state) if x.actor == actor), None)


def pending(state: GameState, action: str) -> Gunpoint | None:
    return next(
        (
            x
            for x in gunpoints(state)
            if x.action == action
            and x.phase in ("awaiting_attacker", "responding", "awaiting_resolution")
        ),
        None,
    )


def scene_gunpoints(state: GameState, scene: str) -> list[dict[str, Any]]:
    return [
        dict(
            id=x.id,
            action=x.action,
            attacker=x.attacker.model_dump(mode="json"),
            secretary=x.actor.model_dump(mode="json"),
            phase=x.phase,
        )
        for x in gunpoints(state)
        if x.cast.id == scene
        and x.phase in ("awaiting_attacker", "responding", "awaiting_resolution")
    ]


def reads_performance(value: Performed, controller: int) -> bool:
    if value.principal.entity == str(controller):
        return True
    if value.recipient_roles:
        return any(x.controller == controller for x in value.recipient_roles)
    return any(x.entity == str(controller) for x in value.recipients)
