"""The original Jackdaw's Hallucinations and their durable role-specific consequences."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, tier
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.rolls import Face

RULE = "gorgon-type.jackdaw.hallucinations"
PLAYS = ("jackdaw_hallucinations", "jackdaw_hallucinations_day")
KIND = "jackdaw_hallucinations"


class Roll(Model):
    faces: tuple[Face, Face]
    heat: int = Field(ge=0)
    event: str

    @property
    def result(self) -> Literal["low", "mid", "high"]:
        return tier(sum(self.faces) + self.heat)


class Effect(Model):
    action: str
    scene: str
    source: ActorRef
    girl: ActorRef
    interference: str
    roll: Roll
    tag: str
    event: str
    identities_erased: tuple[str, ...] = ()
    identity: str | None = None
    void_asset: str | None = None
    void_work: tuple[str, ...] = ()


def records(state: GameState) -> tuple[Effect, ...]:
    return tuple(
        Effect.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def immunity(state: GameState, girl: ActorRef, interference: str) -> bool:
    return any(
        x.girl == girl and x.interference == interference and x.roll.result == "high"
        for x in records(state)
    )


DAY_KIND = "jackdaw_hallucinations_day"


class DailyVoid(Model):
    action: str
    scene: str
    source: ActorRef
    girl: ActorRef
    original: str
    day: int = Field(ge=1)
    review: str
    event: str
    void_asset: str | None = None
    void_work: tuple[str, ...] = ()


def days(state: GameState, original: str | None = None) -> tuple[DailyVoid, ...]:
    values = (
        DailyVoid.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == DAY_KIND
    )
    return tuple(x for x in values if original is None or original == x.original)
