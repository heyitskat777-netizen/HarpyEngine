"""A mandatory decision has one actual context; no fabricated phase is needed."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import Model


class WorkScope(Model):
    mission_id: str | None = Field(default=None, min_length=1)
    off_duty_id: str | None = Field(default=None, min_length=1)
    scene_id: str | None = Field(default=None, min_length=1)
    campaign_context: bool = False

    @model_validator(mode="after")
    def exactly_one(self) -> "WorkScope":
        if (
            sum(x is not None for x in (self.mission_id, self.off_duty_id, self.scene_id))
            + int(self.campaign_context)
            != 1
        ):
            raise ValueError("Required work needs exactly one actual context")
        return self

    @property
    def kind(self) -> Literal["mission", "off_duty", "scene", "campaign"]:
        return (
            "mission"
            if self.mission_id is not None
            else "off_duty"
            if self.off_duty_id is not None
            else "scene"
            if self.scene_id is not None
            else "campaign"
        )
