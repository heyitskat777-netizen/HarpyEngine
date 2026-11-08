"""Source-owned legal designations; personal identity and natural Status remain owned."""

from typing import Any, Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "handler-advancement.handler-advancement.gender-designation-request"
Gender = Literal["man", "woman", "animal"]


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Designation(Model):
    id: str
    acquisition: str
    actor: ActorRef
    gender: Gender
    event: str
    controller: int
    account: str = Field(min_length=1, max_length=1200)


class SpeechNo(Model):
    id: str
    speaker: ActorRef
    man: ActorRef
    speaker_designation: str
    man_designation: str
    handler: ActorRef
    appointment: str
    scene: str
    cast: SceneCast
    event: str
    account: str = Field(min_length=1, max_length=1800)
    action: str | None = None
    punishment: str


class AnimalGift(Model):
    id: str
    action: str
    animal: ActorRef
    target: ActorRef
    designation: str
    event: str
    tag: str | None = None
    tag_event: str | None = None


class ManPairedWork(Model):
    id: str
    action: str
    marker: ActorRef
    owner: ActorRef
    controller: int
    designation: str
    relation: str
    paired: str
    slot: int | None
    tag: str
    label: str
    already_marked: bool
    event: str


class ManPairedDecision(Model):
    id: str
    work: str
    choice: str
    marker: ActorRef
    controller: int
    convert: bool
    event: str


def paired_works(state: GameState) -> tuple[ManPairedWork, ...]:
    return tuple(
        ManPairedWork.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "gender_man_paired_work"
    )


def paired_decisions(state: GameState) -> tuple[ManPairedDecision, ...]:
    return tuple(
        ManPairedDecision.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "gender_man_paired_decision"
    )


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "gender_designation_acquisition"
    )


def designations(state: GameState) -> tuple[Designation, ...]:
    return tuple(
        Designation.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "gender_designation"
    )


def speeches(state: GameState) -> tuple[SpeechNo, ...]:
    return tuple(
        SpeechNo.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "gender_spoken_no"
    )


def gifts(state: GameState) -> tuple[AnimalGift, ...]:
    return tuple(
        AnimalGift.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "gender_animal_gift"
    )


def put(
    state: GameState,
    value: Acquisition | Designation | SpeechNo | AnimalGift | ManPairedWork | ManPairedDecision,
) -> None:
    kind = {
        Acquisition: "gender_designation_acquisition",
        Designation: "gender_designation",
        SpeechNo: "gender_spoken_no",
        AnimalGift: "gender_animal_gift",
        ManPairedWork: "gender_man_paired_work",
        ManPairedDecision: "gender_man_paired_decision",
    }[type(value)]
    if not isinstance(value, AnimalGift) and any(
        x.get("kind") == kind and x.get("id") == value.id for x in state.facts
    ):
        raise ValueError("Preserve the actual original legal-designation source")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def current(state: GameState, actor: ActorRef) -> Designation | None:
    return next((x for x in reversed(designations(state)) if x.actor == actor), None)


def presentation(state: GameState, actor: ActorRef) -> dict[str, str | None]:
    value = current(state, actor)
    return dict(
        legal_gender=value.gender if value else None,
        legal_pronouns={"man": "he/him", "woman": "she/her"}.get(value.gender) if value else None,
    )


def man_floor(action: dict[str, Any]) -> int | None:
    return 11 if action["data"].get("gender_man", {}).get("applied") else None
