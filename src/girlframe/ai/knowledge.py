"""Typed GM epistemic proposals; no mechanics, world mutation or implicit hearing."""

from typing import Literal, Protocol

from pydantic import Field, model_validator

from girlframe.ai.contracts import Contract
from girlframe.ai.director import DirectorContext, KnowledgeReference
from girlframe.engine.m3_actor_state import ActorRef


class KnowledgeSource(Contract):
    id: str
    revision: int
    kind: Literal["message", "approved_outcome"]
    text: str
    actor: ActorRef | None = None
    fictional_channel: Literal["scene", "private", "comms"] = "scene"


class Acquisition(Contract):
    basis: Literal["perception", "report", "outcome"]
    quote: str = Field(min_length=1, max_length=1000)
    recipients: tuple[ActorRef, ...] = Field(min_length=1, max_length=10)
    prior_reference: str | None = None
    topic: Literal["general", "objective", "scope", "status", "briefing", "tactical", "debrief"] = (
        "general"
    )

    @model_validator(mode="after")
    def distinct_roles(self) -> "Acquisition":
        if len({x.token for x in self.recipients}) != len(self.recipients):
            raise ValueError("Select each actual recipient once")
        if (self.basis == "report") != (self.prior_reference is not None):
            raise ValueError("A report requires exactly one speaker-known prior reference")
        return self


class KnowledgePacket(Contract):
    request_id: str
    scene_id: str
    source: KnowledgeSource
    context: DirectorContext
    recipients: tuple[ActorRef, ...]
    revision: str


class KnowledgeProposal(Contract):
    request_id: str
    updates: tuple[Acquisition, ...] = Field(default=(), max_length=10)
    private_reasoning: str = Field(default="", max_length=2000)


class KnowledgeProvider(Protocol):
    def propose(self, packet: KnowledgePacket) -> KnowledgeProposal: ...


def reference_text(update: Acquisition) -> str:
    prefix = "Confirmed outcome: " if update.basis == "outcome" else "Reported claim: "
    return prefix + update.quote


def fact_text(reference: KnowledgeReference) -> str:
    for prefix in ("Reported claim: ", "Confirmed outcome: "):
        if reference.text.startswith(prefix):
            return reference.text[len(prefix) :]
    return reference.text
