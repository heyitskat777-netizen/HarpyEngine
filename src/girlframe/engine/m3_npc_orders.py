"""An actual NPC order's original Broken-relative authority, never controller rank."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_alpha import conditions, current
from girlframe.engine.m3_alpha_state import Broken

Origin = Literal["broken", "am_secret"]


class Order(Model):
    id: str
    action: str
    issuer: ActorRef
    target: ActorRef
    controller: int
    condition: str
    event: str
    cast: SceneCast
    registry: str
    instruction: str = Field(min_length=1, max_length=1200)
    origin_kind: Origin = Field(default="broken", exclude_if=lambda value: value == "broken")


def authority(state: GameState, issuer: ActorRef, target: ActorRef) -> Broken:
    if issuer.kind != "npc" or target.kind != "pilot" or not current(state, issuer):
        raise ValueError("An actual living original NPC issues this Broken-relative order")
    if not current(state, target):
        raise ValueError("Only the actual original Broken Pilot receives this order")
    found = conditions(state, target, issuer)
    if len(found) != 1:
        raise ValueError("A real active Broken condition against this exact NPC is required")
    return found[0]
