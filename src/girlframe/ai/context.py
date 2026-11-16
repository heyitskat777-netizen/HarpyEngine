"""Pure whitelisting over existing authorized public character projections.

The caller obtains projections under current server authorization and a stable
campaign snapshot. Public visibility does not confer fictional knowledge: this
builder supports OOC summaries only, with an even smaller Handler roster view.
"""

from girlframe.ai.contracts import AssistanceContext, Audience, ContextFact
from girlframe.engine.character_documents import CharacterSheetDocument


def build_context(
    *,
    campaign_id: str,
    requester_id: str,
    audience: Audience,
    campaign_revision: int,
    projections: tuple[CharacterSheetDocument, ...],
) -> AssistanceContext:
    """Select fixed scalar references; never copy whole projections or private fields."""
    if len(projections) > 24:
        raise ValueError("Reference summary supports at most 24 authorized characters")
    facts: list[ContextFact] = []
    for document in sorted(projections, key=lambda item: item.owner_id):
        if document.audience != "public":
            raise ValueError("AI reference context requires an authorized public projection")
        if audience == "player" and document.owner_id != requester_id:
            raise ValueError("Player context cannot include another owner's projection")
        fields = (
            ("callsign",)
            if audience == "handler"
            else ("callsign", "girl_playbook", "frame_playbook", "state")
        )
        for field in fields:
            # Active public_sheet uses status; character exports expose state.
            value = document.sheet.get(field)
            if field == "state" and value is None:
                value = document.sheet.get("status")
            if value is None:
                continue
            facts.append(
                ContextFact.model_validate(
                    {
                        "source_id": (
                            f"sheet:{document.owner_id}:{document.character_id or 'draft'}:"
                            f"{document.revision}:{field}"
                        ),
                        "subject_id": document.owner_id,
                        "source_revision": document.revision,
                        "field": field,
                        "value": value,
                    }
                )
            )
    return AssistanceContext(
        campaign_id=campaign_id,
        requester_id=requester_id,
        audience=audience,
        campaign_revision=campaign_revision,
        facts=tuple(facts),
    )
