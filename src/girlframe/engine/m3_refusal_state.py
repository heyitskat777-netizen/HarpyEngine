"""One actual Low Rebellion control-slip source, consumed by one real refusal."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model


class RefusalBonus(Model):
    id: str = Field(min_length=1)
    period: str = Field(min_length=1)
    handler: Snowflake
    source_event: str = Field(min_length=1)
    amount: Literal[2] = 2
    action: str | None = Field(default=None, min_length=1)
    actor: ActorRef | None = None

    @model_validator(mode="after")
    def actual_consumption(self) -> "RefusalBonus":
        if (self.action is None) != (self.actor is None) or (
            self.actor is not None and self.actor.kind != "pilot"
        ):
            raise ValueError("A consumed refusal bonus records its actual Girl and action together")
        return self
