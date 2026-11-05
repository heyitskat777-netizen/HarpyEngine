"""Actual higher-up visits and original-person reparation demands."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler

RULE = "strain.budget.low.5.1"


class Demand(Model):
    id: str
    girl: ActorRef
    offense: str = Field(min_length=1, max_length=1200)
    demand: str = Field(min_length=1, max_length=1200)
    event: str
    response: str | None = None
    response_event: str | None = None
    settlement: str | None = None
    settlement_event: str | None = None

    @model_validator(mode="after")
    def actual_response(self) -> "Demand":
        if (
            self.girl.kind != "pilot"
            or bool(self.response) != bool(self.response_event)
            or bool(self.settlement) != bool(self.settlement_event)
            or self.settlement is not None
            and self.response is None
        ):
            raise ValueError("Preserve the actual original demand, response and settlement")
        return self


class Visit(Model):
    id: str
    source_work: str
    source_event: str
    period: str
    handler: ActorRef
    visitor: ActorRef
    controller: int
    cell: tuple[int, int]
    people: tuple[ActorRef, ...]
    account: str = Field(min_length=1, max_length=2400)
    phase: Literal["active", "complete"] = "active"
    ended_event: str | None = None
    demands: tuple[Demand, ...] = ()

    @model_validator(mode="after")
    def actual_source(self) -> "Visit":
        if (
            self.handler.kind != "handler"
            or self.visitor.kind != "npc"
            or not self.people
            or len(set(self.people)) != len(self.people)
            or any(x.kind != "pilot" for x in self.people)
            or len({x.id for x in self.demands}) != len(self.demands)
            or any(x.girl not in self.people for x in self.demands)
            or (self.phase == "complete") != bool(self.ended_event)
        ):
            raise ValueError("Preserve the source higher-up, original Cadre and actual ending")
        return self


def visits(state: GameState) -> tuple[Visit, ...]:
    return tuple(
        Visit.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_visitor"
    )


def get(state: GameState, identity: str) -> Visit:
    value = next((x for x in visits(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Open the original higher-up visit")
    return value


def put(state: GameState, value: Visit) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "budget_visitor" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="budget_visitor", id=value.id, body=value.model_dump_json()))


def create(
    state: GameState, work: str, period: str, event: str, npc: str, account: str
) -> GameState:
    from girlframe.engine.m3_battle import category

    visitor = ActorRef(kind="npc", entity=npc)
    actor = resolve(state, visitor, ())
    handler = active_handler(state)
    if (
        category(state, visitor) != "npc"
        or actor.cell is None
        or handler is None
        or not state.order
        or any(x.source_work == work for x in visits(state))
    ):
        raise ValueError("Choose an actual living ordinary NPC at the known visit location")
    changed = GameState.model_validate_json(state.model_dump_json())
    put(
        changed,
        Visit(
            id=work + ":visit",
            source_work=work,
            source_event=event,
            period=period,
            handler=handler,
            visitor=visitor,
            controller=actor.controller,
            cell=actor.cell,
            people=tuple(current_ref(state, uid) for uid in state.order),
            account=account,
        ),
    )
    return changed
