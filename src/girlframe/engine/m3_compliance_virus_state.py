"""Actual virus strains, Frame identity and one-shot purge causes; no dice receipts."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_work_scope import WorkScope


class Record(Model):
    id: str = Field(min_length=1)


class FrameRef(Model):
    owner: ActorRef
    instance: str = Field(min_length=1, max_length=180)


class Strain(Record):
    id: str = Field(min_length=1)
    creator: ActorRef
    controller: int = Field(gt=0)
    grant: str = Field(min_length=1)
    creator_frame: str = Field(min_length=1)
    target: FrameRef
    source_event: str = Field(min_length=1)
    cockpit_source: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    purged_event: str | None = None


class InfectedPerson(Record):
    id: str = Field(min_length=1)
    strain: str = Field(min_length=1)
    actor: ActorRef
    controller: int = Field(gt=0)
    source_event: str = Field(min_length=1)
    link_source: str = Field(min_length=1)
    purged_event: str | None = None


class Purge(Record):
    id: str = Field(min_length=1)
    kind: Literal["girl", "frame"]
    strain: str = Field(min_length=1)
    creator: ActorRef
    creator_controller: int = Field(gt=0)
    creator_frame: str = Field(min_length=1)
    grant: str = Field(min_length=1)
    target: ActorRef | None
    target_controller: int | None = Field(default=None, gt=0)
    frame_controller: int = Field(gt=0)
    operational_action: str = Field(min_length=1)
    target_frame: FrameRef | None = None
    person_infection: str | None = None
    scope: WorkScope
    channel: int = Field(gt=0)
    judge: ActorRef | None
    judge_controller: int = Field(gt=0)
    appointment: str = Field(min_length=1)
    registry: str = Field(min_length=1)
    cast_json: str = Field(min_length=1)
    cast_sha256: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    phase: Literal[
        "queued",
        "vacancy_proposal",
        "vacancy_review",
        "contact_review",
        "order",
        "awaiting_order",
        "punishment",
        "complete",
        "ended",
    ]
    revision: int = Field(default=1, ge=1)
    vacancy_kind: Literal["vacant", "owner_linked"] | None = None
    vacancy_proposed_event: str | None = None
    vacancy_reviewed_event: str | None = None
    review_event: str | None = None
    contact_confirmed: bool = False
    order_text: str = Field(default="", max_length=1200)
    order_action: str | None = None
    order_id: str | None = None
    order_event: str | None = None
    immune: bool = False
    role_case: str | None = None
    effect_event: str | None = None
    punishment_executor: ActorRef | None = None
    punishment_executor_frame: str | None = None
    discovery_action: str | None = None
    discovery_choice: str | None = None
    completion_event: str | None = None
    end_reason: str | None = None
    cancelled_by: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def honest_cause(self) -> "Purge":
        if not self.account.strip():
            raise ValueError("A real original owner purges another person's actual infection")
        if self.kind == "frame":
            if self.target_frame is None or self.person_infection is not None:
                raise ValueError("Frame purge preserves its actual Frame and linked original")
            if self.phase not in (
                "queued",
                "vacancy_proposal",
                "vacancy_review",
                "punishment",
                "complete",
                "ended",
            ):
                raise ValueError("A remote Frame purge has no invented touching review")
        elif self.person_infection is None or self.target_frame is not None or self.target is None:
            raise ValueError("Touch purge names one actual infected original person")
        if (self.target is None) != (self.target_controller is None):
            raise ValueError(
                "An actual Pilot has both source body and actual human; vacant has neither"
            )
        if self.phase == "punishment" and (
            self.role_case is None or self.effect_event is None or self.target is None
        ):
            raise ValueError("Printed fixed11 has its actual source and owned Punishment case")
        if self.phase == "complete" and self.completion_event is None:
            raise ValueError("Only a genuine source completion ends this purge")
        return self


class PainRestraint(Record):
    id: str = Field(min_length=1)
    purge: str = Field(min_length=1)
    actor: ActorRef
    inflictor: ActorRef
    source_event: str = Field(min_length=1)
    active: bool = True
    ended_event: str | None = None

    @model_validator(mode="after")
    def actual_duration(self) -> "PainRestraint":
        if self.active == (self.ended_event is not None):
            raise ValueError("Pain restraint lasts through its actual immediate Punishment chain")
        return self


class PastLinkExposure(Record):
    """Newly recorded owned fact about a real earlier episode; never current control."""

    id: str = Field(min_length=1)
    actor: ActorRef
    context_actor: ActorRef
    controller: int = Field(gt=0)
    strain: str = Field(min_length=1)
    frame: FrameRef
    frame_controller: int = Field(gt=0)
    judge: ActorRef | None
    judge_controller: int = Field(gt=0)
    appointment: str = Field(min_length=1)
    prior_event: str = Field(min_length=1)
    proposed_event: str = Field(min_length=1)
    channel: int = Field(gt=0)
    cast_json: str = Field(min_length=1)
    episode: str = Field(min_length=1, max_length=1200)
    frame_confirmed_event: str | None = None
    reviewed_event: str | None = None
    phase: Literal["frame_confirmation", "judge_review", "approved", "rejected"] = (
        "frame_confirmation"
    )
    revision: int = Field(default=1, ge=1)
