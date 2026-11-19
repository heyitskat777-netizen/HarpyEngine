"""A new Foundation court ends the original Handler and approves an owned successor."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequence_state import HandlerFatalSource
from girlframe.engine.m3_handler_consequences import force_end

RULE = "strain.rebellion.endgame.7"
KIND = "new_foundation_succession"


class Succession(Model):
    id: str
    source: str
    period: str
    group: str
    old_handler: ActorRef
    appointment: str
    court: str
    controller: int
    assimilation: str
    ideals: str = Field(default="", max_length=1200)
    sentence: str = Field(default="", max_length=1200)
    sentenced: str | None = None
    executed: str | None = None
    pledge: str = Field(default="", max_length=1200)
    pledged: str | None = None
    draft_fingerprint: str | None = None
    approved: str | None = None
    refused: str | None = None
    replacement: ActorRef | None = None
    completed: str | None = None


def successions(state: GameState) -> tuple[Succession, ...]:
    return tuple(
        Succession.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, value: Succession) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)] + [
        dict(kind=KIND, id=value.id, body=value.model_dump_json())
    ]


def execute(state: GameState, value: Succession, event: str, appointment: str) -> GameState:
    if (
        value not in successions(state)
        or not value.sentenced
        or value.executed
        or value.appointment != appointment
    ):
        raise ValueError("Recover the original Foundation sentence and Handler body")
    changed = force_end(
        state,
        HandlerFatalSource(
            id="foundation-sentence:" + value.id,
            actor=value.old_handler,
            source_event=event,
            source_work=value.id,
            clause="strain.rebellion.endgame.7.execution",
            appointment=appointment,
            account=value.sentence,
        ),
    )
    save(changed, value.model_copy(update=dict(executed=event)))
    return changed
