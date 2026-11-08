"""Original-person Bonded sources and narrowly scoped printed effects."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

PAIR = "girl.bonded.bonded-pair"
SIDE = "girl.bonded.always-by-her-side"
INTIMACY = "girl.bonded.workplace-inappropriate-intimacy"
SEX = "girl.bonded.sex-play"
RULES = (PAIR, SIDE, INTIMACY, SEX)
SIDE_PLAY = "bonded_side"
SEX_PLAY = "bonded_sex"


class Source(Model):
    changeling_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    id: str
    kind: Literal["side", "intimacy", "sex"]
    actor: ActorRef
    pair: ActorRef
    target: ActorRef | None = None
    observer: ActorRef | None = None
    controllers: dict[str, int]
    vessels: dict[str, str]
    cast: SceneCast
    registry: str
    pair_source: str
    apart: bool = Field(default=False, exclude_if=lambda value: not value)
    event: str
    account: str = Field(min_length=1, max_length=1200)
    phase: Literal["invited", "accepted", "declined", "bound", "results", "child", "complete"]
    route: Literal["pair", "seven", "delegated"] = "pair"
    delegated_rule: str | None = None
    action: str | None = None
    bound_event: str | None = None
    effect_event: str | None = None
    tier: Literal["low", "mid", "high"] | None = None
    completed_event: str | None = None


class Consent(Model):
    id: str
    source: str
    person: ActorRef
    controller: int
    accepted: bool
    event: str
    account: str


class Activation(Model):
    id: str
    source: str
    actor: ActorRef
    event: str
    account: str


class Selection(Model):
    id: str
    source: str
    action: str | None
    person: ActorRef
    controller: int
    kind: str
    options: tuple[str, ...]
    identities: tuple[str, ...] = ()
    request: str | None = None
    text: str
    event: str


class PairHelp(Model):
    id: str
    source: str
    actor: ActorRef
    pair: ActorRef
    controller: int
    event: str
    account: str


class Child(Model):
    id: str
    source: str
    actor: ActorRef
    target: ActorRef
    parent: str | None
    play: str
    account: str
    event: str
    child: str | None = None
    bound_event: str | None = None
    completed_event: str | None = None
    total: int | None = None


class Silence(Model):
    id: str
    source: str
    child: str
    actor: ActorRef
    pair: ActorRef
    observer: ActorRef
    observation: str
    event: str


class Detail(Model):
    """Actual addressed secret, changed appearance, Tag request or source-authorized Order."""

    id: str
    source: str
    kind: Literal["secret", "appearance", "order"]
    actor: ActorRef
    target: ActorRef
    controller: int
    account: str
    event: str
    order: str | None = None


class Delegation(Model):
    id: str
    source: str
    session: str
    rule: str
    actor: ActorRef
    target: ActorRef
    event: str
    completed_event: str | None = None
    action: str | None = None


class OrderBinding(Model):
    id: str
    detail: str
    source: str
    actor: ActorRef
    target: ActorRef
    order: str
    event: str


KINDS: dict[type[Model], str] = {
    Source: "bonded_source",
    Consent: "bonded_consent",
    Activation: "bonded_activation",
    Selection: "bonded_selection",
    PairHelp: "bonded_pair_help",
    Child: "bonded_child",
    Silence: "bonded_silence",
    Detail: "bonded_detail",
    OrderBinding: "bonded_order_binding",
    Delegation: "bonded_delegation",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], str(value.model_dump()["id"])
    if not isinstance(value, (Source, Child, Delegation)) and any(
        x.get("kind") == kind and x.get("id") == identity for x in state.facts
    ):
        raise ValueError("Preserve the original person's immutable Bonded response")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def get(state: GameState, identity: str) -> Source:
    value = next((x for x in records(state, Source) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the genuine original Bonded source")
    return value


def pair(state: GameState, actor: ActorRef) -> ActorRef:
    sheet = state.sheets.get(actor.entity)
    if actor.kind != "pilot" or sheet is None or sheet.character_id != actor.incarnation:
        raise ValueError("Use the original current Bonded Girl")
    setup = sheet.girl_runtime.setup if sheet.girl_runtime else None
    actual = setup.pair if setup else None
    if actual is None:
        saved = [x.pair for x in records(state, Source) if x.actor == actor]
        if not saved or len(set(saved)) != 1:
            raise ValueError("SOURCE_PAIR_REQUIRED: prove the original accepted creation Bond")
        actual = saved[0]
    other = state.sheets.get(actual.entity)
    if actual.kind != "pilot" or other is None or other.character_id != actual.incarnation:
        raise ValueError("SOURCE_PAIR_REQUIRED: the original Pair cannot alias a replacement")
    if actual == actor:
        raise ValueError("The Pair is a distinct actual person")
    return actual


def helpless(state: GameState, actor: ActorRef) -> bool:
    return any(
        x.actor == actor
        and x.kind == "side"
        and x.tier == "low"
        and x.effect_event is not None
        and not any(
            y.source == x.id and y.actor == actor and y.pair == x.pair
            for y in records(state, PairHelp)
        )
        for x in records(state, Source)
    )


def can_disclose(state: GameState, speaker: ActorRef, observation: str) -> bool:
    return not any(
        x.observer == speaker and x.observation == observation for x in records(state, Silence)
    )


def appearance(state: GameState, actor: ActorRef) -> str | None:
    value = next(
        (
            x
            for x in reversed(records(state, Detail))
            if x.kind == "appearance" and x.target == actor
        ),
        None,
    )
    if value is None:
        return None
    placement = next((x for x in state.placements if x.actor == actor), None)
    source = get(state, value.source)
    return (
        value.account
        if placement is not None and placement.vessel_id == source.vessels.get(actor.token)
        else None
    )
