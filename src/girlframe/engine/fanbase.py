"""Prince creation choices: book PDF 61–62, printed 59–60; sheet PDF 18."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEMOGRAPHICS = ("Young boys", "Young girls", "Older men", "Online shippers", "The anti-political")
QUALITIES = (
    "Sexy",
    "A queer icon",
    "A model pilot",
    "Dangerous",
    "Relatable",
    "A leader",
    "Intelligent",
    "Kind",
    "Girly",
    "Masculine",
)


class Fanbase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    demographics: tuple[str, ...] = Field(default=(), max_length=2)
    demanded: tuple[str, ...] = Field(default=(), max_length=2)
    rejected: tuple[str, ...] = Field(default=(), max_length=2)
    custom_demographic: str = Field(default="", max_length=80)
    custom_quality_1: str = Field(default="", max_length=80)
    custom_quality_2: str = Field(default="", max_length=80)

    @model_validator(mode="after")
    def legal(self) -> Self:
        for choices, allowed in (
            (self.demographics, (*DEMOGRAPHICS, "custom:1")),
            (self.demanded, (*QUALITIES, "custom:1", "custom:2")),
            (self.rejected, (*QUALITIES, "custom:1", "custom:2")),
        ):
            if len(set(choices)) != len(choices) or not set(choices) <= set(allowed):
                raise ValueError("Choose distinct printed options or explicit custom slots")
        if set(self.demanded) & set(self.rejected):
            raise ValueError("A quality cannot be both demanded and rejected")
        # Prevent equivalent labels bypassing distinctness with a custom slot.
        for custom, printed in (
            ((self.custom_demographic,), DEMOGRAPHICS),
            ((self.custom_quality_1, self.custom_quality_2), QUALITIES),
        ):
            names = [x.strip().casefold() for x in custom if x.strip()]
            if len(names) != len(set(names)) or set(names) & {x.casefold() for x in printed}:
                raise ValueError(
                    "Custom labels must be distinct from printed labels and each other"
                )
        return self

    def label(self, value: str, demographic: bool = False) -> str:
        if not value.startswith("custom:"):
            return value
        text = (
            self.custom_demographic if demographic else getattr(self, "custom_quality_" + value[-1])
        )
        return text.strip() or "Custom choice (needs text)"

    @property
    def additional_identities(self) -> tuple[str, ...]:
        return tuple(
            self.label(x, True)
            for x in self.demographics
            if x != "custom:1" or self.custom_demographic.strip()
        )

    def missing(self) -> list[str]:
        missing = []
        for name, label in (
            ("demographics", "two fan demographics"),
            ("demanded", "two demanded fanbase qualities"),
            ("rejected", "two rejected fanbase qualities"),
        ):
            choices = getattr(self, name)
            if len(choices) != 2:
                missing.append(label)
            if any(
                x.startswith("custom:")
                and self.label(x, name == "demographics") == "Custom choice (needs text)"
                for x in choices
            ):
                missing.append("text for selected custom " + name)
        return missing
