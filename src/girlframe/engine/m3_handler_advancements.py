"""Finite original Handler awards and the printed group Permission spend."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_location_build import Effect as LocationBuildEffect
from girlframe.engine.m3_location_rebuild import Effect as LocationRebuildEffect

RULES = ("strain.void.endgame.6", "strain.void.endgame.7")


class PermissionGrant(Model):
    actor: ActorRef
    amount: Literal[1, 2]

    @model_validator(mode="after")
    def original_girl(self) -> "PermissionGrant":
        if self.actor.kind != "pilot":
            raise ValueError("Select an actual original current Girl for these Permissions")
        return self


class PermissionEffect(PermissionGrant):
    label: str = Field(min_length=1, max_length=120)
    before: int = Field(ge=0)
    after: int = Field(ge=1)

    @model_validator(mode="after")
    def exact_gain(self) -> "PermissionEffect":
        if self.after != self.before + self.amount:
            raise ValueError("Keep the exact actual Permission gain")
        return self


class Award(Model):
    id: str = Field(min_length=1)
    rule: Literal["strain.void.endgame.6", "strain.void.endgame.7"]
    handler: ActorRef
    appointment: str = Field(min_length=1)
    source_work: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    award_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    phase: Literal["held", "spent"] = "held"
    effects: tuple[PermissionEffect, ...] = ()
    acquired_rule: (
        Literal[
            "handler-advancement.handler-advancement.supply-drop",
            "handler-advancement.handler-advancement.cute-uniforms",
            "handler-advancement.handler-advancement.girl-insurance",
        ]
        | None
    ) = Field(default=None, exclude_if=lambda value: value is None)
    acquisition: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
    location_rebuild: LocationRebuildEffect | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    location_build: LocationBuildEffect | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    spend_event: str | None = None
    spend_account: str | None = Field(default=None, min_length=1, max_length=1200)

    @model_validator(mode="after")
    def exact_original_award(self) -> "Award":
        if self.handler.kind != "handler" or self.id != self.source_work:
            raise ValueError("Keep this exact actual original Handler source award")
        variants = (
            int(bool(self.effects))
            + int(self.acquired_rule is not None)
            + int(self.location_rebuild is not None)
            + int(self.location_build is not None)
        )
        if self.phase == "held":
            if variants or self.spend_event or self.spend_account or self.acquisition:
                raise ValueError("An unspent advancement has no fabricated effects")
        elif (
            not self.spend_event
            or not self.spend_account
            or variants != 1
            or (self.acquired_rule is None) != (self.acquisition is None)
        ):
            raise ValueError(
                "A spent advancement preserves its exact implemented effect and source"
            )
        if self.location_rebuild is not None and (
            self.location_rebuild.award != self.id
            or self.location_rebuild.handler != self.handler
            or self.location_rebuild.appointment != self.appointment
            or self.location_rebuild.event != self.spend_event
        ):
            raise ValueError("Keep this exact original Handler's actual location rebuild spend")
        if self.location_build is not None and (
            self.location_build.award != self.id
            or self.location_build.handler != self.handler
            or self.location_build.appointment != self.appointment
            or self.location_build.event != self.spend_event
        ):
            raise ValueError("Keep this exact original Handler's actual new-location spend")
        if len({x.actor for x in self.effects}) != len(self.effects):
            raise ValueError("One advancement grants each selected original Girl Permissions once")
        return self


def awards(state: GameState) -> tuple[Award, ...]:
    return tuple(
        Award.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "handler_advancement_award"
    )


def put(state: GameState, value: Award) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "handler_advancement_award" and x.get("id") == value.id)
    ]
    state.facts.append(
        dict(kind="handler_advancement_award", id=value.id, body=value.model_dump_json())
    )


def grant(state: GameState, value: Award) -> None:
    if value.phase != "held" or any(x.id == value.id for x in awards(state)):
        raise ValueError("This actual finite advancement source has already been awarded")
    if not same_handler_body(state, value.handler):
        raise ValueError("This advancement belongs to its actual original living Handler")
    put(state, value)


def spend(
    original: GameState,
    identity: str,
    grants: tuple[PermissionGrant, ...],
    event: str,
    account: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    value = next((x for x in awards(state) if x.id == identity), None)
    if value is None or value.phase != "held" or not same_handler_body(state, value.handler):
        raise ValueError("Use one actual unspent advancement owned by this original Handler")
    if not grants or len({x.actor for x in grants}) != len(grants) or not account.strip():
        raise ValueError(
            "Select a nonempty group of distinct original Girls and actual grant account"
        )
    effects = []
    for choice in grants:
        if (
            choice.actor.kind != "pilot"
            or int(choice.actor.entity) not in state.order
            or current_ref(state, int(choice.actor.entity)) != choice.actor
        ):
            raise ValueError("Permissions belong to selected original Girls, never replacements")
        sheet = state.sheets[choice.actor.entity]
        before = sheet.permissions
        sheet.permissions += choice.amount
        sheet.revision += 1
        effects.append(
            PermissionEffect(
                actor=choice.actor,
                amount=choice.amount,
                label=sheet.callsign,
                before=before,
                after=sheet.permissions,
            )
        )
    changed = Award.model_validate_json(
        value.model_copy(
            update=dict(
                phase="spent",
                effects=tuple(effects),
                spend_event=event,
                spend_account=account.strip(),
            )
        ).model_dump_json()
    )
    put(state, changed)
    return state
