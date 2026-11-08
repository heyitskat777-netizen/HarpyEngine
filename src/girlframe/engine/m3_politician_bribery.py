"""Real political contacts, authored NPC Bonds and source-owned Strings (PDF156/154)."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_world_state import Npc

RULE = "handler-advancement.handler-advancement.politician-bribery-fund"
SPHERES = (
    "healthcare",
    "human_rights",
    "broadcasting",
    "transportation",
    "warfare_against",
    "warfare_for",
)
LABELS = (
    "Healthcare",
    "Human Rights & Dignity",
    "Public Broadcasting",
    "Transportation",
    "Warfare (against)",
    "Warfare (for)",
)
JOB_LOSS = "strain.budget.low.6.2"


class Politician(Model):
    city: str
    npc: Npc


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)
    cadre: tuple[ActorRef, ...]
    politicians: tuple[Politician, ...]
    cities: tuple[str, ...]


class Assignment(Model):
    id: str
    acquisition: str
    npc: str
    sphere: str
    actor: ActorRef
    feelings: str = Field(min_length=1, max_length=500)
    event: str


class Aid(Model):
    id: str
    acquisition: str
    assignment: str
    actor: ActorRef
    npc: str
    cast: SceneCast
    activity: str = Field(min_length=1, max_length=1200)
    benefit: str = Field(min_length=1, max_length=1200)
    action: str | None = None
    judge: int
    judge_source: str | None
    event: str


class Earned(Model):
    id: str
    acquisition: str
    aid: str
    npc: str
    judge: int
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Causation(Model):
    id: str
    acquisition: str
    work: str
    work_event: str
    work_revision: int
    original: Npc
    choice_json: str
    cause_kind: Literal["pilot_play", "handler_play"]
    cause: str
    cause_event: str
    account: str = Field(min_length=1, max_length=1200)
    event: str


class Reservation(Model):
    id: str
    acquisition: str
    cause: str
    politician: str
    string: str
    event: str


class Cashout(Model):
    id: str
    acquisition: str
    politician: str
    kind: Literal["budget", "tag", "scapegoat"]
    strings: tuple[str, ...]
    event: str
    account: str = Field(min_length=1, max_length=1200)
    target: str | None = None
    tag: str | None = None
    reservation: str | None = None


KINDS: dict[type[Model], str] = {
    Acquisition: "bribery_acquisition",
    Assignment: "bribery_assignment",
    Aid: "bribery_aid",
    Earned: "bribery_string",
    Causation: "bribery_causation",
    Reservation: "bribery_reservation",
    Cashout: "bribery_cashout",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind = KINDS[type(value)]
    identity = value.model_dump()["id"]
    if any(x.get("kind") == kind and x.get("id") == identity for x in state.facts):
        raise ValueError("Preserve the immutable original political source")
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return records(state, Acquisition)


def available(state: GameState, acquisition: str, politician: str) -> tuple[Earned, ...]:
    used = {s for x in records(state, Cashout) for s in x.strings}
    used.update(x.string for x in records(state, Reservation))
    return tuple(
        x
        for x in records(state, Earned)
        if x.acquisition == acquisition and x.npc == politician and x.id not in used
    )


def complete_assignments(state: GameState, source: Acquisition) -> bool:
    rows = [x for x in records(state, Assignment) if x.acquisition == source.id]
    return {x.npc for x in rows} == {x.npc.id for x in source.politicians} and {
        x.sphere for x in rows
    } == set(SPHERES)
