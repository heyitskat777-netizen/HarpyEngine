"""Actual combat declarations and source-owned effects; no synthetic combatants or hit points."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model

Play = Literal["all_out_assault", "go_for_the_core"]
Category = Literal["pilot", "harpy", "gorgon", "npc", "handler"]
Counter = Literal["damage_attacker_asset", "own_play", "helpless", "die_handler_play"]
COUNTERS: tuple[Counter, ...] = (
    "damage_attacker_asset",
    "own_play",
    "helpless",
    "die_handler_play",
)


class Declaration(Model):
    play: Play
    actor: ActorRef
    target: ActorRef
    attacking_asset: str = Field(min_length=1, max_length=180)
    target_asset: str | None = Field(default=None, min_length=1, max_length=180)
    actor_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def actual_combatants(self) -> "Declaration":
        if self.actor == self.target or not self.account.strip():
            raise ValueError("Declare two distinct actual combatants and the actual opening")
        if (self.play == "all_out_assault") != (self.target_asset is not None):
            raise ValueError(
                "All Out Assault names its actual opposing Asset; Core names its vitals"
            )
        return self


class Defense(Model):
    target: ActorRef
    kind: Literal["item", "capability", "cover"]
    source_id: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)


class Context(Model):
    id: str = Field(min_length=1)
    scene: str = Field(min_length=1)
    declaration: Declaration
    owner: Snowflake
    adjudicator: Snowflake
    appointment: str = Field(min_length=1)
    proposed_event: str = Field(min_length=1)
    state: Literal["proposed", "confirmed", "withdrawn"] = "proposed"
    confirmed_event: str | None = None
    opening: bool = False
    reach: bool = False
    outside_permission: bool = False
    indirect: bool = False
    evidence: str = Field(default="", max_length=1200)
    cast_revision: int = Field(ge=1)
    actor_position: str | None = None
    target_position: str | None = None
    core_source: str | None = None
    defense: Defense | None = None
    source_action: str | None = None
    source_choice: str | None = None
    source_work: str | None = Field(default=None, exclude_if=lambda value: value is None)
    source_author: Snowflake | None = Field(default=None, exclude_if=lambda value: value is None)
    dormant_awakened: bool = False
    dormant_close: bool = False
    judge_actor: ActorRef | None = None
    judge_controller: Snowflake | None = None
    judge_source: str | None = None
    core_capability_confirmed: bool = False
    actor_outside_frame: bool | None = None
    target_outside_frame: bool | None = None

    @model_validator(mode="after")
    def actual_facts(self) -> "Context":
        if self.judge_actor is not None and (
            self.judge_actor.kind != "npc"
            or self.judge_controller is None
            or self.judge_source is None
        ):
            raise ValueError(
                "A selected Director judge needs its actual NPC, controller and role source"
            )
        if self.judge_actor is None and self.judge_source is not None:
            raise ValueError(
                "An ordinary procedural GM does not invent a Director adjudication source"
            )
        if self.dormant_close and not self.dormant_awakened:
            raise ValueError(
                "Use the independent close-contact Dormant Play when no awakening occurs"
            )
        if (self.source_action is None) != (self.source_choice is None):
            raise ValueError("A counter preserves its actual parent and source choice together")
        if self.source_author is not None and not (
            self.source_action and self.source_choice and self.source_work
        ):
            raise ValueError(
                "A directed declaration retains its complete original authority source"
            )
        if self.declaration.actor.kind == "pilot" and self.owner != int(
            self.declaration.actor.entity
        ):
            raise ValueError("The original acting Girl owns her actual declaration")
        if self.state == "confirmed" and (
            not self.confirmed_event
            or not self.opening
            or not self.reach
            or not self.evidence.strip()
        ):
            raise ValueError("The actual adjudicator confirms real opening/reach facts before dice")
        return self


class FrameExposure(Model):
    owner: ActorRef
    frame_instance: str = Field(min_length=1)
    opponent: ActorRef | None = None
    source_event: str = Field(min_length=1)
    willing: bool = False
    tag: str | None = None
    scene: str | None = Field(default=None, min_length=1, exclude_if=lambda value: value is None)
    intense: bool = False
    girl_assets: bool = False
    identities: bool = False
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def printed_conditions(self) -> "FrameExposure":
        if not self.account.strip() or (
            not self.willing
            and (
                self.opponent is None
                or sum((self.tag is not None, self.intense, self.girl_assets, self.identities)) < 2
            )
        ):
            raise ValueError(
                "Expose one actual Frame willingly or through two actual source conditions"
            )
        return self


class Required(Model):
    kind: Literal[
        "defeat",
        "harpy_defeat",
        "npc_damage",
        "handler_damage",
        "handler_helpless",
        "director_damage",
        "director_helpless",
        "handler_play",
        "counter_play",
        "collateral",
        "dormant_void",
        "aggressive_damage",
        "sprite_intercept",
    ]
    target: ActorRef
    opponent: ActorRef | None = None
    asset: str | None = None
    source_pdf: int = Field(ge=1)
    details: dict[str, str] = Field(default_factory=dict)


class Applied(Model):
    """A typed summary, while actual effects remain in the one canonical GameState."""

    target: ActorRef
    effect: str = Field(min_length=1)
    event: str = Field(min_length=1)
    asset: str | None = None


class NpcDamage(Model):
    id: str = Field(min_length=1)
    target: ActorRef
    attacker: ActorRef | None = None
    chooser: Snowflake
    source_action: str | None = None
    source_work: str | None = None
    source_event: str = Field(min_length=1)
    asset: str | None = None
    state: Literal["pending", "resolved"] = "pending"
    effect: Literal["injure_tag", "take_item", "move", "advantage", "kill"] | None = None
    effect_event: str | None = None

    @model_validator(mode="after")
    def actual_npc(self) -> "NpcDamage":
        if self.target.kind != "npc" or self.target == self.attacker:
            raise ValueError("NPC Asset replacement targets the actual distinct human NPC")
        if self.source_action is None and self.source_work is None:
            raise ValueError("NPC damage needs its actual source action or effect grant")
        if self.state == "resolved" and (self.effect is None or not self.effect_event):
            raise ValueError("Resolve the NPC through a real printed consequence")
        return self
