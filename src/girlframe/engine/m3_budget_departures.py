"""The selected Budget Endgame changes actual related NPCs, never proxy Pilots."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_battle import end_actor_casts
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical import interrupt_journeys
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import NPC_JOBS, Npc

RULE = "strain.budget.endgame.7"


class Departure(Model):
    actor: ActorRef
    outcome: Literal["quit", "die"]
    jobs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def ordinary_original(self) -> "Departure":
        if (
            self.actor.kind != "npc"
            or (self.outcome == "quit") != bool(self.jobs)
            or not set(self.jobs) <= set(NPC_JOBS) - {"director"}
            or len(set(self.jobs)) != len(self.jobs)
        ):
            raise ValueError("Choose an ordinary original NPC and actual post-quitting jobs only")
        return self


class Record(Model):
    id: str
    handler: ActorRef
    source_event: str
    event: str
    departures: tuple[Departure, ...] = Field(min_length=3, max_length=5)
    originals: tuple[Npc, ...] = Field(min_length=3, max_length=5)
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def exact_originals(self) -> "Record":
        if (
            self.handler.kind != "handler"
            or len({x.actor for x in self.departures}) != len(self.departures)
            or tuple(x.actor.entity for x in self.departures) != tuple(x.id for x in self.originals)
        ):
            raise ValueError("Keep each actual original person and outcome exactly once")
        return self


def records(state: GameState) -> tuple[Record, ...]:
    return tuple(
        Record.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_bond_departures"
    )


def eligible(state: GameState) -> tuple[Npc, ...]:
    if state.world is None:
        return ()
    people = [current_ref(state, uid) for uid in state.order]
    handler = active_handler(state)
    if handler is not None:
        people.append(handler)
    return tuple(
        x
        for x in state.world.npcs
        if x.alive
        and "director" not in x.jobs
        and any(depth(state, ActorRef(kind="npc", entity=x.id), person) > 0 for person in people)
    )


def apply(
    original: GameState,
    identity: str,
    source_event: str,
    event: str,
    selected: tuple[Departure, ...],
    account: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    available = {x.id: x for x in eligible(state)}
    handler = active_handler(state)
    if (
        handler is None
        or len(selected) not in range(3, 6)
        or len({x.actor for x in selected}) != len(selected)
        or any(x.actor.entity not in available for x in selected)
        or any(x.id == identity for x in records(state))
        or not account.strip()
    ):
        raise ValueError("Choose three to five distinct actual living NPC Bonds for this source")
    affected = {x.actor for x in selected}
    if any(
        not case.completion_event
        and not case.ended_event
        and affected.intersection((case.subject, case.executor, case.chooser))
        for case in state.role_punishments
    ):
        raise ValueError("Finish the affected NPC's pending Punishment before its departure")
    saved = Record(
        id=identity,
        handler=handler,
        source_event=source_event,
        event=event,
        departures=selected,
        originals=tuple(available[x.actor.entity] for x in selected),
        account=account.strip(),
    )
    for choice in selected:
        before = available[choice.actor.entity]
        if choice.outcome == "quit" and before.employment == "unemployed":
            raise ValueError("An already unemployed NPC cannot lose that employment again")
        changed = (
            before.model_copy(update=dict(jobs=choice.jobs, employment="unemployed"))
            if choice.outcome == "quit"
            else before.model_copy(update=dict(alive=False))
        )
        if choice.outcome == "die":
            state = interrupt_journeys(state, choice.actor, event, account)
            state = end_actor_casts(state, choice.actor, event)
        assert state.world is not None
        state.world = update(
            state.world, npcs=tuple(changed if x.id == before.id else x for x in state.world.npcs)
        )
    state.facts.append(
        dict(kind="budget_bond_departures", id=identity, body=saved.model_dump_json())
    )
    return state
