"""Mission-bound repair restrictions and private exact-price offers."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model


class Shortage(Model):
    id: str = Field(min_length=1)
    source_period: str = Field(min_length=1)
    mission: str | None = None
    dispatch_event: str | None = None
    mission_end_event: str | None = None
    period: str | None = None
    closed: bool = False

    @model_validator(mode="after")
    def actual_timing(self) -> "Shortage":
        if (
            (self.mission is None) != (self.dispatch_event is None)
            or (self.mission_end_event is not None and self.mission is None)
            or (self.period is not None and self.mission_end_event is None)
            or (self.closed and self.period is None)
        ):
            raise ValueError(
                "Repair restrictions retain actual dispatch, end and period provenance"
            )
        return self


class Quote(Model):
    id: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)
    period: str = Field(min_length=1)
    shortages: tuple[str, ...] = Field(min_length=1)
    owner: ActorRef
    handler: Snowflake
    asset: str = Field(min_length=1)
    asset_name: str = Field(min_length=1)
    frame_instance: str = Field(min_length=1)
    sheet_revision: int = Field(ge=1)
    cost: int = Field(ge=0)
    source_event: str = Field(min_length=1)
    state: Literal["pending", "accepted", "declined"] = "pending"
    response_event: str | None = None

    @model_validator(mode="after")
    def actual_owner(self) -> "Quote":
        if (
            self.owner.kind != "pilot"
            or len(set(self.shortages)) != len(self.shortages)
            or ((self.state == "pending") != (self.response_event is None))
        ):
            raise ValueError("A quote retains its real Pilot and actual optional response")
        return self
