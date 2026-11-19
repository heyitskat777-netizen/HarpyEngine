"""The original Cadre's saved traversal roll and its actual discovered route."""

from girlframe.engine.m2 import GameState, tier
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "situational.situational.voidspace-invasion"
KIND = "voidspace_invasion"


class Traversal(Model):
    actor: ActorRef
    controller: int
    travel: str


class Encounter(Model):
    source: str
    actor: ActorRef
    label: str
    event: str
    account: str


class Gain(Model):
    actor: ActorRef
    event: str
    asset: str | None = None
    work: str | None = None


class Invasion(Model):
    id: str
    rift: str
    scene: str
    gm: int
    appointment: str
    cadre: tuple[Traversal, ...]
    ace: ActorRef
    faces: tuple[int, int]
    void_assets: tuple[str, ...]
    account: str
    route: str | None = None
    discovery: str | None = None
    encounter: Encounter | None = None
    gains: tuple[Gain, ...] = ()

    @property
    def result(self) -> str:
        return tier(sum(self.faces) + len(self.void_assets))


def records(state: GameState) -> tuple[Invasion, ...]:
    return tuple(
        Invasion.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def put(state: GameState, value: Invasion) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))
