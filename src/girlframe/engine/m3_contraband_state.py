"""A private random find and the original Girl's optional Asset decision."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_requisition_state import GirlAsset


class ContrabandFind(Model):
    id: str = Field(min_length=1)
    period: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    base: str = Field(min_length=1)
    population: tuple[ActorRef, ...] = Field(min_length=1)
    index: int = Field(ge=0)
    rng_source: Literal["os", "test_injected"]
    label: str = Field(min_length=1, max_length=120)
    taken: bool | None = None
    choice: GirlAsset | None = None
    asset_id: str | None = None
    response_event: str | None = None
    account: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def actual_find(self) -> "ContrabandFind":
        if (
            self.index >= len(self.population)
            or len(set(self.population)) != len(self.population)
            or any(x.kind != "pilot" for x in self.population)
        ):
            raise ValueError("Use one valid uniform draw among actual distinct original Girls")
        if self.taken is None:
            if (
                self.choice is not None
                or self.asset_id is not None
                or self.response_event is not None
                or self.account
            ):
                raise ValueError("An offered find has no invented owner decision")
        elif not self.response_event or self.response_event == self.source_event:
            raise ValueError("Record the actual distinct owner response event")
        if self.taken is True:
            if self.choice is None or not self.asset_id or not self.account.strip():
                raise ValueError("The owner confirms the actual find and chosen Girl Asset")
        elif self.choice is not None or self.asset_id is not None:
            raise ValueError("An unclaimed find cannot grant an Asset")
        return self

    @property
    def actor(self) -> ActorRef:
        return self.population[self.index]
