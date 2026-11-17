"""Source-bound reference context and synthetic five-way Director decisions."""

from typing import Literal, Protocol

from pydantic import Field, model_validator

from girlframe.ai.contracts import Contract
from girlframe.engine.m3_actor_state import ActorRef


class KnowledgeRelation(Contract):
    """A stated relationship between accounts, not an engine verdict about truth."""

    kind: Literal["competes_with", "corrects"]
    reference_id: str = Field(min_length=1, max_length=100)


class KnowledgeReference(Contract):
    id: str
    source_id: str
    source_revision: int
    order: int
    dependencies: tuple[str, ...] = ()
    known_by: tuple[str, ...] = ()
    reported_by: ActorRef | None = Field(default=None, exclude_if=lambda x: x is None)
    relations: tuple[KnowledgeRelation, ...] = Field(
        default=(), max_length=10, exclude_if=lambda x: not x
    )
    origin_scene: str | None = Field(default=None, exclude_if=lambda x: x is None)
    origin_reference: str | None = Field(default=None, exclude_if=lambda x: x is None)
    topic: Literal["general", "objective", "scope", "status", "briefing", "tactical", "debrief"] = (
        "general"
    )
    classification: Literal["reported_claim", "committed_play", "approved_outcome"]
    text: str = Field(max_length=1200)

    @model_validator(mode="after")
    def complete_origin(self) -> "KnowledgeReference":
        if (self.origin_scene is None) != (self.origin_reference is None):
            raise ValueError("Continuity requires both original scene and reference")
        return self


class DirectorContext(Contract):
    schema_version: Literal[1] = 1
    campaign_id: str
    scene_id: str
    audience: Literal["gm", "actor"]
    actor: ActorRef | None = None
    revision: str
    references: tuple[KnowledgeReference, ...] = Field(max_length=100)


class DirectorDecision(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["WAIT", "REQUEST_PLAY", "NPC_DIALOGUE", "WORLD_EVENT_PROPOSAL", "NEEDS_REVIEW"]
    reason_code: Literal["no_grounded_need", "completed_play", "explicit_request", "unsupported"]
    source_refs: tuple[str, ...] = Field(default=(), max_length=100)
    actor_id: str | None = None
    rule_id: str | None = None
    brief: str = Field(default="", max_length=1200)
    # Mechanical effects have no consumer in the synthetic trial.
    proposed_effects: tuple[()] = ()
    requires_player_choice: bool = False


class DirectorProvider(Protocol):
    def decide(self, context: DirectorContext) -> DirectorDecision: ...


class SyntheticDirector:
    """No network/model emulation claims: conservative, deterministic reference policy."""

    def decide(self, context: DirectorContext) -> DirectorDecision:
        plays = tuple(
            x.id
            for x in context.references
            if x.classification in ("committed_play", "approved_outcome")
        )
        if plays:
            return DirectorDecision(
                kind="NEEDS_REVIEW",
                reason_code="completed_play",
                source_refs=plays,
                brief="A committed Play is available for facilitator review.",
            )
        return DirectorDecision(kind="WAIT", reason_code="no_grounded_need")
