"""The Gorgon rolls with the actual original occupied Frame's Void assets."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, tier
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.engine.rolls import Face

PLAY = "intimate_frame_contact"
RULE = "gorgon.gorgon.gorgons-fucking-frames"


class Roll(Model):
    faces: tuple[Face, Face]
    void_assets: tuple[str, ...]
    event: str
    frame: str = Field(min_length=1)

    @property
    def result(self) -> Literal["low", "mid", "high"]:
        return tier(sum(self.faces) + len(self.void_assets))


def frame_void(state: GameState, girl: ActorRef) -> tuple[str, ...]:
    return tuple(x.id for x in effective_assets(state, girl) if x.family == "frame" and x.void)


KIND = "gorgon_frame_contact_consequence"


class Consequence(Model):
    action: str
    scene: str
    event: str
    source: ActorRef
    girl: ActorRef
    roll: Roll
    damaged_asset: str
    void_asset: str | None = None
    void_work: str | None = None
    core_exposed: bool
    punishment_if_discovered: bool


def results(state: GameState) -> tuple[Consequence, ...]:
    return tuple(
        Consequence.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )
