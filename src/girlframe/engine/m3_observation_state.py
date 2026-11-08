"""Saved Observation authority and choices; no implicit answers for either human."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import Model

Kind = Literal[
    "remove_girl_void_asset",
    "remove_frame_void_asset",
    "assigned_observer",
    "medical_probing",
    "hospital_stay",
    "public_display_tag",
    "moderate_punishment",
    "reprogram",
    "become_dog",
    "harpy_candidate_tag",
    "director_or_rival_arrives",
]


class Outcome(Model):
    id: str
    kind: Kind
    chooser: Snowflake
    resolved: bool = False
    source_event: str | None = None


class Observation(Model):
    source_event: str
    obligations: tuple[str, ...] = Field(min_length=1)
    suspects_hiding: bool
    hiding_review_event: str | None = None
    actor_choices: tuple[Kind, ...] | None = None
    handler_choices: tuple[Kind, ...] | None = None
    outcomes: tuple[Outcome, ...] = ()

    @model_validator(mode="after")
    def distinct(self) -> "Observation":
        values = (*(self.actor_choices or ()), *(self.handler_choices or ()))
        if len(values) != len(set(values)) or len({x.id for x in self.outcomes}) != len(
            self.outcomes
        ):
            raise ValueError("Observation choices and outcome IDs must remain distinct")
        if {x.kind for x in self.outcomes} != set(values):
            raise ValueError("Each selected Observation consequence needs its actual outcome")
        return self


class Details(Model):
    asset: str | None = None
    npc: str | None = None
    tag: str = Field(default="", max_length=120)
    identity: str | None = None
    slot: str | None = None
    account: str = Field(min_length=1, max_length=1200)
