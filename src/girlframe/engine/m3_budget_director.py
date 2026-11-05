"""A real source meeting, separately played Director and owned presence setup."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler


class Meeting(Model):
    id: str
    source_work: str
    source_event: str
    period: str
    handler: ActorRef
    director: ActorRef
    controller: int
    phase: Literal["appearance", "setup", "active", "complete"] = "appearance"
    appearance_event: str | None = None
    context: str | None = None
    heat: int = 0
    ended_event: str | None = None
    account: str = Field(min_length=1, max_length=2400)


def meetings(state: GameState) -> tuple[Meeting, ...]:
    return tuple(
        Meeting.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_director_meeting"
    )


def get(state: GameState, identity: str) -> Meeting:
    value = next((x for x in meetings(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Open the actual Budget Director meeting")
    return value


def put(state: GameState, value: Meeting) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "budget_director_meeting" and x.get("id") == value.id)
    ]
    state.facts.append(
        dict(kind="budget_director_meeting", id=value.id, body=value.model_dump_json())
    )


def create(
    state: GameState, work: str, period: str, event: str, npc: str, account: str
) -> GameState:
    handler = active_handler(state)
    body = (
        next(
            (x for x in state.world.npcs if x.id == npc and x.alive and "director" in x.jobs), None
        )
        if state.world
        else None
    )
    if (
        handler is None
        or body is None
        or body.controller == state.handler
        or any(x.source_work == work for x in meetings(state))
    ):
        raise ValueError("Choose an existing Director played by a different human for this source")
    changed = GameState.model_validate_json(state.model_dump_json())
    put(
        changed,
        Meeting(
            id=work + ":meeting",
            source_work=work,
            source_event=event,
            period=period,
            handler=handler,
            director=ActorRef(kind="npc", entity=body.id),
            controller=body.controller,
            account=account,
        ),
    )
    return changed
