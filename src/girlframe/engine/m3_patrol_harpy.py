"""One actual Low Void patrol sighting; its die grants no attack, escape or healing."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_world_state import AdversaryPilot
from girlframe.engine.rolls import Face

RULE = "strain.void.low.3.1"
MOODS = ("watching", "laughing", "singing", "ready to flee", "regrowing", "preparing for attack")


class Encounter(Model):
    id: str
    work: str
    source_event: str
    handler: ActorRef
    controller: int
    observer: ActorRef
    observer_controller: int
    observer_vessel: str
    observer_position: str
    harpy: ActorRef
    harpy_body: AdversaryPilot
    harpy_vessel: str
    harpy_position: str
    cast: SceneCast
    account: str
    event: str


class Sighting(Model):
    id: str
    encounter: str
    work: str
    face: Face
    rng_source: Literal["os", "test_injected"]
    event: str

    @property
    def mood(self) -> str:
        return MOODS[self.face - 1]


def identity(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:patrol-harpy:" + ":".join(parts)))


KINDS: dict[type[Model], str] = {
    Encounter: "patrol_harpy_encounter",
    Sighting: "patrol_harpy_sighting",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def get[T: Model](state: GameState, model: type[T], key: str) -> T:
    matches = [x for x in records(state, model) if x.model_dump()["id"] == key]
    if len(matches) != 1:
        raise ValueError("Recover the actual original patrol sighting")
    return matches[0]


def put(state: GameState, value: Encounter | Sighting) -> None:
    if any(x.model_dump()["id"] == value.id for x in records(state, type(value))):
        raise ValueError("Preserve the original immutable patrol fact")
    state.facts.append(dict(kind=KINDS[type(value)], id=value.id, body=value.model_dump_json()))
