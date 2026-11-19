"""The Chained Darling's permanent limitations follow the original physical pose."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_ancillary import find
from girlframe.engine.m3_leviathan_arrival import external_pose

RULE = "ancillary.chained-darling.inherently-dangerous"
KIND = "chained_pose_enabled"


def helpless(state: GameState, actor: ActorRef) -> bool:
    role = find(state, actor)
    if role is None or role.draft.book != "CHAINED DARLING":
        return False
    pose = external_pose(state, actor)
    return bool(
        pose
        and pose.mode == "outside_frame"
        and pose.owner == role.controller
        and state.world
        and any(
            body.id == actor.entity and body.alive and body.controller == role.controller
            for body in state.world.pilots
        )
        and any(
            x.get("kind") == KIND
            and x.get("actor") == actor.token
            and x.get("source") == pose.source_event
            for x in state.facts
        )
    )
