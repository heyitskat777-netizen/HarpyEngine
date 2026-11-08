"""Actual interruption evidence; no inferred old answers, dice or prior states."""

import hashlib
import json
from typing import Any, Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import Model


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class SavedChoice(Model):
    id: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    revision: int = Field(ge=1)
    state: Literal["pending", "submitted"]
    body_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Interruption(Model):
    version: Literal[1] = 1
    root: str = Field(min_length=1)
    event: str = Field(min_length=1)
    registry: str = Field(pattern=r"^[a-f0-9]{64}$")
    nodes: tuple[str, ...] = Field(min_length=1)
    known_roll: bool
    cancellable: bool
    state: Literal["acquiring", "ready_to_roll", "tag_window", "awaiting_choices"]
    body_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    choices: tuple[SavedChoice, ...] = ()

    @model_validator(mode="after")
    def actual_chain(self) -> "Interruption":
        if self.root not in self.nodes or len(set(self.nodes)) != len(self.nodes):
            raise ValueError("An interruption retains its actual distinct root and chain")
        if self.known_roll and self.cancellable:
            raise ValueError("A known roll cannot be cancelled")
        if len({x.id for x in self.choices}) != len(self.choices):
            raise ValueError("An interruption preserves distinct original pending choices")
        return self
