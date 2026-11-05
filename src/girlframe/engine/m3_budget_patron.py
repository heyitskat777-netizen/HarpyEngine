"""One original rich patron's Bond and explicitly observed visit consequences."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler


class Interest(Model):
    id: str = Field(min_length=1)
    patron: ActorRef
    girl: ActorRef
    handler: ActorRef
    source_event: str = Field(min_length=1)
    period: str = Field(min_length=1)


def interests(state: GameState) -> tuple[Interest, ...]:
    return tuple(
        Interest.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_patron_interest"
    )


def create(
    state: GameState, work: str, girl: str, patron: str, period: str, event: str
) -> GameState:
    if state.world is None or girl not in {str(x) for x in state.order}:
        raise ValueError("Choose an actual current original Girl and existing rich patron")
    npc = next(
        (x for x in state.world.npcs if x.id == patron and x.alive and "patron" in x.jobs), None
    )
    handler = active_handler(state)
    if npc is None or handler is None or any(x.id == work for x in interests(state)):
        raise ValueError("Use an existing living patron, original Handler and new source result")
    subject, person = current_ref(state, int(girl)), ActorRef(kind="npc", entity=patron)
    changed = set_depth(
        state, subject, person, 2 if depth(state, subject, person) == 2 else 1, event
    )
    record = Interest(
        id=work, patron=person, girl=subject, handler=handler, source_event=event, period=period
    )
    changed.facts.append(
        dict(kind="budget_patron_interest", id=work, body=record.model_dump_json())
    )
    return changed
