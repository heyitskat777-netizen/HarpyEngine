"""A dead Vatgrown's successor is another person, with separately sourced equipment."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_career_state import CareerArchive
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_vatgrown_plays import EXPERIMENT

RULE = EXPERIMENT


class Replacement(Model):
    id: str
    archive: str
    original: ActorRef
    new_actor: ActorRef
    started_event: str
    handler: ActorRef
    handler_controller: int
    activated_event: str | None = None


class KitRequest(Model):
    id: str
    replacement: str
    actor: ActorRef
    profile_revision: int
    fingerprint: str
    review_json: str
    event: str


class Issue(Model):
    id: str
    replacement: str
    request: str
    actor: ActorRef
    handler: ActorRef
    controller: int
    frame_instance: str
    body_vessel: str
    cell: tuple[int, int]
    account: str = Field(min_length=1, max_length=1200)
    event: str


class Notice(Model):
    id: str
    replacement: str
    recipient: ActorRef
    controller: int
    event: str
    answer: Literal["yes", "no", "uncertain"] | None = None
    account: str | None = None
    response_event: str | None = None


def identity(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:vatgrown-death:" + ":".join(parts)))


def required(archive: CareerArchive) -> bool:
    old = PilotSheet.model_validate_json(archive.sheet_json)
    return (
        archive.ending in ("death", "execution")
        and old.girl == "VATGROWN"
        and has_rule(old, RULE, "VATGROWN")
    )


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    kinds = {
        Replacement: "vatgrown_replacement",
        KitRequest: "vatgrown_kit_request",
        Issue: "vatgrown_kit_issue",
        Notice: "vatgrown_replacement_notice",
    }
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == kinds[model]
    )


def put(state: GameState, value: Replacement | KitRequest | Issue | Notice) -> None:
    kinds = {
        Replacement: "vatgrown_replacement",
        KitRequest: "vatgrown_kit_request",
        Issue: "vatgrown_kit_issue",
        Notice: "vatgrown_replacement_notice",
    }
    kind = kinds[type(value)]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def activation_source(state: GameState, actor: ActorRef) -> Replacement | None:
    from girlframe.engine.m3_careers import binding

    current = binding(state, int(actor.entity)) if actor.kind == "pilot" else None
    archive = next(
        (x for x in state.career_archives if current and x.id == current.previous_archive), None
    )
    values = [x for x in records(state, Replacement) if x.new_actor == actor]
    if archive and required(archive):
        if (
            len(values) != 1
            or values[0].archive != archive.id
            or values[0].original != archive.actor
            or current is None
            or current.character != actor.incarnation
        ):
            raise ValueError("Recover the genuine distinct Vatgrown replacement source")
        return values[0]
    if values:
        raise ValueError("A replacement record cannot invent an original Vatgrown death")
    return None
