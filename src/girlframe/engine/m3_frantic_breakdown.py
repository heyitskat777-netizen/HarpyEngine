"""An original Frantic breakdown keeps its roll, chooser roles and consequences."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState, tier
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.rolls import Face

RULE = "handler-playbook.frantic.break-down"
Option = Literal["office", "minor_all", "moderate_one"]
OPTIONS: dict[Option, str] = {
    "office": "Choose a Girl to find you in your office",
    "minor_all": "Minor Punishment for each original Girl",
    "moderate_one": "Moderate Punishment for one original Girl",
}


class Selection(Model):
    option: Option
    chooser: ActorRef
    event: str
    target: ActorRef | None = None
    debts: tuple[str, ...] = ()
    discovered_event: str | None = None

    @model_validator(mode="after")
    def exact(self) -> "Selection":
        if (
            (self.target is None) != (self.option == "minor_all")
            or bool(self.debts) != (self.option in ("minor_all", "moderate_one"))
            or (self.discovered_event and self.option != "office")
        ):
            raise ValueError("Keep the actual targets and consequences of this breakdown choice")
        return self


class Breakdown(Model):
    id: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    handler: ActorRef
    scene: str = Field(min_length=1)
    channel: int = Field(gt=0)
    faces: tuple[Face, Face]
    bases: tuple[str, ...]
    cadre: tuple[ActorRef, ...]
    in_scene: tuple[ActorRef, ...]
    ace: ActorRef
    dog: ActorRef
    account: str = Field(min_length=1, max_length=1200)
    choices: tuple[Selection, ...] = ()

    @property
    def total(self) -> int:
        return sum(self.faces) + len(self.bases)

    def next_choice(self) -> tuple[ActorRef, int] | None:
        level = tier(self.total)
        count = len(self.choices)
        if level == "low":
            return (self.dog, 3) if count == 0 else None
        if level == "mid":
            return (self.handler, 2) if count == 0 else None
        if count == 0:
            return self.handler, 1
        return (self.ace, 1) if count == 1 else None

    @model_validator(mode="after")
    def original(self) -> "Breakdown":
        if (
            self.handler.kind != "handler"
            or len(set(self.bases)) != len(self.bases)
            or len(set(self.cadre)) != len(self.cadre)
            or not set(self.in_scene) <= set(self.cadre)
            or self.ace not in self.cadre
            or self.dog not in self.cadre
            or self.ace == self.dog
            or len({x.option for x in self.choices}) != len(self.choices)
        ):
            raise ValueError("Preserve the original Frantic, Cadre, Status and base modifier")
        return self


def records(state: GameState) -> tuple[Breakdown, ...]:
    return tuple(
        Breakdown.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "frantic_breakdown"
    )


def put(state: GameState, value: Breakdown) -> None:
    state.facts = [
        x for x in state.facts if x.get("kind") != "frantic_breakdown" or x.get("id") != value.id
    ]
    state.facts.append(dict(kind="frantic_breakdown", id=value.id, body=value.model_dump_json()))


def phase(state: GameState, value: Breakdown) -> Literal["choice", "effects", "complete"]:
    if value.next_choice() is not None:
        return "choice"
    terminal = {x.id for x in state.obligations if x.state == "fulfilled"}
    for item in value.choices:
        if (
            item.option == "office"
            and item.discovered_event is None
            or not set(item.debts) <= terminal
        ):
            return "effects"
    return "complete"
