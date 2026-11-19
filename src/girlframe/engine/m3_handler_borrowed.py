"""An original Handler can spend an advancement on a different book's Play."""

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_advocate_alone import RULE as ALONE
from girlframe.engine.m3_frantic_breakdown import RULE as BREAK_DOWN
from girlframe.engine.m3_handler_play_state import DRESS_RULE
from girlframe.engine.m3_handler_state import Playbook

RULE = "handler-advancement.handler-advancement.take-a-play"
PLAYS: dict[str, tuple[Playbook, str]] = {
    DRESS_RULE: ("Dogrunner", "Dress Them Down"),
    BREAK_DOWN: ("Frantic", "Break Down"),
    ALONE: ("Advocate", "Get Them Alone"),
}


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    rule: str = DRESS_RULE
    book: Playbook = "Dogrunner"
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def original_rule(self) -> "Acquisition":
        option = PLAYS.get(self.rule)
        if option is None or option[0] != self.book:
            raise ValueError("Use an actual portable Play and its source Handler book")
        return self


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "borrowed_handler_play"
    )


def put(state: GameState, value: Acquisition) -> None:
    state.facts.append(
        dict(kind="borrowed_handler_play", id=value.id, body=value.model_dump_json())
    )
