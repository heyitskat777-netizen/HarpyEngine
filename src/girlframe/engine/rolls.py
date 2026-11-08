"""Raw dice primitives only: no official Play, modifiers, tier or consequences."""

import secrets
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

Face = Annotated[int, Field(strict=True, ge=1, le=6)]


class DiceSource(Protocol):
    def roll(self) -> tuple[int, int]: ...


class OsDice:
    def roll(self) -> tuple[int, int]:
        return secrets.randbelow(6) + 1, secrets.randbelow(6) + 1


class D6Source(Protocol):
    def roll_d6(self) -> int: ...


class OsD6:
    def roll_d6(self) -> int:
        return secrets.randbelow(6) + 1


class IndexSource(Protocol):
    def choose(self, size: int) -> int: ...


class OsIndex:
    def choose(self, size: int) -> int:
        if type(size) is not int or size < 1:
            raise ValueError("Choose from an actual nonempty population")
        return secrets.randbelow(size)


class RollReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str
    campaign_id: str
    event_id: str
    actor_id: str
    character_id: str
    callsign: str
    faces: tuple[Face, Face]
    total: Annotated[int, Field(ge=2, le=12)]
    rolled_utc: str
    revision: Annotated[int, Field(ge=1)]
    kind: Literal["raw_2d6_test"] = "raw_2d6_test"
    visibility: Literal["private", "campaign"]
    rng_source: Literal["os", "test_injected"]
    idempotency_key: str

    @model_validator(mode="after")
    def summed(self) -> "RollReceipt":
        if sum(self.faces) != self.total:
            raise ValueError("Dice total must equal recorded faces")
        return self

    def contract(self) -> dict[str, object]:
        """Illustrative handoff wire contract; callers must still authorize this receipt."""
        return {
            "roll_id": self.id,
            "campaign_id": self.campaign_id,
            "event_id": self.event_id,
            "kind": "2d6",
            "faces": list(self.faces),
            "modifiers": [],
            "modifier_total": 0,
            "total": self.total,
            "rolled_utc": self.rolled_utc,
            "rng_source": self.rng_source,
            "idempotency_key": self.idempotency_key,
            "play_id": None,
            "acting_character_id": self.character_id,
            "state": "rolled",
        }
