"""The original Handler's award and actual departure at the source period boundary."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import depart, same_handler_body

RULE = "strain.void.endgame.3"
KIND = "void_handler_retirement"


class Retirement(Model):
    id: str
    source: str
    awarded: str
    period: str
    handler: ActorRef
    appointment: str
    medal: str = Field(min_length=1, max_length=120)
    safe_home: str = Field(min_length=1, max_length=300)
    account: str = Field(min_length=1, max_length=1200)
    retired: str | None = None


def awards(state: GameState) -> tuple[Retirement, ...]:
    return tuple(
        Retirement.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, award: Retirement) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, award.id)] + [
        dict(kind=KIND, id=award.id, body=award.model_dump_json())
    ]


def finish(state: GameState, period: str, event: str, appointment: str) -> GameState:
    award = next((x for x in awards(state) if x.period == period and not x.retired), None)
    if award is None:
        return state
    if appointment != award.appointment or not same_handler_body(state, award.handler):
        raise ValueError("Review the competing change to the original Handler retirement")
    state = depart(
        state,
        award.handler,
        reason="retired",
        source_work=award.id,
        event=event,
        appointment=award.appointment,
        account=award.account,
    )
    save(state, award.model_copy(update={"retired": event}))
    return state
