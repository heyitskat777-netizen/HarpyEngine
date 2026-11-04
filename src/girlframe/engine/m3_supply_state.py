"""A real random supply-loss assignment, bound to one character and period."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class SupplyLoss(Model):
    id: str = Field(min_length=1)
    period: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    population: tuple[ActorRef, ...] = Field(min_length=1)
    index: int = Field(ge=0)
    rng_source: Literal["os", "test_injected"]
    resource: str = Field(min_length=1, max_length=120)
    amount: Literal[-2] = -2
    action: str | None = None

    @model_validator(mode="after")
    def actual_population(self) -> "SupplyLoss":
        if (
            self.index >= len(self.population)
            or len(set(self.population)) != len(self.population)
            or any(x.kind != "pilot" for x in self.population)
            or not self.resource.strip()
        ):
            raise ValueError("Use one valid uniform index in the actual distinct Pilot population")
        return self

    @property
    def owner(self) -> ActorRef:
        return self.population[self.index]
