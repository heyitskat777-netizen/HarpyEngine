"""Source-owned battlefield maneuvers; Conversation effects do not invent map cells."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from girlframe.engine.m2 import MANEUVERS, ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef, ActorView


class Maneuver(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    kind: Literal[
        "pin", "advance", "drive_back", "reposition", "cover", "shatter", "protect", "lure"
    ]
    actor: ActorRef
    opponent: ActorRef
    asset: str = Field(min_length=1)
    circumstances: str = Field(min_length=1, max_length=1200)
    source_action: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    scene: str = Field(min_length=1)


def select(
    actor: ActorView,
    level: str,
    answer: ChoiceAnswer,
    *,
    assault_extra: bool = False,
    casualty_extra: bool = False,
    substitute_damage: bool = False,
) -> tuple[dict[str, str], str | None]:
    """Exact human choices, one real owned Asset per maneuver, one optional Harpy extra."""
    if answer.flag is not None or answer.number is not None or answer.member is not None:
        raise ValueError("Choose maneuvers, their actual Assets and the resulting circumstances")
    harpy = actor.ref.kind == "external_pilot" and actor.girl == "harpy"
    if assault_extra:
        if not harpy and not (casualty_extra and actor.ref.kind == "pilot"):
            raise ValueError("Use the actual Harpy or source-owned Casualty extra maneuver")
        minimum, maximum = 0, 1
    else:
        minimum = {"low": 1, "mid": 2, "high": 3}[level]
        maximum = minimum + int(harpy)
    if not minimum <= len(answer.options) <= maximum or not set(answer.options) <= set(MANEUVERS):
        raise ValueError("Choose the exact tier's distinct maneuvers, plus any owned Harpy extra")
    if set(answer.fields) != set(answer.options):
        raise ValueError("Choose one actual Asset for every selected maneuver")
    usable = {asset.id for asset in actor.assets if not asset.damaged}
    if not set(answer.fields.values()) <= usable:
        raise ValueError("Use the actual acting body's currently undamaged owned Assets")
    if answer.options and not answer.text.strip():
        raise ValueError("Describe the actual battlefield circumstances these maneuvers create")
    damage = not assault_extra and level in ("low", "high")
    if substitute_damage:
        if not damage or answer.denied:
            raise ValueError("Substitute only the actual Engage Asset damage, never both costs")
        return dict(answer.fields), None
    if damage:
        if len(answer.denied) != 1 or answer.denied[0] not in answer.fields.values():
            raise ValueError("Damage exactly one of the actual Assets used for these maneuvers")
    elif answer.denied:
        raise ValueError("This choice does not add Engage Asset damage")
    return dict(answer.fields), answer.denied[0] if damage else None
