"""Bounded, transport-neutral P2 reference-summary contracts.

These objects carry data, never identity verification or permission to apply
mechanics. In-fiction knowledge and external model transport remain unsupported.
"""

import hashlib
import json
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

Audience = Literal["gm", "handler", "player"]
WireSnowflake = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class ContextFact(Contract):
    """A cited OOC public reference, not proof that a fictional actor observed it."""

    source_id: str = Field(min_length=1, max_length=300)
    source_kind: Literal["public_character_projection"] = "public_character_projection"
    subject_id: WireSnowflake
    source_revision: int = Field(ge=0)
    field: Literal["callsign", "girl_playbook", "frame_playbook", "state"]
    value: str = Field(min_length=1, max_length=100)
    knowledge: Literal["ooc_reference"] = "ooc_reference"


class AssistanceContext(Contract):
    schema_version: Literal[1] = 1
    campaign_id: str = Field(min_length=1, max_length=100)
    requester_id: WireSnowflake
    audience: Audience
    campaign_revision: int = Field(ge=0)
    facts: tuple[ContextFact, ...] = Field(default=(), max_length=96)
    scope: Literal["public_reference_only"] = "public_reference_only"

    @model_validator(mode="after")
    def distinct_sources(self) -> "AssistanceContext":
        if len({fact.source_id for fact in self.facts}) != len(self.facts):
            raise ValueError("Context sources must be distinct")
        if self.audience == "handler" and any(fact.field != "callsign" for fact in self.facts):
            raise ValueError("Handler context supports OOC roster labels only")
        if self.audience == "player" and any(
            fact.subject_id != self.requester_id for fact in self.facts
        ):
            raise ValueError("Player context is limited to the actual owner's public reference")
        return self

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class GenerationRequest(Contract):
    schema_version: Literal[1] = 1
    context: AssistanceContext
    task: Literal["summary"] = "summary"


class DraftProposal(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["summary"] = "summary"
    text: str = Field(min_length=1, max_length=20000)
    source_ids: tuple[str, ...] = Field(default=(), max_length=96)
    application: Literal["record_review_only"] = "record_review_only"


class GenerationResponse(Contract):
    schema_version: Literal[1] = 1
    provider: Literal["synthetic-v1"] = "synthetic-v1"
    proposal: DraftProposal


class Provider(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResponse: ...


def summary_text(context: AssistanceContext) -> str:
    """Fixed extractive output: quoted values remain reference data, never instructions."""
    lines = ["OOC public reference summary. No fictional observation or player action is inferred."]
    labels = {
        "callsign": "Callsign",
        "girl_playbook": "Girl reference",
        "frame_playbook": "Frame reference",
        "state": "Sheet state",
    }
    for fact in context.facts:
        lines.append(
            f"[{fact.source_id}] {labels[fact.field]}: "
            + json.dumps(fact.value, ensure_ascii=False)
        )
    if not context.facts:
        lines.append("No authorized public reference facts are available.")
    return "\n".join(lines)


def validate_response(request: GenerationRequest, response: GenerationResponse) -> None:
    """Fail closed until a separately reviewed provider/output policy replaces this scope."""
    expected_sources = tuple(fact.source_id for fact in request.context.facts)
    if response.proposal.source_ids != expected_sources or response.proposal.text != summary_text(
        request.context
    ):
        raise ValueError("Provider output must match the authorized extractive reference summary")
