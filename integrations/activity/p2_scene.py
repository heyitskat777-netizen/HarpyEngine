"""Activity P2 server adapter. Call only after resolving a verified viewer and native scene."""

import json
from typing import Any, cast

from girlframe.ai.director_dossiers import HandlerExperienceSelection
from girlframe.ai.director_reactions import ReactionProposal
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
from girlframe.engine.m3_handler_character import PROFILES
from girlframe.engine.m3_handler_state import GEAR, HISTORY_LABELS, PLAYBOOKS, Draft, HandlerNotes
from girlframe.services.activity_shadow import ActivityShadowReview
from girlframe.services.activity_timing import ActivityTiming
from girlframe.services.campaign_opening import CampaignOpeningService, OpeningDraft
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_npc_delivery import NpcDeliveryService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.director_time import scene_time
from girlframe.services.director_timing_review import DirectorTimingReview
from girlframe.services.gm_outcomes import GMOutcomeService, SourceKind
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class P2Scene:
    def __init__(
        self,
        session: DirectorSessionService,
        *,
        models: OpenAIResponses | None = None,
        facilitator_id: int | None = None,
    ):
        self.session = session
        self.models = models
        self.opening = CampaignOpeningService(session.knowledge, facilitator_id=facilitator_id)
        self.handler_setup = HandlerCreationService(session.store)
        self.shadow = ActivityShadowReview(session.conversation)
        self.npc_delivery = NpcDeliveryService(session.context)
        self.time = ActivityTiming(session.game)
        self.timing_reviews = DirectorTimingReview(session.observer, facilitator_id)

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
            time = scene_time(c, self.session.store.campaign_id, scene)
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
            "timing_reviews": work["timing_reviews"],
            "response_requests": work["response_requests"],
            "npc_roster": self.session.reactions.npc_roster(viewer, scene),
            "model_rulings": self.session.outcomes.provider is not None,
            "response_targets": targets,
            **({"fictional_time": time.model_dump(mode="json")} if time else {}),
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
        experience: HandlerExperienceSelection | None = None,
    ) -> dict[str, Any]:
        return self.session.close_scene(
            viewer, key, scene, channel, revision, report_ids=reports, experience=experience
        )

    def read(
        self, viewer: GuildViewer, scene: str, route: str, identity: str | None = None
    ) -> dict[str, Any]:
        if route == "fictional-time" and identity is None:
            view = self.time.view(viewer)
            if not scene and "handler_controls" in view:
                reviews: list[dict[str, Any]] = []
                for booking in view.get("scenes", ()):
                    if booking["joined"]:
                        try:
                            items = self.timing_reviews.view(viewer, booking["id"])
                        except WorkflowError:
                            continue
                        reviews.extend(item for item in items if item["kind"] == "missed_cutoff")
                view["timing_reviews"] = reviews
            return view
        if route == "activity-policy":
            return self.session.observer.activity_policy(viewer)
        if route == "activity-review":
            return {"batches": self.shadow.records(viewer, scene)}
        if route == "npc-hearing" and identity is not None:
            return self.npc_delivery.hearing(viewer, scene, identity)
        if route == "opening":
            return self.opening.view(viewer, scene)
        if route == "opening-brief":
            return self.opening.brief(viewer, scene)
        if route == "persona-setup":
            with self.session.store.engine.connect() as c:
                self.session.game.authorize(c, viewer, game=False)
                appointed = (
                    HandlerService(self.session.store).current(c)[1].handler_id == viewer.user_id
                )
            sheet = self.handler_setup.view(viewer) if appointed else None
            if sheet is not None:
                for npc in sheet["npcs"]:
                    npc["controller"] = str(npc["controller"])
            return {
                "sheet": sheet,
                "requests": self.handler_setup.tasks(viewer),
                "playbooks": PLAYBOOKS if appointed else (),
                "profiles": {
                    name: profile.model_dump(mode="json") for name, profile in PROFILES.items()
                }
                if appointed
                else {},
                "gear": GEAR if appointed else (),
                "histories": HISTORY_LABELS if appointed else {},
            }
        if route == "persona-agreement" and identity is not None:
            return self.handler_setup.get_agreement(viewer, identity)
        if route == "status":
            return self.session.observer.status(viewer, scene).model_dump(mode="json")
        if route == "timeline":
            return self.timeline(viewer, scene)
        if route == "work":
            return self.session.work(viewer, scene)
        if route == "gm-work":
            return self.gm_work(viewer, scene)
        if route == "timing-review" and scene and identity is None:
            return {"items": self.timing_reviews.view(viewer, scene)}
        if route == "reports":
            return self.session.handler_reports(viewer, scene)
        if route == "closeout" and identity is None:
            return self.session.closeout_options(viewer, scene)
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
            with self.session.store.engine.connect() as c:
                self.session.observer._authorize_input(c, viewer, scene, "handler")
            return self.handler_setup.view(viewer)
        raise ValueError("Unknown scene view.")

    def write(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        route: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if route == "time-acknowledge" and data.keys() == {"scene", "source_receipt"}:
            if (
                not isinstance(data["scene"], str)
                or not isinstance(data["source_receipt"], str)
                or (scene and data["scene"] != scene)
            ):
                raise ValueError("Use the original scene and cutoff receipt.")
            return self.timing_reviews.acknowledge(
                viewer, key, data["scene"], data["source_receipt"]
            )
        if route.startswith("time-"):
            return self.time.write(viewer, key, route, data)
        if route == "activity-policy-save" and data.keys() == {"revision", "enabled"}:
            return self.session.observer.configure_activity(
                viewer, key, data["revision"], data["enabled"]
            )
        if route == "activity-review-run" and not data:
            return {"batch": self.shadow.process(viewer, scene)}
        if (
            route == "npc-deliver"
            and data.keys() == {"proposal"}
            and isinstance(data["proposal"], str)
        ):
            return self.npc_delivery.deliver(viewer, key, scene, data["proposal"])
        if route == "npc-review" and data.keys() == {
            "proposal",
            "decision",
            "reason",
            "recipients",
        }:
            if (
                not self.session.observer.activity_shadow
                or not isinstance(data["proposal"], str)
                or not isinstance(data["reason"], str)
                or not isinstance(data["recipients"], list)
                or data["decision"] not in ("approve", "reject")
            ):
                raise ValueError("Select a reviewed NPC reaction and its actual listeners.")
            return self.session.reactions.review(
                viewer,
                key,
                scene,
                data["proposal"],
                data["decision"],
                data["reason"],
                recipients=tuple(ActorRef.model_validate(x) for x in data["recipients"]),
            )
        if route == "opening-save" and data.keys() == {"revision", "draft"}:
            if type(data["revision"]) is not int:
                raise ValueError("Supply the last saved opening revision.")
            draft = OpeningDraft.model_validate_json(json.dumps(data["draft"]))
            return self.opening.save(viewer, key, scene, data["revision"], draft)
        if route == "opening-launch" and data.keys() == {"review"}:
            if not isinstance(data["review"], str) or len(data["review"]) != 64:
                raise ValueError("Confirm the actual opening review.")
            return self.opening.launch(viewer, key, scene, data["review"])
        if route == "persona-save" and data.keys() == {
            "revision",
            "appointment",
            "draft",
            "generation",
        }:
            if (
                type(data["revision"]) is not int
                or not isinstance(data["appointment"], str)
                or not isinstance(data["generation"], str)
            ):
                raise ValueError("Use the saved Handler draft and appointment.")
            raw = data["draft"]
            if isinstance(raw, dict) and isinstance(raw.get("npc_starting"), list):
                for npc in raw["npc_starting"]:
                    if isinstance(npc, dict) and isinstance(
                        controller := npc.get("controller"), str
                    ):
                        if (
                            not controller.isascii()
                            or not controller.isdecimal()
                            or len(controller) > 20
                        ):
                            raise ValueError("Use the exact NPC controller.")
                        npc["controller"] = int(controller)
            draft_sheet = Draft.model_validate_json(json.dumps(raw))
            return self.handler_setup.save(
                viewer,
                key,
                data["revision"],
                data["appointment"],
                draft_sheet,
                generation=data["generation"],
            )
        if route == "persona-notes" and data.keys() == {"revision", "persona_id", "notes"}:
            if type(data["revision"]) is not int or not isinstance(data["persona_id"], str):
                raise ValueError("Use your current saved Handler sheet.")
            notes = (
                HandlerNotes.model_validate(data["notes"]) if data["notes"] is not None else None
            )
            return self.handler_setup.save_notes(
                viewer, key, data["revision"], data["persona_id"], notes
            )
        if route == "persona-propose" and data.keys() == {"revision", "generation"}:
            if type(data["revision"]) is not int or not isinstance(data["generation"], str):
                raise ValueError("Use the saved Handler draft revision.")
            return self.handler_setup.propose(
                viewer, key, data["revision"], generation=data["generation"]
            )
        if route == "persona-activate" and data.keys() == {
            "revision",
            "game_revision",
            "confirmed",
        }:
            if (
                type(data["revision"]) is not int
                or type(data["game_revision"]) is not int
                or data["confirmed"] is not True
            ):
                raise ValueError("Confirm the current Handler profile.")
            return self.handler_setup.activate(
                viewer, key, data["revision"], data["game_revision"], True
            )
        if route == "persona-answer" and data.keys() == {"id", "revision", "accept"}:
            if (
                not isinstance(data["id"], str)
                or type(data["revision"]) is not int
                or type(data["accept"]) is not bool
            ):
                raise ValueError("Answer the exact saved relationship proposal.")
            return self.handler_setup.answer(
                viewer, key, data["id"], data["revision"], data["accept"]
            )
        if (
            route == "configure"
            and data.keys() == {"revision", "policy"}
            and self.session.observer.activity_shadow
        ):
            if type(data["revision"]) is not int:
                raise ValueError("Use the current scene notice revision.")
            return self.session.observer.configure_scene(
                viewer,
                key,
                scene,
                data["revision"],
                ObservationPolicy.model_validate(data["policy"]),
            )
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
        if route == "close" and data.keys() in (
            {"revision", "reports"},
            {"revision", "reports", "experience"},
        ):
            if (
                type(data["revision"]) is not int
                or not isinstance(data["reports"], list)
                or any(not isinstance(value, str) for value in data["reports"])
            ):
                raise ValueError("Select the current scene revision and report IDs.")
            with self.session.store.engine.connect() as c:
                row = self.session.observer._scene(c, scene, viewer, allow_closed=True)
            return self.close(
                viewer,
                key,
                scene,
                int(row["channel_id"]),
                data["revision"],
                tuple(data["reports"]),
                HandlerExperienceSelection.model_validate(data["experience"])
                if "experience" in data
                else None,
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
        if (
            route == "reaction-propose"
            and data.keys() == {"request", "proposal"}
            and self.session.observer.activity_shadow
        ):
            return self.session.reactions.propose(
                viewer,
                key,
                scene,
                data["request"],
                ReactionProposal.model_validate_json(json.dumps(data["proposal"])),
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


def manual_campaign_setup(game: GameService, facilitator: int) -> P2Scene:
    """Use verified campaign identity for setup with Director observation disabled."""
    observer = DirectorObservationService(game.store)
    observer.game = game
    return P2Scene(
        DirectorSessionService(DirectorContextService(observer)), facilitator_id=facilitator
    )


def local_fixture_director(game: GameService, *, activity_shadow: bool = False) -> P2Scene:
    """Exercise the real model contracts through a disposable, no-network lab transport."""
    from urllib.request import Request

    from girlframe.ai.model_transport import ModelLimits

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

    observer = DirectorObservationService(
        game.store, synthetic=True, activity_shadow=activity_shadow
    )
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
