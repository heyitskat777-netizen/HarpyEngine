"""Source Girl-rules Handler corruption uses actual held mechanical Assets only."""

from typing import Literal

from pydantic import Field

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model


class ExistingAsset(Model):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1200)
    evidence: str = Field(min_length=1, max_length=1200)
    damaged: bool = False
    weapon: bool = False
    proposal_event: str = Field(min_length=1)
    state: Literal["proposed", "accepted", "rejected"] = "proposed"
    review_event: str | None = None
    review: str = Field(default="", max_length=1200)
    item: str | None = None
    asset_json: str | None = None


class HandlerGirlVoid(Model):
    id: str = Field(min_length=1)
    work: str = Field(min_length=1)
    actor: ActorRef
    body: ActorRef
    controller: Snowflake
    caster: ActorRef
    caster_controller: Snowflake
    context_source: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    appointment: str = Field(min_length=1)
    judge: Snowflake
    judge_actor: ActorRef | None = None
    phase: Literal["asset", "facts", "review", "rewrite", "complete", "allure", "ended"]
    proposals: tuple[ExistingAsset, ...] = ()
    asset: str | None = None
    asset_before: str | None = None
    asset_choice_event: str | None = None
    rewrite: str = Field(default="", max_length=1200)
    corruption_event: str | None = None
    allure: bool = False
    # Handler Girl-rules provide no assigned Frame. A foreign occupied Frame is not one.
    assigned_frame: ActorRef | None = None
    ended_event: str | None = None
