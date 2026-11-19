"""A declared physical Gorgon Play is a source intent, never an invented Girl roll."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class Declaration(Model):
    kind: Literal["attack", "collateral", "warp", "corrupt"]
    actor: ActorRef
    assets: tuple[str, ...] = ()
    actor_sha256: str = Field(min_length=64, max_length=64)
    target: ActorRef | None = None
    target_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    account: str = Field(min_length=1, max_length=1200)
    reach_confirmed: Literal[True]

    @model_validator(mode="after")
    def source_shape(self) -> "Declaration":
        if self.actor.kind != "gorgon" or len(set(self.assets)) != len(self.assets):
            raise ValueError("Declare distinct actual Assets of the actual attacking Gorgon")
        if not all(x.strip() for x in self.assets) or not self.account.strip():
            raise ValueError("State the actual physical attack/destruction and source capabilities")
        if bool(self.assets) != (self.kind in ("attack", "collateral")):
            raise ValueError(
                "Attack and Collateral declare actual Assets. Warp and Corrupt do not."
            )
        if self.kind == "attack":
            if self.target is None or self.target_sha256 is None or self.target == self.actor:
                raise ValueError("An Attack needs its actual distinct opposing body and source")
        elif self.target is not None or self.target_sha256 is not None:
            raise ValueError("This Play targets the actual environment, not a substituted person")
        return self
