"""Actual named held objects retain their source and current physical custodian."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class HeldItem(Model):
    id: str = Field(min_length=1)
    holder: ActorRef
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)
    source_owner: ActorRef
    origin_event: str | None = None
    origin_asset_json: str | None = None
    state_event: str | None = None
    proposed_event: str | None = None
    confirmed_by: ActorRef | None = None
    confirmed_controller: int | None = Field(default=None, gt=0)
    confirmed_event: str | None = None
    asset_json: str | None = None
    asset_id: str | None = None
    asset_owner: ActorRef | None = None
    factual_source_action: str | None = None
    transferred_event: str | None = None
    weapon: bool = False
    location_mode: Literal["carried", "scene"] = Field(
        default="carried", exclude_if=lambda value: value == "carried"
    )
    scene_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    location_event: str | None = Field(default=None, exclude_if=lambda value: value is None)
    condition: Literal["intact", "ruined"] = Field(
        default="intact", exclude_if=lambda value: value == "intact"
    )

    @model_validator(mode="after")
    def actual_object(self) -> "HeldItem":
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Name and describe the actual held object")
        if self.confirmed_event is not None and self.confirmed_controller is None:
            raise ValueError(
                "A factual confirmation names the actual adjudicating human and source"
            )
        destroyed_mechanical_origin = (
            self.condition == "ruined"
            and self.origin_asset_json is not None
            and self.state_event is not None
            and self.asset_id is None
            and self.asset_owner is None
        )
        if (
            self.asset_json is None
            and self.confirmed_event is None
            and not destroyed_mechanical_origin
        ):
            raise ValueError("An unmodeled possession needs actual Handler factual confirmation")
        if self.location_mode == "scene" and (not self.scene_id or not self.location_event):
            raise ValueError("A stored object needs its actual source scene and location event")
        if self.location_mode == "carried" and self.scene_id is not None:
            raise ValueError("A carried object does not also occupy an old source room")
        if self.asset_json is not None and self.condition != "intact":
            raise ValueError("Mechanical Asset condition uses its sole real damage authority")
        return self


class ItemTransfer(Model):
    id: str = Field(min_length=1)
    item: str = Field(min_length=1)
    source: ActorRef
    recipient: ActorRef
    action: str = Field(min_length=1)
    event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    prior_event: str | None = None
    source_work: str | None = None
    source_kind: Literal["enforcement_initiative", "npc_damage", "enforcer_snoop"] | None = None
    removed_asset: str | None = None
    received_asset: str | None = None
    last_girl_asset: bool = False
    inside_frame: bool | None = None

    @model_validator(mode="after")
    def actual_transfer(self) -> "ItemTransfer":
        if self.source == self.recipient or not self.account.strip():
            raise ValueError("Transfer an actual object between distinct people")
        return self
