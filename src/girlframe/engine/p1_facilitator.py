"""Owned human adjudication requests; a ruling alone never changes fictional resources."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m3_actor_state import Model

KIND = "facilitator_request"


class Recipient(Model):
    kind: Literal["user", "role"]
    id: int = Field(gt=0)
    event: str


class Request(Model):
    id: str
    revision: int = Field(ge=1)
    requester: int = Field(gt=0)
    channel: int = Field(gt=0)
    rule: str
    source_kind: Literal["action", "work", "scene"]
    source: str
    source_revision: int = Field(ge=1)
    state_revision: int = Field(ge=0)
    source_actor: str | None = None
    receipt: str | None = None
    mandatory: bool
    reason: str = Field(min_length=1, max_length=1200)
    shared: bool = False
    recipient: Recipient | None = None
    status: Literal[
        "configuration_required",
        "awaiting_ruling",
        "awaiting_owned_effect",
        "adapter_blocked",
        "resolved",
        "declined",
    ]
    ruling: str = Field(default="", max_length=1200)
    adapter: Literal["existing_source", "blocked", "fiction_only"] = "blocked"
    ruling_by: int | None = None
    resolution_event: str | None = None
