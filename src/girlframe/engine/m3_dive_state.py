"""Human-owned Dive Deep effects and exact table proposals."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import Model
from girlframe.engine.m3_sup import Growth

Manifestation = Literal["brain", "bones", "flesh", "abstract"]


class NpcVoid(Model):
    npc: str = Field(min_length=1, max_length=100)
    manifestation: Manifestation


class Effect(Model):
    account: str = Field(min_length=1, max_length=1200)
    asset: str | None = None
    growth: Growth | None = Field(default=None, exclude_if=lambda value: value is None)
    description: str = Field(default="", max_length=1200)
    identity: str | None = None
    question: str = Field(default="", max_length=1200)
    replacement: str = Field(default="", max_length=120)
    npcs: tuple[NpcVoid, ...] = ()

    @model_validator(mode="after")
    def actual(self) -> "Effect":
        if not self.account.strip() or len({x.npc for x in self.npcs}) != len(self.npcs):
            raise ValueError("Describe the actual source effect and each distinct nearby NPC")
        return self
