"""The actual performances required by the Dogrunner's options."""

from typing import TYPE_CHECKING, Literal

from girlframe.engine.m3_actor_state import Model
from girlframe.engine.m3_handler_play_state import DRESS_CONTACTS, DRESS_STEPS, Effect

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState

DELEGATE_OPTIONS = (
    tuple(
        option
        for option in DRESS_STEPS
        if option[0]
        in (
            "competency",
            "appearance",
            "identity",
            "dog",
        )
    )
    + DRESS_CONTACTS
)


class Performance(Model):
    grant: str
    effect: Effect
    event: str
    phase: Literal["delegate", "contact", "ready", "declined"]
    delegate_owner: int | None = None
    delegate_choice: str | None = None
    delegate_account: str | None = None
    contact_account: str | None = None


def performances(state: "GameState") -> dict[str, Performance]:
    result = {}
    for fact in state.facts:
        if fact.get("kind") == "dogrunner_dress_performance":
            record = Performance.model_validate_json(fact["body"])
            result[record.grant] = record
    return result


def save(state: "GameState", record: Performance) -> None:
    state.facts.append(dict(kind="dogrunner_dress_performance", body=record.model_dump_json()))
