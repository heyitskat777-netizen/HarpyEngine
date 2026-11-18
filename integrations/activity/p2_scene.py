"""Activity P2 server adapter. Call only after resolving a verified viewer and native scene."""

import json
from typing import Any, cast

from girlframe.ai.gm_outcomes import OutcomeProposal
from girlframe.ai.gm_protocol import TaskFrame
from girlframe.ai.model_adapters import (
    ModelHandler,
    ModelHandlerNeeds,
    ModelOutcomes,
    ModelReactions,
    ModelWorldbuilding,
)
from girlframe.ai.model_transport import OpenAIResponses
from girlframe.ai.observation import AppendSceneInput, ObservationPolicy
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.campaign_opening import CampaignOpeningService, OpeningDraft
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.gm_outcomes import GMOutcomeService, SourceKind
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class P2Scene:
    def __init__(self, session: DirectorSessionService, *, models: OpenAIResponses | None = None):
        self.session = session
        self.models = models
        self.opening = CampaignOpeningService(session.knowledge)

    @classmethod
    def model_fixture(
        cls,
        context: DirectorContextService,
        handler: OpenAIResponses,
        director: OpenAIResponses | None = None,
    ) -> "P2Scene":
        """Explicit server-side wiring for synthetic observation."""
        context.observations._scope()
        conversation = DirectorConversationService(
            context,
            handler=ModelHandler(handler),
            handler_mode="reviewed",
        )
        outcomes = GMOutcomeService(
            context,
            ModelOutcomes(director) if director else None,
            require_response_scope=True,
        )
        return cls(
            DirectorSessionService(context, conversation=conversation, outcomes=outcomes),
            models=director,
        )

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
        with self.session.store.engine.connect() as c:
            self.session.outcomes._scope(c, viewer, scene, gm=True)
            row = self.session.observer._scene(c, scene, viewer)
            state = load_state(c, self.session.store.campaign_id)
            names = {npc.id: npc.name for npc in state.world.npcs} if state.world else {}
            names.update({key: sheet.callsign for key, sheet in state.sheets.items()})
            targets = [
                {
                    "actor": actor.model_dump(mode="json"),
                    "label": "Handler"
                    if actor.kind == "handler"
                    else names.get(actor.entity, actor.entity),
                }
                for actor in self.session.knowledge._actors(c, row)
            ]
        return {
            "outcome_sources": work["outcome_sources"],
            "handler_drafts": work["handler_drafts"],
            "response_requests": work["response_requests"],
            "npc_roster": self.session.reactions.npc_roster(viewer, scene),
            "model_rulings": self.session.outcomes.provider is not None,
            "response_targets": targets,
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
        if route == "opening":
            return self.opening.view(viewer, scene)
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
        if route == "world-draft" and identity is not None:
            return self.session.worldbuilding.private(viewer, scene, identity)
        if route == "npc-owner-review" and identity is not None:
            return self.session.reactions.owner_review(viewer, scene, identity)
        if route == "handler-sheet":
            from girlframe.services.m3_handler_creation import HandlerCreationService

            with self.session.store.engine.connect() as c:
                self.session.observer._authorize_input(c, viewer, scene, "handler")
            return HandlerCreationService(self.session.store).view(viewer)
        raise ValueError("Unknown scene view.")

    def write(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        route: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if route == "opening-save" and data.keys() == {"revision", "draft"}:
            if type(data["revision"]) is not int:
                raise ValueError("Supply the last saved opening revision.")
            draft = OpeningDraft.model_validate_json(json.dumps(data["draft"]))
            return self.opening.save(viewer, key, scene, data["revision"], draft)
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
        if route == "ruling-generate" and data.keys() == {"request"}:
            return self.session.outcomes.propose(viewer, key, scene, data["request"])
        if route == "handler-reject" and data.keys() == {"draft", "reason"}:
            return self.session.conversation.review_handler(
                viewer,
                key,
                scene,
                data["draft"],
                "reject",
                data["reason"],
            )
        if route == "world-open" and data.keys() == {"source_id"}:
            return self.session.worldbuilding.open(viewer, key, scene, data["source_id"])
        if route == "reaction-open" and data.keys() == {"source_id", "actor"}:
            actor = ActorRef.model_validate(data["actor"])
            if actor.kind != "npc":
                raise ValueError("Use an actual cast NPC for this reaction.")
            return self.session.reactions.open(
                viewer,
                key,
                scene,
                actor,
                data["source_id"],
            )
        if route == "handler-need-open" and data.keys() == {"source_id"}:
            return self.session.conversation.open_handler_need(
                viewer, key, scene, data["source_id"]
            )
        if self.models is not None and data.keys() == {"request"}:
            request = data["request"]
            if route == "world-generate":
                return self.session.worldbuilding.generate(
                    viewer,
                    key,
                    scene,
                    request,
                    ModelWorldbuilding(self.models),
                )
            if route == "reaction-generate":
                return self.session.reactions.generate(
                    viewer,
                    key,
                    scene,
                    request,
                    ModelReactions(self.models),
                )
            if route == "handler-need-generate":
                return self.session.conversation.generate_handler_need(
                    viewer,
                    key,
                    scene,
                    request,
                    ModelHandlerNeeds(self.models),
                )
        raise ValueError("Unknown scene operation or malformed fields.")


def local_fixture_director(game: GameService) -> P2Scene:
    """Exercise the real model contracts through a disposable, no-network lab transport."""
    from urllib.request import Request

    from girlframe.ai.model_transport import ModelLimits
    from girlframe.services.director_observation import DirectorObservationService

    def reply(request: Request, timeout: float) -> bytes:
        if not isinstance(request.data, bytes):
            raise ValueError("Fixture requires a JSON request body.")
        envelope = json.loads(request.data)
        packet = json.loads(envelope["input"][1]["content"])["packet"]
        result = {
            "disposition": "clarification",
            "source_refs": packet["response_need"]["source_refs"],
            "text": "I can stay here while you check the current report.",
            "handler_action": "I set my own report pad on the table.",
        }
        return json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": json.dumps(result)}],
                    }
                ],
            }
        ).encode()

    observer = DirectorObservationService(game.store, synthetic=True)
    observer.game = game
    return P2Scene.model_fixture(
        DirectorContextService(observer),
        OpenAIResponses(
            model="local-fixture",
            api_key="offline-fixture",
            limits=ModelLimits(attempts=1000, output_tokens=600),
            post=reply,
        ),
    )
