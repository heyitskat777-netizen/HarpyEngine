"""One actual Ankou nomination linked to one genuine owned Alpha recipe."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

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
    rule: Literal["girl.alpha.sex-play"] = "girl.alpha.sex-play"
    actor: ActorRef
    target: ActorRef
    cast: SceneCast
    event: str
    action: str | None = None
    bound_event: str | None = None
    completed_event: str | None = None
    releases: tuple[Release, ...] = ()
    retired_event: str | None = None


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
