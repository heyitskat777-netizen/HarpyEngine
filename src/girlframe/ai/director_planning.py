"""A private Director proposal over existing character plans and sourced Fronts."""

from typing import Literal, Protocol

from pydantic import Field, model_validator

from girlframe.ai.contracts import Contract
from girlframe.ai.director import KnowledgeReference, SceneTime
from girlframe.ai.director_dossiers import DossierProfile, DossierState
from girlframe.ai.director_fronts import Front
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.scenes.opening import SceneOpening

PlanningKind = Literal["outcome", "closeout"]


class PlanningSource(Contract):
    kind: PlanningKind
    scene: str
    source: str
    label: str


class PlanningActor(Contract):
    actor: ActorRef
    label: str
    profile: DossierProfile | None
    state: DossierState | None
    known_refs: tuple[str, ...]


class PlanningFront(Contract):
    front: Front
    evidence: tuple[str, ...]
    actors: tuple[ActorRef, ...]


class DirectorPlanningPacket(Contract):
    scene: str
    opening: SceneOpening | None = None
    fictional_time: SceneTime | None = None
    source: PlanningSource
    trigger_refs: tuple[str, ...]
    references: tuple[KnowledgeReference, ...]
    actors: tuple[PlanningActor, ...]
    fronts: tuple[PlanningFront, ...]
    revision: str


class PlannedMove(Contract):
    front: str = Field(min_length=1, max_length=100)
    actor: ActorRef
    text: str = Field(min_length=1, max_length=400)
    evidence: tuple[str, ...] = Field(min_length=1, max_length=6)
    why: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def usable(self) -> "PlannedMove":
        if (
            not self.text.strip()
            or not self.why.strip()
            or len(set(self.evidence)) != len(self.evidence)
        ):
            raise ValueError(
                "Use a concise move, private rationale and distinct source references."
            )
        return self


class DirectorPlanningDecision(Contract):
    moves: tuple[PlannedMove, ...] = Field(default=(), max_length=3)
    reasoning: str = Field(min_length=1, max_length=1600)

    @model_validator(mode="after")
    def unique_proposals(self) -> "DirectorPlanningDecision":
        if (
            not self.reasoning.strip()
            or len({move.front for move in self.moves}) != len(self.moves)
            or len({move.actor for move in self.moves}) != len(self.moves)
        ):
            raise ValueError("Give each affected Front and character at most one move.")
        return self


class DirectorPlanningProvider(Protocol):
    def propose(self, packet: DirectorPlanningPacket) -> DirectorPlanningDecision: ...
