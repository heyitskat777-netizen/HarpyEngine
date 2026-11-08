"""One actual neural link owns its printed choices and temporary mental-Asset provenance."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

BatteryChoice = Literal["heat", "bond", "identities", "cognition", "offset", "question"]
MentalChoice = Literal["cognition", "offset"]
MENTAL_NAMES = {"cognition": "Harpy Cognition", "offset": "Offset Emotional Load"}


class BatteryAsset(Model):
    link: str = Field(min_length=1, max_length=80)
    choice: MentalChoice

    @property
    def asset_id(self) -> str:
        return "battery:" + self.link + ":" + self.choice

    @property
    def name(self) -> str:
        return MENTAL_NAMES[self.choice]


class BorrowedAsset(Model):
    source: BatteryAsset
    event: str = Field(min_length=1)


class BrainMessage(Model):
    actor: ActorRef
    controller: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)


class BatteryLink(Model):
    id: str = Field(min_length=1, max_length=80)
    caster: ActorRef
    caster_controller: int = Field(gt=0)
    caster_frame_owner: ActorRef
    caster_frame: str = Field(min_length=1)
    battery: ActorRef
    battery_controller: int = Field(gt=0)
    core_source: str | None = None
    connection: str | None = Field(default=None, exclude_if=lambda value: value is None)
    source_action: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    source_cast: SceneCast
    source_tags: tuple[str, ...]
    universal: bool
    tier: Literal["low", "mid", "high"] | None = None
    selected: tuple[BatteryChoice, ...] = ()
    borrowed: tuple[BorrowedAsset, ...] = ()
    erasure_before_tags: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)
    erased_tag: str | None = None
    erased_absent: bool = False
    erasure_event: str | None = None
    effects_event: str | None = None
    question: str = Field(default="", max_length=1200)
    answer: str = Field(default="", max_length=1200)
    answer_event: str | None = None
    target_tag: str | None = Field(default=None, max_length=120)
    phase: Literal["choosing", "question", "connected", "unplugged", "ended"] = "choosing"
    end_event: str | None = None
    end_reason: str = Field(default="", max_length=1200)
    frame_takeover: str | None = None
    messages: tuple[BrainMessage, ...] = Field(default=(), exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def actual_source(self) -> "BatteryLink":
        if self.caster == self.battery:
            raise ValueError("Living Battery connects to an actual distinct person's spinal cord")
        if len(set(self.source_tags)) != len(self.source_tags) or len(set(self.selected)) != len(
            self.selected
        ):
            raise ValueError("Count each actual Tag and choose each printed option only once")
        if any(x.source.link != self.id for x in self.borrowed) or len(
            {x.source.choice for x in self.borrowed}
        ) != len(self.borrowed):
            raise ValueError("Each actual mental Asset belongs once to this source link/choice")
        if self.effects_event is not None and (
            self.tier is None or len(self.selected) != {"low": 1, "mid": 2, "high": 4}[self.tier]
        ):
            raise ValueError("Apply exactly this actual final result's printed choices")
        if self.answer_event and (not self.question.strip() or not self.answer.strip()):
            raise ValueError("A private brain answer needs the actual question and human source")
        if (self.phase in ("unplugged", "ended")) != (self.end_event is not None):
            raise ValueError("A link ends only through actual unplug or source-proved interruption")
        return self
