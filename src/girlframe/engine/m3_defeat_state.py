"""Human-owned Defeat choices and a Handler-authored, explicitly accepted alternative."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class NewVoidAsset(Model):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1200)
    replace: str | None = None

    @model_validator(mode="after")
    def actual_description(self) -> "NewVoidAsset":
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Name and describe the actual new Void Asset")
        return self


class Decision(Model):
    options: tuple[str, ...]
    account: str = Field(min_length=1, max_length=1200)
    girl_asset: NewVoidAsset | None = None
    frame_asset: NewVoidAsset | None = None
    rescuer: ActorRef | None = None
    tag_giver: ActorRef | None = None
    girl_playbook: str | None = None
    amnesiac_slot: int | None = Field(default=None, ge=0, le=3)


class Alternative(Model):
    account: str = Field(min_length=1, max_length=1200)
    equally_ruinous_confirmed: Literal[True]
    permissions_lost: int = Field(default=0, ge=0)
    assets_removed: tuple[str, ...] = ()
    identities_removed: tuple[str, ...] = ()
    tag: str = Field(default="", max_length=120)
    helpless_foe: ActorRef | None = None
    outside_frame: bool | None = None


class Consequence(Model):
    kind: Literal[
        "death", "frame_replacement", "medical_wake", "void_threshold", "tag_gift", "alternative"
    ]
    owner: ActorRef
    source_pdf: int = 29
    details: dict[str, str] = Field(default_factory=dict)
