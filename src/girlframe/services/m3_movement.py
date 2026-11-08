"""Record permitted ordinary movement of actual controlled bodies or piloted Frames."""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

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
                    actors.append(
                        dict(
                            ref=ref.model_dump(mode="json"),
                            id=ref.token,
                            label=actual.label,
                            cell=actual.cell,
                            piloting=actual.piloting,
                        )
                    )
            return dict(
                revision=state.revision,
                actors=actors,
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
    ) -> dict[str, Any]:
        actor = ActorRef.model_validate_json(actor.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_physical import PhysicalService
            from girlframe.services.p1_facilitator import require_scene_clear
            from girlframe.services.p1_source_pause import require_clear

            Access(self.store).authorize(c, viewer, "world", director_response=True)
            self.game.unpaused(c)
            PhysicalService(self.store)._idle(c)
            require_clear(self.game, c, channel)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            scene = self.game.scene(c, channel)
            if (
                type(revision) is not int
                or state.revision != revision
                or state.world is None
                or viewer.user_id not in scene["participants"]
                or not account.strip()
                or len(account) > 1200
                or len(destination) != 2
                or any(type(x) is not int for x in destination)
                or not state.world.board.contains(destination)
            ):
                raise WorkflowError(
                    "Choose actual current physical movement within the mapped scene"
                )
            bound = profiles(c, self.store.campaign_id)
            actual = resolve(state, actor, bound, require_current_profile=False)
            if (
                actual.controller != viewer.user_id
                or actual.cell is None
                or actual.offstage_source
                or actual.custody not in (None, "free")
                or is_helpless(state, actor)
                or pinned(state, actor)
            ):
                raise WorkflowError(
                    "Resolve genuine custody, Helplessness or the source pin before moving"
                )
            cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
            if cast is not None and not any(
                x.actor == actor and x.controller == viewer.user_id for x in cast.roles
            ):
                raise WorkflowError("Join this actual role in the source scene first")
            event = str(uuid4())
            if actor.kind == "pilot":
                pose = next((x for x in state.placements if x.actor == actor), None)
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
                    values = dict(frame_cell=destination, girl_cell=destination)
                else:
                    if actual.inside_frame is not False:
                        raise WorkflowError(
                            "Actually exit the cockpit before ordinary movement on foot"
                        )
                    values = dict(girl_cell=destination)
                moved = pose.model_copy(update=values | dict(source_event=event, account=account))
                moved = type(pose).model_validate_json(moved.model_dump_json())
                state.placements = [moved if x.actor == actor else x for x in state.placements]
            elif actor.kind == "npc":
                npc = next(x for x in state.world.npcs if x.id == actor.entity)
                if npc.source_kind is not None or frame or actual.inside_frame is True:
                    raise WorkflowError(
                        "This source body needs its actual carrier or software-access adapter"
                    )
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
                            x.model_copy(update=dict(cell=destination))
                            if x.id == actor.entity
                            else x
                            for x in state.world.gorgons
                        )
                    )
                )
            elif actor.kind == "handler" and not frame and actual.inside_frame is not True:
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
                if (
                    external_pose is None
                    or (frame and external_pose.mode != "piloting")
                    or (not frame and external_pose.mode != "outside_frame")
                ):
                    raise WorkflowError(
                        "Retain the actual external body's known cockpit and Frame context"
                    )
                update = dict(position_event=event, account=account, girl_cell=destination)
                if frame:
                    update["frame_cell"] = destination
                state.external_poses = [
                    external_pose.model_copy(update=update) if x.actor == actor else x
                    for x in state.external_poses
                ]
            else:
                raise WorkflowError(
                    "This actual body requires its specific movement source adapter"
                )
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
                destination=destination,
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
            ),
            operation,
            auto_audit=False,
        )
