"""Actual Gorgon Dormant cost changes its sole original World Asset authority."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model


class Payment(Model):
    work: str = Field(min_length=1)
    actor: ActorRef
    dormant: ActorRef
    event: str = Field(min_length=1)
    outcome: Literal["asset_altered", "already_fully_void"]
    asset: str | None
    before_assets: tuple[str, ...]
    description: str = Field(min_length=1, max_length=1200)
    dive_eligible: Literal[False] = False
    dive_reason: Literal["gorgon_has_no_frame_play"] = "gorgon_has_no_frame_play"

    @model_validator(mode="after")
    def actual_body(self) -> "Payment":
        if (
            self.actor.kind != "gorgon"
            or self.dormant.kind != "gorgon"
            or self.actor == self.dormant
        ):
            raise ValueError("The cost names the actual distinct attacking and awakened Gorgon")
        if not self.before_assets or not self.description.strip():
            raise ValueError("Record the actual original Gorgon resources and their alteration")
        if (self.outcome == "asset_altered") != (self.asset is not None):
            raise ValueError(
                "A real alteration and an already-fully-Void fact are distinct outcomes"
            )
        return self


def inflict(
    original: GameState,
    actor: ActorRef,
    dormant: ActorRef,
    work: str,
    asset: str | None,
    description: str,
    event: str,
) -> GameState:
    """No new Asset/Frame, Heat, HP, Harpy conversion or controller Pilot is invented."""
    if actor.kind != "gorgon" or dormant.kind != "gorgon" or actor == dormant:
        raise ValueError("Use the original actual Gorgon that incurred this Dormant cost")
    if not event.strip() or not work.strip() or not description.strip():
        raise ValueError("The actual cost needs its real source and owned description")
    if any(
        x.get("kind") == "gorgon_dormant_void_paid" and x.get("work") == work
        for x in original.facts
    ):
        raise ValueError("This original counter already has its actual Void outcome")
    body = (
        next((x for x in original.world.gorgons if x.id == actor.entity and x.alive), None)
        if original.world
        else None
    )
    if body is None or not body.assets:
        raise ValueError("Recover the original living Gorgon and actual extant World Assets")
    selected = next((x for x in body.assets if x.id == asset), None)
    if asset is None:
        if not all(x.void for x in body.assets):
            raise ValueError("An actual uncorrupted Gorgon Asset must take the gained Void")
        outcome: Literal["asset_altered", "already_fully_void"] = "already_fully_void"
        resources = body.assets
    else:
        if selected is None or selected.void:
            raise ValueError("Choose the actual original Gorgon's uncorrupted World Asset")
        if description.strip() == selected.description.strip():
            raise ValueError("Rewrite that actual Asset to describe its new Void alteration")
        outcome = "asset_altered"
        resources = tuple(
            x.model_copy(update={"void": True, "description": description.strip()})
            if x.id == asset
            else x
            for x in body.assets
        )
    state = GameState.model_validate_json(original.model_dump_json())
    assert state.world is not None
    state.world = state.world.model_copy(
        update={
            "gorgons": tuple(
                x.model_copy(update={"assets": resources}) if x.id == actor.entity else x
                for x in state.world.gorgons
            )
        }
    )
    payment = Payment(
        work=work,
        actor=actor,
        dormant=dormant,
        event=event,
        outcome=outcome,
        asset=asset,
        before_assets=tuple(x.model_dump_json() for x in body.assets),
        description=description.strip(),
    )
    state.facts.append(
        dict(
            kind="gorgon_dormant_void_paid", work=work, event=event, body=payment.model_dump_json()
        )
    )
    return GameState.model_validate_json(state.model_dump_json())
