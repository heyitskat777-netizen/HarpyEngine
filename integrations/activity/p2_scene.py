"""Activity P2 server adapter. Call only after resolving a verified viewer and native scene."""

import json
from typing import Any, cast

from girlframe.ai.gm_outcomes import OutcomeProposal
from girlframe.ai.gm_protocol import TaskFrame
from girlframe.ai.observation import AppendSceneInput, ObservationPolicy
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.gm_outcomes import SourceKind
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class P2Scene:
    def __init__(self, session: DirectorSessionService):
        self.session = session

    def submit(self, viewer: GuildViewer, scene: str, command: AppendSceneInput) -> dict[str, Any]:
        result = self.session.submit(viewer, scene, command)
        # The scene composer gets an input receipt. Review and rules results have
        # their own authenticated surfaces and are never transcript entries.
        return {"input": result["input"]}

    def timeline(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        return self.session.timeline(viewer, scene)

    def play_results(self, viewer: GuildViewer, scene: str, action: str) -> dict[str, Any]:
        with self.session.store.engine.connect() as c:
            self.session.observer._scene(c, scene, viewer)
            if self.session.game.action(c, action)["scene_id"] != scene:
                raise WorkflowError("SOURCE_UNAVAILABLE: use the Play's original scene.")
        return self.session.game.inspect(viewer, action)

    def gm_work(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        work = self.session.work(viewer, scene, gm=True)
        return {
            "outcome_sources": work["outcome_sources"],
            "handler_drafts": work["handler_drafts"],
            "response_requests": work["response_requests"],
        }

    def open_ruling(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        source_kind: str,
        source_id: str,
        frame: TaskFrame | None = None,
    ) -> dict[str, Any]:
        return self.session.outcomes.open(
            viewer, key, scene, cast(SourceKind, source_kind), source_id, frame
        )

    def ruling_packet(self, viewer: GuildViewer, scene: str, request: str) -> dict[str, Any]:
        return self.session.outcomes.packet(viewer, scene, request).model_dump(mode="json")

    def propose_ruling(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        request: str,
        proposal: OutcomeProposal,
    ) -> dict[str, Any]:
        return self.session.outcomes.propose(viewer, key, scene, request, proposal)

    def confirm_ruling(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        proposal: str,
    ) -> dict[str, Any]:
        return self.session.outcomes.confirm(viewer, key, scene, proposal)

    def approve_handler(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        draft: str,
        reason: str,
        recipients: tuple[ActorRef, ...],
    ) -> dict[str, Any]:
        return self.session.conversation.review_handler(
            viewer,
            key,
            scene,
            draft,
            "approve",
            reason,
            delivery_recipients=recipients,
        )

    def deliver_handler(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        draft: str,
    ) -> dict[str, Any]:
        return self.session.conversation.delivery.deliver(viewer, key, scene, draft)

    def close(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        channel: int,
        revision: int,
        reports: tuple[str, ...],
    ) -> dict[str, Any]:
        return self.session.close_scene(viewer, key, scene, channel, revision, report_ids=reports)

    def read(
        self, viewer: GuildViewer, scene: str, route: str, identity: str | None = None
    ) -> dict[str, Any]:
        if route == "status":
            return self.session.observer.status(viewer, scene).model_dump(mode="json")
        if route == "timeline":
            return self.timeline(viewer, scene)
        if route == "work":
            return self.session.work(viewer, scene)
        if route == "gm-work":
            return self.gm_work(viewer, scene)
        if route == "reports":
            return self.session.handler_reports(viewer, scene)
        if route == "rules" and identity is not None:
            return self.play_results(viewer, scene, identity)
        if route == "ruling" and identity is not None:
            return self.ruling_packet(viewer, scene, identity)
        if route == "owner-review" and identity is not None:
            return self.session.outcomes.owner_review(viewer, scene, identity)
        if route == "handler-preview" and identity is not None:
            return self.session.conversation.delivery.preview(viewer, scene, identity)
        if route == "handler-draft" and identity is not None:
            return self.session.conversation.private_handler(viewer, scene, identity)
        raise ValueError("Unknown scene view.")

    def write(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        route: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if route == "configure" and data.keys() == {"revision"} and type(data["revision"]) is int:
            return self.session.observer.configure_scene(
                viewer,
                key,
                scene,
                data["revision"],
                ObservationPolicy(mode="shadow"),
            )
        for name in ("source_kind", "source_id", "request", "draft", "reason"):
            if name in data and not isinstance(data[name], str):
                raise ValueError("Use actual source identifiers and text.")
        if route == "input":
            return self.submit(
                viewer, scene, AppendSceneInput.model_validate(data | {"command_key": key})
            )
        if route == "close" and data.keys() == {"revision", "reports"}:
            if (
                type(data["revision"]) is not int
                or not isinstance(data["reports"], list)
                or any(not isinstance(value, str) for value in data["reports"])
            ):
                raise ValueError("Select the current scene revision and report IDs.")
            with self.session.store.engine.connect() as c:
                row = self.session.observer._scene(c, scene, viewer, allow_closed=True)
            return self.close(
                viewer, key, scene, int(row["channel_id"]), data["revision"], tuple(data["reports"])
            )
        if route == "consent" and data.keys() == {"policy_revision", "consent"}:
            if type(data["policy_revision"]) is not int or type(data["consent"]) is not bool:
                raise ValueError("Supply the current notice and your own decision.")
            return self.session.observer.set_consent(
                viewer, key, scene, data["policy_revision"], consent=data["consent"]
            )
        if route == "ruling-open" and data.keys() == {"source_kind", "source_id", "frame"}:
            frame = (
                TaskFrame.model_validate_json(json.dumps(data["frame"]))
                if data["frame"] is not None
                else None
            )
            return self.open_ruling(
                viewer, key, scene, data["source_kind"], data["source_id"], frame
            )
        if route == "ruling-propose" and data.keys() == {"request", "proposal"}:
            return self.propose_ruling(
                viewer,
                key,
                scene,
                data["request"],
                OutcomeProposal.model_validate_json(json.dumps(data["proposal"])),
            )
        if (
            route == "ruling-confirm"
            and data.keys() == {"proposal"}
            and isinstance(data["proposal"], str)
        ):
            return self.confirm_ruling(viewer, key, scene, data["proposal"])
        if route == "handler-approve" and data.keys() == {"draft", "reason", "recipients"}:
            if not isinstance(data["recipients"], list) or not isinstance(data["reason"], str):
                raise ValueError("Specify the reviewed reason and the actual listeners.")
            return self.approve_handler(
                viewer,
                key,
                scene,
                data["draft"],
                data["reason"],
                tuple(ActorRef.model_validate(x) for x in data["recipients"]),
            )
        if route == "handler-deliver" and data.keys() == {"draft"}:
            return self.deliver_handler(viewer, key, scene, data["draft"])
        raise ValueError("Unknown scene operation or malformed fields.")


def local_fixture_director(game: Any) -> P2Scene:
    """Configure the disposable Activity lab with a reviewed, local response fixture."""
    from girlframe.ai.conversation import ConversationReply, HandlerRequest
    from girlframe.services.director_context import DirectorContextService
    from girlframe.services.director_conversation import DirectorConversationService
    from girlframe.services.director_observation import DirectorObservationService

    class LocalHandler:
        def respond(self, request: HandlerRequest) -> ConversationReply:
            refs = request.response_need.source_refs if request.response_need else ()
            return ConversationReply(
                route="handler",
                provider="reviewed-handler-v1",
                disposition="clarification",
                text="I can stay here while you check the current report.",
                source_refs=refs,
                handler_action="I set my own report pad on the table.",
            )

    observer = DirectorObservationService(game.store, synthetic=True)
    observer.game = game
    context = DirectorContextService(observer)
    return P2Scene(
        DirectorSessionService(
            context,
            conversation=DirectorConversationService(
                context,
                handler=LocalHandler(),
                handler_mode="reviewed",
            ),
        )
    )
