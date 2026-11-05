"""Original televised combat participants and actual source-owned attendance."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler

RULE = "strain.budget.high.4.1"


class Fight(Model):
    id: str
    source_work: str
    source_event: str
    period: str
    handler: ActorRef
    people: tuple[ActorRef, ActorRef]
    scene: str
    channel: int = Field(ge=1)
    account: str = Field(min_length=1, max_length=2400)
    attended: tuple[ActorRef, ...] = ()
    phase: Literal["attendance", "fighting", "complete"] = "attendance"
    started_event: str | None = None
    ended_event: str | None = None
    actions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def original_participants(self) -> "Fight":
        if (
            self.handler.kind != "handler"
            or len(set(self.people)) != 2
            or any(x.kind != "pilot" for x in self.people)
            or len(set(self.attended)) != len(self.attended)
            or not set(self.attended) <= set(self.people)
            or (self.phase != "attendance") != bool(self.started_event)
            or self.phase != "attendance"
            and set(self.attended) != set(self.people)
            or (self.phase == "complete") != bool(self.ended_event)
            or self.phase == "complete"
            and not self.actions
            or len(set(self.actions)) != len(self.actions)
        ):
            raise ValueError("Preserve actual original attendance, opposing Plays and ending")
        return self


def fights(state: GameState) -> tuple[Fight, ...]:
    return tuple(
        Fight.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "budget_fight"
    )


def get(state: GameState, identity: str) -> Fight:
    value = next((x for x in fights(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Open the original televised fight")
    return value


def put(state: GameState, value: Fight) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == "budget_fight" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="budget_fight", id=value.id, body=value.model_dump_json()))


def create(
    state: GameState,
    work: str,
    period: str,
    event: str,
    scene: str,
    channel: int,
    people: tuple[int, ...],
    account: str,
) -> GameState:
    handler = active_handler(state)
    if (
        handler is None
        or len(set(people)) != 2
        or len(people) != 2
        or not set(people) <= set(state.order)
        or any(x.source_work == work for x in fights(state))
    ):
        raise ValueError("Choose two distinct actual current Girls for this new fight source")
    changed = GameState.model_validate_json(state.model_dump_json())
    put(
        changed,
        Fight(
            id=work + ":fight",
            source_work=work,
            source_event=event,
            period=period,
            handler=handler,
            people=(current_ref(state, people[0]), current_ref(state, people[1])),
            scene=scene,
            channel=channel,
            account=account,
        ),
    )
    return changed
