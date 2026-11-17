"""Private situation records: evidence, hypotheses and attention, never executable effects."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from girlframe.ai.contracts import Contract
from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_world_development import Subject

Text = Annotated[str, Field(min_length=1, max_length=1200)]
FrontStatus = Literal["active", "dormant", "ready", "resolved"]


class FrontEvidence(Contract):
    kind: Literal["reference", "world_development"]
    id: str = Field(min_length=1, max_length=100)


class FrontParticipant(Contract):
    subject: Subject
    objective_refs: tuple[FrontEvidence, ...] = Field(default=(), max_length=12)
    resource_refs: tuple[FrontEvidence, ...] = Field(default=(), max_length=12)


class FrontHypothesis(Contract):
    id: str = Field(min_length=1, max_length=100)
    text: Text
    support_refs: tuple[FrontEvidence, ...] = Field(default=(), max_length=12)


class FrontMove(Contract):
    id: str = Field(min_length=1, max_length=100)
    subject: Subject
    text: Text
    evidence_refs: tuple[FrontEvidence, ...] = Field(default=(), max_length=12)


class FrontClock(Contract):
    mark: int = Field(default=0, ge=0, le=1000)
    limit: int = Field(ge=1, le=1000)

    @model_validator(mode="after")
    def bounded(self) -> "FrontClock":
        if self.mark > self.limit:
            raise ValueError("Front attention cannot exceed its clock limit")
        return self


class FrontAdvance(Contract):
    kind: Literal["outcome", "fictional_time"]
    id: str = Field(min_length=1, max_length=200)


class FrontDraft(Contract):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.:-]*$")
    title: str = Field(min_length=1, max_length=120)
    situation: Text
    participants: tuple[FrontParticipant, ...] = Field(default=(), max_length=12)
    # These are evidence records, not a claim that testimony is established truth.
    fact_refs: tuple[FrontEvidence, ...] = Field(min_length=1, max_length=32)
    hypotheses: tuple[FrontHypothesis, ...] = Field(default=(), max_length=12)
    possible_moves: tuple[FrontMove, ...] = Field(default=(), max_length=12)
    unresolved_consequences: tuple[Text, ...] = Field(default=(), max_length=12)
    clock: FrontClock | None = None
    deadline_tick: int | None = Field(default=None, ge=0)
    status: FrontStatus = "active"
    supersedes: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def distinct(self) -> "FrontDraft":
        if not self.title.strip() or not self.situation.strip():
            raise ValueError("Front narrative fields must be nonblank")
        for values in (self.hypotheses, self.possible_moves):
            if len({value.id for value in values}) != len(values):
                raise ValueError("Use distinct hypothesis and possible-move IDs")
        if len({value.subject for value in self.participants}) != len(self.participants):
            raise ValueError("List each actual participant once")
        return self


class Front(FrontDraft):
    id: str
    scene_id: str
    version: int = Field(ge=1)
    source_event: str
    confirmed_by: Snowflake
    consent_generation: int = Field(ge=0)
    subject_controllers: dict[str, Snowflake]
    advance: FrontAdvance | None = None
    advance_source: str | None = None
    fictional_tick: int = Field(ge=0)


class FictionalTime(Contract):
    id: str
    scene_id: str
    source_event: str
    confirmed_by: Snowflake
    consent_generation: int = Field(ge=0)
    steps: int = Field(ge=1, le=1_000_000)
    tick: int = Field(ge=1)
    account: Text
