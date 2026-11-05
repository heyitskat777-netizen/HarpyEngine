"""One native Priestess relationship and actual Off-Duty treatment scene."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_nightmare import native
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import ComfortScene, FrameRuleReceipt

RULE = "frame.class.priestess.void-physiotherapist"
KIND = "physiotherapist"


class Therapy(Model):
    id: str
    actor: ActorRef
    npc: ActorRef
    controller: int
    purchase: str
    phase: Literal["bond", "ready", "scene", "closed"] = "bond"
    source_event: str
    event: str
    relationship: str = Field(min_length=1, max_length=1200)
    accepted_account: str = Field(default="", max_length=1200)
    period: str | None = None
    scene: ComfortScene | None = None
    asset: str | None = None
    treatment: str = Field(default="", max_length=1200)
    tag: str | None = None


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    try:
        sheet, frame = native(state, actor)
    except (ValueError, KeyError):
        return None
    return next(
        (
            x
            for x in state.requisitions
            if isinstance(x, FrameRuleReceipt)
            and x.actor == actor
            and x.frame_instance == frame
            and x.frame == sheet.frame
            and x.donor_frame == sheet.frame
            and x.rule_id == RULE
            and x.kind == "ability_unlock"
            and not suspended(state, x.id)
        ),
        None,
    )


def put(state: GameState, value: Therapy) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == KIND and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))


def scene(
    state: GameState,
    bindings: tuple[ProfileBinding, ...],
    value: Therapy,
    cast: SceneCast,
    location: str,
    summary: str,
    identity: str,
) -> ComfortScene:
    participants = {value.actor, value.npc}
    roles = tuple(x for x in cast.roles if x.actor in participants)
    place = (
        next((x for x in state.world.locations if x.id == location and x.operational), None)
        if state.world
        else None
    )
    if not cast.open or {x.actor for x in roles} != participants or place is None:
        raise ValueError("Record the actual two roles in an open scene at a surviving location")
    for role in roles:
        actual = resolve(state, role.actor, bindings, require_current_profile=False)
        if (
            actual.controller != role.controller
            or actual.controller
            != (int(value.actor.entity) if role.actor == value.actor else value.controller)
            or (actual.cell is not None and actual.cell != place.cell)
        ):
            raise ValueError(
                "Actual casting does not move bodies or supply another human's attendance"
            )
    return ComfortScene(
        id=identity,
        cast_id=cast.id,
        cast_revision=cast.revision,
        location=location,
        roles=roles,
        summary=summary,
        acknowledgements=(int(value.actor.entity),),
    )
