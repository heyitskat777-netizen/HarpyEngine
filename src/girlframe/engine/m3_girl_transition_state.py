"""Actual Girl baseline configuration, distinct from frozen creation drafts."""

from pydantic import Field, model_validator

from girlframe.engine.creation_details import DesireChoice
from girlframe.engine.m3_actor_state import ActorRef, Model


class Investor(Model):
    npc: str = Field(min_length=1, max_length=100)
    desires: DesireChoice


class BodyPart(Model):
    name: str
    damaged: bool = False


class Plan(Model):
    account: str = Field(min_length=1, max_length=1200)
    pair: ActorRef | None = None
    paired_identity: str | None = None
    maxims: tuple[int, ...] = Field(default=(), max_length=2)
    dna_basis: str = Field(default="", max_length=300)
    investors: tuple[Investor, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def distinct(self) -> "Plan":
        if not self.account.strip() or len(set(self.maxims)) != len(self.maxims):
            raise ValueError("Describe the actual change and choose distinct maxims")
        if any(x < 0 or x > 9 for x in self.maxims):
            raise ValueError("Choose printed maxim slots")
        if len({x.npc for x in self.investors}) != len(self.investors):
            raise ValueError("Each actual investor has one desire choice")
        return self


class GirlSetup(Model):
    epoch: str = Field(min_length=1)
    book: str
    source_event: str = Field(min_length=1)
    account: str
    mentor: ActorRef | None = None
    pair: ActorRef | None = None
    paired_identity: str | None = None
    maxims: tuple[int, ...] = ()
    dna_basis: str = ""
    investors: tuple[Investor, ...] = ()
    handler_desires: DesireChoice | None = None
    handler: ActorRef | None = None
    appointment: str | None = None
    body_parts: tuple[BodyPart, ...] = ()
