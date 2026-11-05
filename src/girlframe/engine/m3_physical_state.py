"""Actual original Pilot placement; character identity is not a physical vessel."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell

Mode = Literal["outside_frame", "inside_frame", "piloting"]


class CockpitAction(Model):
    actor: ActorRef
    operation: Literal["exit", "sit", "pilot"]
    expected_position: str = Field(pattern=r"^[a-f0-9]{64}$")
    account: str = Field(min_length=1, max_length=1200)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def actual_owner_action(self) -> "CockpitAction":
        if self.actor.kind != "pilot" or not self.account.strip():
            raise ValueError("Choose your actual original Girl's cockpit operation")
        return self


class InitialPlacement(Model):
    actor: ActorRef
    frame_instance: str = Field(min_length=1, max_length=180)
    girl_cell: Cell
    frame_cell: Cell
    mode: Mode
    account: str = Field(min_length=1, max_length=1200)
    facts_confirmed: Literal[True]

    @model_validator(mode="after")
    def actual_facts(self) -> "InitialPlacement":
        if self.actor.kind != "pilot" or not self.account.strip():
            raise ValueError("Record the actual original Girl, Frame and physical facts")
        if self.mode != "outside_frame" and self.girl_cell != self.frame_cell:
            raise ValueError("A Girl inside a Frame is at that actual Frame's map cell")
        return self


class Placement(Model):
    actor: ActorRef
    vessel_id: str = Field(min_length=1, max_length=100)
    frame_instance: str = Field(min_length=1, max_length=180)
    girl_cell: Cell | None
    frame_cell: Cell | None
    mode: Mode
    occupied_frame_owner: ActorRef | None = None
    occupied_frame_instance: str | None = Field(default=None, min_length=1, max_length=180)
    custody: ActorRef | None = None
    vitals_active: bool = True
    incapacitated: bool = False
    subsumed: bool = False
    proposed_event: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def actual_placement(self) -> "Placement":
        if self.actor.kind != "pilot" or any(
            not x.strip()
            for x in (
                self.vessel_id,
                self.frame_instance,
                self.proposed_event,
                self.source_event,
                self.account,
            )
        ):
            raise ValueError("An original Pilot placement retains its actual character and source")
        if (self.occupied_frame_owner is None) != (self.occupied_frame_instance is None):
            raise ValueError("A passenger records both actual occupied Frame owner and instance")
        if self.occupied_frame_owner is not None and (
            self.occupied_frame_owner.kind != "pilot"
            or self.occupied_frame_owner == self.actor
            or self.mode != "inside_frame"
        ):
            raise ValueError(
                "A passenger occupies another actual Girl's cockpit without piloting it"
            )
        if (
            self.mode != "outside_frame"
            and self.occupied_frame_owner is None
            and (self.girl_cell != self.frame_cell)
        ):
            raise ValueError("An occupied Frame and its Girl share the actual map cell")
        if self.mode == "outside_frame" and self.occupied_frame_owner is not None:
            raise ValueError("A body outside a Frame has no cockpit occupancy")
        if self.subsumed and (self.mode == "outside_frame" or self.vitals_active):
            raise ValueError("A subsumed Girl is inside a cockpit with no active vital signs")
        if self.proposed_event == self.source_event:
            raise ValueError("The owned factual proposal and actual review have distinct events")
        return self


class ParkedFrame(Model):
    owner: ActorRef
    frame_instance: str = Field(min_length=1)
    cell: Cell | None
    source_event: str = Field(min_length=1)
    prior_event: str = Field(min_length=1)
    core_id: str | None = None
    frame_json: str = Field(min_length=1)

    @model_validator(mode="after")
    def actual_old_frame(self) -> "ParkedFrame":
        if self.owner.kind != "pilot" or self.source_event == self.prior_event:
            raise ValueError("A parked actual old Frame preserves its distinct original source")
        return self


class ExtractionConsent(Model):
    actor: ActorRef
    controller: Snowflake
    allowed: bool
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    used_event: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def actual_response(self) -> "ExtractionConsent":
        if self.actor.kind not in ("pilot", "external_pilot") or not self.account.strip():
            raise ValueError("An extraction response names the actual original Girl")
        if self.used_event is not None and not self.allowed:
            raise ValueError("A refused extraction cannot be consumed as consent")
        return self


class FrameLock(Model):
    id: str = Field(min_length=1)
    owner: ActorRef
    frame_instance: str = Field(min_length=1)
    subject: ActorRef
    source_event: str = Field(min_length=1)
    core_id: str | None = Field(default=None, min_length=1)
    active: bool = True
    consents: tuple[ExtractionConsent, ...] = ()
    released_event: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def actual_frame(self) -> "FrameLock":
        if self.owner.kind not in ("pilot", "external_pilot") or self.subject.kind not in (
            "pilot",
            "external_pilot",
        ):
            raise ValueError("A source-bound cockpit lock names its actual Frame and original Girl")
        if self.active == (self.released_event is not None):
            raise ValueError("Only an explicitly released cockpit lock has a release source")
        if len({x.source_event for x in self.consents}) != len(self.consents):
            raise ValueError("Every Frame response has one actual source event")
        return self


class EscortJourney(Model):
    id: str = Field(min_length=1)
    traveler: ActorRef
    supervisor: ActorRef
    traveler_origin: Placement
    supervisor_origin: Placement | None = None
    supervisor_cell: Cell | None = None
    departure_event: str = Field(min_length=1)
    active: bool = True
    return_event: str | None = Field(default=None, min_length=1)
    interruption_event: str | None = Field(default=None, min_length=1)
    offstage_refs: tuple[ActorRef, ...] = ()

    @model_validator(mode="after")
    def actual_party(self) -> "EscortJourney":
        if (
            self.traveler.kind != "pilot"
            or self.traveler == self.supervisor
            or self.traveler_origin.actor != self.traveler
        ):
            raise ValueError("A supervised journey preserves its actual distinct original roles")
        if (self.supervisor.kind == "pilot") != (self.supervisor_origin is not None):
            raise ValueError("A Pilot supervisor retains its original physical body snapshot")
        if self.supervisor_origin is not None and self.supervisor_origin.actor != self.supervisor:
            raise ValueError("The supervisor's original body belongs to that exact role")
        endings = int(self.return_event is not None) + int(self.interruption_event is not None)
        if (self.active and endings) or (not self.active and endings != 1):
            raise ValueError(
                "A journey has one actual return or interruption, never a fabricated return"
            )
        if (
            len(set(self.offstage_refs)) != len(self.offstage_refs)
            or any(x not in (self.traveler, self.supervisor) for x in self.offstage_refs)
            or (self.offstage_refs and self.interruption_event is None)
        ):
            raise ValueError(
                "Interrupted physical presence stays attached to the actual original party"
            )
        return self


class Review(Model):
    proposal: InitialPlacement
    label: str = Field(min_length=1, max_length=120)
    handler: Snowflake
    proposed_event: str = Field(min_length=1)
    origin: Placement | None = None
    decision: Literal["pending", "accepted", "declined", "withdrawn"] = "pending"
    review_event: str | None = None
    vessel_id: str | None = None
    response: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def actual_review(self) -> "Review":
        if self.decision == "pending":
            if self.review_event is not None or self.vessel_id is not None or self.response:
                raise ValueError("A pending physical proposal has no invented review")
        elif (
            not self.review_event
            or not self.response.strip()
            or self.review_event == self.proposed_event
        ):
            raise ValueError("Record the actual distinct owned review source and response")
        if (self.decision == "accepted") != (self.vessel_id is not None):
            raise ValueError("Only accepted original physical facts establish a vessel")
        return self
