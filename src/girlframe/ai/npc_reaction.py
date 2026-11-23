"""Scoped inputs and a speech-only model proposal for an actual NPC."""

from typing import Protocol

from pydantic import Field, field_validator

from girlframe.ai.provider import ProviderUsage
from girlframe.engine.m2 import Model
from girlframe.scenes.canon import Statement

PROMPT_VERSION = "npc-reaction-v1"
GUIDE_PROMPT_VERSION = "npc-guide-offer-v1"
LEAD_PROMPT_VERSION = "npc-private-lead-v1"


class NpcReactionContext(Model):
    npc_name: str = Field(min_length=1, max_length=120)
    address: Statement
    public_manner: str | None = Field(
        default=None, max_length=500, exclude_if=lambda value: value is None
    )
    guide_destination: str | None = Field(
        default=None, max_length=120, exclude_if=lambda value: value is None
    )

    lead_fact: Statement | None = Field(default=None, exclude_if=lambda value: value is None)


class NpcReactionText(Model):
    speech: Statement | None

    @field_validator("speech")
    @classmethod
    def one_line(cls, value: str | None) -> str | None:
        if value is not None and not value.isprintable():
            raise ValueError("An NPC reply must be one printable line of speech.")
        return value


class NpcReactionResult(ProviderUsage):
    proposal: NpcReactionText


class NpcReactionGateway(Protocol):
    def generate(
        self, model: str, context: NpcReactionContext, request_id: str
    ) -> NpcReactionResult: ...
