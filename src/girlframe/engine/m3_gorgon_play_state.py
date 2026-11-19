"""A declared physical Gorgon Play is a source intent, never an invented Girl roll."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_gorgon_type_tags import LABELS, TypeTag


class Declaration(Model):
    kind: Literal["attack", "collateral", "warp", "corrupt"] | TypeTag
    actor: ActorRef
    assets: tuple[str, ...] = ()
    actor_sha256: str = Field(min_length=64, max_length=64)
    target: ActorRef | None = None
    target_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    account: str = Field(min_length=1, max_length=1200)
    reach_confirmed: Literal[True]
    tag: str | None = Field(default=None, max_length=40, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def source_shape(self) -> "Declaration":
        if self.actor.kind != "gorgon" or len(set(self.assets)) != len(self.assets):
            raise ValueError("Declare distinct actual Assets of the actual attacking Gorgon")
        if not all(x.strip() for x in self.assets) or not self.account.strip():
            raise ValueError("State the actual physical attack/destruction and source capabilities")
        if bool(self.assets) != (self.kind in ("attack", "collateral")):
            raise ValueError("Attack and Collateral require actual owned Assets")
        if self.kind in ("attack", "incubus_inflict", "mother_mutation"):
            if self.target is None or self.target_sha256 is None or self.target == self.actor:
                raise ValueError("This Play needs its actual distinct target body and source")
        elif self.target is not None or self.target_sha256 is not None:
            raise ValueError("This Play targets the actual environment, not a substituted person")
        if self.kind in ("incubus_inflict", "mother_mutation"):
            if self.tag not in dict(LABELS[self.kind]):
                raise ValueError("Choose a printed Tag for this Gorgon effect")
        elif self.tag is not None:
            raise ValueError("This Gorgon Play has no direct Tag choice")
        return self
