"""A human selects an actual original role; relationship bonuses never use controller IDs."""

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, ProfileBinding, SceneCast
from girlframe.engine.m3_actors import resolve


class Marker(Model):
    actor: ActorRef | None
    controller: int
    source_binding: str = Field(min_length=1)
    source_actor_sha256: str = Field(min_length=1)
    label: str
    bond_depth: int = Field(default=0, ge=0, le=2)
    bonus: int = Field(default=1, ge=1, le=2)

    @model_validator(mode="after")
    def no_body_authority(self) -> "Marker":
        if self.actor is None and (self.bond_depth != 0 or self.bonus != 1):
            raise ValueError("An OOC human has no fictional Bond or Status authority")
        return self

    @property
    def token(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


def make_marker(state: GameState, view: ActorView, binding: str, roller: ActorRef) -> Marker:
    amount = depth(state, roller, view.ref)
    bonus = 2 if amount == 1 else int(state.intense_tag_bonus or 1) if amount == 2 else 1
    return Marker(
        actor=view.ref,
        controller=view.controller,
        source_binding=binding,
        source_actor_sha256=view.source_sha256,
        label=view.label,
        bond_depth=amount,
        bonus=bonus,
    )


def ooc_marker(controller: int, binding: str, source: str) -> Marker:
    return Marker(
        actor=None,
        controller=controller,
        source_binding=binding,
        source_actor_sha256=hashlib.sha256(source.encode()).hexdigest(),
        label="OOC facilitator (no fictional body)",
    )


def markers(
    state: GameState,
    bindings: tuple[ProfileBinding, ...],
    cast: SceneCast,
    controller: int,
    roller: ActorRef,
    handler: ActorRef | None,
) -> tuple[Marker, ...]:
    result: list[Marker] = []
    rolling_human = resolve(state, roller, bindings, require_current_profile=False).controller
    for role in cast.roles:
        if role.controller != controller:
            continue
        view = resolve(state, role.actor, bindings, require_current_profile=False)
        if view.controller != controller:
            raise ValueError("STALE_TAG_MARKER: recover the original role's actual controller")
        if controller == rolling_human and role.actor != roller:
            continue  # A second role never bypasses the rolling human's self-mark restriction.
        result.append(make_marker(state, view, role.source_event, roller))
    if (
        controller == cast.facilitator
        and controller == state.handler
        and cast.facilitator_source is not None
        and controller != rolling_human
        and (handler is None or not any(x.actor == handler for x in result))
    ):
        if handler is None:
            result.append(
                ooc_marker(
                    controller,
                    cast.facilitator_source,
                    cast.model_dump_json()
                    + ":"
                    + ":".join(x.source_event for x in state.handler_archives),
                )
            )
        else:
            view = resolve(state, handler, bindings, require_current_profile=False)
            result.append(make_marker(state, view, cast.facilitator_source, roller))
    return tuple(result)


def modifier(state: GameState, roller: ActorRef, marker: Marker, direction: Literal[-1, 1]) -> int:
    amount = depth(state, roller, marker.actor) if marker.actor is not None else 0
    bonus = 2 if amount == 1 else int(state.intense_tag_bonus or 1) if amount == 2 else 1
    if amount != marker.bond_depth or bonus != marker.bonus:
        raise ValueError("STALE_TAG_MARKER: review the actual changed source Bond and modifier")
    return bonus * direction
