"""Offer only native Play controls available to the approved scene actor."""

from collections.abc import Callable
from typing import Any, NotRequired, TypedDict, cast

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
    alternate: NotRequired[dict[str, Any]]


PlayProjection = Callable[[Connection, dict[str, Any], ActorRef], tuple[NativePlayOption, ...]]


def initiative_play_options(
    context: DirectorContextService,
    c: Connection,
    scene: str,
    actor: ActorRef,
    *,
    alternate: bool = False,
) -> tuple[NativePlayOption, ...]:
    if alternate and actor.kind in ("npc", "external_pilot", "gorgon"):
        native = getattr(context.native_play_projection, "alternate", None)
        if native is not None:
            return cast(PlayProjection, native)(c, context.observations._scene(c, scene), actor)
        return ()
    project = context.native_play_projection
    if actor.kind not in ("pilot", "handler") or project is None:
        return ()
    return project(c, context.observations._scene(c, scene), actor)
