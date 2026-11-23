"""State and Core guard for an original Sentinel's Withdraw Into Your Shell."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, tier
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Asset, Cell, Gorgon, World
from girlframe.engine.rolls import Face

PLAY = "sentinel_withdraw"
RELEASE = "sentinel_release"
RULE = "gorgon-type.sentinel.withdraw-into-your-shell"
KIND = "sentinel_shell"
OPTIONS = ("trapped", "cockpit", "void")


class Roll(Model):
    faces: tuple[Face, Face]
    heat: int = Field(ge=0)
    event: str

    @property
    def result(self) -> Literal["low", "mid", "high"]:
        return tier(sum(self.faces) + self.heat)


class Ensnarement(Model):
    action: str
    scene: str
    source: ActorRef
    girl: ActorRef
    origin: Cell
    roll: Roll
    effects: tuple[Literal["trapped", "cockpit", "void"], ...]
    event: str
    shell_asset: str | None = None
    frame_instance: str | None = None
    void_asset: str | None = None
    void_event: str | None = None
    void_work: str | None = None
    released: str | None = None


def records(state: GameState) -> tuple[Ensnarement, ...]:
    return tuple(
        Ensnarement.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def put(state: GameState, value: Ensnarement) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.action)]
    state.facts.append(dict(kind=KIND, id=value.action, body=value.model_dump_json()))


def nearest(source: ActorView, present: tuple[ActorView, ...]) -> tuple[ActorRef, ...]:
    if source.cell is None:
        return ()
    sx, sy = source.cell
    distances = {
        girl.ref: abs(girl.cell[0] - sx) + abs(girl.cell[1] - sy)
        for girl in present
        if girl.ref.kind == "pilot"
        and girl.rules == "girl_frame"
        and girl.alive
        and girl.offstage_source is None
        and girl.cell is not None
    }
    closest = min(distances.values(), default=None)
    return tuple(actor for actor, distance in distances.items() if distance == closest)


def active(state: GameState) -> tuple[Ensnarement, ...]:
    if state.world is None:
        return ()
    living = {x.id: x for x in state.world.gorgons if x.alive and "sentinel" in x.types}
    return tuple(
        value
        for value in records(state)
        if value.released is None
        and any(x in value.effects for x in ("trapped", "cockpit"))
        and (body := living.get(value.source.entity)) is not None
        and (
            value.shell_asset is None
            or body.shell_asset == value.shell_asset
            and shell_intact(body)
        )
    )


def holds(state: GameState, actor: ActorRef, kind: str) -> bool:
    return any(x.girl == actor and kind in x.effects for x in active(state))


def release(state: GameState, source: ActorRef, girl: ActorRef, scene: str, event: str) -> None:
    candidates = [x for x in active(state) if (x.source, x.girl, x.scene) == (source, girl, scene)]
    if len(candidates) != 1:
        raise ValueError("Choose the original Sentinel's single active captive in this scene")
    put(state, candidates[0].model_copy(update=dict(released=event)))


def shell_intact(body: Gorgon) -> bool:
    return body.shell_asset is not None and any(
        x.id == body.shell_asset and not x.damaged for x in body.assets
    )


def close(world: World, source: ActorRef, action: str) -> tuple[World, str]:
    body = next((x for x in world.gorgons if x.id == source.entity and x.alive), None)
    if (
        source.kind != "gorgon"
        or body is None
        or "sentinel" not in body.types
        or shell_intact(body)
    ):
        raise ValueError("Only the original living Sentinel can close a new actual shell")
    identity = "sentinel-shell:" + action
    shell = Asset(
        id=identity,
        family="gorgon",
        name="Sentinel shell",
        description="The original intact barrier closing over the Sentinel's Core",
    )
    closed = body.model_copy(
        update=dict(shell_asset=identity, assets=(*body.assets, shell), exposed=False)
    )
    return update(
        world, gorgons=tuple(closed if x.id == body.id else x for x in world.gorgons)
    ), identity
