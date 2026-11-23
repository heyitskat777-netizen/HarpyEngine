"""Activity controls for manually reviewed canon and scene safety."""

from typing import Any

from girlframe.scenes.canon import CanonWindow
from girlframe.services.activity_timing import _snowflake
from girlframe.services.canon import CanonService, fact_identity
from girlframe.services.canon_briefings import CanonBriefings
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import OnboardingStore
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.scene_safety import SceneSafety


class ActivityCanon:
    def __init__(self, store: OnboardingStore):
        self.canon = CanonService(store)
        self.briefings = CanonBriefings(store)
        self.safety = SceneSafety(store)

    def read(self, viewer: GuildViewer, scene: str, route: str) -> dict[str, Any]:
        if route == "canon-witnesses":
            with self.canon.store.engine.connect() as c:
                c.exec_driver_sql("BEGIN")
                self.canon._access(c, viewer, facilitator=True)
                channel = self.canon._channel(c, fact_identity(scene))
                self.canon.current_window(c, viewer, channel, facilitator=True)
                scene_row = self.canon.game.scene(c, channel, check_slot=False)
                actors = self.canon._participants(c, scene_row)
                state = load_state(c, self.canon.campaign)
                handler = self.canon.handler.current(c)[1].handler_id
                return {
                    "pilots": [
                        {"id": str(pilot), "label": state.sheets[str(pilot)].callsign}
                        for pilot in sorted(actors)
                        if pilot != handler and str(pilot) in state.sheets
                    ]
                }
        if route in ("canon-window", "canon-review-window"):
            return self.canon.window_for_scene(
                viewer, scene, facilitator=route == "canon-review-window"
            ).model_dump(mode="json")
        if route in ("canon-proposals", "canon-review"):
            return {"proposals": self.canon.proposals(viewer, facilitator=route == "canon-review")}
        if route == "canon-briefing":
            return {"drafts": self.briefings.drafts(viewer)}
        if route == "canon-known":
            facts = self.canon.known(viewer)
            return {"facts": [fact.model_dump(mode="json") for fact in facts]}
        if route in ("canon-public", "canon-world"):
            world = self.canon.world(viewer, public=route == "canon-public")
            return {"facts": [fact.model_dump(mode="json") for fact in world]}
        raise ValueError("Unknown canon view.")

    @staticmethod
    def _text(data: dict[str, Any], key: str) -> str:
        value = data[key]
        if not isinstance(value, str):
            raise ValueError("Use a canon statement or receipt ID.")
        return value

    def write(
        self, viewer: GuildViewer, key: str, scene: str, route: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        fields = data.keys()
        if route == "canon-review" and fields == {"id", "approve", "public"}:
            if any(type(data[field]) is not bool for field in ("approve", "public")):
                raise ValueError("Choose an explicit canon review decision.")
            return {
                "id": self.canon.review(
                    viewer,
                    key,
                    self._text(data, "id"),
                    approve=data["approve"],
                    public=data["public"],
                )
            }
        if route == "canon-correct" and fields == {"fact", "statement"}:
            return {
                "id": self.canon.correct(
                    viewer, key, self._text(data, "fact"), self._text(data, "statement")
                )
            }
        if route == "canon-briefing" and fields == {"facts"}:
            if not isinstance(data["facts"], list) or not all(
                isinstance(fact, str) for fact in data["facts"]
            ):
                raise ValueError("Select the Handler's current known facts.")
            return {"id": self.briefings.draft(viewer, key, tuple(data["facts"]))}
        if route == "scene-safety" and fields == {"pause"}:
            if type(data["pause"]) is not bool:
                raise ValueError("Choose pause or resume.")
            scene = fact_identity(scene)
            with self.canon.store.engine.connect() as c:
                self.canon.store.guild_member(viewer)
                self.canon.store._membership(c, viewer)
                channel = self.canon._channel(c, scene)
            return self.safety.change(viewer, key, channel, scene, pause=data["pause"])
        if "window" not in fields:
            raise ValueError("Open the original scene first.")
        window = CanonWindow.model_validate(data["window"])
        if window.scene_id != scene or window.scene_revision is None:
            raise ValueError("Refresh the current scene window.")
        if route == "canon-submit" and fields == {"window", "statement"}:
            return {
                "id": self.canon.propose_activity(
                    viewer, key, window, self._text(data, "statement")
                )
            }
        if route == "canon-establish" and fields == {"window", "statement"}:
            return {"id": self.canon.establish(viewer, key, window, self._text(data, "statement"))}
        if route == "canon-witness" and fields == {"window", "fact", "pilot"}:
            return {
                "id": self.canon.witness(
                    viewer, key, window, self._text(data, "fact"), _snowflake(data["pilot"])
                )
            }
        if route == "canon-report" and fields == {"window", "fact"}:
            return {"id": self.canon.report(viewer, key, window, self._text(data, "fact"))}
        raise ValueError("Unknown canon action.")
