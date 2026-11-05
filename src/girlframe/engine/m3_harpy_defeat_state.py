"""Actual Harpy bodies and Defeat effects, without fabricated original Pilot sheets."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_lobotomy_state import BlockedPlay
from girlframe.engine.m3_void_state import HarpyIdentity, HarpyTag
from girlframe.engine.m3_world_state import Cell


class NativeHarpyFacts(Model):
    actor: ActorRef
    linked: bool
    girl_cell: Cell | None
    frame_cell: Cell | None
    heat: int = Field(ge=0)
    frame_shutdown: bool
    body_incapacitated: bool
    custody: Literal["free", "captured", "transported", "core"]
    custodian: ActorRef | None = None
    identities: tuple[HarpyIdentity, ...]
    tags: tuple[HarpyTag, ...]
    account: str = Field(min_length=1, max_length=1200)
    facts_confirmed: bool

    @model_validator(mode="after")
    def actual_known_facts(self) -> "NativeHarpyFacts":
        if (
            self.actor.kind != "external_pilot"
            or self.facts_confirmed is not True
            or not self.account.strip()
        ):
            raise ValueError("Confirm this actual external Harpy's current factual resources")
        if self.linked and self.girl_cell != self.frame_cell:
            raise ValueError(
                "An actually linked Harpy and Frame share their real known or unknown cell"
            )
        if (self.custody == "free") != (self.custodian is None):
            raise ValueError("Record the actual current custodian only when this Harpy is held")
        for values in (self.identities, self.tags):
            if len({x.id for x in values}) != len(values):
                raise ValueError("Keep each actual existing resource identity distinct")
        return self


class NativeHarpyRuntime(Model):
    id: str = Field(min_length=1)
    controller: Snowflake
    source_event: str = Field(min_length=1)
    proposed_event: str = Field(min_length=1)
    world_source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    body_vessel: str = Field(min_length=1)
    frame_instance: str = Field(min_length=1)
    cell: Cell | None
    frame_cell: Cell | None
    linked: bool
    heat: int = Field(ge=0)
    identities: tuple[HarpyIdentity, ...]
    tags: tuple[HarpyTag, ...]
    blocked_plays: tuple[BlockedPlay, ...] = ()
    frame_shutdown: bool = False
    body_incapacitated: bool = False
    subsumed: bool = False
    vitals_active: bool = True
    physical_source_event: str | None = None
    condition_event: str | None = None
    custody: Literal["free", "captured", "transported", "core"] = "free"
    custodian: ActorRef | None = None
    custody_event: str | None = None

    @model_validator(mode="after")
    def source_body(self) -> "NativeHarpyRuntime":
        if self.linked and self.cell != self.frame_cell:
            raise ValueError("An actually linked Harpy and Frame share their current cell")
        if self.custody == "free" and (
            self.custodian is not None or self.custody_event is not None
        ):
            raise ValueError("A free actual Harpy has no invented custodian")
        if self.custody != "free" and (self.custodian is None or self.custody_event is None):
            raise ValueError("Actual custody needs the real captor and its source event")
        return self


class HarpySetup(Model):
    id: str = Field(min_length=1)
    owner: Snowflake
    handler: Snowflake
    appointment: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    facts: NativeHarpyFacts
    state: Literal["proposed", "declined", "approved"] = "proposed"
    response_event: str | None = None
    review: str = Field(default="", max_length=1200)


class Rift(Model):
    id: str = Field(min_length=1)
    owner: ActorRef
    action: str = Field(min_length=1)
    scene: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    open: bool = True
    closed_event: str | None = None
    description: str = Field(min_length=1, max_length=1200)


class Travel(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    controller: Snowflake
    source_event: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rift: str | None = None
    escape_effect: str | None = None
    frame_instance: str | None = None
    travels_frame: bool
    destination: Cell | None
    account: str = Field(min_length=1, max_length=1200)
    navigation: str = Field(min_length=1, max_length=1200)
    judge: Snowflake
    adjudicator: ActorRef | None = None
    appointment: str = Field(min_length=1)
    state: Literal["proposed", "offstage", "returned", "rejected"] = "proposed"
    response_event: str | None = None
    review: str = Field(default="", max_length=1200)
    return_of: str | None = None

    @model_validator(mode="after")
    def actual_route(self) -> "Travel":
        if (self.rift is None) == (self.escape_effect is None):
            raise ValueError("A route belongs to exactly one actual Rift or printed escape")
        if self.travels_frame and self.frame_instance is None:
            raise ValueError("Traveling with a Frame records its actual instance")
        if self.rift is not None and self.return_of is None and self.destination is not None:
            raise ValueError("A Rift crossing preserves its unknown offstage destination")
        if self.return_of is not None and self.destination is None:
            raise ValueError("A real reviewed return names its actual known destination")
        return self


class DefeatEffect(Model):
    id: str = Field(min_length=1)
    departed: tuple[ActorRef, ...] = ()
    action: str = Field(min_length=1)
    work: str = Field(min_length=1)
    actor: ActorRef
    frame_instance: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    tier: Literal["low", "mid", "high"]
    choice: Literal[
        "message", "rift", "kidnap", "foundation", "plead", "death", "shutdown", "rescue"
    ]
    account: str = Field(min_length=1, max_length=1200)
    girl: ActorRef | None = None
    rescuer: ActorRef | None = None
    killer: ActorRef | None = None
    captor: ActorRef | None = None
    phase: Literal[
        "awaiting_girl",
        "awaiting_killer",
        "awaiting_captor",
        "awaiting_physical",
        "rejected",
        "complete",
    ] = "complete"
    response_event: str | None = None
    response: str = Field(default="", max_length=1200)
    escaped: bool = False
    cut_link: bool = False
    tag: str | None = None
    tag_id: str | None = None
    factual_source: str | None = None
    source_cast: SceneCast


class Declaration(Model):
    id: str = Field(min_length=1)
    work: str = Field(min_length=1)
    work_revision: int = Field(ge=1)
    actor: ActorRef
    controller: Snowflake
    frame_instance: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_action: str | None
    source_request: str | None
    registry: str = Field(min_length=1)
    gm_controller: Snowflake
    adjudicator: ActorRef | None = None
    appointment: str = Field(min_length=1)
    handler: ActorRef | None
    cast: SceneCast
    modifier: Literal[2, 4]
    bond_girl: ActorRef | None = None
