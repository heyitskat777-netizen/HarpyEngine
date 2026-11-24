"""Controller-authored character perspectives, separate from canonical mechanics."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from girlframe.ai.contracts import Contract
from girlframe.ai.director import DirectorContext
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.pilot_portrayal import PilotPortrayal


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


TermKind = Literal["agreement", "refusal", "condition"]


class DossierMemorySource(Contract):
    reference_id: str = Field(min_length=1, max_length=100)
    origin_scene: str = Field(min_length=1, max_length=100)
    consent_generation: int = Field(ge=0)


class RelationshipTerm(RelationshipPerspective):
    term: TermKind
    knowledge_refs: tuple[str, ...] = Field(min_length=1, max_length=10)
    memory_sources: tuple[DossierMemorySource, ...] = Field(
        default=(), max_length=10, exclude_if=lambda value: not value
    )


class PressurePlan(Contract):
    stake: str = Field(min_length=1, max_length=500)
    next_step: str | None = Field(default=None, min_length=1, max_length=500)
    blocker: str | None = Field(
        default=None, min_length=1, max_length=500, exclude_if=lambda value: value is None
    )
    trigger: str | None = Field(
        default=None, min_length=1, max_length=500, exclude_if=lambda value: value is None
    )
    fallback: str | None = Field(
        default=None, min_length=1, max_length=500, exclude_if=lambda value: value is None
    )
    consequence: str | None = Field(
        default=None, min_length=1, max_length=800, exclude_if=lambda value: value is None
    )
    status: Literal["open", "deferred", "resolved", "withdrawn"] = "open"
    account: str | None = Field(default=None, min_length=1, max_length=800)

    @model_validator(mode="after")
    def pressure_shape(self) -> "PressurePlan":
        if any(
            not text.strip()
            for text in (
                self.stake,
                self.next_step,
                self.blocker,
                self.trigger,
                self.fallback,
                self.consequence,
                self.account,
            )
            if text
        ):
            raise ValueError("Use nonblank pressure details")
        if (self.status in ("open", "deferred")) != (self.next_step is not None):
            raise ValueError("An unfinished pressure needs one possible next step")
        if self.status != "open" and self.account is None:
            raise ValueError("Record why the Girl deferred, resolved or withdrew the pressure")
        return self


class DossierPressure(DossierPerspective):
    pressure_id: str = Field(min_length=1, max_length=100)
    pressure: PressurePlan
    memory_sources: tuple[DossierMemorySource, ...] = Field(
        default=(), max_length=10, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def supported_choice(self) -> "DossierPressure":
        if (
            self.pressure.status != "open" or self.pressure.consequence
        ) and not self.knowledge_refs:
            raise ValueError("A changed pressure needs a witnessed source")
        return self


class DossierMemoryEdit(DossierPerspective):
    kind: Literal[
        "pressures", "promises", "beliefs", "obligations", "experiences", "relationships", "terms"
    ]
    subject: ActorRef | None = None
    term: TermKind | None = Field(default=None, exclude_if=lambda value: value is None)
    pressure_id: str | None = Field(
        default=None, min_length=1, max_length=100, exclude_if=lambda value: value is None
    )
    pressure: PressurePlan | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def memory_shape(self) -> "DossierMemoryEdit":
        if (self.kind in ("relationships", "terms")) != (self.subject is not None):
            raise ValueError("A relationship perspective names the other character")
        if (self.kind == "terms") != (self.term is not None) or (
            self.term and not self.knowledge_refs
        ):
            raise ValueError("A relationship term needs a kind and a heard source")
        if self.kind in ("promises", "experiences") and not self.knowledge_refs:
            raise ValueError("A witnessed promise or experience needs an authorized source")
        if (self.pressure is not None and self.kind != "pressures") or (
            self.pressure_id is not None and self.pressure is None
        ):
            raise ValueError("A pressure revision belongs on the pressure list")
        return self


class DossierContinuityEdit(DossierPerspective):
    """A short, reviewed update to the author's own characterization."""

    kind: Literal["intention", "commitment", "relationship"]
    text: str = Field(min_length=1, max_length=320)
    knowledge_refs: tuple[str, ...] = Field(min_length=1, max_length=3)
    subject: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def relationship_subject(self) -> "DossierContinuityEdit":
        if (self.kind == "relationship") != (self.subject is not None):
            raise ValueError("A relationship update names its counterpart")
        return self


class DossierContinuity(DossierContinuityEdit):
    origin_scene: str = Field(min_length=1, max_length=100)
    consent_generation: int = Field(ge=0)


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
    kind: Literal["accepted_help", "declined_help", "completed_handoff", "kept_promise"]
    offer_reference: str | None = Field(
        default=None, min_length=1, max_length=100, exclude_if=lambda value: value is None
    )


class HandlerExperience(HandlerExperienceSelection):
    pilot: ActorRef
    scene: str
    close_event: str
    reported_text: str
    offer_text: str | None = Field(default=None, exclude_if=lambda value: value is None)


SetupCue = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
SetupEntry = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class CharacterSetup(Contract):
    """Private portrayal guidance. Resources and limits cannot change engine state."""

    drive: SetupCue = ""
    fear: SetupCue = Field(default="", exclude_if=lambda value: not value)
    contradiction: SetupCue = Field(default="", exclude_if=lambda value: not value)
    default_approach: SetupCue = Field(default="", exclude_if=lambda value: not value)
    resources: tuple[SetupEntry, ...] = Field(default=(), max_length=6)
    limits: tuple[SetupEntry, ...] = Field(default=(), max_length=6)
    voice_at_ease: SetupCue = ""
    voice_under_pressure: SetupCue = ""
    voice_on_repair: SetupCue = ""
    gorgon_speech: bool = Field(default=False, exclude_if=lambda value: not value)


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
    pilot_portrayal: PilotPortrayal | None = Field(default=None, exclude_if=lambda x: x is None)
    character_setup: CharacterSetup | None = Field(default=None, exclude_if=lambda x: x is None)

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
    pressures: tuple[DossierPressure | DossierPerspective, ...] = Field(default=(), max_length=10)
    promises: tuple[DossierPerspective, ...] = Field(default=(), max_length=10)
    beliefs: tuple[DossierPerspective, ...] = Field(default=(), max_length=10)
    obligations: tuple[DossierPerspective, ...] = Field(default=(), max_length=10)
    experiences: tuple[DossierPerspective, ...] = Field(default=(), max_length=10)
    relationships: tuple[RelationshipPerspective, ...] = Field(default=(), max_length=10)
    terms: tuple[RelationshipTerm, ...] = Field(
        default=(), max_length=10, exclude_if=lambda value: not value
    )
    continuity: tuple[DossierContinuity, ...] = Field(
        default=(), max_length=12, exclude_if=lambda value: not value
    )

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
        if len({(x.subject, x.term) for x in self.terms}) != len(self.terms):
            raise ValueError("Keep one current term of each kind per counterpart")
        pressures = [x.pressure_id for x in self.pressures if isinstance(x, DossierPressure)]
        if len(set(pressures)) != len(pressures):
            raise ValueError("Keep one current version per pressure")
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
