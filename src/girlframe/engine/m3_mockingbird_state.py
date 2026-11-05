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
    decision: Literal["pending", "accepted", "declined"] = "pending"
    event: str | None = None


class Trigger(Model):
    id: str = Field(min_length=1)
    play: Literal["mockingbird_person", "mockingbird_sex"]
    actor: ActorRef
    parties: tuple[Party, ...]
    scene: str = Field(min_length=1)
    channel: Snowflake
    cast_sha256: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    state: Literal["proposed", "ready", "declined", "started", "complete"]
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


class MockingbirdState(Model):
    triggers: tuple[Trigger, ...] = ()
    conversations: tuple[Conversation, ...] = ()
    starry: tuple[Starry, ...] = ()
    exposures: tuple[Exposure, ...] = ()
