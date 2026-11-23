"""Offer only native Play controls available to the approved scene actor."""

from collections.abc import Callable
from typing import TypedDict

from sqlalchemy import Connection

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.director_context import DirectorContextService


class NativePlayOption(TypedDict):
    id: str
    label: str
    destination: str
    trigger: str
    control: str
    room: str


PlayProjection = Callable[[Connection, dict, ActorRef], tuple[NativePlayOption, ...]]


def initiative_play_options(
    context: DirectorContextService, c: Connection, scene: str, actor: ActorRef
) -> tuple[NativePlayOption, ...]:
    project = context.native_play_projection
    if actor.kind not in ("pilot", "handler") or project is None:
        return ()
    return project(c, context.observations._scene(c, scene), actor)
