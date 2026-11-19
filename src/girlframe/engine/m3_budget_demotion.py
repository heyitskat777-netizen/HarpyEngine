"""The original Handler remains a living person and gains an owned Girl sheet."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import depart, same_handler_body

RULE = "strain.budget.endgame.2"
KIND = "budget_handler_demotion"


class Demotion(Model):
    id: str
    period: str
    source: str
    handler: ActorRef
    appointment: str
    successor: int
    offered: str
    account: str = Field(min_length=1, max_length=1200)
    accepted: str | None = None
    declined: str | None = None
    demoted: str | None = None
    girl: ActorRef | None = None
    girl_activation: str | None = None
    new_appointment: str | None = None
    replacement: ActorRef | None = None
    completed: str | None = None


def demotions(state: GameState) -> tuple[Demotion, ...]:
    return tuple(
        Demotion.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, value: Demotion) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)] + [
        dict(kind=KIND, id=value.id, body=value.model_dump_json())
    ]


def demote(state: GameState, value: Demotion, event: str, appointment: str) -> GameState:
    if (
        value not in demotions(state)
        or value.accepted is None
        or value.declined is not None
        or value.demoted is not None
        or value.appointment != appointment
        or not same_handler_body(state, value.handler)
        or value.handler.entity in state.sheets
    ):
        raise ValueError("Recover the original accepted succession and unambiguous Handler body")
    changed = depart(
        state,
        value.handler,
        reason="demoted",
        source_work=value.id,
        event=event,
        appointment=appointment,
        account=value.account,
    )
    save(changed, value.model_copy(update=dict(demoted=event)))
    return changed
