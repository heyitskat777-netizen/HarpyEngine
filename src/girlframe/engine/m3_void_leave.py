"""Actual Handler leave and an original-table decision at the period boundary."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import same_handler_body

RULE = "strain.void.endgame.1"
Response = Literal["continue", "close"]


class Vote(Model):
    voter: ActorRef
    preference: Response
    event: str


class Leave(Model):
    id: str
    selection: str
    approved: str
    period: str
    handler: ActorRef
    appointment: str
    voters: tuple[ActorRef, ...] = Field(min_length=1)
    home: str = Field(min_length=1, max_length=300)
    quadrant: int = Field(ge=1)
    bond: ActorRef | None = None
    account: str = Field(min_length=1, max_length=900)
    departed: str | None = None
    returned: str | None = None
    votes: tuple[Vote, ...] = ()
    decision: Response | None = None
    decided: str | None = None

    @model_validator(mode="after")
    def actual_leave(self) -> "Leave":
        voted = {x.voter for x in self.votes}
        if (
            self.handler.kind != "handler"
            or self.quadrant == 12
            or self.bond is not None
            and self.bond.kind != "npc"
            or any(x.kind != "pilot" for x in self.voters)
            or len(self.voters) != len(set(self.voters))
            or len(voted) != len(self.votes)
            or not voted <= set(self.voters)
            or self.returned is not None
            and self.departed is None
            or self.votes
            and self.returned is None
            or (self.decision is None) != (self.decided is None)
            or self.decided is not None
            and (voted != set(self.voters) or self.returned is None)
        ):
            raise ValueError("Preserve actual leave, its original table and their owned responses")
        return self


def leaves(state: GameState) -> tuple[Leave, ...]:
    return tuple(
        Leave.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "void_leave"
    )


def save(state: GameState, leave: Leave) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != ("void_leave", leave.id)
    ] + [dict(kind="void_leave", id=leave.id, body=leave.model_dump_json())]


def away(state: GameState, actor: ActorRef) -> Leave | None:
    if actor.kind != "handler" or not same_handler_body(state, actor):
        return None
    return next(
        (
            x
            for x in leaves(state)
            if x.departed and x.returned is None and same_handler_body(state, x.handler)
        ),
        None,
    )


def start(state: GameState, period: str, event: str, appointment: str) -> Leave | None:
    leave = next((x for x in leaves(state) if x.period == period and x.departed is None), None)
    if leave is None:
        return None
    if not same_handler_body(state, leave.handler) or leave.appointment != appointment:
        raise ValueError("Review the original Handler appointment before its actual leave")
    if any(x.active and x.handler == int(leave.handler.entity) for x in state.director_contexts):
        raise ValueError("Finish the actual Director encounter before departing the Quadrant")
    if any(x.state == "boarded" and x.actor == leave.handler for x in state.passengers):
        raise ValueError("Resolve the original Handler's actual transport before leave")
    actual = leave.model_copy(update={"departed": event})
    save(state, actual)
    return actual


def finish(state: GameState, period: str, event: str) -> Leave | None:
    leave = next(
        (x for x in leaves(state) if x.period == period and x.departed and not x.returned), None
    )
    if leave is None:
        return None
    actual = leave.model_copy(update={"returned": event})
    save(state, actual)
    return actual
