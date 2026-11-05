"""Owned optional exchange choices, separate from compulsory Handler packages."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.creation import AssetChoice
from girlframe.engine.fanbase import Fanbase
from girlframe.engine.m3_actor_state import ActorRef, Model


class Selection(Model):
    frame: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    appearance: str = Field(min_length=1, max_length=700)
    assets: tuple[AssetChoice, ...] = Field(min_length=2, max_length=2)
    retained_asset: str = Field(min_length=1)
    retained_rule: str = Field(min_length=1)
    fanbase: Fanbase | None = None
    court_role: str | None = None
    court_target: ActorRef | None = None
    psych_strings: tuple[ActorRef, ...] = ()
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def actual_choices(self) -> "Selection":
        if not all(x.strip() for x in (self.name, self.appearance, self.account)):
            raise ValueError("Name and describe the actual new Frame and exchange")
        if len(set(self.psych_strings)) != len(self.psych_strings):
            raise ValueError("Use each actual initial Bond counterpart once")
        return self


class SwapReceipt(Model):
    id: str = Field(min_length=1)
    kind: Literal["frame_swap"] = "frame_swap"
    actor: ActorRef
    price: Literal[4] = 4
    old_frame: str = Field(min_length=1)
    new_frame: str = Field(min_length=1)
    selection: Selection
    source_event: str = Field(min_length=1)
    plan: str = Field(min_length=1)
