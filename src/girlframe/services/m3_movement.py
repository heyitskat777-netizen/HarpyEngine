"""Record permitted ordinary movement of actual controlled bodies or piloted Frames."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_wyvern import cargo, pinned
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def proposal_context(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    channel: int,
    actor: ActorRef,
    destination: tuple[int, int],
    frame: bool,
    account: str,
) -> dict[str, Any]:
    """Prove an actual possible physical proposal without moving any body."""
    Access(game.store).authorize(c, viewer, "world", director_response=True)
    return _physical_context(
        game, c, state, channel, actor, destination, frame, account, controller=viewer.user_id
    )


def _physical_context(
    game: GameService,
    c: Connection,
    state: GameState,
    channel: int,
    actor: ActorRef,
    destination: tuple[int, int],
    frame: bool,
    account: str,
    *,
    controller: int,
) -> dict[str, Any]:
    """Physical checks only; callers prove live-viewer or canonical source authorization."""
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.p1_facilitator import require_scene_clear
    from girlframe.services.p1_source_pause import require_clear

    game.unpaused(c)
    PhysicalService(game.store)._idle(c)
    require_clear(game, c, channel)
    require_scene_clear(game, c, channel)
    scene = game.scene(c, channel)
    if (
        state.world is None
        or controller not in scene["participants"]
        or not c.scalar(
            sa.select(t.members.c.active).where(
                t.members.c.campaign_id == game.store.campaign_id,
                t.members.c.user_id == str(controller),
            )
        )
        or not account.strip()
        or len(account) > 1200
        or len(destination) != 2
        or any(type(x) is not int for x in destination)
        or not state.world.board.contains(destination)
    ):
        raise WorkflowError("Choose actual current physical movement within the mapped scene")
    bound = profiles(c, game.store.campaign_id)
    actual = resolve(state, actor, bound, require_current_profile=False)
    if (
        actual.controller != controller
        or actual.cell is None
        or actual.offstage_source
        or actual.custody not in (None, "free")
        or is_helpless(state, actor)
        or pinned(state, actor)
    ):
        raise WorkflowError("Resolve genuine custody, Helplessness or the source pin before moving")
    cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
    if cast is not None and not any(
        x.actor == actor and x.controller == controller for x in cast.roles
    ):
        raise WorkflowError("Join this actual role in the source scene first")
    pose = next((x for x in state.placements if x.actor == actor), None)
    external_pose = next((x for x in state.external_poses if x.actor == actor), None)
    if actor.kind == "pilot":
        if (
            pose is None
            or pose.custody
            or pose.incapacitated
            or pose.subsumed
            or not pose.vitals_active
        ):
            raise WorkflowError("Use the real known free body/Frame placement")
        if frame:
            if (
                actual.piloting is not True
                or actual.occupied_frame_instance != actual.frame_instance
                or cargo(state, actor, pose.frame_instance)
            ):
                raise WorkflowError(
                    "Move only the original Frame you actually pilot, after unloading it"
                )
        elif actual.inside_frame is not False:
            raise WorkflowError("Actually exit the cockpit before ordinary movement on foot")
    elif actor.kind == "npc":
        assert state.world is not None
        npc = next(x for x in state.world.npcs if x.id == actor.entity)
        if npc.custody_event and "prisoner" in npc.jobs:
            raise WorkflowError("Resolve this actual Foundation prisoner's custody before moving")
        if npc.source_kind is not None or frame or actual.inside_frame is True:
            raise WorkflowError(
                "This source body needs its actual carrier or software-access adapter"
            )
    elif actor.kind == "gorgon":
        pass
    elif actor.kind == "handler" and not frame and actual.inside_frame is not True:
        pass
    elif actor.kind == "external_pilot":
        if (
            external_pose is None
            or frame
            and external_pose.mode != "piloting"
            or not frame
            and external_pose.mode != "outside_frame"
        ):
            raise WorkflowError("Retain the actual external body's known cockpit and Frame context")
    else:
        raise WorkflowError("This actual body requires its specific movement source adapter")
    return dict(
        actor=actor.model_dump(mode="json"),
        controller=actual.controller,
        channel=channel,
        scene=scene["id"],
        cast=cast.model_dump(mode="json") if cast is not None else None,
        participants=list(scene["participants"]),
        origin=list(actual.cell),
        destination=list(destination),
        frame=frame,
        mode=pose.mode if pose is not None else external_pose.mode if external_pose else None,
        vessel_id=actual.vessel_id,
        frame_instance=actual.frame_instance,
        position_sha256=actual.position_sha256,
        source_sha256=actual.source_sha256,
        revision=state.revision,
        account=account,
    )


def _apply_context(state: GameState, context: dict[str, Any], event: str) -> None:
    """Apply an already authorized and physically validated movement; allocate no source."""
    actor = ActorRef.model_validate_json(json.dumps(context["actor"]))
    destination = tuple(context["destination"])
    frame, account = context["frame"], context["account"]
    assert state.world is not None
    if actor.kind == "pilot":
        pose = next((x for x in state.placements if x.actor == actor), None)
        assert pose is not None
        if frame:
            values = dict(frame_cell=destination, girl_cell=destination)
        else:
            values = dict(girl_cell=destination)
        moved = pose.model_copy(update=values | dict(source_event=event, account=account))
        moved = type(pose).model_validate_json(moved.model_dump_json())
        state.placements = [moved if x.actor == actor else x for x in state.placements]
    elif actor.kind == "npc":
        npc = next(x for x in state.world.npcs if x.id == actor.entity)
        state.world = state.world.model_copy(
            update=dict(
                npcs=tuple(
                    x.model_copy(update=dict(cell=destination)) if x.id == npc.id else x
                    for x in state.world.npcs
                )
            )
        )
    elif actor.kind == "gorgon":
        state.world = state.world.model_copy(
            update=dict(
                gorgons=tuple(
                    x.model_copy(update=dict(cell=destination)) if x.id == actor.entity else x
                    for x in state.world.gorgons
                )
            )
        )
    elif actor.kind == "handler":
        state.facts.append(
            dict(
                kind="ordinary_handler_movement",
                actor=actor.model_dump_json(),
                cell=json.dumps(destination),
                event=event,
                account=account,
            )
        )
    elif actor.kind == "external_pilot":
        external_pose = next((x for x in state.external_poses if x.actor == actor), None)
        assert external_pose is not None
        update = dict(position_event=event, account=account, girl_cell=destination)
        if frame:
            update["frame_cell"] = destination
        state.external_poses = [
            external_pose.model_copy(update=update) if x.actor == actor else x
            for x in state.external_poses
        ]
    else:
        raise WorkflowError("This actual body requires its specific movement source adapter")


class MovementService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "world", director_response=True)
            state = load_state(c, self.store.campaign_id)
            scene = self.game.scene(c, channel)
            if state.world is None or viewer.user_id not in scene["participants"]:
                raise WorkflowError("Use the actual current mapped source scene")
            choices = ActorService(MissionService(self.store)).choices(viewer)["actors"]
            bound = profiles(c, self.store.campaign_id)
            actors = []
            for choice in choices:
                ref = ActorRef.model_validate(choice["ref"])
                actual = resolve(state, ref, bound, require_current_profile=False)
                if actual.controller == viewer.user_id and actual.cell is not None:
                    from girlframe.engine.m3_girl_runtime_state import has_rule

                    sheet = state.sheets.get(ref.entity) if ref.kind == "pilot" else None
                    actors.append(
                        dict(
                            ref=ref.model_dump(mode="json"),
                            id=ref.token,
                            label=actual.label,
                            cell=actual.cell,
                            piloting=actual.piloting,
                            vatgrown=bool(
                                sheet
                                and has_rule(sheet, "girl.vatgrown.just-an-experiment", "VATGROWN")
                            ),
                        )
                    )
            companions = []
            if any(row["vatgrown"] for row in actors):
                from girlframe.services.m3_cast import CastService
                from girlframe.services.m3_dose_up import _cast

                try:
                    actual_cast = _cast(self.game, c, state, channel)
                    visible = {
                        role["token"]: role
                        for role in CastService(ActorService(MissionService(self.store))).view(
                            viewer, channel
                        )["roles"]
                        if not role["stale"]
                    }
                except (ValueError, WorkflowError):
                    actual_cast = None
                    visible = {}
                for role in actual_cast.roles if actual_cast else ():
                    if role.actor.token not in visible:
                        continue
                    try:
                        actual = resolve(state, role.actor, bound, require_current_profile=False)
                    except ValueError:
                        continue
                    if (
                        actual.controller != role.controller
                        or actual.cell is None
                        or actual.vessel_id is None
                        or actual.offstage_source
                        or (
                            role.actor.kind == "npc"
                            and any(
                                npc.id == role.actor.entity and npc.source_kind is not None
                                for npc in state.world.npcs
                            )
                        )
                    ):
                        continue
                    companions.append(
                        dict(
                            id=role.actor.token,
                            label=visible[role.actor.token]["label"],
                            ref=role.actor.model_dump(mode="json"),
                        )
                    )
            return dict(
                revision=state.revision,
                actors=actors,
                companions=companions,
                minimum=state.world.board.minimum,
                maximum=state.world.board.maximum,
                channel=channel,
            )

    def move(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        actor: ActorRef,
        destination: tuple[int, int],
        *,
        frame: bool = False,
        account: str,
        vatgrown_travel: str | None = None,
    ) -> dict[str, Any]:
        actor = ActorRef.model_validate_json(actor.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if type(revision) is not int or state.revision != revision:
                raise WorkflowError(
                    "Choose actual current physical movement within the mapped scene"
                )
            context = proposal_context(
                self.game, c, viewer, state, channel, actor, destination, frame, account
            )
            assert state.world is not None
            from girlframe.services.m3_vatgrown_travel import before_move, stage_movement

            before_move(self.game, c, state, viewer, context, travel=vatgrown_travel)
            before = GameState.model_validate_json(state.model_dump_json())
            event = str(uuid4())
            _apply_context(state, context, event)
            stage_movement(self.game, c, before, state, context, vatgrown_travel, event)
            from girlframe.services.m3_prisoner_escape import stage_movement as stage_escape

            stage_escape(self.game, c, before, state, context, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.physical_moved",
                state,
                event_id=event,
                movement=event,
            )
            return dict(
                actor=actor.model_dump(mode="json"),
                destination=list(destination),
                frame=frame,
                revision=state.revision,
            )

        return self.store._write(
            viewer,
            key,
            "m3.physical_moved",
            dict(
                actor=actor.model_dump(mode="json"),
                destination=list(destination),
                frame=frame,
                revision=revision,
                account=account,
                **({"vatgrown_travel": vatgrown_travel} if vatgrown_travel is not None else {}),
            ),
            operation,
            auto_audit=False,
        )
