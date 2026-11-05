"""Honest no-roll decisions for source-imposed inability at mandatory triggers."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_lobotomy_state import BlockedPlay

MandatoryPlay = Literal["defeat", "go_off_duty", "void_observation", "harpy_defeat"]


class Required(Model):
    play: MandatoryPlay
    actor: ActorRef
    actor_controller: Snowflake | None = None
    adjudicator: ActorRef | None = None
    handler: ActorRef | None = None
    gm_controller: Snowflake | None = None
    appointment: str | None = None
    prohibition: BlockedPlay
    source_kind: Literal["defeat_work", "defeat_response", "off_duty", "harpy_defeat_work"]
    source_id: str = Field(min_length=1)
    source_revision: int = Field(ge=1)
    registry: str = Field(min_length=1)

    @model_validator(mode="after")
    def source_owned(self) -> "Required":
        if (
            (
                self.actor.kind != "pilot"
                and not (
                    self.play == "harpy_defeat"
                    and self.actor.kind == "external_pilot"
                    and self.actor_controller is not None
                )
            )
            or self.handler is not None
            and self.handler.kind != "handler"
        ):
            raise ValueError("The actual original Girl and current Handler own this exception")
        if self.adjudicator is not None and (
            self.play != "harpy_defeat" or self.adjudicator.kind != "npc"
        ):
            raise ValueError(
                "Only this actual Harpy source may retain its scene Director adjudicator"
            )
        if self.gm_controller is None and self.handler is None:
            raise ValueError("Keep the actual appointed human GM independently of fictional bodies")
        if (
            self.gm_controller is not None
            and self.handler is not None
            and (str(self.gm_controller) != self.handler.entity)
        ):
            raise ValueError("The historical Handler body cannot impersonate a different human GM")
        actual_play = self.prohibition.play
        if (
            (
                actual_play != self.play
                and not (self.play == "harpy_defeat" and actual_play == "defeat")
            )
            or (self.play in ("defeat", "harpy_defeat")) != (self.source_kind != "off_duty")
            or (self.play == "harpy_defeat") != (self.source_kind == "harpy_defeat_work")
        ):
            raise ValueError("Use the actual mandatory source and forbidden Play")
        return self

    @property
    def patient_controller(self) -> int:
        return (
            self.actor_controller if self.actor_controller is not None else int(self.actor.entity)
        )

    @property
    def controller(self) -> int:
        if self.gm_controller is not None:
            return self.gm_controller
        assert self.handler is not None
        return int(self.handler.entity)


class Decision(Model):
    id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    request: str = Field(min_length=1)
    required: Required
    total: int = Field(ge=-1000, le=1000)
    reason: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)

    @model_validator(mode="after")
    def actual_reason(self) -> "Decision":
        if not self.reason.strip():
            raise ValueError("The Handler must describe the actual no-roll ruling")
        return self
