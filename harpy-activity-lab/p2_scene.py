"""Activity P2 server adapter. Call only after resolving a verified viewer and native scene."""

import json
from dataclasses import asdict, replace
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.activity_batch import (
    ActivityBatchProvider,
    ActivityPilotProvider,
    BatchHandlerPlay,
)
from girlframe.ai.briefing import BriefingGateway
from girlframe.ai.director_dossiers import (
    CharacterSetup,
    DossierContinuityEdit,
    DossierMemoryEdit,
    DossierPerspective,
    HandlerExperienceSelection,
    PilotDossierOrigin,
)
from girlframe.ai.director_planning import DirectorPlanningProvider
from girlframe.ai.director_reactions import ReactionProposal
from girlframe.ai.gm_outcomes import OutcomeProposal
from girlframe.ai.gm_protocol import TaskFrame
from girlframe.ai.model_adapters import (
    ModelActivityBatch,
    ModelActivityPilot,
    ModelDirectorPlanning,
    ModelHandler,
    ModelHandlerNeeds,
    ModelOutcomes,
    ModelReactions,
    ModelWorldbuilding,
)
from girlframe.ai.model_transport import OpenAIResponses
from girlframe.ai.observation import AppendSceneInput, ObservationPolicy
from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_advocate_alone import Order as AdvocateOrder
from girlframe.engine.m3_handler_character import PROFILES
from girlframe.engine.m3_handler_state import GEAR, HISTORY_LABELS, PLAYBOOKS, Draft, HandlerNotes
from girlframe.engine.pilot_portrayal import PILOT_CALLSIGNS, PILOT_PORTRAYALS, PilotPortrayal
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.scenes.opening import OpeningDraft as SceneOpeningDraft
from girlframe.services.activity_canon import ActivityCanon
from girlframe.services.activity_handler_followups import ActivityHandlerFollowups
from girlframe.services.activity_scene_opening import ActivitySceneOpening
from girlframe.services.activity_session_zero import READS as SESSION_ZERO_READS
from girlframe.services.activity_session_zero import WRITES as SESSION_ZERO_WRITES
from girlframe.services.activity_session_zero import SessionZeroDesk
from girlframe.services.activity_shadow import ActivityShadowReview
from girlframe.services.activity_timing import ActivityTiming, _snowflake
from girlframe.services.campaign_difficulty import review_facilitator
from girlframe.services.ai_mission_briefings import DraftMissionBriefingService
from girlframe.services.campaign_opening import CampaignOpeningService, OpeningDraft
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_npc_delivery import NpcDeliveryService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.director_planning import DirectorPlanningService
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
from girlframe.services.session_zero import SessionZeroService
from girlframe.services.sheet_portrayal import SheetPortrayalService

REVIEW_READS = frozenset(
    {
        "activity-policy",
        "activity-review",
        "closeout",
        "status",
        "gm-work",
        "handler-draft",
        "handler-need",
        "handler-commitments",
        "plan-review",
        "ruling",
        "scene-opening",
        "scene-initiative",
        "scene-initiative-review",
        "timing-review",
        "world-draft",
    }
)
ALTERNATE_CHOICES = frozenset({
    "gorgon_asset_capability", "gorgon_defend", "gorgon_damage_asset",
    "tag_window", "harpy_beneath_select",
})


def alternate_choice_fields(decision):
    from girlframe.discord_adapter.m2_forms import Field
    from girlframe.discord_adapter.m2_ui import choice_fields

    kind = decision["kind"]
    if kind == "gorgon_asset_capability":
        return [
            Field("flag", "Approve capability and reach", (("yes", "Approve"), ("no", "Decline"))),
            Field("text", "Your ruling", paragraph=True),
        ]
    if kind == "gorgon_defend":
        labels = {"damage": "Take the blow", "play": "Make your assigned response Play"}
        options = tuple((value, labels[value]) for value in decision["detail"]["options"])
        return [
            Field("options", "How do you respond?", options),
            Field("text", "Describe your response", paragraph=True),
        ]
    if kind == "gorgon_damage_asset":
        assets = tuple((asset["id"], asset["name"]) for asset in decision["detail"]["assets"])
        return [
            Field("options", "Your Asset taking the blow", assets),
            Field("text", "Describe the hit", paragraph=True),
        ]
    return choice_fields(decision)


MODEL_WRITES = frozenset({
    "activity-review-run", "handler-need-generate", "mission-briefing-queue",
    "mission-briefing-run", "plan-generate", "reaction-generate", "ruling-generate",
    "world-generate",
})
REVIEW_WRITES = frozenset(
    {
        "activity-policy-save",
        "activity-review-run",
        "activity-review-refer",
        "close",
        "configure",
        "handler-approve",
        "handler-reject",
        "handler-need-open",
        "handler-need-generate",
        "handler-need-review",
        "handler-commitment-link",
        "plan-generate",
        "plan-review",
        "ruling-open",
        "ruling-generate",
        "ruling-propose",
        "scene-opening-publish",
        "scene-memory-carry",
        "scene-initiative-open",
        "scene-initiative-review",
        "time-acknowledge",
        "world-open",
        "world-generate",
        "reaction-open",
        "reaction-generate",
        "reaction-propose",
    }
)


def activity_facilitator(connection, store, fallback=None):
    opened = review_facilitator(connection, store.campaign_id)
    if opened is not None:
        return opened
    service = SessionZeroService(store)
    plan = service._latest(connection)
    if plan.plan_approved and plan.facilitator in plan.members and service._active_group(connection, plan):
        return plan.facilitator
    return fallback if plan.plan_proposal is None else None


class ReviewedActivityObservation(DirectorObservationService):
    def facilitator(self, c: Connection) -> int | None:
        return activity_facilitator(c, self.store, self.facilitator_id)


class P2Scene:
    def __init__(
        self,
        session: DirectorSessionService,
        *,
        models: OpenAIResponses | None = None,
        pilot_batch: ActivityPilotProvider | None = None,
        facilitator_id: int | None = None,
        opening_channel: int | None = None,
        setup_organizer: int | None = None,
        briefing_gateway: BriefingGateway | None = None,
        planning_provider: DirectorPlanningProvider | None = None,
    ):
        self.session = session
        self.models = models
        self.opening = CampaignOpeningService(
            session.knowledge,
            facilitator_id=facilitator_id,
            managed_setup=opening_channel is not None,
        )
        self.session_zero = SessionZeroDesk(
            SessionZeroService(session.store, group_owner=facilitator_id, setup_organizer=setup_organizer),
            opening_channel,
        )
        self.portrayal = SheetPortrayalService(session.dossiers)
        self.handler_setup = HandlerCreationService(session.store)
        self.shadow = ActivityShadowReview(session.conversation, pilot_batch)
        self.scene_opening = ActivitySceneOpening(session.context, facilitator_id)
        self.npc_delivery = NpcDeliveryService(session.context)
        self.time = ActivityTiming(session.game)
        self.timing_reviews = DirectorTimingReview(session.observer, facilitator_id)
        self.canon = ActivityCanon(session.store)
        self.mission_briefing = DraftMissionBriefingService(session.store, briefing_gateway)
        self.planning = DirectorPlanningService(session.context, provider=planning_provider)
        self.handler_followups = ActivityHandlerFollowups(session)

    @classmethod
    def reviewed_activity(
        cls,
        game: GameService,
        *,
        facilitator_id: int | None,
        opening_channel: int,
        handler_batch: ActivityBatchProvider,
        pilot_batch: ActivityPilotProvider | None = None,
        planning_provider: DirectorPlanningProvider | None = None,
        review_models: OpenAIResponses | None = None,
    ) -> "P2Scene":
        """Wire trusted role providers. The authenticated host owns entry and configuration."""
        observer = ReviewedActivityObservation(
            game.store,
            activity_shadow=True,
            reviewed_activity_trial=True,
            facilitator_id=facilitator_id,
        )
        observer.game = game
        context = DirectorContextService(observer)
        conversation = DirectorConversationService(
            context, handler_mode="reviewed", activity_batch=handler_batch
        )
        outcomes = GMOutcomeService(
            context,
            ModelOutcomes(review_models) if review_models else None,
            require_response_scope=True,
        )
        return cls(
            DirectorSessionService(context, conversation=conversation, outcomes=outcomes),
            facilitator_id=facilitator_id,
            opening_channel=opening_channel,
            models=review_models,
            pilot_batch=pilot_batch,
            planning_provider=planning_provider,
        )

    def ai_enabled(self) -> bool:
        with self.session.store.engine.connect() as c:
            observer = self.session.observer
            return observer._activity_policy(c)["enabled"] and observer.facilitator(c) is not None

    @classmethod
    def model_fixture(
        cls,
        context: DirectorContextService,
        handler: OpenAIResponses,
        director: OpenAIResponses | None = None,
        *,
        batch: OpenAIResponses | None = None,
        pilot_batch: OpenAIResponses | None = None,
        briefing_gateway: BriefingGateway | None = None,
        planning_provider: DirectorPlanningProvider | None = None,
    ) -> "P2Scene":
        """Explicit server-side wiring for synthetic observation."""
        context.observations._scope()
        conversation = DirectorConversationService(
            context,
            handler=ModelHandler(handler),
            handler_mode="reviewed",
            activity_batch=ModelActivityBatch(batch) if batch is not None else None,
        )
        outcomes = GMOutcomeService(
            context,
            ModelOutcomes(director) if director else None,
            require_response_scope=True,
        )
        return cls(
            DirectorSessionService(context, conversation=conversation, outcomes=outcomes),
            models=director,
            pilot_batch=ModelActivityPilot(pilot_batch) if pilot_batch is not None else None,
            briefing_gateway=briefing_gateway,
            planning_provider=planning_provider
            if planning_provider is not None
            else ModelDirectorPlanning(director)
            if director is not None
            else None,
        )

    def submit(self, viewer: GuildViewer, scene: str, command: AppendSceneInput) -> dict[str, Any]:
        result = self.session.submit(viewer, scene, command)
        # The scene composer gets an input receipt. Review and rules results have
        # their own authenticated surfaces and are never transcript entries.
        return {"input": result["input"]}

    def timeline(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        timeline = self.session.timeline(viewer, scene)
        if self.session.observer.reviewed_activity_trial:
            with self.session.store.engine.connect() as c:
                state = load_state(c, self.session.store.campaign_id)
            for entry in timeline["entries"]:
                actor = entry["actor"]
                sheet = state.sheets.get(actor["entity"])
                if (
                    actor["kind"] == "pilot"
                    and sheet
                    and sheet.character_id == actor["incarnation"]
                ):
                    entry["speaker"] = sheet.callsign
        return timeline

    def _review_viewer(self, c: Connection, viewer: GuildViewer) -> GuildViewer:
        observer = self.session.observer
        if observer.reviewed_activity_trial and viewer.user_id == observer.facilitator(c):
            return replace(viewer, is_administrator=True, activity_review=True)
        return viewer

    def authorize_provider(self, viewer: GuildViewer) -> None:
        with self.session.store.engine.connect() as c:
            reviewer = self._review_viewer(c, viewer)
            if not reviewer.activity_review:
                raise WorkflowError("Only the trial facilitator can check providers.")
            self.session.store.administrator(reviewer)
            self.session.game.authorize(c, reviewer, game=False)

    def trial_scenes(self, viewer: GuildViewer) -> dict[str, Any]:
        observer = self.session.observer
        if not observer.reviewed_activity_trial:
            return {"scenes": []}
        with self.session.store.engine.connect() as c:
            self.session.game.authorize(c, viewer, game=False)
            reviewer = self._review_viewer(c, viewer)
            caster = load_state(c, self.session.store.campaign_id)
            rows = t.m2["m2_scenes"]
            identities = c.scalars(
                sa.select(rows.c.id).where(
                    rows.c.campaign_id == self.session.store.campaign_id, rows.c.open.is_(True)
                )
            ).all()
            available = []
            for identity in identities:
                try:
                    row = observer._scene(c, identity, reviewer)
                except WorkflowError:
                    continue
                if not row["participants"]:
                    continue
                speaker = "handler" if viewer.user_id == caster.handler else "pilot"
                opening = self.scene_opening.current(c, row)
                available.append(
                    {
                        "id": identity,
                        "label": opening.location if opening else f"Scene {row['channel_id']}",
                        "speaker": speaker if viewer.user_id in row["participants"] else None,
                    }
                )
        return {"scenes": available}

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
            "handler_needs": work["handler_needs"],
            "can_generate_handler_need": self.models is not None,
            "timing_reviews": work["timing_reviews"],
            "response_requests": work["response_requests"],
            "npc_roster": self.session.reactions.npc_roster(viewer, scene),
            "model_rulings": self.session.outcomes.provider is not None,
            "response_targets": targets,
            **(
                {
                    "scene_initiatives": self.session.reactions.pending(
                        viewer, scene, gm=True, handler_initiative=True
                    )
                }
                if self.session.observer.activity_shadow
                else {}
            ),
            **(
                {"planning": self.planning.work(viewer, scene)}
                if self.session.observer.activity_shadow
                else {}
            ),
            **({"next_plan": work["next_plan"]} if "next_plan" in work else {}),
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
        if self.session.observer.reviewed_activity_trial and route in REVIEW_READS:
            with self.session.store.engine.connect() as c:
                viewer = self._review_viewer(c, viewer)
        if route in SESSION_ZERO_READS and identity is None:
            state = self.session_zero.read(viewer, route)
            if route == "session-zero" and state.get("can_edit_plan") and "pilot_generator" not in state:
                state["pilot_generator"] = {
                    "callsigns": PILOT_CALLSIGNS,
                    "portrayals": tuple(item.model_dump(mode="json") for item in PILOT_PORTRAYALS),
                    "girl_types": GIRL_TYPES,
                    "frame_types": FRAME_TYPES,
                }
            return state
        if route == "portrayal-sheets" and identity is None:
            return self.portrayal.view(viewer)
        if route == "portrayal-preview" and identity is not None and scene:
            return self.portrayal.preview(viewer, scene, identity)
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
        if route.startswith("canon-") and identity is None:
            return self.canon.read(viewer, scene, route)
        if route == "mission-briefing":
            if identity is not None:
                return self.mission_briefing.get(viewer, identity)
            with self.session.store.engine.connect() as c:
                try:
                    self.mission_briefing.briefings._principal(c, viewer)
                except WorkflowError:
                    handler = False
                else:
                    handler = True
            return {
                "drafts": self.mission_briefing.list(viewer),
                "enabled": self.session.store.policy.ai_mission_briefing is not None,
                "facilitator": viewer.user_id == self.session.store.policy.canon_facilitator_id,
                "can_request": handler,
            }
        if route == "activity-review":
            return {"batches": self.shadow.records(viewer, scene)}
        if route == "handler-hunt" and scene and identity is not None:
            return self.handler_followups.signatures.hunt_preview(viewer, scene, identity)
        if route == "handler-native-work" and scene:
            from girlframe.discord_adapter.m2_forms import Field
            from girlframe.discord_adapter.m2_ui import choice_fields
            from girlframe.discord_adapter.m3_tag_markers import marker_field

            work = self.handler_followups.read(viewer, scene)
            for item in work["signatures"]["choices"]:
                if not item.pop("show_form", False):
                    continue
                try:
                    decision = self.session.game.decision(viewer, item["id"])
                except WorkflowError:
                    continue
                kind = item["kind"]
                fields = choice_fields(decision)
                yes_no = (("yes", "Yes"), ("no", "No"))
                if kind == "battle_assault_table":
                    fields = [
                        Field("flag", "Does the opposing Asset have a vast advantage?", yes_no),
                        Field("text", "Your reasoning", paragraph=True),
                    ]
                elif kind == "engage_assault_extra":
                    detail = decision["engage"]
                    maneuvers = tuple((key, key.replace("_", " ")) for key in detail["maneuvers"])
                    assets = tuple((x["id"], x["name"]) for x in detail["assets"])
                    fields = [
                        Field("options", "Choose the earned Engage maneuver", maneuvers),
                        Field("text", "What do you do?", paragraph=True, required=False),
                    ]
                    fields.extend(
                        Field("fields." + key, label + " Asset", assets, minimum=0, required=False)
                        for key, label in maneuvers
                    )
                elif kind in (
                    "battle_low_damage",
                    "battle_actor_damage",
                    "battle_target_damage",
                    "battle_trainer_protect",
                ):
                    fields = [
                        Field(
                            "fields.asset",
                            "Affected Asset",
                            tuple((x["id"], x["name"]) for x in decision["battle"]["assets"]),
                        )
                    ]
                elif kind == "battle_handler":
                    fields = [
                        Field(
                            "options",
                            "Choose consequences",
                            tuple((x, x.replace("_", " ")) for x in decision["battle"]["options"]),
                            maximum=2,
                        ),
                        Field("text", "Actual collateral, if any", required=False),
                    ]
                elif kind == "battle_counter":
                    fields = [
                        Field(
                            "options",
                            "Choose counters or pass",
                            (("pass", "Pass"),)
                            + tuple(
                                (x, x.replace("_", " ")) for x in decision["battle"]["options"]
                            ),
                            maximum=decision["battle"]["maximum"],
                        )
                    ]
                if item["kind"] == "tag_window":
                    if extra := marker_field(decision):
                        fields.append(extra)
                    elif len(decision.get("tag_markers", [])) == 1:
                        item["tag_marker"] = decision["tag_markers"][0]["token"]
                item["fields"] = [asdict(field) for field in fields]
            return work
        if route == "scene-opening" and scene and identity is None:
            return self.scene_opening.view(viewer, scene)
        if route == "scene-initiative" and scene and identity is None:
            options = self.session.reactions.initiative_options(viewer, scene)
            return {
                "options": [
                    item
                    | {"model_configured": self._initiative_model(item["actor"]["kind"]) is not None}
                    for item in options
                ],
            }
        if route == "scene-initiative-review" and scene and identity is not None:
            return self.session.reactions.handler_initiative_review(viewer, scene, identity)
        if route == "scene-alternate-actors" and scene and identity is None:
            return {"actors": self.session.reactions.initiative.alternate_controls(viewer, scene)}
        if route == "scene-alternate-handovers" and scene and identity is None:
            from girlframe.services.m3_npc_handover import NpcHandoverService

            native = NpcHandoverService(self.session.game)
            with self.session.store.engine.connect() as c:
                self.session.observer._scene(c, scene, viewer)
                state = load_state(c, self.session.store.campaign_id)
                owned = [x.id for x in native.tasks(c, state, viewer) if x.scene == scene]
            return {"handovers": [native.get(viewer, ident) | {"id": ident} for ident in owned]}
        if route == "scene-alternate-choices" and scene and identity is None:
            with self.session.store.engine.connect() as c:
                self.session.observer._scene(c, scene, viewer)
                actions = self.session.reactions.alternate_action_ids(c, scene)
            choices = []
            for item in self.session.game.choices(viewer):
                if item["action_id"] not in actions or item["kind"] not in ALTERNATE_CHOICES:
                    continue
                decision = self.session.game.decision(viewer, item["id"])
                fields = alternate_choice_fields(decision)
                if fields:
                    choices.append(dict(
                        id=item["id"], revision=item["revision"], kind=item["kind"],
                        fields=[asdict(field) for field in fields],
                    ))
            return {"choices": choices}
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
        if route == "plan-review" and scene and identity is not None:
            return self.planning.private(viewer, scene, identity)
        if route == "pilot-dossiers" and identity is None:
            return self.session.dossiers.pilot_options(viewer, scene)
        if route == "dossier-review" and identity is not None:
            return self.session.dossiers.review(viewer, scene, identity).model_dump(mode="json")
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
        if route == "handler-need" and identity is not None:
            proposal = self.session.conversation.private_handler_need(viewer, scene, identity)
            if proposal["status"] == "stale_reopen_source":
                return {"id": identity, "status": proposal["status"]}
            return proposal
        if route == "handler-commitments" and self.session.observer.activity_shadow:
            from girlframe.services.handler_commitments import HandlerCommitments

            return {"items": HandlerCommitments(self.session.context).work(viewer, scene)}
        if route == "world-draft" and identity is not None:
            return self.session.worldbuilding.private(viewer, scene, identity)
        if route == "npc-owner-review" and identity is not None:
            return self.session.reactions.owner_review(viewer, scene, identity)
        if route == "handler-sheet":
            with self.session.store.engine.connect() as c:
                self.session.observer._authorize_input(c, viewer, scene, "handler")
            return self.handler_setup.view(viewer)
        raise ValueError("Unknown scene view.")

    def _initiative_model(self, actor_kind: str) -> ModelReactions | None:
        if actor_kind == "handler":
            provider = self.session.conversation.activity_batch
            if isinstance(provider, ModelActivityBatch):
                return ModelReactions(provider.client)
        elif actor_kind in ("npc", "pilot", "external_pilot", "gorgon"):
            provider = self.shadow.pilot_provider
            if isinstance(provider, ModelActivityPilot):
                return ModelReactions(provider.client)
        if not self.session.observer.reviewed_activity_trial and self.models is not None:
            return ModelReactions(self.models)
        return None

    def write(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        route: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if self.session.observer.reviewed_activity_trial and route in REVIEW_WRITES:
            with self.session.store.engine.connect() as c:
                viewer = self._review_viewer(c, viewer)
        if self.session.observer.reviewed_activity_trial and route in MODEL_WRITES and not self.ai_enabled():
            raise WorkflowError("AI assistance is off for this campaign.")
        if route in SESSION_ZERO_WRITES:
            return self.session_zero.write(viewer, key, route, data)
        if route.startswith("canon-") or route == "scene-safety":
            return self.canon.write(viewer, key, scene, route, data)
        if route == "mission-briefing-queue" and data.keys() == {"facts"}:
            facts = data["facts"]
            if not isinstance(facts, list) or not all(isinstance(fact, str) for fact in facts):
                raise ValueError("Select facts from the current Handler's knowledge.")
            return {"id": self.mission_briefing.queue(viewer, key, tuple(facts))}
        if route == "mission-briefing-run" and data.keys() == {"id"}:
            if not isinstance(data["id"], str):
                raise ValueError("Choose your saved briefing request.")
            return self.mission_briefing.run(viewer, data["id"])
        if route == "mission-briefing-review" and data.keys() == {"id", "result", "approve"}:
            if (
                not isinstance(data["id"], str)
                or not isinstance(data["result"], str)
                or type(data["approve"]) is not bool
            ):
                raise ValueError("Choose the exact draft result and a review decision.")
            return self.mission_briefing.review(
                viewer, key, data["id"], data["result"], approve=data["approve"]
            )
        if route == "mission-briefing-offer" and data.keys() == {"briefing_draft", "pilots"}:
            if not isinstance(data["briefing_draft"], str) or not isinstance(data["pilots"], list):
                raise ValueError("Choose an approved draft and its invited Pilots.")
            return self.mission_briefing.offer(
                viewer, key, data["briefing_draft"], tuple(map(_snowflake, data["pilots"]))
            )
        if route == "gm-answer" and data.keys() == {"source", "revision"}:
            if not isinstance(data["source"], str) or type(data["revision"]) is not int:
                raise ValueError("Choose your current GM request.")
            return self.session.answer_gm(viewer, key, scene, data["source"], data["revision"])
        if route == "open-declared-keep" and data.keys() == {"review", "sheet_revision", "heat"}:
            if (
                not isinstance(data["review"], str)
                or type(data["sheet_revision"]) is not int
                or type(data["heat"]) is not int
            ):
                raise ValueError("Confirm the original declaration and your native cost.")
            return self.session.open_declared_keep(
                viewer, scene, data["review"], data["sheet_revision"], data["heat"]
            )
        if route == "handler-start-brief" and data.keys() == {"draft", "game_revision"}:
            if not isinstance(data["draft"], str) or type(data["game_revision"]) is not int:
                raise ValueError("Choose the current approved Handler briefing action.")
            return self.session.conversation.start_handler_brief(
                viewer, scene, data["draft"], data["game_revision"]
            )
        if route == "handler-start-play":
            play = data.get("play")
            fields = {"draft", "game_revision", "play"}
            if play == "get_them_alone":
                fields.add("advocate_order")
            if play == "break_down":
                fields.add("breakdown_account")
            if (
                data.keys() != fields
                or play
                not in (
                    "brief",
                    "support",
                    "expectation",
                    "dress_them_down",
                    "get_them_alone",
                    "break_down",
                )
                or not isinstance(data["draft"], str)
                or type(data["game_revision"]) is not int
                or (play == "get_them_alone" and data["advocate_order"] not in ("amuse", "silence"))
                or (
                    play == "break_down"
                    and (
                        not isinstance(data["breakdown_account"], str)
                        or not 1 <= len(data["breakdown_account"].strip()) <= 1200
                    )
                )
            ):
                raise ValueError("Choose an approved Handler Play and complete its native fields.")
            return self.session.conversation.start_handler_play(
                viewer,
                scene,
                data["draft"],
                data["game_revision"],
                expected_play=cast(BatchHandlerPlay, play),
                advocate_order=cast(AdvocateOrder | None, data.get("advocate_order")),
                breakdown_account=data.get("breakdown_account"),
            )
        if route == "handler-native" and scene:
            return self.handler_followups.write(viewer, key, scene, data)
        if route == "portrayal-draft" and data.keys() == {"actor", "version", "character_setup"}:
            if type(data["version"]) is not int:
                raise ValueError("Use the current approved dossier revision.")
            return self.portrayal.draft(
                viewer,
                key,
                ActorRef.model_validate(data["actor"]),
                data["version"],
                character_setup=CharacterSetup.model_validate_json(json.dumps(data["character_setup"])),
            )
        if route == "portrayal-draft" and data.keys() == {"actor", "version", "portrayal"}:
            if type(data["version"]) is not int:
                raise ValueError("Use the current approved dossier revision.")
            return self.portrayal.draft(
                viewer,
                key,
                ActorRef.model_validate(data["actor"]),
                data["version"],
                portrayal=PilotPortrayal.model_validate(data["portrayal"]),
            )
        if (
            route == "portrayal-experience"
            and scene
            and data.keys()
            == {
                "actor",
                "version",
                "reference",
                "text",
            }
        ):
            if type(data["version"]) is not int:
                raise ValueError("Use the current approved dossier revision.")
            return self.portrayal.draft(
                viewer,
                key,
                ActorRef.model_validate(data["actor"]),
                data["version"],
                scene=scene,
                experience=DossierPerspective(
                    text=data["text"], knowledge_refs=(data["reference"],)
                ),
            )
        if route == "portrayal-confirm" and data.keys() == {"actor", "id"}:
            if not isinstance(data["id"], str):
                raise ValueError("Choose the actual saved draft.")
            return self.portrayal.confirm(
                viewer, key, ActorRef.model_validate(data["actor"]), data["id"]
            )
        if route == "portrayal-memory" and scene and data.keys() == {"actor", "version", "memory"}:
            if type(data["version"]) is not int:
                raise ValueError("Use the current approved dossier revision.")
            return self.portrayal.draft(
                viewer,
                key,
                ActorRef.model_validate(data["actor"]),
                data["version"],
                scene=scene,
                memory=DossierMemoryEdit.model_validate_json(json.dumps(data["memory"])),
            )
        if (
            route == "portrayal-continuity"
            and scene
            and data.keys() == {"actor", "version", "updates"}
        ):
            updates = data["updates"]
            if (
                type(data["version"]) is not int
                or not isinstance(updates, list)
                or not 1 <= len(updates) <= 3
            ):
                raise ValueError("Use the current dossier revision and one to three updates.")
            return self.portrayal.draft(
                viewer,
                key,
                ActorRef.model_validate(data["actor"]),
                data["version"],
                scene=scene,
                continuity=tuple(
                    DossierContinuityEdit.model_validate_json(json.dumps(update))
                    for update in updates
                ),
            )
        if route == "pilot-dossier-propose" and data.keys() in (
            {"actor", "origin"}, {"actor", "origin", "version"}
        ):
            version = data.get("version", 0)
            if type(version) is not int:
                raise ValueError("Use the current approved dossier revision.")
            return self.session.dossiers.propose_pilot(
                viewer,
                key,
                scene,
                ActorRef.model_validate(data["actor"]),
                PilotDossierOrigin.model_validate(data["origin"]),
                version,
            )
        if route == "dossier-confirm" and data.keys() == {"id"} and isinstance(data["id"], str):
            return self.session.dossiers.confirm(viewer, key, scene, data["id"])
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
        if route == "activity-review-refer" and scene and data.keys() == {"run"}:
            if not isinstance(data["run"], str) or not 1 <= len(data["run"]) <= 100:
                raise ValueError("Select a current flagged review.")
            return self.shadow.refer(viewer, key, scene, data["run"])
        if route == "plan-generate" and scene and data.keys() == {"kind", "source_scene", "source"}:
            kind, source_scene, source = data["kind"], data["source_scene"], data["source"]
            if (
                kind not in ("outcome", "closeout")
                or not isinstance(source_scene, str)
                or not isinstance(source, str)
                or not source_scene
                or not source
            ):
                raise ValueError("Choose a current planning source.")
            return self.planning.generate(viewer, key, scene, kind, source_scene, source)
        if route == "plan-review" and scene and data.keys() == {"proposal", "decision"}:
            proposal, decision = data["proposal"], data["decision"]
            if (
                not isinstance(proposal, str)
                or not proposal
                or decision not in ("approve", "reject")
            ):
                raise ValueError("Use the current plan and an explicit review decision.")
            return self.planning.review(viewer, key, scene, proposal, decision)
        if route == "scene-opening-publish" and scene and data.keys() == {"revision", "draft"}:
            revision = data["revision"]
            if not isinstance(revision, str) or len(revision) != 64:
                raise ValueError("Use the current scene opening preview.")
            draft = SceneOpeningDraft.model_validate_json(json.dumps(data["draft"]))
            return self.scene_opening.publish(viewer, key, scene, revision, draft)
        if route == "scene-memory-carry" and scene and data.keys() == {"source_scene", "review"}:
            source, review = data["source_scene"], data["review"]
            if (
                not isinstance(source, str)
                or len(source) != 36
                or not isinstance(review, str)
                or len(review) != 64
            ):
                raise ValueError("Use a current scene memory suggestion.")
            return self.scene_opening.carry_memory(viewer, key, scene, source, review)
        if route == "front-preparation" and scene and data.keys() == {"move", "decision"}:
            move, decision = data["move"], data["decision"]
            if (
                not isinstance(move, str)
                or len(move) != 64
                or decision not in ("prepare", "decline")
            ):
                raise ValueError("Use the current preparation review.")
            return self.session.fronts.review_preparation(viewer, key, scene, move, decision)
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
            campaign_draft = OpeningDraft.model_validate_json(json.dumps(data["draft"]))
            return self.opening.save(viewer, key, scene, data["revision"], campaign_draft)
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
        if (
            route == "handler-commitment-link"
            and self.session.observer.activity_shadow
            and data.keys() == {"commitment", "reference"}
            and all(isinstance(value, str) and value for value in data.values())
        ):
            from girlframe.services.handler_commitments import HandlerCommitments

            return HandlerCommitments(self.session.context).link(
                viewer, key, scene, data["commitment"], data["reference"]
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
        if (
            route == "scene-initiative-open"
            and scene
            and data.keys() == {"option"}
            and isinstance(data["option"], str)
            and len(data["option"]) == 64
        ):
            return self.session.reactions.open_initiative(viewer, key, scene, data["option"])
        if (
            route == "scene-alternate-control" and scene
            and data.keys() == {"actor", "enabled", "revision"}
            and type(data["enabled"]) is bool
            and (data["revision"] is None or isinstance(data["revision"], str))
        ):
            return self.session.reactions.initiative.control_alternate(
                viewer, key, scene, ActorRef.model_validate(data["actor"]),
                data["enabled"], data["revision"],
            )
        if (
            route == "scene-alternate-start" and scene
            and data.keys() == {"proposal", "choices"}
            and isinstance(data["proposal"], str) and isinstance(data["choices"], dict)
        ):
            return self.session.reactions.start_alternate_play(
                viewer, scene, data["proposal"], data["choices"],
            )
        if route == "scene-alternate-refer" and scene and data.keys() == {"actor"}:
            return self.session.reactions.initiative.refer_alternate(
                viewer, key, scene, ActorRef.model_validate(data["actor"]),
            )
        if (
            route == "scene-alternate-handover-answer" and scene
            and data.keys() == {"id", "revision", "item"} and isinstance(data["id"], str)
            and type(data["revision"]) is int and (data["item"] is None or isinstance(data["item"], str))
        ):
            from girlframe.services.m3_npc_handover import NpcHandoverService, records

            def guard(c: Connection) -> None:
                self.session.observer._scene(c, scene, viewer)
                state = load_state(c, self.session.store.campaign_id)
                if not any(x.id == data["id"] and x.scene == scene for x in records(state)):
                    raise WorkflowError("Use the original handover in its own scene.")

            with self.session.store.source_guard(guard):
                return NpcHandoverService(self.session.game).respond(
                    viewer, key, data["id"], data["revision"], data["item"],
                )
        if (
            route == "scene-alternate-answer" and scene
            and data.keys() == {"id", "revision", "answer"} and isinstance(data["id"], str)
            and type(data["revision"]) is int
        ):
            def guard(c: Connection) -> None:
                self.session.observer._scene(c, scene, viewer)
                table = t.m2["m2_choices"]
                action = c.scalar(sa.select(table.c.action_id).where(
                    table.c.campaign_id == self.session.store.campaign_id,
                    table.c.id == data["id"], table.c.kind.in_(ALTERNATE_CHOICES),
                    table.c.actor_id == str(viewer.user_id),
                ))
                if action not in self.session.reactions.alternate_action_ids(c, scene):
                    raise WorkflowError("Use your own native choice from this scene's alternate Play.")

            return self.session.game.respond(viewer, key, data["id"], data["revision"],
                ChoiceAnswer.model_validate_json(json.dumps(data["answer"])), source_authorize=guard)
        if (
            route == "scene-initiative-review"
            and scene
            and data.keys() == {"proposal", "decision", "reason"}
            and isinstance(data["proposal"], str)
            and data["decision"] in ("approve", "reject")
        ):
            return self.session.reactions.review(
                viewer,
                key,
                scene,
                data["proposal"],
                data["decision"],
                data["reason"],
                handler_initiative=True,
            )
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
        if route == "handler-need-review" and data.keys() == {"proposal", "decision", "reason"}:
            if not isinstance(data["proposal"], str) or data["decision"] not in (
                "approve",
                "reject",
            ):
                raise ValueError("Choose a saved response-need proposal and its review decision.")
            return self.session.conversation.review_handler_need(
                viewer, key, scene, data["proposal"], data["decision"], data["reason"]
            )
        if (
            route == "reaction-generate"
            and data.keys() == {"request"}
            and data["request"].startswith("reaction-initiative:")
        ):
            request = data["request"]
            packet = self.session.reactions.packet(viewer, scene, request)
            model = self._initiative_model(packet["actor"]["kind"])
            if model is None:
                raise WorkflowError("The approved initiative role has no configured model.")
            return self.session.reactions.generate(viewer, key, scene, request, model)
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


def manual_campaign_setup(
    game: GameService,
    facilitator: int,
    *,
    opening_channel: int | None = None,
    setup_organizer: int | None = None,
) -> P2Scene:
    """Use verified campaign identity for setup with Director observation disabled."""
    observer = DirectorObservationService(game.store)
    observer.game = game
    return P2Scene(
        DirectorSessionService(DirectorContextService(observer)),
        facilitator_id=facilitator,
        opening_channel=opening_channel,
        setup_organizer=setup_organizer,
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
