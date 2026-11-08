"""Low obsession records real completed movement; it never grants teleportation/control."""

import json
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_leviathan_arrival_state import (
    ArrivalRequirement,
    ExternalPose,
    LeviathanArrival,
)
from girlframe.engine.m3_leviathan_obsession import _harpy, subject_ref
from girlframe.engine.m3_world_state import Cell


def external_pose(state: GameState, actor: ActorRef) -> ExternalPose | None:
    return next((x for x in state.external_poses if x.actor == actor), None)


def body_pose(state: GameState, actor: ActorRef) -> LeviathanArrival | None:
    actor = subject_ref(state, actor)
    return next((x for x in state.leviathan_arrivals if x.actor == actor), None)


def install_external_pose(
    original: GameState,
    actor: ActorRef,
    girl_cell: Cell | None,
    frame_cell: Cell | None,
    mode: Literal["outside_frame", "inside_frame", "piloting"],
    event: str,
    account: str,
    *,
    owner: int,
    judge: int,
) -> GameState:
    if actor.kind != "external_pilot" or _harpy(original, actor) or original.world is None:
        raise ValueError("Review only an existing Foundation/Rebel Girl's actual current pose")
    actual = resolve(original, actor, ())
    body = next(x for x in original.world.pilots if x.id == actor.entity)
    if body.kind not in ("foundation", "rebel") or actual.controller != owner or judge <= 0:
        raise ValueError("Use this original body's actual owner and source judge")
    if external_pose(original, actor) is not None:
        raise ValueError("Never reset an existing physical authority with factual setup")
    if mode not in ("outside_frame", "inside_frame", "piloting") or not account.strip():
        raise ValueError("Record actual current occupancy and a factual account")
    pose = ExternalPose(
        actor=actor,
        vessel=str(uuid5(NAMESPACE_URL, "original-external-body:" + actor.token)),
        frame=actual.frame_instance or "initial:" + actor.entity,
        girl_cell=girl_cell,
        frame_cell=frame_cell,
        mode=mode,
        source_event=event,
        position_event=event,
        owner=owner,
        judge=judge,
        account=account,
    )
    state = GameState.model_validate_json(original.model_dump_json())
    state.external_poses.append(pose)
    state.facts.append(
        dict(
            kind="external_pose_factual",
            actor=actor.model_dump_json(),
            event=event,
            body=pose.model_dump_json(),
        )
    )
    return GameState.model_validate_json(state.model_dump_json())


def requirements(
    state: GameState,
    actor: ActorRef,
    source: ActorRef,
    bindings: tuple[ProfileBinding, ...] = (),
) -> ArrivalRequirement:
    from girlframe.engine.m3_frame_control import controller
    from girlframe.engine.m3_passengers import passenger_view

    actual = resolve(state, actor, bindings, require_current_profile=False)
    endpoint = resolve(state, source, (), require_alive=False)
    if (
        source.kind != "gorgon"
        or source == actor
        or state.world is None
        or not any(x.id == source.entity and "leviathan" in x.types for x in state.world.gorgons)
    ):
        raise ValueError("Follow the actual original source Leviathan's trail")
    blocker = (
        "actual_rift_route_required" if actual.offstage_source or endpoint.offstage_source else None
    )
    frame_owner, frame = None, None
    passenger = passenger_view(state, actor)
    if passenger is not None:
        frame_owner, frame = passenger.carrier, passenger.frame
    elif actor.kind == "pilot":
        placed = next((x for x in state.placements if x.actor == actor), None)
        if placed is None:
            blocker = "actual_original_pilot_pose_required"
        elif placed.mode != "outside_frame":
            frame_owner = placed.occupied_frame_owner or actor
            frame = placed.occupied_frame_instance or placed.frame_instance
    elif _harpy(state, actor):
        from girlframe.engine.m3_harpy_defeat import harpy

        current = harpy(state, actor)
        if current.custody == "core":
            if hasattr(current, "core_frame_owner"):
                frame_owner = current.core_frame_owner
                frame = getattr(current, "core_frame_instance", None)
            else:
                frame_owner = getattr(current, "frame_owner", None)
                frame = getattr(current, "frame_instance", None)
        elif current.linked:
            frame_owner, frame = actor, current.frame_instance
    elif actor.kind == "external_pilot":
        pose = external_pose(state, actor)
        if pose is None:
            blocker = "actual_external_pose_required"
        elif pose.mode != "outside_frame":
            frame_owner, frame = actor, pose.frame
    mover = controller(state, frame_owner, frame, bindings) if frame_owner and frame else actor
    if frame_owner and mover is None:
        blocker = blocker or "actual_frame_control_required"
    if not frame_owner and (actual.vitals_active is False or actual.subsumed):
        blocker = blocker or "actual_extraction_or_help_required"
    if actual.custody not in (None, "free") and not frame_owner:
        blocker = blocker or "actual_custodian_transport_required"
    mover_view = resolve(state, mover, bindings, require_current_profile=False) if mover else None
    return ArrivalRequirement(
        actor=actor,
        source=source,
        mover=mover,
        frame_owner=frame_owner,
        frame=frame,
        destination=endpoint.cell,
        actor_position=actual.position_sha256 or actual.source_sha256,
        source_position=endpoint.position_sha256 or endpoint.source_sha256,
        mover_position=(mover_view.position_sha256 or mover_view.source_sha256)
        if mover_view
        else None,
        blocker=blocker,
        attestors=tuple(dict.fromkeys((actor, mover))) if mover else (actor,),
    )


def _move_body(
    state: GameState, actor: ActorRef, cell: Cell | None, event: str, account: str
) -> GameState:
    """Apply attested body movement without relocating its parked assigned Frame."""
    if actor.kind == "pilot":
        state.placements = [
            x.model_copy(update={"girl_cell": cell, "source_event": event, "account": account})
            if x.actor == actor
            else x
            for x in state.placements
        ]
    elif _harpy(state, actor):
        from girlframe.engine.m3_harpy_defeat import update

        state = update(state, actor, cell=cell, physical_source_event=event)
    elif actor.kind == "external_pilot":
        state.external_poses = [
            x.model_copy(update={"girl_cell": cell, "position_event": event, "account": account})
            if x.actor == actor
            else x
            for x in state.external_poses
        ]
    elif actor.kind == "gorgon":
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "gorgons": tuple(
                    x.model_copy(update={"cell": cell, "position_event": event})
                    if x.id == actor.entity
                    else x
                    for x in state.world.gorgons
                )
            }
        )
    elif actor.kind == "npc" and cell is not None:
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"cell": cell}) if x.id == actor.entity else x
                    for x in state.world.npcs
                )
            }
        )
    return state


def _move_frame(
    state: GameState, owner: ActorRef, frame: str, cell: Cell | None, event: str, account: str
) -> GameState:
    """The actual Frame carries its existing occupants; other assigned Frames stay put."""
    if owner.kind == "pilot":
        state.placements = [
            x.model_copy(
                update={
                    **(
                        {"frame_cell": cell}
                        if x.actor == owner and x.frame_instance == frame
                        else {}
                    ),
                    **(
                        {"girl_cell": cell}
                        if (
                            (
                                x.actor == owner
                                and x.frame_instance == frame
                                and x.mode != "outside_frame"
                            )
                            or (
                                x.occupied_frame_owner == owner
                                and x.occupied_frame_instance == frame
                            )
                        )
                        else {}
                    ),
                    "source_event": event,
                    "account": account,
                }
            )
            if (x.actor == owner and x.frame_instance == frame)
            or (x.occupied_frame_owner == owner and x.occupied_frame_instance == frame)
            else x
            for x in state.placements
        ]
    elif _harpy(state, owner):
        from girlframe.engine.m3_harpy_defeat import harpy, update

        body = harpy(state, owner)
        state = update(
            state,
            owner,
            frame_cell=cell,
            physical_source_event=event,
            **({"cell": cell} if body.linked else {}),
        )
    elif owner.kind == "external_pilot":
        state.external_poses = [
            x.model_copy(
                update={
                    "frame_cell": cell,
                    **({"girl_cell": cell} if x.mode != "outside_frame" else {}),
                    "position_event": event,
                    "account": account,
                }
            )
            if x.actor == owner and x.frame == frame
            else x
            for x in state.external_poses
        ]
    else:
        raise ValueError("Move only the actual source-proven carrier Frame")
    return state


def arrive(
    original: GameState,
    requirement: ArrivalRequirement,
    event: str,
    account: str,
    *,
    source_action: str,
    bindings: tuple[ProfileBinding, ...] = (),
    already_at_endpoint: bool = False,
) -> GameState:
    """Commit an actually completed, owner/mover/judge-attested source arrival.

    The service owns those human attestations. This reducer re-proves the frozen
    positions and actual control; it supplies no permission to travel or extract.
    """
    if not event.strip() or not account.strip() or not source_action.strip():
        raise ValueError("Record the actual source action, arrival event and factual account")
    current = requirements(original, requirement.actor, requirement.source, bindings)
    if current != requirement:
        raise ValueError("STALE_POSITION: refresh the actual body, source and mover facts")
    if requirement.blocker or requirement.mover is None:
        raise ValueError(requirement.blocker or "Actual mover facts are required")
    if requirement.method != "self":
        raise ValueError("Use an actual completed custody/transport source before this arrival")
    actual = resolve(original, requirement.actor, bindings, require_current_profile=False)
    destination = requirement.destination
    if already_at_endpoint:
        if actual.cell is not None and destination is not None and actual.cell != destination:
            raise ValueError("Known different positions contradict already being at this endpoint")
        destination = actual.cell
    state = GameState.model_validate_json(original.model_dump_json())
    if any(x.arrival_event == event for x in state.leviathan_arrivals):
        raise ValueError("This actual arrival event was already applied")
    if requirement.frame_owner and requirement.frame:
        state = _move_frame(
            state, requirement.frame_owner, requirement.frame, destination, event, account
        )
    state = _move_body(state, requirement.actor, destination, event, account)
    normalized = subject_ref(state, requirement.actor)
    arrival = LeviathanArrival(
        actor=normalized,
        source=requirement.source,
        mover=requirement.mover,
        cell=destination,
        frame_owner=requirement.frame_owner,
        frame=requirement.frame,
        source_action=source_action,
        arrival_event=event,
        position_event=event,
        custody=actual.custody,
        account=account,
        already_at_endpoint=already_at_endpoint,
    )
    state.leviathan_arrivals = [x for x in state.leviathan_arrivals if x.actor != normalized] + [
        arrival
    ]
    state.facts.append(
        dict(
            kind="leviathan_actual_arrival",
            actor=normalized.model_dump_json(),
            source=requirement.source.model_dump_json(),
            cell=json.dumps(destination),
            event=event,
            source_action=source_action,
            requirement=requirement.model_dump_json(),
            body=arrival.model_dump_json(),
            account=account,
        )
    )
    return GameState.model_validate_json(state.model_dump_json())


def record_existing_body_position(
    state: GameState,
    actor: ActorRef,
    cell: Cell | None,
    event: str,
    account: str,
) -> GameState:
    """Called by an actual existing movement/release source; no new authority is granted."""
    ref = subject_ref(state, actor)
    state.external_poses = [
        x.model_copy(
            update={
                "girl_cell": cell,
                "position_event": event,
                "account": account,
                **(
                    {"mode": "outside_frame"}
                    if any(
                        p.actor == actor and p.state == "left" and p.left_event == event
                        for p in state.passengers
                    )
                    else {}
                ),
            }
        )
        if x.actor == ref
        else x
        for x in state.external_poses
    ]
    state.leviathan_arrivals = [
        x.model_copy(
            update={
                "cell": cell,
                "position_event": event,
                "account": account,
            }
        )
        if x.actor == ref
        else x
        for x in state.leviathan_arrivals
    ]
    if ref.kind == "handler" and body_pose(state, ref) is not None:
        state.facts.append(
            dict(
                kind="leviathan_actual_arrival",
                actor=ref.model_dump_json(),
                cell=json.dumps(cell),
                event=event,
                account=account,
            )
        )
    return state
