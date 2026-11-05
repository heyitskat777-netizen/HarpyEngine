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

    @model_validator(mode="after")
    def actual_object(self) -> "HeldItem":
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Name and describe the actual held object")
        if self.confirmed_event is not None and self.confirmed_controller is None:
            raise ValueError(
                "A factual confirmation names the actual adjudicating human and source"
            )
        if self.asset_json is None and self.confirmed_event is None:
            raise ValueError("An unmodeled possession needs actual Handler factual confirmation")
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
    source_kind: Literal["enforcement_initiative", "npc_damage"] | None = None
    removed_asset: str | None = None
    received_asset: str | None = None
    last_girl_asset: bool = False
    inside_frame: bool | None = None

    @model_validator(mode="after")
    def actual_transfer(self) -> "ItemTransfer":
        if self.source == self.recipient or not self.account.strip():
            raise ValueError("Transfer an actual object between distinct people")
        return self
