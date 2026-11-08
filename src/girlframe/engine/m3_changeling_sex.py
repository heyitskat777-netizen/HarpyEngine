"""A real psychic initiation links to one genuine Girl-specific Sex source."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_changeling import BrainRef

RULES = {
    "ALPHA": "girl.alpha.sex-play",
    "PRINCESS": "girl.princess.sex-play",
    "MOCKINGBIRD": "girl.mockingbird.sex-play",
    "STIM-BLISSED": "girl.stim-blissed.sex-play",
    "OLDGEN": "girl.oldgen.sex-play",
    "CASUALTY": "girl.casualty.sex-play",
    "VATGROWN": "girl.vatgrown.sex-play",
    "NEWGIRL": "girl.newgirl.sex-play",
    "BONDED": "girl.bonded.sex-play",
    "AM": "girl.am.sex-play",
}
PLAYS = {book: book.lower().replace("stim-blissed", "stim") + "_sex" for book in RULES}


class Link(Model):
    id: str
    use: str
    initiator: BrainRef
    counterpart: BrainRef
    performer: ActorRef
    partner: ActorRef
    rule: str
    event: str
    controller: int
    account: str
    route: Literal["pair", "seven", "delegated"] = "pair"
    delegated_rule: str | None = None
    session: str | None = None
    source_event: str | None = None
    action: str | None = None
    bound_event: str | None = None
    completed_event: str | None = None
    completion_source: str | None = None
    outcome: Literal["performed", "declined"] | None = None


def identity(use: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:changeling-sex:" + use))


def records(state: GameState) -> tuple[Link, ...]:
    return tuple(
        Link.model_validate_json(item["body"])
        for item in state.facts
        if item.get("kind") == "changeling_sex_link"
    )


def get(state: GameState, identity: str) -> Link:
    found = next((item for item in records(state) if item.id == identity), None)
    if found is None:
        raise ValueError("Recover the actual original psychic Sex source link")
    return found


def put(state: GameState, value: Link) -> None:
    state.facts = [
        item
        for item in state.facts
        if not (item.get("kind") == "changeling_sex_link" and item.get("id") == value.id)
    ]
    state.facts.append(dict(kind="changeling_sex_link", id=value.id, body=value.model_dump_json()))


class UnrolledAMSex(Model):
    id: str
    link: str
    actor: ActorRef
    target: ActorRef
    controllers: dict[str, int]
    cast: SceneCast
    vessels: dict[str, str]
    event: str
    account: str
    kind: Literal["sex"] = "sex"
    action: None = None
    phase: Literal["invited", "accepted", "declined", "effects", "complete"] = "invited"
    consent_event: str | None = None
    consent_account: str = ""
    effect_event: str | None = None
    completed_event: str | None = None


class AMPerformance(Model):
    id: str
    source: str
    actor: ActorRef
    controller: int
    account: str
    event: str


def am_sources(state: GameState) -> tuple[UnrolledAMSex, ...]:
    return tuple(
        UnrolledAMSex.model_validate_json(item["body"])
        for item in state.facts
        if item.get("kind") == "changeling_am_sex"
    )


def am_source(state: GameState, identity: str) -> UnrolledAMSex:
    found = next((item for item in am_sources(state) if item.id == identity), None)
    if found is None:
        raise ValueError("Recover the genuine no-extra-roll AM source")
    return found


def performances(state: GameState) -> tuple[AMPerformance, ...]:
    return tuple(
        AMPerformance.model_validate_json(item["body"])
        for item in state.facts
        if item.get("kind") == "changeling_am_performance"
    )


def put_am(state: GameState, value: UnrolledAMSex | AMPerformance) -> None:
    kind = "changeling_am_sex" if isinstance(value, UnrolledAMSex) else "changeling_am_performance"
    state.facts = [
        item
        for item in state.facts
        if not (item.get("kind") == kind and item.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))
