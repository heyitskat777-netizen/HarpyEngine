"""Immutable narrative evidence and separately scoped character knowledge."""

from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import Model
from girlframe.engine.m3_missions import MissionTerms
from girlframe.scenes.campaign_time import Identity, Position, nonblank

Statement = Annotated[str, Field(max_length=600), AfterValidator(nonblank)]
FactStatus = Literal["current", "superseded", "needs_review"]
FactRefs = Annotated[tuple[Identity, ...], Field(max_length=10)]


class Moment(Model):
    anchor_id: Identity
    position: Position


class CanonWindow(Moment):
    scene_id: Identity
    scene_revision: int | None = Field(default=None, gt=0, exclude_if=lambda value: value is None)


class ShadowConsent(Model):
    activity_epoch: int
    consent_generation: int


class WorldFact(Model):
    window: CanonWindow
    statement: Statement
    public: bool = False
    supersedes: Identity | None = None
    depends_on: FactRefs = ()
    proposal_id: Identity | None = None
    shadow_consent: ShadowConsent | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class LegacyMessageSource(Model):
    """Decode preserved M4 records written before Activity-only intake."""

    message_id: Snowflake
    channel_id: Snowflake
    author_id: Snowflake


class ActivitySource(Model):
    submission_id: Identity


class Proposal(Model):
    window: CanonWindow
    statement: Statement
    source: ActivitySource | LegacyMessageSource | None = None
    depends_on: FactRefs = ()
    shadow_consent: ShadowConsent | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class BriefingSource(Moment):
    mission_id: Identity
    offer_event_id: Identity


class BriefingApproval(Model):
    handler: Snowflake
    review_id: Identity
    plan: Identity
    game_revision: int = Field(ge=0)
    introductory: bool
    objective: str = Field(min_length=1, max_length=1200)
    hard_stake: str | None = Field(max_length=300)
    terms: MissionTerms | None = Field(default=None, exclude_if=lambda value: value is None)


class BriefingDraft(Model):
    principal: str
    facts: FactRefs
    approval: BriefingApproval | None = Field(default=None, exclude_if=lambda value: value is None)


class KnowledgeGrant(Model):
    window: CanonWindow | None = None
    fact_id: Identity
    recipient: Snowflake
    method: Literal["witnessed", "reported", "briefed", "told"]
    source_grant_id: Identity | None = None
    principal: str | None = None
    briefing: BriefingSource | None = None
    shadow_consent: ShadowConsent | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if (self.method == "witnessed") == (self.source_grant_id is not None):
            raise ValueError("A disclosure must cite what its sender learned.")
        if self.method == "told" and self.principal is None:
            raise ValueError("An NPC lead must identify its original Pilot recipient.")
        if self.method == "briefed":
            if self.briefing is None or self.window is not None or self.principal is None:
                raise ValueError("A briefing grant must cite its offer and recipient.")
        elif self.window is None or self.briefing is not None:
            raise ValueError("A witness or report must occur in a scene.")
        return self

    @property
    def learned_at(self) -> Position:
        if self.briefing is not None:
            return self.briefing.position
        assert self.window is not None
        return self.window.position


class FactView(Model):
    fact_id: Identity
    statement: Statement
    established_at: Position
    status: FactStatus = "current"
    supersedes: Identity | None = None
    depends_on: FactRefs = ()


class KnownFact(Model):
    fact_id: Identity
    statement: Statement
    grant_id: Identity
    method: Literal["witnessed", "reported", "briefed", "told"]
    learned_at: Position
    status: FactStatus = "current"
