"""The saved Rebel pilot, base, cockpit proof and actual strafing pass."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_leviathan_arrival import external_pose
from girlframe.engine.m3_world import distance
from girlframe.engine.m3_world_state import AdversaryPilot, Cell, Location

RULE = "strain.rebellion.low.2.1"
KIND = "strain_rebel_strafe"


class Pass(Model):
    id: str
    source: str
    period: str
    actor: ActorRef
    controller: int
    handler: ActorRef
    base: str
    account: str = Field(min_length=1, max_length=1200)
    pose_event: str | None = None
    pose_account: str | None = None
    pose_cell: Cell | None = None
    pose_review: str | None = None
    performance: str | None = None
    scene: str | None = None
    origin: Cell | None = None
    destination: Cell | None = None
    asset: str | None = None
    action_account: str | None = None


def passes(state: GameState) -> tuple[Pass, ...]:
    return tuple(Pass.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def save(state: GameState, case: Pass) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.id)] + [
        dict(kind=KIND, id=case.id, body=case.model_dump_json())
    ]


def source(
    state: GameState, pilot_id: str | None, base_id: str | None
) -> tuple[AdversaryPilot, Location]:
    world = state.world
    pilot = next((x for x in world.pilots if x.id == pilot_id), None) if world else None
    base = next((x for x in world.locations if x.id == base_id), None) if world else None
    if (
        world is None
        or pilot is None
        or not pilot.alive
        or pilot.kind != "rebel"
        or pilot.custody != "free"
        or not any(x.id == pilot.faction and x.kind == "rebel" and x.active for x in world.factions)
        or base is None
        or base.kind != "base"
        or not base.foundation_operational
    ):
        raise ValueError("Choose an actual free Rebel Pilot and an operational Foundation base")
    return pilot, base


def destinations(state: GameState, actor: ActorRef, base: Location) -> tuple[Cell, ...]:
    pose = external_pose(state, actor)
    if state.world is None or pose is None or pose.mode != "piloting" or pose.girl_cell is None:
        return ()
    start = pose.girl_cell
    if distance(start, base.cell) != 1:
        return ()
    return tuple(
        cell
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        if (dx, dy) != (0, 0)
        and state.world.board.contains(cell := (start[0] + dx, start[1] + dy))
        and distance(cell, base.cell) == 1
    )
