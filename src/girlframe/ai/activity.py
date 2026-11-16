"""Version 1 logical Activity API; no HTTP routes or authentication are installed."""

from typing import Annotated, Literal

from pydantic import Field

from girlframe.ai.contracts import (
    AssistanceContext,
    Audience,
    Contract,
    GenerationResponse,
    WireSnowflake,
)

CommandKey = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9:_-]+$")]
ProposalStatus = Literal["requested", "draft", "failed", "approved", "rejected"]


class ContextView(Contract):
    schema_version: Literal[1] = 1
    context: AssistanceContext
    context_digest: str


class RequestAssistance(Contract):
    schema_version: Literal[1] = 1
    command_key: CommandKey
    expected_campaign_revision: int = Field(ge=0)
    audience: Audience
    context_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    task: Literal["summary"] = "summary"


class GenerateDraft(Contract):
    schema_version: Literal[1] = 1
    command_key: CommandKey
    expected_campaign_revision: int = Field(ge=0)
    expected_proposal_revision: int = Field(ge=1)


class ReviewDraft(GenerateDraft):
    decision: Literal["approve", "reject"]


class AssistanceRecord(Contract):
    schema_version: Literal[1] = 1
    proposal_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    owner_id: WireSnowflake
    revision: int = Field(ge=1)
    status: ProposalStatus
    context: AssistanceContext
    response: GenerationResponse | None = None
    failure: Literal["PROVIDER_UNAVAILABLE", "INVALID_RESPONSE"] | None = None


class MutationResult(Contract):
    schema_version: Literal[1] = 1
    proposal_id: str
    proposal_revision: int
    status: ProposalStatus
    campaign_revision: int
    application: Literal["blocked"] = "blocked"


class AssistanceView(Contract):
    schema_version: Literal[1] = 1
    record: AssistanceRecord
    campaign_revision: int
    sources_current: bool
    application: Literal["blocked"] = "blocked"
