"""A real source Type declaration and compulsory no-Heat roll, never a controller PC."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_leviathan_obsession_state import GrantedIdentity


class Declaration(Model):
    mode: Literal["give_tag", "succumb"]
    source: ActorRef
    subject: ActorRef
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    subject_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tag: str | None = Field(default=None, min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    reach_confirmed: Literal[True]

    @model_validator(mode="after")
    def actual_type(self) -> "Declaration":
        if self.source.kind != "gorgon" or self.source == self.subject or not self.account.strip():
            raise ValueError(
                "Declare an actual Leviathan's influence on a distinct original person"
            )
        if (self.mode == "succumb") != (self.tag is not None):
            raise ValueError(
                "Succumb marks one actual obsessed Tag; a gift creates its own new Tag"
            )
        return self


class FactualIdentities(Model):
    """Actual resource facts, not a new starting build or arbitrary unlocked slots."""

    ordinary: tuple[str, ...] = ()
    identities: tuple[GrantedIdentity, ...] = ()
    mentor: ActorRef | None = None
    account: str = Field(min_length=1, max_length=1200)
