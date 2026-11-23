"""The short, facilitator-approved framing of one scene."""

from typing import Annotated

from pydantic import AfterValidator, Field, model_validator

from girlframe.ai.contracts import Contract
from girlframe.scenes.campaign_time import Position, nonblank

LocationLabel = Annotated[str, Field(max_length=120), AfterValidator(nonblank)]


class OpeningDraft(Contract):
    location: LocationLabel
    intro: str = Field(max_length=600)
    details: tuple[str, ...] = Field(max_length=2)
    off_duty: bool | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def has_framing(self) -> "OpeningDraft":
        if not self.intro.strip() and not self.details:
            raise ValueError("Enter a short introduction or keep an approved scene detail.")
        if len(set(self.details)) != len(self.details):
            raise ValueError("Choose each scene detail only once.")
        return self


class OpeningDetail(Contract):
    id: str
    text: str


class SceneOpening(Contract):
    receipt: str
    location: LocationLabel
    position: Position | None
    intro: str
    details: tuple[OpeningDetail, ...]
    off_duty: bool = Field(default=False, exclude_if=lambda value: not value)
