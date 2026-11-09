"""Source-owned Mockingbird interactions and their lasting mechanical effects."""

from typing import Literal

from pydantic import Field

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model

Capability = Literal[
    "words", "sentences", "body_language", "expressions", "eye_contact", "deception"
]
CAPABILITIES: tuple[Capability, ...] = (
    "words",
    "sentences",
    "body_language",
    "expressions",
    "eye_contact",
    "deception",
)
PERSON = "mockingbird_person"
SEX = "mockingbird_sex"


class Party(Model):
    actor: ActorRef
    controller: Snowflake
    label: str = Field(default="", max_length=120, exclude_if=lambda value: not value)
    decision: Literal["pending", "accepted", "declined"] = "pending"
    event: str | None = None


class Trigger(Model):
    learned_sex_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    learned_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    bonded_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    changeling_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    id: str = Field(min_length=1)
    play: Literal["mockingbird_person", "mockingbird_sex"]
    actor: ActorRef
    parties: tuple[Party, ...]
    scene: str = Field(min_length=1)
    channel: Snowflake
    cast_sha256: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    state: Literal["proposed", "ready", "declined", "withdrawn", "started", "complete"]
    action: str | None = None


class Conversation(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    counterparts: tuple[Party, ...]
    action: str
    source_event: str
    allowed: tuple[Capability, ...]
    selected: tuple[Capability, ...] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    unavailable: tuple[Capability, ...]
    low: bool
    tag: str | None = None
    giver: ActorRef | None = None
    proposed_tag: str = Field(default="", max_length=120)
    agreements: tuple[Party, ...] = ()
    released: tuple[ActorRef, ...] = ()
    release_events: tuple[str, ...] = ()
    ended_event: str | None = None


class Starry(Model):
    id: str
    speaker: ActorRef
    holder: ActorRef
    tag: str
    capability: Capability
    source_event: str
    action: str


class Exposure(Model):
    id: str
    source_action: str
    actor: ActorRef
    counterpart: ActorRef
    kind: Literal["teaching", "both_risk", "low_tag"]
    source_event: str
    disclosed_event: str | None = None
    witness: ActorRef | None = None
    tag_event: str | None = None
    account: str = Field(default="", max_length=1200)
    handler: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    handler_controller: Snowflake | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class Discovery(Model):
    id: str
    exposure: str
    source_event: str
    recorder: Snowflake
    witness: ActorRef
    witness_controller: Snowflake
    handler: ActorRef
    handler_controller: Snowflake
    scene: str
    cast_sha256: str
    account: str = Field(min_length=1, max_length=1200)
    revision: int = 1
    phase: Literal["witness", "handler", "resolved", "declined", "ended"] = "witness"
    witness_event: str | None = None
    handler_event: str | None = None
    tag: str | None = None


class CallSession(Model):
    id: str
    source_action: str
    source_choice: str
    source_event: str
    step: int = Field(ge=0)
    actor: ActorRef
    controller: Snowflake
    kind: Literal["guest", "relay"]
    revision: int = Field(default=1, ge=1)
    phase: Literal["select", "invite", "effect", "npc", "table", "threshold", "complete"] = "select"
    guest: ActorRef | None = None
    guest_controller: Snowflake | None = None
    passenger: str | None = None
    table: tuple[Snowflake, ...] = ()
    option: str | None = None
    effect_json: str | None = None
    replies_json: str = "{}"
    proposal_revision: int = 0
    choice_event: str | None = None
    store_void: bool = Field(default=False, exclude_if=lambda value: not value)
    message: str = Field(default="", max_length=1200)
    answer: str = Field(default="", max_length=1200)
    account: str = Field(default="", max_length=1200)
    completed_event: str | None = None


class MockingbirdState(Model):
    triggers: tuple[Trigger, ...] = ()
    conversations: tuple[Conversation, ...] = ()
    starry: tuple[Starry, ...] = ()
    exposures: tuple[Exposure, ...] = ()
    discoveries: tuple[Discovery, ...] = Field(default=(), exclude_if=lambda value: not value)
    calls: tuple[CallSession, ...] = Field(default=(), exclude_if=lambda value: not value)
