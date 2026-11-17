"""Typed GM epistemic proposals; no mechanics, world mutation or implicit hearing."""

from typing import Literal, Protocol

from pydantic import ConfigDict, Field, model_validator

from girlframe.ai.contracts import Contract
from girlframe.ai.director import DirectorContext, KnowledgeReference
from girlframe.engine.m3_actor_state import ActorRef


class KnowledgeSource(Contract):
    id: str
    revision: int
    kind: Literal["message", "approved_outcome"]
    text: str
    actor: ActorRef | None = None
    fictional_channel: Literal["scene", "private", "comms", "mixed", "unclassified"] = "scene"


class ActorDirectoryEntry(Contract):
    actor: ActorRef
    name: str
    controller: int
    # Native labels only: aliases are navigation, never authorization selectors.
    aliases: tuple[str, ...] = ()


class Disclosure(Contract):
    """GM-classified actual speech, with exact source text and selected listeners."""

    quote: str = Field(min_length=1, max_length=1000)
    recipients: tuple[ActorRef, ...] = Field(
        min_length=1, max_length=10, json_schema_extra={"uniqueItems": True}
    )

    @model_validator(mode="after")
    def distinct_roles(self) -> "Disclosure":
        if len({x.token for x in self.recipients}) != len(self.recipients):
            raise ValueError("Select each actual listener once")
        return self


class Acquisition(Contract):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"basis": {"enum": ["report", "paraphrase"]}},
                        "required": ["basis"],
                    },
                    "then": {
                        "required": ["prior_reference"],
                        "properties": {"prior_reference": {"type": "string", "minLength": 1}},
                    },
                    "else": {"properties": {"prior_reference": {"type": "null"}}},
                }
            ]
        }
    )
    basis: Literal["perception", "report", "testimony", "paraphrase", "outcome"]
    quote: str = Field(
        min_length=1,
        max_length=1000,
        description="Exact current-source words, including uncertainty/negation.",
    )
    recipients: tuple[ActorRef, ...] = Field(
        min_length=1, max_length=10, json_schema_extra={"uniqueItems": True}
    )
    prior_reference: str | None = Field(
        default=None,
        min_length=1,
        description="Required for relay report/paraphrase; forbidden for new testimony.",
    )
    topic: Literal["general", "objective", "scope", "status", "briefing", "tactical", "debrief"] = (
        "general"
    )

    @model_validator(mode="after")
    def distinct_roles(self) -> "Acquisition":
        if len({x.token for x in self.recipients}) != len(self.recipients):
            raise ValueError("Select each actual recipient once")
        linked = self.basis in ("report", "paraphrase")
        if linked != (self.prior_reference is not None):
            raise ValueError(
                "A relayed report or paraphrase requires one speaker-known prior reference"
            )
        return self


class KnowledgePacket(Contract):
    request_id: str
    scene_id: str
    source: KnowledgeSource
    context: DirectorContext
    recipients: tuple[ActorRef, ...]
    actor_directory: tuple[ActorDirectoryEntry, ...] = ()
    accepted_disclosures: tuple[Disclosure, ...] = ()
    revision: str


class KnowledgeProposal(Contract):
    request_id: str
    updates: tuple[Acquisition, ...] = Field(default=(), max_length=10)
    disclosures: tuple[Disclosure, ...] = Field(
        default=(), max_length=10, exclude_if=lambda x: not x
    )
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
