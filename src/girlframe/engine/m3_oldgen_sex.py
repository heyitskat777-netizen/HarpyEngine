"""Original Oldgen intimacy, actual choices and source-owned physiological incapacity."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "girl.oldgen.sex-play"
PLAY = "oldgen_sex"
EFFECTS = ("tag", "status", "unmark", "bond", "helpless")
Role = Literal["caster", "reciprocal", "additional", "creep", "rewrite"]
EffectKind = Literal["tag", "status", "unmark", "bond", "helpless", "rewrite"]


class Session(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    counterpart: int
    cast: SceneCast
    registry: str
    bonded_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    changeling_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    actor_vessel: str
    target_vessel: str
    proposed_event: str
    proposal: str
    consent_event: str | None = None
    consent_account: str = ""
    phase: str = "invited"
    action: str | None = None
    bound_event: str | None = None
    effect_event: str | None = None
    tier: Literal["low", "mid", "high"] | None = None
    creep: bool | None = None
    completed_event: str | None = None


class Selection(Model):
    id: str
    session: str
    action: str
    controller: int
    role: Role
    options: tuple[str, ...]
    text: str
    maxim: str | None = None
    event: str


class Effect(Model):
    id: str
    session: str
    action: str
    selection: str
    owner: ActorRef
    target: ActorRef
    kind: EffectKind
    event: str
    maxim: str | None = None
    text: str = ""
    tag: TagState | None = None
    before: int | None = None
    after: int | None = None


class Recovery(Model):
    id: str
    effect: str
    subject: ActorRef
    event: str


KINDS: dict[type[Model], str] = {
    Session: "oldgen_sex_session",
    Selection: "oldgen_sex_selection",
    Effect: "oldgen_sex_effect",
    Recovery: "oldgen_sex_recovery",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], value.model_dump()["id"]
    if not isinstance(value, Session) and any(
        x.get("kind") == kind and x.get("id") == identity for x in state.facts
    ):
        raise ValueError("Preserve the immutable actual Oldgen Sex consequence")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def get(state: GameState, identity: str) -> Session:
    value = next((x for x in records(state, Session) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original Oldgen intimacy source")
    return value


def helpless(state: GameState, subject: ActorRef, foe: ActorRef | None = None) -> bool:
    return any(
        x.kind == "helpless"
        and x.target == subject
        and not any(y.effect == x.id for y in records(state, Recovery))
        for x in records(state, Effect)
    )
