"""Source-admitted original JANUS Core, never a copied Pilot or second Frame."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_lobotomy_state import BlockedPlay
from girlframe.engine.m3_void_state import HarpyAsset, HarpyIdentity, HarpyTag
from girlframe.engine.m3_world_state import Cell

BASELINE = (
    ("drugged", "Drugged"),
    ("restrained", "Restrained"),
    ("muzzled", "Muzzled"),
    ("surgery", "Recovering from Surgery"),
)


class CoreFacts(Model):
    """Unspecified existing body facts require the real controller and source review."""

    appearance: str = Field(min_length=1, max_length=1200)
    heat: int = Field(ge=0)
    identities: tuple[HarpyIdentity, ...]
    girl_assets: tuple[HarpyAsset, ...] = Field(max_length=4)
    exposed: bool
    account: str = Field(min_length=1, max_length=1200)
    facts_confirmed: bool

    @model_validator(mode="after")
    def original_facts(self) -> "CoreFacts":
        if (
            self.facts_confirmed is not True
            or not self.appearance.strip()
            or not self.account.strip()
        ):
            raise ValueError("The actual controller confirms real unspecified existing Core facts")
        if any(x.family != "girl" for x in self.girl_assets):
            raise ValueError("The Core shares the original JANUS Frame; never copy its Assets")
        if any(x.battery_asset is not None for x in self.girl_assets):
            raise ValueError("Initial Core facts cannot manufacture source-linked borrowed Assets")
        if any(not x.void for x in self.girl_assets):
            raise ValueError("A normal Harpy Core's actual Girl Assets are Touched by the Void")
        for values in (self.identities, self.girl_assets):
            if len({x.id for x in values}) != len(values):
                raise ValueError("Use distinct original existing Core resource identities")
        return self


class JanusCore(Model):
    id: str = Field(min_length=1, max_length=100)
    controller: Snowflake
    frame_owner: ActorRef
    frame_instance: str = Field(min_length=1)
    source_setup: str = Field(min_length=1)
    proposed_event: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    judge: Snowflake
    appointment: str = Field(min_length=1)
    source_facts: CoreFacts
    body_vessel: str = Field(min_length=1)
    girl_assets: tuple[HarpyAsset, ...]
    heat: int = Field(ge=0)
    identities: tuple[HarpyIdentity, ...]
    tags: tuple[HarpyTag, ...]
    baseline_tags: dict[str, str]
    control_tags: dict[str, str] = Field(default_factory=dict, exclude_if=lambda value: not value)
    attached: bool = True
    linked: bool = True
    alive: bool = True
    revealed: bool = False
    exposed: bool = False
    cell: Cell | None = None
    frame_cell: Cell | None = None
    physical_source_event: str | None = None
    condition_event: str | None = None
    frame_shutdown: bool = False
    body_incapacitated: bool = False
    subsumed: bool = False
    vitals_active: bool = True
    custody: Literal["core", "free", "captured", "transported"] = "core"
    custodian: ActorRef | None = None
    custody_event: str | None = None
    blocked_plays: tuple[BlockedPlay, ...] = ()
    takeover_event: str | None = None
    state_event: str = Field(min_length=1)

    @property
    def name(self) -> str:
        return "Harpy Core"

    @property
    def original_frame(self) -> str:
        return "JANUS-B"

    @property
    def core_frame_owner(self) -> ActorRef:
        return self.frame_owner

    @property
    def core_frame_instance(self) -> str:
        return self.frame_instance

    @model_validator(mode="after")
    def actual_attachment(self) -> "JanusCore":
        if self.frame_owner.kind != "pilot" or self.frame_owner.incarnation is None:
            raise ValueError("The original JANUS owner and physical Frame remain source-bound")
        if set(self.baseline_tags) != {x[0] for x in BASELINE}:
            raise ValueError("Preserve the actual four original printed Tag identities")
        if (
            len(set(self.baseline_tags.values())) != len(BASELINE)
            or not set(self.control_tags) <= {x[0] for x in BASELINE}
            or len(set(self.control_tags.values())) != len(self.control_tags)
        ):
            raise ValueError("Use distinct actual control Tag identities and printed meanings")
        for values in (self.girl_assets, self.identities, self.tags):
            if len({x.id for x in values}) != len(values):
                raise ValueError("Core resources retain actual distinct original identities")
        if any(x.family != "girl" for x in self.girl_assets):
            raise ValueError("The same JANUS Frame Assets stay at their single existing authority")
        if self.attached and self.custody != "core":
            raise ValueError("Actual spinal attachment remains inside the original Frame")
        return self


class CoreSetup(Model):
    id: str = Field(min_length=1)
    owner: ActorRef
    frame: str = Field(min_length=1)
    controller: Snowflake
    judge: Snowflake
    appointment: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    phase: Literal["controller", "review", "admitted", "declined", "withdrawn"] = "controller"
    facts: CoreFacts | None = None
    proposed_event: str | None = None
    review_event: str | None = None
    review: str = Field(default="", max_length=1200)
    core: ActorRef | None = None

    @model_validator(mode="after")
    def original_review(self) -> "CoreSetup":
        if self.owner.kind != "pilot" or self.owner.incarnation is None:
            raise ValueError("Set up the actual original JANUS Pilot's distinct Core")
        if (self.facts is None) != (self.proposed_event is None):
            raise ValueError("The original controller's actual facts need their own source")
        if self.phase in ("review", "admitted") and self.facts is None:
            raise ValueError("Review actual proposed facts before admitting the Core")
        if self.phase == "admitted" and (self.core is None or self.review_event is None):
            raise ValueError("Actual Core admission needs the reviewed source and original actor")
        return self
