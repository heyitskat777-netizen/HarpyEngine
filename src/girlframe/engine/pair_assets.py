"""Pair-authored names only. The Bonded owner supplies all descriptions."""

from dataclasses import dataclass
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from girlframe.engine.creation_catalog import CATALOG


class PairNames(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    names: tuple[str, ...] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def legal(self) -> Self:
        if len(set(self.names)) != 2 or not set(self.names) <= set(CATALOG["BONDED"]["assets"]):
            raise ValueError("Choose exactly two distinct Bonded Girl Assets")
        return self


@dataclass(frozen=True)
class PairChoice:
    bond_id: str
    bond_revision: int
    revision: int
    names: tuple[str, ...]

    @property
    def token(self) -> str:
        return f"{self.bond_id}:{self.bond_revision}:{self.revision}"
