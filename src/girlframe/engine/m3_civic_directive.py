"""Printed Strain directives with separate fictional Director and Handler authors."""

from typing import Final, Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_world_state import Npc

PROTEST: Final = "strain.rebellion.low.3.1"
SUPPORT: Final = "strain.rebellion.high.3.2"
RULES = frozenset({PROTEST, SUPPORT})
KIND = "strain_civic_directive"


class Directive(Model):
    id: str
    source_event: str
    period: str
    rule: Literal["strain.rebellion.low.3.1", "strain.rebellion.high.3.2"]
    director: str
    controller: int
    handler: ActorRef
    city: str | None = None
    faction: str | None = None
    order: str | None = None
    order_event: str | None = None
    action: str | None = None
    action_event: str | None = None


def cases(state: GameState) -> tuple[Directive, ...]:
    return tuple(
        Directive.model_validate_json(fact["body"])
        for fact in state.facts
        if fact.get("kind") == KIND
    )


def put(state: GameState, value: Directive) -> None:
    state.facts = [
        fact for fact in state.facts if (fact.get("kind"), fact.get("id")) != (KIND, value.id)
    ] + [dict(kind=KIND, id=value.id, body=value.model_dump_json())]


def director(state: GameState, identity: str | None) -> Npc:
    npc = next((x for x in state.world.npcs if x.id == identity), None) if state.world else None
    if (
        npc is None
        or not npc.alive
        or npc.captive_of is not None
        or "director" not in npc.jobs
        or npc.controller == state.handler
    ):
        raise ValueError("Recover the living fictional Director played by a separate controller")
    return npc


def create(
    state: GameState,
    *,
    rule: str,
    identity: str,
    event: str,
    period: str,
    speaker: str | None,
    city: str | None,
) -> None:
    npc = director(state, speaker)
    handler = active_handler(state)
    if handler is None or any(x.id == identity for x in cases(state)):
        raise ValueError("Bind one original directive to the actual current Handler")
    if rule == PROTEST:
        world = state.world
        if world is None or not any(
            x.id == city and x.kind == "city" and x.operational and in_responsibility(state, x.cell)
            for x in world.locations
        ):
            raise ValueError("Choose the actual nearby operational city affected by the protest")
    elif rule != SUPPORT or city is not None:
        raise ValueError("Use only the original protest or show-of-support source")
    put(
        state,
        Directive(
            id=identity,
            source_event=event,
            period=period,
            rule=PROTEST if rule == PROTEST else SUPPORT,
            director=npc.id,
            controller=npc.controller,
            handler=handler,
            city=city,
        ),
    )


def public_conditions(state: GameState) -> list[dict[str, str]]:
    conditions = []
    for case in cases(state):
        if case.rule == PROTEST and case.city is not None:
            conditions.append(dict(kind="protest", city=case.city))
            if case.action_event:
                conditions.append(dict(kind="public_response_to_protest", city=case.city))
        elif case.rule == SUPPORT:
            conditions.append(dict(kind="rebel_public_sympathy"))
            if case.action_event:
                conditions.append(dict(kind="public_show_of_support"))
    return conditions
