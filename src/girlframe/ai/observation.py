"""Scene observation contracts for synthetic and reviewed Activity modes."""

import re
from typing import Literal

from pydantic import Field, model_validator

from girlframe.ai.activity import CommandKey
from girlframe.ai.contracts import Contract, WireSnowflake
from girlframe.engine.m3_actor_state import ActorRef


class ObservationPolicy(Contract):
    mode: Literal["off", "shadow"] = "off"
    scope: Literal["synthetic_only", "reviewed_activity_trial"] = "synthetic_only"
    retention_ref: Literal["synthetic-fixture-v1", "reviewed-activity-trial-v1"] = (
        "synthetic-fixture-v1"
    )
    quiet_seconds: int = Field(default=120, ge=1, le=3600)
    batch_threshold: int = Field(default=20, ge=1, le=100)
    max_age_seconds: int = Field(default=600, ge=1, le=3600)
    min_interval_seconds: int = Field(default=120, ge=1, le=3600)


class SceneTurn(Contract):
    source_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)


class AppendSceneInput(Contract):
    schema_version: Literal[1] = 1
    command_key: CommandKey
    expected_scene_revision: int = Field(ge=1)
    speaker: Literal["pilot", "handler"]
    text: str = Field(min_length=1, max_length=1000)
    classification: Literal["ic", "ooc"] = "ic"
    fictional_channel: Literal["scene", "private", "comms", "mixed", "unclassified"] = Field(
        default="scene", exclude_if=lambda x: x == "scene"
    )
    source_id: str | None = Field(default=None, min_length=1, max_length=100)
    expected_source_revision: int = Field(default=0, ge=0)
    covers_turn: SceneTurn | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def edit_revision(self) -> "AppendSceneInput":
        if (self.source_id is None) != (self.expected_source_revision == 0):
            raise ValueError("An edit requires its actual source and expected source revision")
        if self.source_id is not None and self.classification != "ic":
            raise ValueError("Classification changes require a future redaction workflow")
        if self.covers_turn and (
            self.classification != "ic"
            or self.speaker != "pilot"
            or self.fictional_channel != "comms"
        ):
            raise ValueError("A Pilot takes up another turn through spoken comms.")
        return self


class Observation(Contract):
    schema_version: Literal[1] = 1
    sequence: int = Field(ge=1)
    generation: int = Field(ge=1)
    source_id: str
    source_revision: int = Field(ge=1)
    kind: Literal["message", "completed_play"]
    author_id: WireSnowflake
    actor: ActorRef
    audience_ids: tuple[WireSnowflake, ...]
    accepted_at: float
    cast_controllers: dict[str, int] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    text: str | None = Field(default=None, max_length=1000)
    fictional_channel: Literal["scene", "private", "comms", "mixed", "unclassified"] = Field(
        default="scene", exclude_if=lambda x: x == "scene"
    )
    covers_turn: SceneTurn | None = Field(default=None, exclude_if=lambda value: value is None)
    action_id: str | None = None
    receipt_id: str | None = None
    event_id: str | None = None
    knowledge: Literal["observed_reference_only"] = "observed_reference_only"

    @property
    def gm_addressed(self) -> bool:
        return self.kind == "message" and bool(re.match(r"^\s*gm\s*[:,]", self.text or "", re.I))


class SceneObservationState(Contract):
    policy: ObservationPolicy = Field(default_factory=ObservationPolicy)
    policy_revision: int = 0
    consents: dict[str, int] = Field(default_factory=dict)
    consent_generation: int = 0
    generation: int = 0
    sequence: int = 0
    reviewed_sequence: int = 0
    last_input_at: float | None = None
    last_review_at: float | None = None
    activity_epoch: int | None = None
    activity_audience: tuple[int, ...] = ()
    capture_floor: int = 0
    native_cursor: int = 0


class InputResult(Contract):
    schema_version: Literal[1] = 1
    scene_id: str
    source_id: str | None = None
    source_revision: int = 0
    sequence: int = 0
    generation: int
    status: Literal["accepted", "ignored_ooc"] = "accepted"


class ReviewBatch(Contract):
    schema_version: Literal[1] = 1
    scope: Literal["synthetic_scene_reference_only"] = "synthetic_scene_reference_only"
    campaign_id: str
    scene_id: str
    run_id: str
    lease_token: str
    lease_until: float
    generation: int
    scene_revision: int
    policy_revision: int
    consent_generation: int
    canonical_revision: int
    binding_event: str
    frontier: int
    guard_digest: str
    reason: Literal["quiet", "size", "age", "completed_play"]
    inputs: tuple[Observation, ...] = Field(max_length=20)
    recent_tail: tuple[Observation, ...] = Field(default=(), max_length=3)
    publication: Literal["blocked"] = "blocked"


class ReviewCompletion(Contract):
    schema_version: Literal[1] = 1
    run_id: str
    status: Literal["reviewed", "failed"]
    frontier: int
    publication: Literal["blocked"] = "blocked"


class ObservationStatus(Contract):
    schema_version: Literal[1] = 1
    scene_id: str
    scene_revision: int
    policy_revision: int
    mode: Literal["off", "shadow"]
    consented: bool
    phase: Literal["off", "awaiting_consent", "paused", "idle", "waiting", "ready", "running"]
    pending_messages: int
    pending_triggers: int
    generation: int
    reviewed_sequence: int
    next_review_at: float | None = None


def review_eligibility(
    policy: ObservationPolicy,
    *,
    now: float,
    messages: int,
    triggers: int,
    oldest_at: float | None,
    latest_at: float | None,
    last_review_at: float | None,
) -> tuple[Literal["quiet", "size", "age", "completed_play"] | None, float | None]:
    """Eligibility permits observation only; never permits optional publication."""
    if policy.mode == "off":
        return None, None
    if triggers:
        return "completed_play", now
    if not messages or oldest_at is None or latest_at is None:
        return None, None
    interval = last_review_at + policy.min_interval_seconds if last_review_at is not None else now
    quiet = latest_at + policy.quiet_seconds
    age = oldest_at + policy.max_age_seconds
    next_at = max(interval, min(now if messages >= policy.batch_threshold else quiet, age))
    if now < next_at:
        return None, next_at
    if messages >= policy.batch_threshold:
        return "size", next_at
    return ("quiet" if now >= quiet else "age"), next_at
