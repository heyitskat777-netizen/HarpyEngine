"""Original voluntary Alpha intimacy, finite sleep and scent-bound Broken sources."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_alpha import conditions, current

RULE = "girl.alpha.sex-play"
PLAY = "alpha_sex"


class Session(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    counterpart: int
    cast: SceneCast
    registry: str
    bonded_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    proposed_event: str
    proposal: str = Field(min_length=1, max_length=1200)
    consent_event: str | None = None
    consent_account: str = Field(default="", max_length=1200)
    phase: Literal[
        "invited", "accepted", "declined", "active", "sleeping", "waking", "complete"
    ] = "invited"
    action: str | None = None
    effect_event: str | None = None
    sleep_event: str | None = None
    wake_event: str | None = None
    condition: str | None = None
    case: str | None = None


def sessions(state: GameState) -> tuple[Session, ...]:
    return tuple(
        Session.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "alpha_sex_session"
    )


def get(state: GameState, identity: str) -> Session:
    found = next((x for x in sessions(state) if x.id == identity), None)
    if found is None:
        raise ValueError("Recover this actual original Alpha interaction")
    return found


def put(state: GameState, value: Session) -> None:
    fact = dict(kind="alpha_sex_session", id=value.id, body=value.model_dump_json())
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "alpha_sex_session" and x.get("id") == value.id)
    ] + [fact]


def asleep(state: GameState, actor: ActorRef) -> bool:
    return any(x.actor == actor and x.sleep_event and not x.wake_event for x in sessions(state))


def require_awake(state: GameState, actor: ActorRef) -> None:
    if asleep(state, actor):
        raise ValueError(
            "ASLEEP: resolve the actual counterpart opportunity and your owned wake first"
        )


def tracking(state: GameState, value: Session) -> bool:
    return bool(
        value.condition
        and current(state, value.actor)
        and current(state, value.target)
        and any(
            x.id == value.condition and x.source_action == value.action
            for x in conditions(state, value.target, value.actor)
        )
    )
