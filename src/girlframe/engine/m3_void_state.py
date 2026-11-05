"""Original-source Void thresholds and a distinct live Harpy body/resource authority."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_janus_link_state import BatteryAsset
from girlframe.engine.m3_lobotomy_state import BlockedPlay
from girlframe.engine.m3_world_state import Cell


class HarpyAsset(Model):
    id: str = Field(min_length=1, max_length=180)
    family: Literal["girl", "frame"]
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1200)
    damaged: bool = False
    void: bool = True
    concealed: bool = False
    intrinsic: Literal["wyvern_enormous"] | None = None
    classification_event: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )

    battery_asset: BatteryAsset | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def exact_mental_source(self) -> "HarpyAsset":
        if self.battery_asset is not None and (
            self.family != "girl"
            or self.id != self.battery_asset.asset_id
            or self.name != self.battery_asset.name
            or self.intrinsic is not None
        ):
            raise ValueError("Use the exact printed source-linked mental Girl Asset")
        return self


class HarpyIdentity(Model):
    id: str = Field(min_length=1, max_length=180)
    name: str = Field(min_length=1, max_length=120)
    marked: bool = False
    protected: bool = False
    paired: bool = False
    slot: int | None = Field(default=None, ge=0, le=3)
    obsession_sources: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)


class HarpyTag(Model):
    id: str = Field(min_length=1, max_length=180)
    label: str = Field(min_length=1, max_length=120)
    giver: Snowflake
    giver_character: str | None = None
    giver_ref: ActorRef | None = None
    gm_setter_appointment: str | None = None
    gm_setter_event: str | None = None
    gm_setter_grant: str | None = None
    observers: tuple[Snowflake, ...] = ()
    marked: bool = False
    scene_used: str | None = None
    rejection_pending: bool = False


class HarpyState(Model):
    id: str = Field(min_length=1, max_length=100)
    origin: ActorRef
    controller: Snowflake
    name: str = Field(min_length=1, max_length=120)
    source_event: str = Field(min_length=1)
    original_archive: str = Field(min_length=1)
    old_body_vessel: str = Field(min_length=1)
    body_vessel: str = Field(min_length=1)
    frame_instance: str = Field(min_length=1)
    original_girl: str = Field(min_length=1)
    original_frame: str = Field(min_length=1)
    cell: Cell | None
    frame_cell: Cell | None
    linked: bool = True
    frame_shutdown: bool = False
    body_incapacitated: bool = False
    subsumed: bool = False
    vitals_active: bool = True
    physical_source_event: str | None = None
    condition_event: str | None = None
    heat: int = Field(default=0, ge=0)
    permissions: int = Field(default=0, ge=0)
    assets: tuple[HarpyAsset, ...]
    identities: tuple[HarpyIdentity, ...]
    tags: tuple[HarpyTag, ...] = ()
    plays: tuple[str, ...] = ()
    blocked_plays: tuple[BlockedPlay, ...] = ()
    alive: bool = True
    revealed: bool = False
    exposed: bool = False
    custody: Literal["free", "captured", "transported", "core"] = "free"
    custodian: ActorRef | None = None
    custody_event: str | None = None
    core_frame_owner: ActorRef | None = None
    core_frame_instance: str | None = None

    @model_validator(mode="after")
    def actual_transformation(self) -> "HarpyState":
        if (
            self.origin.kind != "pilot"
            or self.controller != int(self.origin.entity)
            or self.body_vessel == self.old_body_vessel
        ):
            raise ValueError(
                "A reborn Harpy preserves its original controller and distinct actual new body"
            )
        for values in (self.assets, self.identities, self.tags):
            if len({x.id for x in values}) != len(values):
                raise ValueError("Harpy resources retain distinct actual identities")
        if len(set(self.plays)) != len(self.plays):
            raise ValueError("Retain each actual owned Play only once")
        if self.linked and self.cell != self.frame_cell:
            raise ValueError(
                "An actually linked Harpy body and Frame share their known or unknown position"
            )
        if self.custody == "core" and self.linked:
            raise ValueError("An installed captured Core is distinct from her original Frame body")
        if self.custody == "free" and (
            self.custodian is not None or self.custody_event is not None
        ):
            raise ValueError("A free Harpy has no invented active custody")
        if self.custody != "free" and (self.custodian is None or not self.custody_event):
            raise ValueError("Actual Harpy custody needs its custodian and source")
        if (self.custody == "core") != (
            self.core_frame_owner is not None and self.core_frame_instance is not None
        ):
            raise ValueError("A Core is a distinct captured body installed in one actual Frame")
        return self


class VoidAnswer(Model):
    number: int = Field(ge=0, le=4)
    answer: bool
    owner: Snowflake
    source_event: str = Field(min_length=1)
    honest: Literal[True]


class RebirthChoice(Model):
    retained_identities: tuple[str, ...] = ()
    new_identities: tuple[str, ...] = ()
    retained_tags: tuple[str, ...] = ()
    retained_plays: tuple[str, ...] = ()
    discarded_bonds: tuple[ActorRef, ...] = ()
    assets: tuple[HarpyAsset, ...]
    account: str = Field(min_length=1, max_length=1200)


class VoidThreshold(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    frame_instance: str = Field(min_length=1)
    family: Literal["girl", "frame"]
    source_event: str = Field(min_length=1)
    source_action: str | None = None
    source_works: tuple[str, ...] = ()
    sheet_json: str = Field(min_length=1)
    stage: Literal[
        "allured",
        "physical_review",
        "abandoned",
        "enclosed",
        "resist_pending",
        "questions",
        "rebirth",
        "overgrown",
        "overgrown_alive",
        "prevented",
        "escaped",
        "converted",
        "dead",
    ]
    enclosed: bool = False
    free_identity: str | None = None
    answers: tuple[VoidAnswer, ...] = Field(default=(), max_length=5)
    resistance_action: str | None = None
    response_event: str | None = None
    resulting_actor: ActorRef | None = None
    gorgon: ActorRef | None = None
    survival: Literal["pending", "alive", "dead"] | None = None
    pending_advancements: int = Field(default=0, ge=0, le=3)
    guardian: ActorRef | None = None
    allure_persists: bool = False
    protection_release_event: str | None = None

    @model_validator(mode="after")
    def actual_sequence(self) -> "VoidThreshold":
        if self.actor.kind != "pilot" or len(set(self.source_works)) != len(self.source_works):
            raise ValueError("A threshold keeps its original Girl and exact source consequences")
        if tuple(x.number for x in self.answers) != tuple(range(len(self.answers))):
            raise ValueError("The table asks the five actual questions in order")
        if any(x.owner != int(self.actor.entity) for x in self.answers):
            raise ValueError("Only the original Girl's human answers her actual questions")
        if self.stage == "rebirth" and (
            len(self.answers) != 5 or any(x.answer for x in self.answers)
        ):
            raise ValueError("Actual rebirth requires five honest owned no answers")
        return self
