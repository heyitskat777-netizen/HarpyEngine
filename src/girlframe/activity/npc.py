"""Authenticated JSON adapter for the Activity's NPC scene controls."""

from typing import Any, Literal

from pydantic import Field, ValidationError

from girlframe.ai.observation import SceneTurn
from girlframe.engine.m2 import Model
from girlframe.scenes.campaign_time import Identity, Position
from girlframe.scenes.canon import CanonWindow, Statement
from girlframe.services.ai_npc_reactions import GuideChoice, NpcReactionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

Role = Literal["pilot", "handler", "facilitator"]


class Request(Model):
    scene_id: Identity
    operation: Literal[
        "overview",
        "address",
        "draft",
        "resume",
        "review",
        "guide_response",
        "guide_handoff",
        "npc_witness",
        "report_lead",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)


class AddressInput(Model):
    submission_id: Identity
    window: CanonWindow
    npc_id: str = Field(min_length=1, max_length=100)
    statement: Statement
    source_turn: SceneTurn | None = None


class DraftInput(Model):
    submission_id: Identity
    address_id: Identity
    guide_destination_id: str | None = Field(default=None, min_length=1, max_length=100)
    lead_fact_id: Identity | None = None


class SavedRequest(Model):
    request_id: Identity


class ReviewInput(SavedRequest):
    submission_id: Identity
    result_id: Identity
    approve: bool
    edited_speech: Statement | None = None
    expected_audience: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class GuideInput(Model):
    submission_id: Identity
    reaction_id: Identity
    choice: GuideChoice


class GuideHandoffInput(Model):
    submission_id: Identity
    reaction_id: Identity
    destination_scene_id: Identity
    destination_revision: int = Field(gt=0)
    position: Position


class ReportInput(Model):
    submission_id: Identity
    window: CanonWindow
    fact_id: Identity


class WitnessInput(ReportInput):
    npc_id: str = Field(min_length=1, max_length=100)


class ActivityNpcApi:
    def __init__(self, reactions: NpcReactionService):
        self.reactions = reactions

    def _role(self, viewer: GuildViewer) -> Role:
        canon = self.reactions.canon
        with canon.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            if viewer.user_id == canon.store.policy.canon_facilitator_id:
                canon._access(c, viewer, facilitator=True)
                return "facilitator"
            canon._access(c, viewer)
            return (
                "handler" if viewer.user_id == canon.handler.current(c)[1].handler_id else "pilot"
            )

    def _overview(self, viewer: GuildViewer, scene_id: str, role: Role) -> dict[str, Any]:
        enabled = self.reactions.store.policy.ai_npc_reactions is not None
        view: dict[str, Any] = {
            "role": role,
            "enabled": enabled,
            "addresses": self.reactions.addresses(viewer, scene_id),
            "feed": self.reactions.scene_feed(viewer, scene_id),
        }
        if role != "pilot":
            view["requests"] = self.reactions.list_requests(viewer, scene_id)
        try:
            if role == "pilot":
                view["lead_reports"] = self.reactions.reportable_leads(viewer, scene_id)
                if enabled:
                    view["targets"] = self.reactions.targets(viewer, scene_id)
            elif role == "handler":
                if enabled:
                    view["destinations"] = self.reactions.destinations(viewer, scene_id)
                    view["leads"] = self.reactions.lead_controls(
                        viewer, scene_id, facilitator=False
                    )
                if any(
                    item.get("guide_responses") and not item.get("handoff")
                    for item in view["requests"]
                ):
                    view["guide_bookings"] = self.reactions.guide_bookings(viewer, scene_id)
            elif enabled:
                view["lead_witness"] = self.reactions.lead_controls(
                    viewer, scene_id, facilitator=True
                )
        except WorkflowError as error:
            # Saved dialogue remains readable when live controls are unavailable.
            view["unavailable"] = str(error)
        return view

    def dispatch(self, viewer: GuildViewer, body: dict[str, Any]) -> dict[str, Any]:
        """Call from the Activity's authenticated server, off the async request loop."""
        try:
            request = Request.model_validate(body)
            return self._dispatch(viewer, request)
        except ValidationError:
            raise WorkflowError("Check the NPC control inputs and reopen the scene.") from None

    def _dispatch(self, viewer: GuildViewer, request: Request) -> dict[str, Any]:
        role = self._role(viewer)
        scene, operation, payload = request.scene_id, request.operation, request.payload
        if operation == "overview":
            Model.model_validate(payload)
            return self._overview(viewer, scene, role)
        if operation == "address":
            address = AddressInput.model_validate(payload)
            if address.window.scene_id != scene:
                raise WorkflowError("Reopen this Activity scene before addressing the NPC.")
            identity = self.reactions.address(
                viewer,
                address.submission_id,
                address.window,
                address.npc_id,
                address.statement,
                source_turn=address.source_turn,
            )
            return {"id": identity}
        if operation == "guide_response":
            answer = GuideInput.model_validate(payload)
            return self.reactions.respond_to_guide(
                viewer, answer.submission_id, scene, answer.reaction_id, answer.choice
            )
        if operation == "guide_handoff":
            handoff = GuideHandoffInput.model_validate(payload)
            return self.reactions.book_guide(
                viewer,
                handoff.submission_id,
                scene,
                handoff.reaction_id,
                handoff.destination_scene_id,
                handoff.destination_revision,
                handoff.position,
            )
        if operation in ("npc_witness", "report_lead"):
            fact = (
                WitnessInput.model_validate(payload)
                if operation == "npc_witness"
                else ReportInput.model_validate(payload)
            )
            if fact.window.scene_id != scene or fact.window.scene_revision is None:
                raise WorkflowError("Refresh this Activity scene before recording a fact.")
            if isinstance(fact, WitnessInput):
                return {
                    "id": self.reactions.witness_lead(
                        viewer,
                        fact.submission_id,
                        fact.window,
                        fact.npc_id,
                        fact.fact_id,
                    )
                }
            if role != "pilot":
                raise WorkflowError("Only a Pilot can report a lead.")
            key = f"activity.report-lead:{viewer.user_id}:{fact.submission_id}"
            return {"id": self.reactions.canon.report(viewer, key, fact.window, fact.fact_id)}
        if operation == "draft":
            if role != "handler":
                raise WorkflowError("Only the current Handler can request a draft.")
            draft = DraftInput.model_validate(payload)
            identity = self.reactions.queue(
                viewer,
                draft.submission_id,
                draft.address_id,
                scene_id=scene,
                guide_destination_id=draft.guide_destination_id,
                lead_fact_id=draft.lead_fact_id,
            )
            return self.reactions.run(viewer, identity)

        saved = (
            ReviewInput.model_validate(payload)
            if operation == "review"
            else SavedRequest.model_validate(payload)
        )
        if self.reactions.get(viewer, saved.request_id)["scene"] != scene:
            raise WorkflowError("This NPC draft is unavailable in this scene.")
        if isinstance(saved, ReviewInput):
            key = f"activity.npc-review:{viewer.user_id}:{saved.submission_id}"
            return self.reactions.review(
                viewer,
                key,
                saved.request_id,
                saved.result_id,
                approve=saved.approve,
                edited_speech=saved.edited_speech,
                expected_audience=saved.expected_audience,
            )
        return self.reactions.run(viewer, saved.request_id)
