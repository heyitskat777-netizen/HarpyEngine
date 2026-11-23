"""Campaign-member safety pauses scoped to an immutable scene binding."""

from typing import Any

from sqlalchemy import Connection

from girlframe.services import campaign_time_history as calendar
from girlframe.services.campaign_difficulty import opening
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "safety.scene_changed"


def paused_scenes(c: Connection, campaign: str) -> set[str]:
    active: set[tuple[str, str]] = set()
    for row, payload in calendar.history(c, campaign, EVENT):
        key = (payload["scene"], row["actor_id"])
        if payload["pause"]:
            active.add(key)
        else:
            active.discard(key)
    return {scene for scene, _ in active}


def require_scene_unpaused(c: Connection, campaign: str, scene: str) -> None:
    if scene in paused_scenes(c, campaign):
        raise WorkflowError("SAFETY_PAUSED: this scene is paused. Saved views remain available.")


class SceneSafety:
    def __init__(self, store: OnboardingStore):
        self.store = store

    def change(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        expected_scene: str,
        *,
        pause: bool,
    ) -> dict[str, Any]:
        from girlframe.services.m2_game import GameService

        def operation(c: Connection) -> dict[str, Any]:
            scene = GameService(self.store).scene(c, channel, check_slot=False)
            if scene["id"] != expected_scene:
                raise WorkflowError("STALE_SCENE: this channel has a different scene now.")
            record = opening(c, self.store.campaign_id)
            audience = set(scene["participants"])
            if record is not None and record.scene == expected_scene:
                audience.update(record.audience)
            if viewer.user_id not in audience and viewer.user_id not in (
                HandlerService(self.store).current(c)[1].handler_id,
                self.store.policy.canon_facilitator_id,
            ):
                raise WorkflowError("Only someone taking part can pause this scene.")
            receipt = self.store._audit(
                c, viewer.user_id, key, EVENT, {"scene": expected_scene, "pause": pause}
            )
            return {
                "receipt": receipt,
                "paused": expected_scene in paused_scenes(c, self.store.campaign_id),
            }

        return self.store._write(
            viewer,
            key,
            EVENT,
            {"channel": channel, "scene": expected_scene, "pause": pause},
            operation,
            authorize=lambda c: self.store._membership(c, viewer),
            auto_audit=False,
        )
