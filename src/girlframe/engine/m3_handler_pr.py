"""Actual Foundation media-event activities and factual PR outcomes, separate from awards."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model


class Activity(Model):
    actor: ActorRef
    event: str
    description: str = Field(min_length=1, max_length=1200)
    action: str | None = None


class Event(Model):
    id: str
    host: ActorRef
    appointment: str
    planned_session: str
    plan_event: str
    objective: str = Field(min_length=1, max_length=1200)
    context: str = Field(min_length=1, max_length=1200)
    people: tuple[ActorRef, ...]
    phase: Literal["planned", "conduct", "result", "complete"] = "planned"
    hosting: Activity | None = None
    activities: tuple[Activity, ...] = ()
    submitted_event: str | None = None
    submitted_account: str | None = None
    result_event: str | None = None
    successful: bool | None = None
    public_result: str | None = None
    judge: int | None = None
    judge_appointment: str | None = None
    award: str | None = None
    award_session: str | None = None
    award_event: str | None = None
    award_blocked: str | None = None


def events(state: GameState) -> tuple[Event, ...]:
    return tuple(
        Event.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "handler_pr_event"
    )


def put(state: GameState, value: Event) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "handler_pr_event" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="handler_pr_event", id=value.id, body=value.model_dump_json()))
