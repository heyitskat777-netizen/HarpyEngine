"""Bounded mission briefing input, untrusted proposal, and provider contract."""

from typing import Annotated, Literal, Protocol, Self

from pydantic import AfterValidator, Field, model_validator

from girlframe.ai.provider import MAX_OUTPUT_TOKENS as MAX_OUTPUT_TOKENS
from girlframe.ai.provider import ProviderError, ProviderUsage
from girlframe.engine.campaign_opening import Difficulty
from girlframe.engine.m2 import Model
from girlframe.engine.m3_missions import MissionTerms
from girlframe.scenes.campaign_time import Identity, nonblank
from girlframe.scenes.canon import FactRefs, Statement

BriefingProviderError = ProviderError
PROMPT_VERSION = "mission-briefing-v2"
Objective = Annotated[str, Field(max_length=1200), AfterValidator(nonblank)]
Obstacle = Annotated[str, Field(max_length=300), AfterValidator(nonblank)]


class BriefingPolicy(Model):
    model: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
    data_processing_approved: Literal[True]
    reserved_microusd_per_call: int = Field(gt=0, le=1_000_000)
    hourly_budget_microusd: int = Field(gt=0, le=100_000_000)
    daily_budget_microusd: int = Field(gt=0, le=100_000_000)

    @model_validator(mode="after")
    def ordered_limits(self) -> Self:
        if (
            not self.reserved_microusd_per_call
            <= self.hourly_budget_microusd
            <= self.daily_budget_microusd
        ):
            raise ValueError(
                "Allow at least one reserved call within the hourly and daily budgets."
            )
        return self


class BriefingFact(Model):
    id: Identity
    statement: Statement


class BriefingContext(Model):
    goals: str = Field(min_length=1, max_length=800)
    difficulty: Difficulty
    introductory: bool
    facts: tuple[BriefingFact, ...]

    @property
    def needs_obstacle(self) -> bool:
        return self.difficulty == "hard" and not self.introductory


class DraftText(Model):
    objective: Objective
    hard_stake: Obstacle | None
    fact_ids: FactRefs
    terms: MissionTerms | None = Field(default=None, exclude_if=lambda value: value is None)


class GatewayResult(ProviderUsage):
    proposal: DraftText


class BriefingGateway(Protocol):
    def generate(self, model: str, context: BriefingContext, request_id: str) -> GatewayResult: ...
