"""One actual Ankou nomination linked to one genuine owned source recipe."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

KIND = "required_play_link"


class Release(Model):
    action: str
    bound_event: str
    event: str


class RequiredLink(Model):
    id: str
    provider: Literal["ankou_nomination"] = "ankou_nomination"
    source: str
    recipe: str
    rule: Literal[
        "frame.ankou.processor-core",
        "girl.mockingbird.bad-at-being-a-person",
        "girl.mockingbird.sex-play",
        "girl.alpha.sex-play",
        "girl.stim-blissed.dose-up",
        "girl.stim-blissed.sex-play",
        "girl.princess.sex-play",
        "girl.oldgen.sex-play",
        "girl.newgirl.sex-play",
        "girl.vatgrown.sex-play",
        "girl.casualty.sex-play",
    ] = "girl.alpha.sex-play"
    actor: ActorRef
    target: ActorRef
    cast: SceneCast
    event: str
    action: str | None = None
    bound_event: str | None = None
    completed_event: str | None = None
    releases: tuple[Release, ...] = ()
    retired_event: str | None = None
    withdrawn_event: str | None = Field(default=None, exclude_if=lambda value: value is None)


def identity(source: str, recipe: str, event: str) -> str:
    return str(
        uuid5(NAMESPACE_URL, "girlframe:required-play:" + source + ":" + recipe + ":" + event)
    )


def records(state: GameState) -> tuple[RequiredLink, ...]:
    return tuple(
        RequiredLink.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def get(state: GameState, identity: str) -> RequiredLink:
    value = next((x for x in records(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original required-Play link")
    return value


def put(state: GameState, value: RequiredLink) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == KIND and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))


class SelfDoseRecipe(Model):
    """Immutable own self-dose preparation, not a Contact or a drug grant."""

    id: str
    source: str
    actor: ActorRef
    target: ActorRef
    cast: SceneCast
    event: str
    actor_position: str | None
    actor_vessel: str | None


def self_dose_recipes(state: GameState) -> tuple[SelfDoseRecipe, ...]:
    return tuple(
        SelfDoseRecipe.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "required_self_dose_recipe"
    )


def self_dose_recipe(state: GameState, identity: str) -> SelfDoseRecipe:
    value = next((x for x in self_dose_recipes(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original self-Dose recipe")
    return value


def put_self_dose_recipe(state: GameState, value: SelfDoseRecipe) -> None:
    if any(x.id == value.id for x in self_dose_recipes(state)):
        raise ValueError("Preserve the immutable original self-Dose recipe")
    state.facts.append(
        dict(kind="required_self_dose_recipe", id=value.id, body=value.model_dump_json())
    )
