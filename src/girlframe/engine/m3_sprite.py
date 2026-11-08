"""Actual Sprite interception preserves the original roll and targets real bodies/Assets."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import frame_position, resolve


class Candidate(Model):
    actor: ActorRef
    controller: int
    assets: tuple[str, ...]


class Blow(Model):
    target: ActorRef
    asset: str | None
    opponent: ActorRef | None
    chooser: int | None
    source_action: str | None
    source_work: str | None
    source_event: str
    target_frame: str | None = Field(default=None, exclude_if=lambda value: value is None)
    occurrence: str
    indirect: bool = False
    effect: Literal["damage", "fatal", "destroy"] = "damage"
    candidates: tuple[Candidate, ...]


def candidates(
    state: GameState,
    target: ActorRef,
    opponent: ActorRef | None,
    bindings: tuple[ProfileBinding, ...],
    *,
    target_frame: str | None = None,
) -> tuple[Candidate, ...]:
    if state.world is None:
        return ()
    target_body = resolve(state, target, bindings, require_current_profile=False)
    target_cell = frame_position(state, target, target_frame) if target_frame else target_body.cell
    if target_cell is None or target_frame is None and target_body.offstage_source:
        return ()
    result = []
    for sprite in state.world.gorgons:
        ref = ActorRef(kind="gorgon", entity=sprite.id)
        if not sprite.alive or sprite.gorgon_class != "sprite" or ref in (target, opponent):
            continue
        body = resolve(state, ref, ())
        owned = tuple(x.id for x in sprite.assets if not x.damaged)
        if (
            body.cell is not None
            and body.cell == target_cell
            and not body.offstage_source
            and owned
        ):
            result.append(Candidate(actor=ref, controller=body.controller, assets=owned))
    return tuple(result)


def consume_effect(blow: Blow) -> Literal["bite", "kill"] | None:
    """Classification only; the service must prove the real original Eat choice/work."""
    if blow.source_action is not None:
        if (blow.occurrence, blow.effect) == ("consume_bite", "damage"):
            return "bite"
        if (blow.occurrence, blow.effect) == ("consume_kill", "fatal"):
            return "kill"
    return None
