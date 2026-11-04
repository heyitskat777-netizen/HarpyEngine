"""Trusted campaign rulings and explicitly scoped M3 release approvals."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Rulings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    provenance: Literal["owner_approved_campaign_ruling"]
    ace_bonus: Literal["current_ace"]
    standard_unpriced_cost: Literal[1]
    extra_repairs: Literal["handler_quote"]
    reprogramming_fallback: Literal["owner_selects_ordinary_slot"]
    punishment_details: Literal["inflictor_selects"]
    failure_dog_overlap: Literal["one_punishment_both_causes"]


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    ruleset: Literal["girlframe-m3-core-1"] = "girlframe-m3-core-1"
    registry_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope: Literal["rules_subset", "core_complete"]
    subsystems: frozenset[
        Literal["missions", "discipline", "economy", "plays", "strain", "world", "playbooks"]
    ]
    reviewer: str = Field(min_length=1, max_length=120)
    reference: str = Field(min_length=1, max_length=240)
