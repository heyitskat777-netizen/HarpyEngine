"""Authored Strain effects with their own canonical consequences and dice provenance."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_strain_state import Event, Severity, Track
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import WorldTag
from girlframe.engine.rolls import Face

RULE = "strain.custom-events"
PAGE = 143
Mode = Literal["additional", "instead_of_roll", "replace_slot"]
Column = Literal[1, 2]


class Design(Model):
    title: str = Field(min_length=1, max_length=120)
    account: str = Field(min_length=1, max_length=1200)
    npc: str = Field(min_length=1, max_length=100)
    tag: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def actual_event(self) -> "Design":
        if not all(x and x == x.strip() for x in (self.title, self.account, self.npc, self.tag)):
            raise ValueError("Record the name, actual original NPC, Tag and event context")
        return self


class Slot(Model):
    track: Track
    severity: Severity
    face: Face
    column: Column


class Replacement(Model):
    id: str
    slot: Slot
    actor: ActorRef
    controller: int
    period: str | None
    roll: str | None
    target_controller: int
    design: Design


class Occurrence(Model):
    id: str
    mode: Mode | Literal["named_track"]
    actor: ActorRef
    controller: int
    period: str | None
    track: Track | None = None
    source_work: str | None = None
    replaces: str | None = None
    target_controller: int
    design: Design


def replacements(state: GameState) -> tuple[Replacement, ...]:
    return tuple(
        Replacement.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "custom_strain_slot"
    )


def occurrences(state: GameState) -> tuple[Occurrence, ...]:
    return tuple(
        Occurrence.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "custom_strain_event"
    )


def replacement(state: GameState, roll: Event, column: Column) -> Replacement | None:
    slot = Slot(track=roll.track, severity=roll.severity, face=roll.face, column=column)
    return next((x for x in reversed(replacements(state)) if x.slot == slot), None)


def register(state: GameState, value: Replacement) -> None:
    state.facts.append(dict(kind="custom_strain_slot", id=value.id, body=value.model_dump_json()))


def apply(state: GameState, value: Occurrence) -> None:
    world = state.world
    npc = (
        next((x for x in world.npcs if x.id == value.design.npc and x.alive), None)
        if world
        else None
    )
    if (
        world is None
        or npc is None
        or npc.controller != value.target_controller
        or "director" in npc.jobs
        or npc.cell is None
        or not in_responsibility(state, npc.cell)
    ):
        raise ValueError("Recover the custom event's actual living NPC before applying its effect")
    tag = WorldTag(id=value.id, label=value.design.tag, giver_entity=value.actor.model_dump_json())
    state.world = update(
        world,
        npcs=tuple(
            x.model_copy(update={"tags": (*x.tags, tag)}) if x.id == npc.id else x
            for x in world.npcs
        ),
    )
    state.facts.append(dict(kind="custom_strain_event", id=value.id, body=value.model_dump_json()))
