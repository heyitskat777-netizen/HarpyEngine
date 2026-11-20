"""Controller-authored character perspectives, separate from canonical mechanics."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.ai.contracts import Contract
from girlframe.ai.director import DirectorContext
from girlframe.engine.m3_actor_state import ActorRef


class DossierPerspective(Contract):
    text: str = Field(min_length=1, max_length=800)
    knowledge_refs: tuple[str, ...] = Field(default=(), max_length=10)
    provenance: Literal["controller_authored_perspective"] = "controller_authored_perspective"

    @model_validator(mode="after")
    def distinct_sources(self) -> "DossierPerspective":
        if (
            not self.text.strip()
            or len(set(self.knowledge_refs)) != len(self.knowledge_refs)
            or any(not value.strip() or len(value) > 100 for value in self.knowledge_refs)
        ):
            raise ValueError(
                "Use nonblank perspective text and distinct actual knowledge references"
            )
        return self


class RelationshipPerspective(DossierPerspective):
    subject: ActorRef


class StartingRelationship(Contract):
    pilot: ActorRef
    shared_history: str = Field(min_length=1, max_length=1200)


class HandlerIdentity(Contract):
    name: str = Field(min_length=1, max_length=120)
    activation_event: str
    starting_relationship: StartingRelationship | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class HandlerExperienceSelection(Contract):
    reference_id: str = Field(min_length=1, max_length=100)
    kind: Literal["declined_help", "completed_handoff", "kept_promise"]


class HandlerExperience(HandlerExperienceSelection):
    pilot: ActorRef
    scene: str
    close_event: str
    reported_text: str


class DossierProfile(Contract):
    presence: Literal["background", "recurring"] = "background"
    background: str = Field(default="", max_length=2000)
    voice: str = Field(default="", max_length=1000)
    behavior: str = Field(default="", max_length=1000)
    reaction_tendencies: tuple[str, ...] = Field(default=(), max_length=10)
    limits: tuple[str, ...] = Field(default=(), max_length=10)
    values: tuple[str, ...] = Field(default=(), max_length=10)
    fears: tuple[str, ...] = Field(default=(), max_length=10)
    contradictions: tuple[str, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def bounded_traits(self) -> "DossierProfile":
        if any(
            not text.strip() or len(text) > 500
            for text in (
                *self.values,
                *self.fears,
                *self.contradictions,
                *self.reaction_tendencies,
                *self.limits,
            )
        ):
            raise ValueError("Use short nonblank character traits")
        return self


class DossierState(Contract):
    objective_ref: str | None = Field(default=None, min_length=1, max_length=100)
    goal_refs: tuple[str, ...] = Field(default=(), max_length=10)
    resource_refs: tuple[str, ...] = Field(default=(), max_length=10)
    pressures: tuple[DossierPerspective, ...] = Field(default=(), max_length=10)
    promises: tuple[DossierPerspective, ...] = Field(default=(), max_length=10)
    beliefs: tuple[DossierPerspective, ...] = Field(default=(), max_length=10)
    obligations: tuple[DossierPerspective, ...] = Field(default=(), max_length=10)
    experiences: tuple[DossierPerspective, ...] = Field(default=(), max_length=10)
    relationships: tuple[RelationshipPerspective, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def distinct_goals_and_relationships(self) -> "DossierState":
        if len(set(self.goal_refs)) != len(self.goal_refs) or any(
            not x.strip() or len(x) > 100 for x in self.goal_refs
        ):
            raise ValueError("Reference each actual canonical goal once")
        if len(set(self.resource_refs)) != len(self.resource_refs) or any(
            not value.strip() or len(value) > 100 for value in self.resource_refs
        ):
            raise ValueError("Reference each actual known resource source once")
        if len({x.subject for x in self.relationships}) != len(self.relationships):
            raise ValueError("Keep one current perspective per relationship")
        return self


class Personnel(Contract):
    """Only these explicitly published fields may enter a personnel lookup."""

    public_summary: str = Field(default="", max_length=500)
    mannerisms: str = Field(default="", max_length=500)


class PilotDossierOrigin(Contract):
    plan: str = Field(min_length=1, max_length=100)
    callsign: str = Field(min_length=1, max_length=100)


class DossierProposal(Contract):
    id: str
    scene_id: str
    actor: ActorRef
    controller: int
    proposer: int
    expected_version: int = Field(ge=0)
    profile: DossierProfile
    state: DossierState
    personnel: Personnel
    binding: str
    application: Literal["controller_review_only"] = "controller_review_only"
    pilot_origin: PilotDossierOrigin | None = Field(default=None, exclude_if=lambda x: x is None)


class DossierRecord(Contract):
    id: str
    actor: ActorRef
    controller: int
    version: int = Field(ge=1)
    supersedes: str | None = None
    profile: DossierProfile
    state: DossierState
    personnel: Personnel
    scene_id: str
    proposal_id: str
    source_event: str
    pilot_origin: PilotDossierOrigin | None = Field(default=None, exclude_if=lambda x: x is None)


class DossierNote(Contract):
    id: str
    actor: ActorRef
    version: int = Field(ge=1)
    supersedes: str | None = None
    text: str = Field(min_length=1, max_length=4000)
    author: int
    scene_id: str
    source_event: str


class DossierPacket(Contract):
    actor: ActorRef
    dossier_version: int = Field(ge=0)
    dossier_id: str | None = None
    profile: DossierProfile | None = None
    state: DossierState | None = None
    handler_identity: HandlerIdentity | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    handler_experiences: tuple[HandlerExperience, ...] = Field(
        default=(), max_length=3, exclude_if=lambda value: not value
    )
    context: DirectorContext
    source_refs: tuple[str, ...]
    revision: str
    controller_rebase_required: bool = False
