"""Actual Pilot Candidate, original assessor and table-authored candidacy process."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world import update


class Assessment(Model):
    id: str
    source_work: str
    source_event: str
    period: str
    handler: ActorRef
    candidate: ActorRef
    assessor: ActorRef
    controller: int
    humans: tuple[int, ...]
    people: tuple[ActorRef, ...]
    account: str = Field(min_length=1, max_length=2400)
    process: str | None = None
    approvals: tuple[int, ...] = ()
    phase: Literal["process", "assessing", "complete"] = "process"
    report: str | None = None
    ended_event: str | None = None

    @model_validator(mode="after")
    def actual_people(self) -> "Assessment":
        if (
            self.handler.kind != "handler"
            or self.candidate.kind != "npc"
            or self.assessor.kind != "pilot"
            or self.assessor not in self.people
            or any(x.kind != "pilot" for x in self.people)
            or len(set(self.people)) != len(self.people)
            or len(set(self.humans)) != len(self.humans)
            or not {int(self.handler.entity), int(self.assessor.entity), self.controller}
            <= set(self.humans)
            or len(set(self.approvals)) != len(self.approvals)
            or not set(self.approvals) <= set(self.humans)
            or (self.phase != "process" and set(self.approvals) != set(self.humans))
            or (self.phase != "process" and not self.process)
            or (self.phase == "complete") != bool(self.report and self.ended_event)
        ):
            raise ValueError("Preserve the original assessor and exact table-agreed process")
        return self


def assessments(state: GameState) -> tuple[Assessment, ...]:
    return tuple(
        Assessment.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_candidate"
    )


def get(state: GameState, identity: str) -> Assessment:
    value = next((x for x in assessments(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Open the original Pilot Candidate assessment")
    return value


def put(state: GameState, value: Assessment) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "budget_candidate" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="budget_candidate", id=value.id, body=value.model_dump_json()))


def create(
    state: GameState, work: str, period: str, event: str, npc: str, girl: int, account: str
) -> GameState:
    body = (
        next((x for x in state.world.npcs if x.id == npc and x.alive), None)
        if state.world
        else None
    )
    handler = active_handler(state)
    if (
        body is None
        or handler is None
        or girl not in state.order
        or any(x.source_work == work for x in assessments(state))
    ):
        raise ValueError("Choose an actual living NPC, original Girl assessor and new source")
    changed = GameState.model_validate_json(state.model_dump_json())
    assert changed.world is not None
    changed.world = update(
        changed.world,
        npcs=tuple(
            x.model_copy(update={"jobs": tuple(dict.fromkeys((*x.jobs, "pilot_candidate")))})
            if x.id == npc
            else x
            for x in changed.world.npcs
        ),
    )
    put(
        changed,
        Assessment(
            id=work + ":candidate",
            source_work=work,
            source_event=event,
            period=period,
            handler=handler,
            candidate=ActorRef(kind="npc", entity=npc),
            assessor=current_ref(state, girl),
            controller=body.controller,
            humans=tuple(sorted({int(handler.entity), *state.order, body.controller})),
            people=tuple(current_ref(state, uid) for uid in state.order),
            account=account,
        ),
    )
    return changed
