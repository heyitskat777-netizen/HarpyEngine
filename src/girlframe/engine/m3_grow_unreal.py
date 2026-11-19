"""The Growth Gorgon's actual sacrificed Asset and source-owned reach choices."""

from typing import Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Gorgon, World

PLAY = "grow_unreal"
RULE = "gorgon-type.growth.grow-unreal"
KIND = "growth_unreal"
Option = Literal[
    "distance",
    "cockpit",
    "fill_square",
    "reinforce",
    "voidspace",
    "tree",
    "underground",
    "thoughts",
    "time",
    "within",
]
OPTIONS: dict[Option, str] = {
    "distance": "Cross the intervening space",
    "cockpit": "Grow into the original cockpit",
    "fill_square": "Fill the current quadrant square",
    "reinforce": "Reinforce the original Core",
    "voidspace": "Grow sideways into the Void",
    "tree": "Grow upwards into branches",
    "underground": "Root yourself underground",
    "thoughts": "Enter conceptual space and cause Void",
    "time": "Grow backwards in time",
    "within": "Grow inside the original Girl",
}


class Episode(Model):
    action: str
    scene: str
    source: ActorRef
    girl: ActorRef
    sacrificed: str
    event: str
    roll: Roll | None = None
    options: tuple[Option, ...] = ()
    account: str | None = None
    effect_event: str | None = None
    void_asset: str | None = None
    void_event: str | None = None
    void_work: str | None = None
    damaged_asset: str | None = None
    frame_instance: str | None = None
    completed: str | None = None


def get(state: GameState, action: str) -> Episode:
    raw = next(
        (x["body"] for x in state.facts if x.get("kind") == KIND and x.get("id") == action), None
    )
    if raw is None:
        raise ValueError("Recover the original paid Grow Unreal source")
    return Episode.model_validate_json(raw)


def put(state: GameState, value: Episode) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.action)]
    state.facts.append(dict(kind=KIND, id=value.action, body=value.model_dump_json()))


def available_assets(body: Gorgon) -> tuple[str, ...]:
    layers = set(body.flesh_layers or ())
    return tuple(x.id for x in body.assets if x.id not in layers)


def original_target(source: ActorView, girl: ActorView) -> bool:
    return bool(
        source.ref.kind == "gorgon"
        and source.alive
        and source.cell is not None
        and source.offstage_source is None
        and girl.ref.kind == "pilot"
        and girl.alive
        and girl.rules == "girl_frame"
        and girl.offstage_source is None
        and girl.cell is not None
    )


def sacrifice(world: World, source: ActorRef, asset: str) -> World:
    body = next((x for x in world.gorgons if x.id == source.entity and x.alive), None)
    if (
        source.kind != "gorgon"
        or body is None
        or "growth" not in body.types
        or asset not in available_assets(body)
    ):
        raise ValueError("Sacrifice one actual original Growth Asset")
    shed = next(x for x in body.assets if x.id == asset)
    changed = body.model_copy(
        update=dict(
            assets=tuple(x for x in body.assets if x.id != asset),
            destroyed_assets=(*body.destroyed_assets, shed.model_copy(update=dict(damaged=True))),
        )
    )
    return update(world, gorgons=tuple(changed if x.id == body.id else x for x in world.gorgons))
