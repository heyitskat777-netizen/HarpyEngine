"""The higher-ups' attack against an original person or Foundation base."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_world_state import AdversaryPilot, Cell

RULE = "strain.budget.high.5.2"
KIND = "strain_foundation_attack"


class Attack(Model):
    id: str
    period: str
    source: str
    handler: ActorRef
    pilot: ActorRef
    controller: int
    base: str | None = None
    cell: Cell
    target: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    attempt: str | None = None
    account: str = Field(default="", max_length=1200)
    cast: SceneCast | None = None
    defenders: tuple[ActorRef, ...] = ()
    resolution: str | None = None
    strike: str | None = Field(default=None, exclude_if=lambda value: value is None)
    followups: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)
    result: Literal["destroyed", "averted", "struck"] | None = None


def attacks(state: GameState) -> tuple[Attack, ...]:
    return tuple(
        Attack.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, attack: Attack) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, attack.id)] + [
        dict(kind=KIND, id=attack.id, body=attack.model_dump_json())
    ]


def pilot(state: GameState, identity: str | None) -> AdversaryPilot:
    original = (
        next((x for x in state.world.pilots if x.id == identity), None) if state.world else None
    )
    if (
        original is None
        or original.kind != "foundation"
        or not original.revealed
        or not original.alive
        or original.custody != "free"
        or original.controller == state.handler
        or not any(x.family == "frame" and not x.damaged for x in original.assets)
    ):
        raise ValueError("Recover the original known Foundation Pilot under independent control")
    return original
