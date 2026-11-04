"""Source-bound purchase receipts; no Discord identity or second resource authority."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class Installation(Model):
    from_frame: str | None = None
    index: int | None = Field(default=None, ge=0)
    name: str = Field(default="", max_length=80)
    description: str = Field(min_length=1, max_length=700)
    replace: str | None = None
    account: str = Field(min_length=1, max_length=1200)
    trigger_confirmed: Literal[True]

    @model_validator(mode="after")
    def source_choice(self) -> "Installation":
        if (
            (self.from_frame is None) != (self.index is None)
            or not self.description.strip()
            or not self.account.strip()
            or (self.from_frame is None and not self.name.strip())
            or (self.from_frame is not None and bool(self.name))
        ):
            raise ValueError(
                "Select one printed Asset or name your custom Asset and its actual installation"
            )
        return self


class Receipt(Model):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["asset_installment"]
    actor: ActorRef
    frame_instance: str = Field(min_length=1)
    price: Literal[1]
    asset_id: str = Field(min_length=1)
    installation: Installation
    source_event: str = Field(min_length=1)
