"""Source-backed starting choices. This model cannot activate a playable character."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.fanbase import Fanbase
from girlframe.engine.playbooks import canonical_frame, canonical_girl


def official_frame(label: str) -> str:
    # Owner approved this cosmetic alias; no new mechanics are attributed to JANUS-B.
    return "JANUS" if label == "JANUS-B" else label


class AssetChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=700)


class CreationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    girl_playbook: str
    frame_playbook: str
    girl_assets: tuple[AssetChoice, ...] = Field(default=(), max_length=2)
    frame_assets: tuple[AssetChoice, ...] = Field(default=(), max_length=2)
    void_asset: str | None = None
    frame_name: str = Field(default="", max_length=80)
    girl_appearance: str = Field(default="", max_length=700)
    frame_appearance: str = Field(default="", max_length=700)

    dna_basis: str = Field(default="", max_length=300)
    fanbase: Fanbase | None = None

    @field_validator("girl_playbook")
    @classmethod
    def girl(cls, value: str) -> str:
        return canonical_girl(value)

    @field_validator("frame_playbook")
    @classmethod
    def frame(cls, value: str) -> str:
        return canonical_frame(value)

    @model_validator(mode="after")
    def legal_choices(self) -> Self:
        for choices, name in (
            (self.girl_assets, self.girl_playbook),
            (self.frame_assets, official_frame(self.frame_playbook)),
        ):
            names = [choice.name for choice in choices]
            if len(set(names)) != len(names) or not set(names) <= set(CATALOG[name]["assets"]):
                raise ValueError("Choose distinct Assets from the selected playbook")
        if self.girl_playbook == "BONDED" and self.girl_assets:
            raise ValueError("Bonded Girl Assets must be selected by the Pair; workflow pending")
        if self.void_asset is not None and (
            self.girl_playbook != "MOCKINGBIRD"
            or self.void_asset not in {a.name for a in self.girl_assets}
        ):
            raise ValueError("Only a selected Mockingbird Girl Asset can start Void-altered")
        if self.dna_basis and self.girl_playbook != "VATGROWN":
            raise ValueError("DNA basis is a Vatgrown creation choice")
        if self.fanbase is not None and official_frame(self.frame_playbook) != "THE PRINCE":
            raise ValueError("Fanbase is a Prince creation choice")
        return self

    @property
    def identities(self) -> tuple[str, ...]:
        return tuple(CATALOG[self.girl_playbook]["identities"])

    @property
    def intrinsic_frame_assets(self) -> tuple[str, ...]:
        return ("Enormous",) if official_frame(self.frame_playbook) == "WYVERN 0.4" else ()

    def missing(self) -> list[str]:
        missing = []
        if self.girl_playbook == "BONDED":
            missing.append("Pair-owned Girl Asset selection (pending relationship workflow)")
        elif len(self.girl_assets) != 2:
            missing.append("two Girl Assets")
        if len(self.frame_assets) != 2:
            missing.append("two chosen Frame Assets")
        if any(not a.description.strip() for a in self.girl_assets + self.frame_assets):
            missing.append("descriptions for chosen Assets")
        if self.girl_playbook == "MOCKINGBIRD" and self.void_asset is None:
            missing.append("one selected Girl Asset altered by the Void")
        for field, label in (
            (self.frame_name, "Frame name"),
            (self.girl_appearance, "Girl appearance"),
            (self.frame_appearance, "Frame appearance"),
        ):
            if not field.strip():
                missing.append(label)
        if self.girl_playbook == "VATGROWN" and not self.dna_basis.strip():
            missing.append("DNA basis")
        if official_frame(self.frame_playbook) == "THE PRINCE":
            missing.extend((self.fanbase or Fanbase()).missing())
        return missing
