"""The Budget trial preserves the original charge, hearing and final consequences."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequence_state import HandlerFatalSource
from girlframe.engine.m3_handler_consequences import force_end

RULE = "strain.budget.endgame.1"
KIND = "budget_warcrime_trial"
Phase = Literal["charge", "hearing", "saved", "execution_due", "executed"]


class Statement(Model):
    actor: ActorRef
    decision: Literal["answer", "defend", "pass"]
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Trial(Model):
    id: str
    period: str
    source: str
    handler: ActorRef
    appointment: str
    director: str
    controller: int
    cadre: tuple[ActorRef, ...]
    phase: Phase = "charge"
    charge: str = ""
    charge_event: str | None = None
    statements: tuple[Statement, ...] = ()
    verdict: str = ""
    verdict_event: str | None = None
    executed: str | None = None


def trials(state: GameState) -> tuple[Trial, ...]:
    return tuple(Trial.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def save(state: GameState, trial: Trial) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, trial.id)] + [
        dict(kind=KIND, id=trial.id, body=trial.model_dump_json())
    ]


def execute(state: GameState, trial: Trial, event: str, appointment: str) -> GameState:
    if (
        trial.phase != "execution_due"
        or trial not in trials(state)
        or trial.executed
        or not trial.verdict_event
        or trial.appointment != appointment
    ):
        raise ValueError("Recover the original signed court sentence and the original Handler")
    changed = force_end(
        state,
        HandlerFatalSource(
            id="budget-trial:" + trial.id,
            actor=trial.handler,
            source_event=event,
            source_work=trial.id,
            clause="strain.budget.endgame.1.execution",
            appointment=appointment,
            account=trial.verdict,
        ),
    )
    save(changed, trial.model_copy(update=dict(phase="executed", executed=event)))
    return changed
