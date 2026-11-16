"""Deterministic local summary provider: no network, credentials or model calls."""

from girlframe.ai.contracts import (
    DraftProposal,
    GenerationRequest,
    GenerationResponse,
    summary_text,
    validate_response,
)


class SyntheticProvider:
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        response = GenerationResponse(
            proposal=DraftProposal(
                text=summary_text(request.context),
                source_ids=tuple(fact.source_id for fact in request.context.facts),
            )
        )
        validate_response(request, response)
        return response
