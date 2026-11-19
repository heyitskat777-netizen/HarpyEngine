"""An actual NPC order's original Broken-relative authority, never controller rank."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_alpha import conditions, current
from girlframe.engine.m3_alpha_state import Broken

Origin = Literal[
    "broken",
    "am_secret",
    "secretary",
    "npc_flirt",
    "stim_sex",
    "rebel_voice",
    "harpy_echoes",
    "npc_handler",
]

FACT_KINDS: dict[Origin, str] = {
    "broken": "npc_broken_order",
    "am_secret": "npc_am_secret_order",
    "secretary": "npc_secretary_order",
    "npc_flirt": "npc_flirt_order",
    "stim_sex": "npc_stim_order",
    "rebel_voice": "npc_rebel_voice_order",
    "harpy_echoes": "harpy_echoes_order",
    "npc_handler": "npc_handler_order",
}


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
    principal: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    origin_kind: Origin = Field(default="broken", exclude_if=lambda value: value == "broken")
    voice: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    voice_label: str | None = Field(default=None, exclude_if=lambda value: value is None)

    def audience(self) -> list[int]:
        facilitator = {self.cast.facilitator} if self.cast.facilitator is not None else set()
        if self.origin_kind == "npc_handler":
            return sorted({self.controller, int(self.target.entity)} | facilitator)
        return sorted({x.controller for x in self.cast.roles} | facilitator)

    @model_validator(mode="after")
    def voice_source(self) -> "Order":
        if (self.voice is None) != (self.voice_label is None) or (
            self.voice is not None and self.origin_kind != "harpy_echoes"
        ):
            raise ValueError("Use an exact supported fictional voice source")
        return self


def authority(state: GameState, issuer: ActorRef, target: ActorRef) -> Broken:
    if issuer.kind != "npc" or target.kind != "pilot" or not current(state, issuer):
        raise ValueError("An actual living original NPC issues this Broken-relative order")
    if not current(state, target):
        raise ValueError("Only the actual original Broken Pilot receives this order")
    found = conditions(state, target, issuer)
    if len(found) != 1:
        raise ValueError("A real active Broken condition against this exact NPC is required")
    return found[0]
