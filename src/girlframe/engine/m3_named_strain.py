"""A Director-authored Strain track with two actual effects on each saved die face."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_custom_strain import Column
from girlframe.engine.rolls import Face


class Option(Model):
    title: str = Field(min_length=1, max_length=120)
    tag: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def named(self) -> "Option":
        if not self.title.strip() or not self.tag.strip():
            raise ValueError("Each column needs a real authored event and Tag")
        return self


class Design(Model):
    name: str = Field(min_length=1, max_length=80)
    npc: str = Field(min_length=1, max_length=100)
    faces: tuple[tuple[Option, Option], ...] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def original_track(self) -> "Design":
        if not self.name.strip() or not self.npc.strip():
            raise ValueError("Name the actual new Strain track and its original NPC")
        if any(left == right for left, right in self.faces):
            raise ValueError("Give the Handler two distinct events for each new face")
        return self


class Table(Model):
    id: str
    director: ActorRef
    controller: int
    target_controller: int
    design: Design
    account: str = Field(min_length=1, max_length=1200)


class SavedRoll(Model):
    id: str
    period_id: str | None
    track: str
    handler: ActorRef
    source: str
    rng_source: Literal["os", "test_injected"]
    face: Face
    column: Column | None = None
    applied: str | None = None

    @model_validator(mode="after")
    def actual_effect(self) -> "SavedRoll":
        if self.handler.kind != "handler" or (self.column is None) != (self.applied is None):
            raise ValueError(
                "The original Handler's choice accompanies the actual new track effect"
            )
        return self


def tables(state: GameState) -> tuple[Table, ...]:
    return tuple(
        Table.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "named_strain"
    )


def rolls(state: GameState) -> tuple[SavedRoll, ...]:
    return tuple(
        SavedRoll.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "named_strain_roll"
    )


def register(state: GameState, table: Table) -> None:
    if any(
        x.design.name.strip().casefold() == table.design.name.strip().casefold()
        for x in tables(state)
    ):
        raise ValueError("Name a new Strain track that does not already exist")
    state.facts.append(dict(kind="named_strain", id=table.id, body=table.model_dump_json()))


def save_roll(state: GameState, roll: SavedRoll) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != ("named_strain_roll", roll.id)
    ] + [dict(kind="named_strain_roll", id=roll.id, body=roll.model_dump_json())]
