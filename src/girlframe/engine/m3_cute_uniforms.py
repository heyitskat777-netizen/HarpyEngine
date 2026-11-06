"""Actual original-body uniforms, separate forced presentation and Tag-like marking."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "handler-advancement.handler-advancement.cute-uniforms"
PRESENTATION = "I seem helpless and adorable."


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Uniform(Model):
    id: str
    acquisition: str
    handler: ActorRef
    target: ActorRef
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1200)
    cell: tuple[int, int]
    position: str
    event: str
    phase: Literal["proposed", "declined", "worn", "rejected"] = "proposed"
    wearing: bool = False
    dressing_event: str | None = None
    dressing_account: str | None = None
    tag: TagState | None = None
    asset: str | None = None
    embraced_identity: str | None = None
    rejection_event: str | None = None
    punishment: str | None = None

    @model_validator(mode="after")
    def real_original_event(self) -> "Uniform":
        if self.handler.kind != "handler" or self.target.kind != "pilot":
            raise ValueError("Keep the actual original Handler and Girl")
        dressed = self.phase in ("worn", "rejected")
        if dressed != bool(self.dressing_event and self.dressing_account and self.tag):
            raise ValueError("An active uniform needs its actual owner-confirmed dressing")
        if self.phase != "worn" and self.wearing:
            raise ValueError("An unperformed or rejected dressing is not actually worn")
        if (self.phase == "rejected") != bool(self.rejection_event and self.punishment):
            raise ValueError("Keep the real uniform rejection and Punishment source")
        if self.tag is not None and (
            self.tag.id != self.id or self.tag.giver_actor != self.handler
        ):
            raise ValueError("Keep the actual Handler-authored uniform Tag")
        return self


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "cute_uniform_acquisition"
    )


def uniforms(state: GameState) -> tuple[Uniform, ...]:
    return tuple(
        Uniform.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "cute_uniform"
    )


def put(state: GameState, value: Acquisition | Uniform) -> None:
    kind = "cute_uniform_acquisition" if isinstance(value, Acquisition) else "cute_uniform"
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def owned(state: GameState, owner: int) -> tuple[Uniform, ...]:
    return tuple(
        x
        for x in uniforms(state)
        if str(owner) in state.sheets
        and x.target == current_ref(state, owner)
        and x.phase == "worn"
    )


def tags(state: GameState, owner: int) -> list[TagState]:
    return [x.tag for x in owned(state, owner) if x.tag is not None and x.embraced_identity is None]


def save_tag(state: GameState, owner: int, tag: TagState) -> None:
    for value in owned(state, owner):
        if value.id == tag.id:
            put(state, value.model_copy(update=dict(tag=tag)))
            return
