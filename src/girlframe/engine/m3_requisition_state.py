"""Source-bound purchase receipts; no Discord identity or second resource authority."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, CastRole, Model
from girlframe.engine.m3_frame_swap_state import SwapReceipt


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


class ComfortReceipt(Model):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["creature_comforts"] = "creature_comforts"
    actor: ActorRef
    price: Literal[0, 1] = 1
    source_offer: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
    account: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)

    @model_validator(mode="after")
    def actual_purchaser(self) -> "ComfortReceipt":
        if (
            self.actor.kind != "pilot"
            or not self.account.strip()
            or self.price != (0 if self.source_offer else 1)
        ):
            raise ValueError(
                "Creature Comforts needs its actual paid request or source-funded gift"
            )
        return self


class SceneReceipt(Model):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["privacy", "visiting_home"]
    actor: ActorRef
    price: Literal[0, 1, 2]
    source_offer: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
    companion: ActorRef | None = None
    account: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)

    @model_validator(mode="after")
    def actual_source(self) -> "SceneReceipt":
        if self.actor.kind != "pilot" or not self.account.strip():
            raise ValueError("The actual purchasing Girl owns this scene Requisition")
        if self.kind == "privacy":
            if (
                self.price != (0 if self.source_offer else 1)
                or self.companion is None
                or self.companion.kind != "pilot"
                or self.companion.entity == self.actor.entity
            ):
                raise ValueError("Privacy costs one Permission and names another actual Girl")
        elif self.price != (0 if self.source_offer else 2) or self.companion is not None:
            raise ValueError(
                "Visiting Home costs two Permissions; supervision is chosen in its scene"
            )
        return self


class RetirementReceipt(Model):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["retirement"] = "retirement"
    actor: ActorRef
    price: Literal[0, 20] = 20
    source_offer: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
    archive_id: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)

    @model_validator(mode="after")
    def actual_girl(self) -> "RetirementReceipt":
        if (
            self.actor.kind != "pilot"
            or not self.account.strip()
            or self.price != (0 if self.source_offer else 20)
        ):
            raise ValueError(
                "Retirement belongs to the actual original Girl and paid or offered source"
            )
        return self


class FrameRuleReceipt(Model):
    id: str = Field(min_length=1)
    kind: Literal["ability_unlock", "frame_grafting"]
    actor: ActorRef
    frame_instance: str = Field(min_length=1)
    frame: str = Field(min_length=1)
    donor_frame: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    grant: str = Field(min_length=1)
    price: Literal[2, 3]
    account: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)

    @model_validator(mode="after")
    def actual_acquisition(self) -> "FrameRuleReceipt":
        if (
            self.actor.kind != "pilot"
            or not self.account.strip()
            or self.price != (2 if self.kind == "ability_unlock" else 3)
        ):
            raise ValueError("Use the original Girl and actual source-priced Frame acquisition")
        return self


Requisition = Annotated[
    Receipt | ComfortReceipt | SceneReceipt | RetirementReceipt | FrameRuleReceipt | SwapReceipt,
    Field(discriminator="kind"),
]


class ComfortScene(Model):
    id: str = Field(min_length=1)
    cast_id: str = Field(min_length=1)
    cast_revision: int = Field(ge=1)
    location: str = Field(min_length=1)
    roles: tuple[CastRole, ...] = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=1200)
    acknowledgements: tuple[int, ...] = ()

    @model_validator(mode="after")
    def attendance(self) -> "ComfortScene":
        if (
            not self.summary.strip()
            or len({x.actor for x in self.roles}) != len(self.roles)
            or len(set(self.acknowledgements)) != len(self.acknowledgements)
            or not set(self.acknowledgements) <= {x.controller for x in self.roles}
        ):
            raise ValueError("A scene needs actual distinct roles and each human's own attendance")
        return self


class ComfortBenefit(Model):
    purchase: str = Field(min_length=1)
    actor: ActorRef
    period: str = Field(min_length=1)
    action: str = Field(min_length=1)
    raw_event: str = Field(min_length=1)
    qualification_event: str = Field(min_length=1)
    total: int = Field(ge=8)
    scene: ComfortScene | None = None
    taken: bool | None = None
    asset_id: str | None = None
    asset_name: str | None = Field(default=None, max_length=80)
    asset_description: str | None = Field(default=None, max_length=700)
    account: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def actual_outcome(self) -> "ComfortBenefit":
        if self.actor.kind != "pilot":
            raise ValueError("A Creature Comforts opportunity belongs to its original Girl")
        if self.taken is True:
            if (
                self.scene is None
                or set(self.scene.acknowledgements) != {x.controller for x in self.scene.roles}
                or not self.asset_id
                or not self.asset_name
                or not self.asset_description
            ):
                raise ValueError(
                    "An actual reward requires owned scene attendance and the actual Asset"
                )
        elif (
            self.asset_id is not None
            or self.asset_name is not None
            or self.asset_description is not None
        ):
            raise ValueError("An ungranted opportunity cannot claim an Asset")
        if self.taken is False and (self.scene is not None or not self.account.strip()):
            raise ValueError("Decline the optional opportunity explicitly before setting its scene")
        return self


class GirlAsset(Model):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=700)
    replace: str | None = None
