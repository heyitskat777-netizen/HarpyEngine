"""Source-owned political target and genuine mission attempts."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle import category
from girlframe.engine.m3_handler_consequences import active_handler

RULE = "strain.budget.low.6.1"


class Assignment(Model):
    id: str
    source_work: str
    source_event: str
    period: str
    handler: ActorRef
    target: ActorRef
    people: tuple[ActorRef, ...]
    account: str = Field(min_length=1, max_length=2400)
    phase: Literal["pending", "mission", "complete"] = "pending"
    mission: str | None = None
    attempts: tuple[str, ...] = ()
    death_event: str | None = None
    completed_event: str | None = None

    @model_validator(mode="after")
    def actual_attempts(self) -> "Assignment":
        if (
            self.handler.kind != "handler"
            or self.target.kind != "npc"
            or not self.people
            or len(set(self.people)) != len(self.people)
            or any(x.kind != "pilot" for x in self.people)
            or len(set(self.attempts)) != len(self.attempts)
            or (self.mission is not None and self.mission not in self.attempts)
            or (self.phase == "pending") != (self.mission is None)
            or (self.phase == "complete") != bool(self.death_event and self.completed_event)
        ):
            raise ValueError(
                "Preserve the original target, actual mission attempts and real ending"
            )
        return self


def assignments(state: GameState) -> tuple[Assignment, ...]:
    return tuple(
        Assignment.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_assassination"
    )


def get(state: GameState, identity: str) -> Assignment:
    value = next((x for x in assignments(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Open the original political assassination assignment")
    return value


def put(state: GameState, value: Assignment) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "budget_assassination" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="budget_assassination", id=value.id, body=value.model_dump_json()))


def create(
    state: GameState, work: str, period: str, event: str, npc: str, account: str
) -> GameState:
    target = ActorRef(kind="npc", entity=npc)
    resolve(state, target, ())
    handler = active_handler(state)
    if (
        category(state, target) != "npc"
        or handler is None
        or not state.order
        or any(x.source_work == work for x in assignments(state))
    ):
        raise ValueError("Select the actual living ordinary NPC politician and original Cadre")
    changed = GameState.model_validate_json(state.model_dump_json())
    put(
        changed,
        Assignment(
            id=work + ":assassination",
            source_work=work,
            source_event=event,
            period=period,
            handler=handler,
            target=target,
            people=tuple(current_ref(state, uid) for uid in state.order),
            account=account,
        ),
    )
    return changed
