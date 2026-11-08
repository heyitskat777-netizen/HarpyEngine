"""Actual unchaperoned proposals and separate physical movement receipts."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "girl.vatgrown.just-an-experiment"


class Proposal(Model):
    actor: ActorRef
    controller: int
    channel: int
    scene: str
    cast: SceneCast | None
    participants: tuple[int, ...]
    origin: tuple[int, int]
    destination: tuple[int, int]
    frame: bool
    mode: str | None
    vessel_id: str | None
    frame_instance: str | None
    position_sha256: str | None
    source_sha256: str
    revision: int
    account: str


class Attempt(Model):
    id: str
    proposal: Proposal
    origin_bases: tuple[str, ...]
    destination_bases: tuple[str, ...]
    violation: str
    event: str


class Movement(Model):
    id: str
    attempt: str
    proposal: Proposal
    event: str


class ChaperonedProposal(Model):
    id: str
    owner: Proposal
    companion_snapshot: Proposal
    policy_sha256: str
    mutual: bool
    mutual_required: bool
    event: str


class ChaperonedResponse(Model):
    id: str
    source: str
    kind: Literal["accepted", "declined", "cancelled"]
    controller: int
    account: str
    mutual: bool
    proposal: Proposal | None = Field(default=None, exclude_if=lambda value: value is None)
    event: str


class JointMovement(Model):
    id: str
    source: str
    response: str
    owner: Proposal
    companion: Proposal
    event: str


KINDS: dict[type[Model], str] = {
    Attempt: "vatgrown_travel_attempt",
    Movement: "vatgrown_travel_movement",
    ChaperonedProposal: "vatgrown_chaperoned_proposal",
    ChaperonedResponse: "vatgrown_chaperoned_response",
    JointMovement: "vatgrown_joint_movement",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(fact["body"])
        for fact in state.facts
        if fact.get("kind") == KINDS[model]
    )


def get[T: Model](state: GameState, model: type[T], identity: str) -> T:
    matches = [value for value in records(state, model) if value.model_dump()["id"] == identity]
    if len(matches) != 1:
        raise ValueError("Recover the original actual travel source")
    return matches[0]


def put(
    state: GameState,
    value: Attempt | Movement | ChaperonedProposal | ChaperonedResponse | JointMovement,
) -> None:
    if any(
        fact.get("id") == value.id and fact.get("kind") == KINDS[type(value)]
        for fact in state.facts
    ):
        raise ValueError("The immutable travel source already exists")
    state.facts.append(dict(kind=KINDS[type(value)], id=value.id, body=value.model_dump_json()))


def bases(state: GameState, cell: tuple[int, int]) -> tuple[str, ...]:
    if state.world is None:
        raise ValueError("Use the actual mapped Foundation base endpoints")
    return tuple(
        sorted(
            location.id
            for location in state.world.locations
            if location.cell == cell
            and location.kind == "base"
            and location.allegiance == "foundation"
            and location.condition != "destroyed"
        )
    )


def outside(state: GameState, proposal: Proposal) -> bool:
    if proposal.origin == proposal.destination:
        return False  # Same-cell interior/exit geometry has no supported producer.
    origin, destination = bases(state, proposal.origin), bases(state, proposal.destination)
    if origin and destination and not set(origin).intersection(destination):
        raise ValueError(
            "TRAVEL_ROUTE_REQUIRED: distinct bases need an actual proved intervening journey"
        )
    return not (origin and destination)
