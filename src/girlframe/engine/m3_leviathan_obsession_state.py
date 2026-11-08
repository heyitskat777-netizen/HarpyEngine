"""Original-person Leviathan influence; only explicitly granted identities live here."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class GrantedIdentity(Model):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=120)
    marked: bool = False
    protected: bool = False
    paired: bool = False
    slot: int | None = Field(default=None, ge=0, le=3)
    obsession_sources: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)


class Obsession(Model):
    id: str = Field(min_length=1)
    source: ActorRef
    subject: ActorRef
    identity_ids: tuple[str, ...] = ()
    level: Literal["mid", "high"]
    event: str = Field(min_length=1)
    released_event: str | None = None

    @model_validator(mode="after")
    def original_source(self) -> "Obsession":
        if self.source.kind != "gorgon" or self.source == self.subject:
            raise ValueError("The actual source Leviathan influences a distinct original person")
        if len(set(self.identity_ids)) != len(self.identity_ids) or (
            not self.identity_ids and self.level != "high"
        ):
            raise ValueError(
                "Record the actual distinct obsessed Identities granted by this source"
            )
        return self


class IdentityAuthority(Model):
    """Only source-granted/imported identities; Harpy ordinary IDs are pointers only."""

    actor: ActorRef
    role: Literal["granted", "external_factual", "harpy_review"]
    identities: tuple[GrantedIdentity, ...] = ()
    ordinary: tuple[str, ...] = ()
    delegated_context: str | None = None
    reviewed_ids: tuple[str, ...] = ()
    mentor: ActorRef | None = None
    event: str = Field(min_length=1)
    owner: int
    judge: int
    revision: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def sole_authority(self) -> "IdentityAuthority":
        if self.role == "harpy_review" and self.identities:
            raise ValueError("Harpy ordinary-slot review points to existing actual identities")
        if self.mentor is not None and self.mentor == self.actor:
            raise ValueError("An actual Newgirl's existing Mentor is another original person")
        if self.role in ("harpy_review", "external_factual") and len(self.ordinary) > 4:
            raise ValueError("Review at most four actual ordinary slots, preserving source extras")
        if self.delegated_context is not None and (self.actor.kind != "handler" or self.identities):
            raise ValueError("A delegated Handler context is the sole active identity authority")
        if len({x.id for x in self.identities}) != len(self.identities) or len(
            set(self.ordinary)
        ) != len(self.ordinary):
            raise ValueError("Keep actual source identities and ordinary pointers distinct")
        if (
            self.role != "harpy_review"
            and self.delegated_context is None
            and not set(self.ordinary) <= {x.id for x in self.identities}
        ):
            raise ValueError("Ordinary slots must name actual current source identities")
        return self
