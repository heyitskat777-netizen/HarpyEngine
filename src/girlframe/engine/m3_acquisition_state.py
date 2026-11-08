"""Source-bound actual Frame grants and issued physical items, separate from accounts."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class FirearmIssue(Model):
    asset: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    action: str | None = None
    kind: Literal["initial", "foundation_replacement"] = "initial"
    recipient: ActorRef | None = None
    controller: int | None = Field(default=None, gt=0)
    replaces_asset: str | None = None

    @model_validator(mode="after")
    def actual_replacement(self) -> "FirearmIssue":
        if self.kind == "foundation_replacement" and (
            self.recipient is None
            or self.controller is None
            or self.replaces_asset is None
            or self.replaces_asset == self.asset
            or self.action is None
        ):
            raise ValueError(
                "A Foundation replacement records its actual original recipient, "
                "human and lost object."
            )
        return self


class PersonalFirearmGrant(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    frame_instance: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    purchase: str | None = None
    source_work: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
    issues: tuple[FirearmIssue, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def actual_original(self) -> "PersonalFirearmGrant":
        if self.purchase is not None and self.source_work is not None:
            raise ValueError("A free replacement package is not a paid acquisition receipt")
        if self.actor.kind != "pilot" or len({x.asset for x in self.issues}) != len(self.issues):
            raise ValueError("An original Girl's entitlement keeps distinct actual issued items")
        if any(
            x.recipient is not None
            and x.recipient != self.actor
            or x.controller is not None
            and x.controller != int(self.actor.entity)
            for x in self.issues
        ):
            raise ValueError(
                "The issued physical object belongs to the actual original Girl and human."
            )
        return self
