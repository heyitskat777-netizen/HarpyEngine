"""One actual Handler rule source, Mission use and delivered temporary Frame equipment."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "handler-advancement.handler-advancement.supply-drop"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Use(Model):
    id: str
    acquisition: str
    handler: ActorRef
    mission: str
    target: ActorRef
    frame: str
    kind: Literal["repair", "drop"]
    phase: Literal["proposed", "repaired", "delivered", "declined", "cancelled", "expired"]
    asset: str
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1200)
    position: str
    cell: tuple[int, int] | None
    event: str
    account: str = Field(min_length=1, max_length=1200)
    effect_event: str | None = None
    effect_account: str | None = None
    replacement: str | None = None
    expiry_event: str | None = None
    context_event: str | None = None
    in_battle: bool | None = None
    reviewer: ActorRef | None = None
    context_account: str | None = None

    @model_validator(mode="after")
    def actual_effect(self) -> "Use":
        if self.target.kind != "pilot" or self.handler.kind != "handler":
            raise ValueError("Use this actual original Handler and Girl source")
        if self.phase in ("repaired", "delivered", "expired") and not self.effect_event:
            raise ValueError("Keep the actual repair or delivery event")
        if (self.phase == "expired") != (self.expiry_event is not None):
            raise ValueError("Expiry keeps its exact actual mechanical removal event")
        if self.kind == "drop" and self.cell is None:
            raise ValueError("Deliver temporary equipment at its actual known Frame position")
        return self


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "supply_drop_acquisition"
    )


def uses(state: GameState) -> tuple[Use, ...]:
    return tuple(
        Use.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "supply_drop_use"
    )


def put(state: GameState, value: Acquisition | Use) -> None:
    kind = "supply_drop_acquisition" if isinstance(value, Acquisition) else "supply_drop_use"
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def spent(state: GameState, acquisition: str, mission: str) -> bool:
    return any(
        x.acquisition == acquisition
        and x.mission == mission
        and x.phase in ("repaired", "delivered", "expired")
        for x in uses(state)
    )


def live(state: GameState, actor: ActorRef) -> tuple[Use, ...]:
    return tuple(
        x for x in uses(state) if x.target == actor and x.kind == "drop" and x.phase == "delivered"
    )


def require_temporary_clear(state: GameState, actor: ActorRef) -> None:
    if live(state, actor):
        raise ValueError("Expire the actual Mission Supply Drop before moving its Frame container")


def current_asset(state: GameState, value: Use) -> str:
    """A real Modular repair replacement retains the original equipment's temporary source."""
    identity = value.asset
    seen = {identity}
    while True:
        next_ids = {
            x["new"]
            for x in state.facts
            if x.get("kind") == "modular_repair"
            and x.get("actor") == value.target.model_dump_json()
            and x.get("old") == identity
        }
        if not next_ids:
            return identity
        if len(next_ids) != 1 or next(iter(next_ids)) in seen:
            raise ValueError("Recover the actual temporary equipment repair lineage")
        identity = next(iter(next_ids))
        seen.add(identity)
