"""Private Activity intake review using the existing observation leases and Handler policy."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from itertools import chain
from typing import Any, TypeVar
from uuid import uuid4

import sqlalchemy as sa
from pydantic import BaseModel, ValidationError
from sqlalchemy import Connection

from girlframe.ai.activity_batch import (
    ActivityBatchDecision,
    ActivityBatchPacket,
    ActivityPilotDecision,
    ActivityPilotPacket,
    ActivityPilotProvider,
    AddressPilotListeners,
    BatchListener,
    Escalate,
    FictionBeat,
    HeardReport,
    NpcSpeech,
    PilotAudienceDecision,
    PilotContribution,
    PilotListener,
    PilotSpeech,
    PrivatePilotIntent,
    ProposeEvent,
    ReviewNativeSignature,
    ScopedActivityPilotProvider,
    StaySilent,
    scene_details,
)
from girlframe.ai.conversation import (
    RULES_IN_PROSE,
    ConversationReply,
    HandlerDecision,
    HandlerRequest,
    handler_question,
    handler_space_request,
)
from girlframe.ai.director_dossiers import DossierPacket, DossierPressure
from girlframe.ai.director_reactions import ReactionProposal
from girlframe.ai.handler_initiative import (
    OFF_DUTY_PERSONAL,
    HandlerInitiative,
    alternate_initiative,
    initiative_for,
    off_duty_initiative,
)
from girlframe.ai.model_transport import (
    ModelBudgetExhausted,
    ModelInvalidResponse,
    ModelTimeout,
    ModelUnavailable,
)
from girlframe.ai.observation import Observation, ObservationPolicy, ReviewBatch
from girlframe.ai.pilot_initiative import PilotInitiative, pilot_initiative, pilot_lenses
from girlframe.ai.worldbuilding import WorldbuildingProposal
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.activity_dialogue import floor_claims, npc_owned
from girlframe.services.activity_fiction import ActivityFiction
from girlframe.services.activity_handler_plays import play_opportunities
from girlframe.services.activity_handler_signatures import native_signature
from girlframe.services.activity_scene_opening import ActivitySceneOpening
from girlframe.services.director_conversation import (
    DirectorConversationService,
    handler_address_name,
)
from girlframe.services.director_dossiers import DirectorDossierService
from girlframe.services.director_fronts import DirectorFrontService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_planning import DirectorPlanningService
from girlframe.services.director_reactions import DirectorReactionService
from girlframe.services.director_worldbuilding import DirectorWorldbuildingService
from girlframe.services.handler_commitments import HandlerCommitments
from girlframe.services.m2_state import load_state
from girlframe.services.m3_handler_book_orders import private_handler_scene
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

# Catch explicit OOC outcome announcements. A facilitator still reads for
# semantic claims, implied decisions, and unsupported feelings in free prose.
_OUTCOME_ANNOUNCEMENT = re.compile(
    r"\b(?:mission|objective|operation|scene)\s+(?:(?:is|has been|was|now)\s+)?"
    r"(?:complete(?:d)?|succeeded|failed|won|lost|over|resolved)\b|"
    r"\b(?:i|we)\s+(?:declare|mark|confirm|end|complete|resolve)\s+"
    r"(?:the|this|our)\s+(?:mission|objective|operation|scene)\b",
    re.IGNORECASE,
)
_PLAYER_NARRATION = re.compile(
    r"(?:^|[.!]\s+|\n)\s*you\s+(?:chose\b|feel\b|felt\b|"
    r"(?:decide|choose)\b(?!\s+(?:whether\b|(?:what|how|when|where|which)\s+to\b)))",
    re.IGNORECASE,
)
_UNRESOLVED_CUES = ("no_handler_need", "update_already_addressed")


@dataclass(frozen=True)
class _BatchProjection:
    packet: ActivityBatchPacket
    source: Observation
    request: HandlerRequest
    fingerprint: str


@dataclass(frozen=True)
class _PilotProjection:
    packet: ActivityPilotPacket
    reaction: dict[str, Any]


_Decision = TypeVar("_Decision", bound=BaseModel)


class ActivityShadowReview:
    def __init__(
        self,
        conversation: DirectorConversationService,
        pilot_provider: ActivityPilotProvider | None = None,
    ):
        self.conversation = conversation
        self.pilot_provider = pilot_provider
        self.observer, self.store = conversation.observations, conversation.store
        self.knowledge = DirectorKnowledgeService(conversation.context)
        self.fiction = ActivityFiction(conversation.context)
        self.fronts = DirectorFrontService(conversation.context)
        self.openings = ActivitySceneOpening(conversation.context)

    def _scope(self, c: Connection, gm: GuildViewer, scene: str) -> None:
        if not self.observer.activity_shadow or self.conversation.handler_mode != "reviewed":
            raise WorkflowError(
                "ACTIVITY_SHADOW_UNAVAILABLE: use an enabled reviewed Activity mode."
            )
        self.store.administrator(gm)
        self.observer._scope()
        self.observer.game.unpaused(c)
        row = self.observer._scene(c, scene, gm)
        state = self.observer._state(c, scene)
        if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
            raise WorkflowError("OBSERVATION_DISABLED: current scene consent is required.")

    def _readiness(
        self, c: Connection, gm: GuildViewer, scene: str, item: Observation
    ) -> dict[str, Any]:
        result = {
            "source": item.source_id,
            "revision": item.source_revision,
            "sequence": item.sequence,
            "kind": item.kind,
        }
        if item.kind == "completed_play":
            return result | {
                "action": item.action_id,
                "native_event": item.event_id,
                "disposition": "assigned_to_human_gm",
            }
        current = {
            role.ref: role.controller
            for role in self.knowledge._actor_views(c, self.observer._scene(c, scene))
        }
        if current.get(item.actor) != int(item.author_id):
            decision = HandlerDecision(action="WAIT", reason="no_handler_need")
            return result | {"decision": decision.model_dump(mode="json"), "facts": []}
        if npc_owned(c, self.store.campaign_id, scene, (item.source_id,)):
            return result | {"disposition": "addressed_npc_has_floor"}
        try:
            request, _ = self.conversation._requests(
                c, gm, scene, item.source_id, "handler", review_source=item
            )
        except WorkflowError as error:
            if not str(error).startswith("HANDLER_UNAVAILABLE:"):
                raise
            decision = HandlerDecision(action="WAIT", reason="handler_absent")
            return result | {"decision": decision.model_dump(mode="json"), "facts": []}
        assert isinstance(request, HandlerRequest)
        decision, _ = self.conversation._handler_decision(c, scene, item, request)
        return result | {
            "decision": decision.model_dump(mode="json"),
            "handler": request.context.actor.model_dump(mode="json")
            if request.context.actor
            else None,
            "facts": [
                dict(id=ref.id, text=ref.text)
                for ref in (*request.context.references, *request.closed_scene_reports)
            ]
            if decision.action == "RESPOND"
            else [],
        }

    def _ensure_pending(self, c: Connection, gm: GuildViewer, batch: ReviewBatch) -> None:
        self._scope(c, gm, batch.scene_id)
        row = self.observer._scene(c, batch.scene_id)
        state = self.observer._state(c, batch.scene_id)
        runs = t.director["runs"]
        status = c.scalar(
            sa.select(runs.c.status).where(
                runs.c.campaign_id == self.store.campaign_id,
                runs.c.run_id == batch.run_id,
                runs.c.lease_token == batch.lease_token,
            )
        )
        self.observer.game.unpaused(c)
        if (
            status != "running"
            or batch.lease_until <= self.store.clock()
            or not self.observer._consented(c, row, state)
            or batch.guard_digest != self.observer._guard(c, row, state)
        ):
            raise WorkflowError("STALE_CLAIM: prepare a fresh Activity batch.")

    @staticmethod
    def _earlier_reports(
        batch: ReviewBatch, cast: dict[str, int], listener: ActorRef
    ) -> tuple[HeardReport, ...]:
        """Use only the reviewer’s bounded tail of comms heard by the current cast."""
        return tuple(
            HeardReport(
                source_id=item.source_id,
                revision=item.source_revision,
                speaker=item.actor,
                text=item.text,
            )
            for item in batch.recent_tail
            if item.kind == "message"
            and item.text
            and item.fictional_channel == "comms"
            and not item.gm_addressed
            and item.cast_controllers == cast
            and item.actor != listener
            and cast.get(item.actor.token) == int(item.author_id)
        )

    def _projection(
        self, c: Connection, gm: GuildViewer, batch: ReviewBatch
    ) -> _BatchProjection | None:
        scene = batch.scene_id
        try:
            role = self.conversation.context._handler_for_request(c, gm, scene)
        except WorkflowError as error:
            if str(error).startswith("HANDLER_UNAVAILABLE:"):
                return None
            raise
        handler = role.actor
        assert handler is not None
        if self.conversation._player_handler(c, handler):
            return None
        row = self.observer._scene(c, scene)
        opening = self.openings.current(c, row)
        if opening is None:
            raise WorkflowError(
                "SCENE_OPENING_REQUIRED: publish the scene opening before AI review."
            )
        actors = self.knowledge._actor_views(c, row)
        cast = {view.ref: view.controller for view in actors}
        if handler not in cast:
            return None
        npc_turns, covered_turns = floor_claims(
            c,
            self.store.campaign_id,
            scene,
            batch.inputs,
            {role.token: controller for role, controller in cast.items()},
        )
        held = npc_turns | covered_turns
        heard = [
            (item, next(iter(self.knowledge.heard(c, scene, item.source_id, handler)), ""))
            for item in batch.inputs
            if item.kind == "message"
            and item.actor.kind == "pilot"
            and item.source_id not in held
            and cast.get(item.actor) == int(item.author_id)
            and item.cast_controllers is not None
            and item.cast_controllers.get(handler.token) == cast[handler]
            and not item.gm_addressed
            and item.fictional_channel != "private"
        ]
        heard = [(item, line) for item, line in heard if line]
        if not heard:
            return None
        source = heard[-1][0]
        request, fingerprint = self.conversation._requests(
            c, gm, scene, source.source_id, "handler", review_source=source
        )
        assert isinstance(request, HandlerRequest)
        name = handler_address_name(request, actors)
        addressed = next(
            (
                item
                for item, line in reversed(heard)
                if handler_question(line)
                or (name is not None and handler_question(line, name))
                or handler_space_request(line, name)
            ),
            None,
        )
        if addressed is not None and addressed != source:
            source = addressed
            request, fingerprint = self.conversation._requests(
                c, gm, scene, source.source_id, "handler", review_source=source
            )
            assert isinstance(request, HandlerRequest)
        need, need_key = self.conversation._handler_decision(c, scene, source, request)
        if addressed is None and need.reason in _UNRESOLVED_CUES and len(heard) > 1:
            approved = self.conversation._approved_cue_sources(
                c, scene, tuple(item.source_id for item, _ in heard[:-1])
            )
            for item, _ in reversed(heard[:-1]):
                if item.source_id not in approved:
                    continue
                earlier, revision = self.conversation._requests(
                    c, gm, scene, item.source_id, "handler", review_source=item
                )
                assert isinstance(earlier, HandlerRequest)
                earlier_need, earlier_key = self.conversation._handler_decision(
                    c, scene, item, earlier
                )
                if earlier_need.reason == "reviewed_character_cue":
                    source, request, fingerprint = item, earlier, revision
                    need, need_key = earlier_need, earlier_key
                    break
        initiative = None
        profile = request.playbook_profile
        personality = request.character_notes.personality if request.character_notes else None
        if (
            addressed is None
            and profile is not None
            and need.reason in _UNRESOLVED_CUES
            and need_key is None
        ):
            delivered = None
            primary = (
                (
                    item,
                    initiative_for(
                        profile,
                        item.source_id,
                        spoken,
                        earlier_comms=tuple(
                            (prior.source_id, line)
                            for prior, line in heard[:index]
                            if item.fictional_channel == prior.fictional_channel == "comms"
                            and item.cast_controllers == prior.cast_controllers
                        )
                        if profile.playbook == "Advocate"
                        else (),
                    ),
                )
                for index, (item, spoken) in reversed(list(enumerate(heard)))
            )
            alternate = (
                (
                    (
                        item,
                        alternate_initiative(
                            profile,
                            personality,
                            item.source_id,
                            spoken,
                            seed=f"{self.store.campaign_id}:{scene}:{handler.token}:{item.actor.token}",
                        ),
                    )
                    for item, spoken in reversed(heard)
                )
                if personality is not None
                else ()
            )
            personal = (
                (
                    item,
                    off_duty_initiative(request.character_notes, opening, item.source_id, spoken),
                )
                for item, spoken in reversed(heard)
            )
            for item, candidate in chain(primary, personal, alternate):
                if candidate is None or self.conversation.peer_covered(c, scene, item, handler):
                    continue
                if delivered is None:
                    delivered = self.fiction.delivered_initiatives(c, scene, handler)
                if candidate.issue in delivered.get(item.actor, ()):
                    continue
                if candidate.prompt == OFF_DUTY_PERSONAL and any(
                    candidate.issue in issues for issues in delivered.values()
                ):
                    continue
                if item != source:
                    source = item
                    request, fingerprint = self.conversation._requests(
                        c, gm, scene, source.source_id, "handler", review_source=source
                    )
                    assert isinstance(request, HandlerRequest)
                    need, need_key = self.conversation._handler_decision(c, scene, source, request)
                if need.reason in _UNRESOLVED_CUES and need_key is None:
                    initiative = candidate
                    if candidate.prompt == "room_to_speak_privately":
                        try:
                            _, girl = private_handler_scene(
                                self.observer.game,
                                c,
                                load_state(c, self.store.campaign_id),
                                int(row["channel_id"]),
                                handler,
                            )
                        except WorkflowError:
                            girl = None
                        if girl != item.actor:
                            initiative = candidate.model_copy(update={"possible_play": None})
                break
        if addressed is None and need.reason in _UNRESOLVED_CUES and need_key is None:
            commitments = HandlerCommitments(self.conversation.context)
            for item, _ in reversed(heard):
                if result := commitments.ready(c, scene, handler, item.actor):
                    if item != source:
                        other, revision = self.conversation._requests(
                            c, gm, scene, item.source_id, "handler", review_source=item
                        )
                        assert isinstance(other, HandlerRequest)
                        other_need, other_key = self.conversation._handler_decision(
                            c, scene, item, other
                        )
                        if other_need.reason not in _UNRESOLVED_CUES or other_key is not None:
                            continue
                        source, request, fingerprint = item, other, revision
                    need = HandlerDecision(
                        action="RESPOND", reason="commitment_result", source_refs=(result.id,)
                    )
                    initiative = None
                    break
        opportunity = None
        if (
            addressed is None
            and initiative is None
            and need.reason in _UNRESOLVED_CUES
            and need_key is None
        ):
            opportunity = DirectorPlanningService(self.conversation.context).portrayal(
                c, scene, handler, listener=source.actor
            )
            if opportunity is not None:
                need = HandlerDecision(
                    action="RESPOND",
                    reason="planned_handler_move",
                    source_refs=opportunity.source_refs,
                    move_id=opportunity.id,
                )
        if opportunity is None and (need.action == "RESPOND" or initiative):
            opportunity = self.fronts.portrayal_move(c, scene, handler)
        speakers = {item.actor for item, _ in heard}
        packet = ActivityBatchPacket(
            scene=scene,
            opening=opening,
            trigger=batch.reason,
            has_completed_play=any(item.kind == "completed_play" for item in batch.inputs),
            handler=handler,
            persona=request.persona,
            playbook_profile=request.playbook_profile,
            character_notes=request.character_notes,
            character_setup=request.persona.profile.character_setup if request.persona else None,
            references=request.context.references,
            private_memories=request.closed_scene_reports,
            reports=tuple(
                HeardReport(
                    source_id=item.source_id,
                    revision=item.source_revision,
                    speaker=item.actor,
                    text=line,
                )
                for item, line in heard
            ),
            earlier_reports=self._earlier_reports(
                batch, {role.token: controller for role, controller in cast.items()}, handler
            ),
            eligible_listeners=tuple(
                BatchListener(
                    actor=listener.ref,
                    label=listener.label,
                    report_ids=tuple(
                        item.source_id
                        for item, line in heard
                        if line in self.knowledge.heard(c, scene, item.source_id, listener.ref)
                    ),
                )
                for listener in actors
                if listener.ref in speakers
            ),
            scene_details=scene_details(request.context.references),
            response_need=need,
            response_report_id=source.source_id if need.action == "RESPOND" else None,
            initiative=initiative,
            recent_contributions=self.fiction.recent(c, scene, handler, source.actor),
            opportunity=opportunity,
            play_opportunities=play_opportunities(
                self.conversation.context, c, scene, source, request, need, initiative
            ),
            native_signatures=native_signature(self.observer.game, c, row, handler, source.actor),
        )
        return _BatchProjection(packet, source, request, fingerprint)

    def _pilot_projection(self, c: Connection, batch: ReviewBatch) -> _PilotProjection | None:
        scene = batch.scene_id
        dossiers = DirectorDossierService(self.conversation.context)
        pilots = dossiers.activity_pilots(c, scene)
        if not pilots:
            return None
        row = self.observer._scene(c, scene)
        opening = self.openings.current(c, row)
        if opening is None:
            raise WorkflowError(
                "SCENE_OPENING_REQUIRED: publish the scene opening before AI review."
            )
        table = t.director_context["shadow"]
        previous = sa.func.json_extract(table.c.body_json, "$.model_outcome.pilot")
        last = c.scalar(
            sa.select(previous)
            .where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                previous.is_not(None),
            )
            .order_by(sa.func.json_extract(table.c.body_json, "$.frontier").desc())
            .limit(1)
        )
        actors = sorted(pilots, key=lambda actor: (pilots[actor][0].casefold(), actor.token))
        if (index := next((i for i, actor in enumerate(actors) if actor.token == last), -1)) >= 0:
            actors = actors[index + 1 :] + actors[: index + 1]
        opportunities = {actor: self.fronts.portrayal_move(c, scene, actor) for actor in actors}
        actors.sort(key=lambda actor: not bool((move := opportunities[actor]) and move.tracked))
        cast_views = self.knowledge._actor_views(c, row)
        cast = {view.ref: view.controller for view in cast_views}
        captured = {role.token: controller for role, controller in cast.items()}
        npc_turns, covered_turns = floor_claims(
            c, self.store.campaign_id, scene, batch.inputs, captured
        )
        held = npc_turns | covered_turns
        common_reports = [
            HeardReport(
                source_id=item.source_id,
                revision=item.source_revision,
                speaker=item.actor,
                text=item.text,
            )
            for item in batch.inputs
            if item.kind == "message"
            and item.text
            and item.source_id not in held
            and item.fictional_channel == "comms"
            and not item.gm_addressed
            and item.cast_controllers == captured
            and cast.get(item.actor) == int(item.author_id)
        ]
        for actor in actors:
            callsign, traits = pilots[actor]
            selected: tuple[Observation, str, PilotInitiative | None] | None = None
            for source in reversed(batch.inputs):
                if (
                    source.kind != "message"
                    or source.source_id in held
                    or source.actor == actor
                    or source.gm_addressed
                    or source.fictional_channel == "private"
                    or cast.get(source.actor) != int(source.author_id)
                    or source.cast_controllers is None
                    or source.cast_controllers.get(actor.token) != cast[actor]
                ):
                    continue
                heard = next(iter(self.knowledge.heard(c, scene, source.source_id, actor)), "")
                if not heard:
                    continue
                initiative = pilot_initiative(
                    traits,
                    source.source_id,
                    heard,
                    seed=f"{self.store.campaign_id}:{scene}:{actor.token}:{source.actor.token}",
                )
                if selected is None or initiative is not None:
                    selected = (source, heard, initiative)
                if initiative is not None:
                    break
            if selected is None:
                continue
            source, heard, initiative = selected
            request = "reaction-request:activity-pilot:" + batch.run_id
            reaction = DirectorReactionService(self.conversation.context)._packet(
                c, scene, actor, source.source_id, request, batch.run_id, activity_pilot=True
            )
            dossier = DossierPacket.model_validate_json(json.dumps(reaction["role"]["dossier"]))
            shared_speech = set(self.knowledge.heard(c, scene, source.source_id, actor))
            known_by = {
                ref.id: set(ref.known_by) for ref in self.conversation.context._current(c, scene)
            }
            audience = tuple(
                PilotListener(
                    actor=view.ref,
                    label=view.label,
                    report_ids=(source.source_id,),
                    source_refs=tuple(
                        ref
                        for ref in dossier.source_refs
                        if view.ref.token in known_by.get(ref, ())
                    ),
                )
                for view in cast_views
                if view.ref != actor
                and (
                    view.ref.kind != "npc"
                    or view.controller == cast[actor]
                    or dossiers._visible_identity(c, actor, view.ref)
                )
                and (
                    view.ref == source.actor
                    or shared_speech
                    <= set(self.knowledge.heard(c, scene, source.source_id, view.ref))
                )
            )
            nearby_reports = tuple(
                report
                for report in common_reports
                if report.source_id != source.source_id and report.speaker != actor
            )[-4:]
            heard_ids = {source.source_id, *(report.source_id for report in nearby_reports)}
            latest_heard = next(
                item.source_id for item in reversed(batch.inputs) if item.source_id in heard_ids
            )
            return _PilotProjection(
                packet=ActivityPilotPacket(
                    scene=scene,
                    opening=opening,
                    trigger=batch.reason,
                    callsign=callsign,
                    dossier=dossier,
                    report=HeardReport(
                        source_id=source.source_id,
                        revision=source.source_revision,
                        speaker=source.actor,
                        text=heard,
                    ),
                    nearby_reports=nearby_reports,
                    earlier_reports=self._earlier_reports(batch, captured, actor),
                    latest_heard_report_id=latest_heard,
                    audience=audience,
                    portrayal_lenses=pilot_lenses(traits),
                    initiative=initiative,
                    scene_details=scene_details(dossier.context.references),
                    front_refs=tuple(
                        item["id"] for item in reaction["role"]["fronts"]["fragments"][-6:]
                    ),
                    recent_contributions=self.fiction.recent(
                        c, scene, actor, source.actor, include_carried=True
                    ),
                    received_offers=self.fiction.received_offers(c, scene, actor),
                    opportunity=opportunities[actor],
                    native_plays=tuple(reaction["role"].get("native_plays", ())),
                ),
                reaction=reaction,
            )
        return None

    @staticmethod
    def _check_fiction(text: str) -> None:
        if not text.strip() or _OUTCOME_ANNOUNCEMENT.search(text):
            raise WorkflowError("BATCH_DIALOGUE_AUTHORITY: keep native outcomes in the engine.")
        if _PLAYER_NARRATION.search(text):
            raise WorkflowError("BATCH_PLAYER_AGENCY: leave other characters' decisions to them.")

    def _check_action(self, fiction: FictionBeat) -> None:
        if fiction.own_action is not None:
            self._check_fiction(fiction.own_action)
            if not re.match(r"^I(?:\b|['’])", fiction.own_action.strip()):
                raise WorkflowError("FICTION_ACTION_OWNER: describe only the speaker's action.")
            if RULES_IN_PROSE.search(fiction.own_action):
                raise WorkflowError("FICTION_ACTION_RULES: use native controls for effects.")

    def _apply_pilot(
        self,
        c: Connection,
        gm: GuildViewer,
        scene: str,
        view: _PilotProjection,
        result: ActivityPilotDecision,
        *,
        front_move: str | None = None,
    ) -> dict[str, str]:
        decision = result.decision
        if isinstance(decision, StaySilent):
            return {"status": "wait", "reason": decision.reason}
        if isinstance(decision, Escalate):
            return {
                "status": "escalated",
                "reason": decision.reason,
                "source": view.packet.report.source_id,
            }
        self._check_fiction(decision.text)
        self._check_action(decision.fiction)
        recipients = decision.intended_recipients
        if decision.kind != "DIALOGUE" and (decision.fiction != FictionBeat() or recipients):
            raise WorkflowError("FICTION_INTENT_ONLY: keep a proposed action in review.")
        if RULES_IN_PROSE.search(decision.text):
            raise WorkflowError("PILOT_RULES_IN_DIALOGUE: keep rules in the native controls.")
        reactions = DirectorReactionService(self.conversation.context)
        request = view.reaction["request_id"]
        citations = decision.source_refs
        if decision.fiction.answers_offer:
            offer = next(
                (
                    item
                    for item in view.packet.received_offers
                    if item.reference == decision.fiction.answers_offer
                ),
                None,
            )
            if offer is None or (recipients and recipients != (offer.speaker,)):
                raise WorkflowError("FICTION_OFFER_UNAVAILABLE: keep the original speaker.")
            recipients = (offer.speaker,)
            if offer.reference not in citations:
                citations += (offer.reference,)
        if len(set(recipients)) != len(recipients) or not set(recipients) <= {
            listener.actor for listener in view.packet.audience
        }:
            raise WorkflowError("AI_PILOT_AUDIENCE: select distinct eligible listeners.")
        if decision.fiction.follows_offer or decision.fiction.answers_offer:
            self.fiction.check(
                c, scene, view.packet.dossier.actor, view.packet.report.speaker, decision.fiction
            )
        with c.begin_nested():
            reactions._save(c, scene, request, "reaction_request", packet=view.reaction)
            saved = reactions._propose(
                c,
                gm,
                scene,
                request,
                ReactionProposal(
                    request_id=request,
                    kind=decision.kind,
                    text=decision.text,
                    cited_references=citations,
                    rationale="Reviewed AI Pilot contribution from an Activity batch.",
                    fiction=decision.fiction if decision.kind == "DIALOGUE" else None,
                    intended_recipients=recipients,
                    play_id=decision.play_id,
                ),
                front_move=front_move,
            )
        return {
            "status": "pilot_review",
            "reason": (
                "dialogue"
                if decision.kind == "DIALOGUE"
                else "native_play"
                if decision.play_id
                else "proposed_intent"
            ),
            "proposal_id": saved["id"],
        }

    def _draft(
        self,
        c: Connection,
        batch: ReviewBatch,
        view: _BatchProjection,
        decision: NpcSpeech,
    ) -> dict[str, str]:
        reports = {report.source_id: report for report in view.packet.reports}
        if decision.fiction.answers_offer:
            raise WorkflowError("FICTION_INTENT_ONLY: received offers use AI Pilot review.")
        if (
            len(set(decision.report_ids)) != len(decision.report_ids)
            or not set(decision.report_ids) <= reports.keys()
        ):
            raise WorkflowError("BATCH_REPORTS_INVALID: select actual heard reports.")
        selected = tuple(reports[identity] for identity in decision.report_ids)
        recipients = decision.intended_recipients
        eligible = {
            listener.actor: set(listener.report_ids) for listener in view.packet.eligible_listeners
        }
        if (
            len(set(recipients)) != len(recipients)
            or view.source.actor not in recipients
            or any(
                actor not in eligible or not set(decision.report_ids) <= eligible[actor]
                for actor in recipients
            )
            or not set(recipients) <= {report.speaker for report in selected}
        ):
            raise WorkflowError(
                "BATCH_AUDIENCE_INVALID: address original speakers who heard the cited reports."
            )
        need = view.packet.response_need
        if (
            need is not None
            and need.reason == "commitment_result"
            and (
                decision.reason != "response_need"
                or recipients != (view.source.actor,)
                or decision.fiction.offers_help
            )
        ):
            raise WorkflowError(
                "HANDLER_COMMITMENT_AUDIENCE: report the reviewed result to the original Pilot."
            )
        if (decision.reason == "character_cue") != (decision.cue is not None):
            raise WorkflowError("BATCH_CUE_INVALID: name the actual portrayal cue.")
        if decision.reason == "shared_report":
            completion = {fact.id for fact in view.packet.references if fact.topic == "completion"}
            if (
                len({report.speaker for report in selected}) != 2
                or set(recipients) != {report.speaker for report in selected}
                or view.source.source_id not in decision.report_ids
                or not completion.intersection(decision.source_refs)
            ):
                raise WorkflowError("BATCH_READBACK_INVALID: require two Pilots and a criterion.")
            # Keep already-authorized report IDs in report provenance, not in evidence citations.
            report_only = set(decision.report_ids) - {fact.id for fact in view.packet.references}
            citations = tuple(ref for ref in decision.source_refs if ref not in report_only)
            decision = decision.model_copy(update={"source_refs": citations})
            need = HandlerDecision(action="RESPOND", reason="batch_readback")
        elif decision.reason in ("character_cue", "follow_through"):
            if decision.report_ids != (view.source.source_id,):
                raise WorkflowError("BATCH_CUE_INVALID: cite the addressed Pilot's heard turn.")
            if decision.reason == "character_cue":
                profile = view.packet.playbook_profile
                initiative = view.packet.initiative
                reviewed = (
                    need is not None
                    and need.reason == "reviewed_character_cue"
                    and need.cue == decision.cue
                )
                off_duty = (
                    initiative is not None
                    and initiative.prompt == OFF_DUTY_PERSONAL
                    and decision.cue == initiative.cue
                )
                if (
                    need is None
                    or profile is None
                    or (decision.cue not in profile.cues and not off_duty)
                    or not (
                        reviewed
                        or (
                            initiative is not None
                            and initiative.report_id == view.source.source_id
                            and initiative.cue == decision.cue
                        )
                    )
                    or self.conversation.peer_covered(
                        c, batch.scene_id, view.source, view.packet.handler
                    )
                ):
                    raise WorkflowError("BATCH_CUE_INVALID: follow the Handler's eligible cues.")
                if not reviewed:
                    need = HandlerDecision(
                        action="RESPOND", reason="reviewed_character_cue", cue=decision.cue
                    )
            else:
                if not decision.fiction.follows_offer:
                    raise WorkflowError("FICTION_OFFER_UNAVAILABLE: select the delivered offer.")
                need = HandlerDecision(action="RESPOND", reason="batch_follow_through")
        elif view.source.source_id not in decision.report_ids or need is None:
            raise WorkflowError("BATCH_RESPONSE_INVALID: require the scoped response need.")
        initiative = view.packet.initiative if decision.reason == "character_cue" else None
        if initiative is not None and (support := initiative.support_report_id):
            if any(support not in eligible[actor] for actor in recipients):
                raise WorkflowError("BATCH_AUDIENCE_INVALID: keep the cue with its listeners.")
            selected += (reports[support],)
        if decision.fiction.follows_offer:
            self.fiction.check(
                c, batch.scene_id, view.packet.handler, view.source.actor, decision.fiction
            )
        self._check_fiction(decision.text)
        self._check_action(decision.fiction)
        if decision.authors_listener_action():
            raise WorkflowError("FICTION_ACTION_OWNER: describe only the Handler's action.")
        decision = decision.with_played_action()
        if (
            need is not None
            and need.reason == "planned_handler_move"
            and (
                decision.reason != "response_need"
                or recipients != (view.source.actor,)
                or not decision.fiction.own_action
                or decision.fiction.offers_help
                or decision.fiction.follows_offer
            )
        ):
            raise WorkflowError(
                "HANDLER_PLAN_ACTION: play one actual own action for the original listener."
            )
        reply = ConversationReply(
            route="handler",
            disposition="answer" if decision.source_refs else "clarification",
            text=decision.text,
            source_refs=decision.source_refs,
            provider="reviewed-handler-v1",
            handler_action=decision.fiction.own_action,
            handler_play_offer=decision.play_offer,
        )
        if decision.play_offer is not None:
            offer = next(
                (x for x in view.packet.play_opportunities if x.play == decision.play_offer), None
            )
            if (
                offer is None
                or decision.report_ids != (offer.report_id,)
                or recipients != (view.source.actor,)
                or not set(offer.source_refs) <= set(decision.source_refs)
            ):
                raise WorkflowError(
                    "HANDLER_PLAY_TRIGGER: select a scoped Play and its actual evidence."
                )
        self.conversation._validate_handler_draft(view.request, reply, need, batch_offer=True)
        identity = self.conversation._save_handler_draft(
            c,
            batch.scene_id,
            view.source,
            view.request,
            view.fingerprint,
            reply,
            need,
            "activity-readiness:" + batch.run_id,
            reports=selected,
            fiction=decision.fiction,
            intended_recipients=recipients,
            initiative=initiative,
        )
        return {"status": "draft", "reason": decision.reason, "draft_id": identity}

    def _event(
        self,
        c: Connection,
        gm: GuildViewer,
        batch: ReviewBatch,
        view: _BatchProjection,
        decision: ProposeEvent,
    ) -> dict[str, str]:
        refs = set(decision.source_refs)
        if len(refs) != len(decision.source_refs) or not refs <= {
            ref.id for ref in view.packet.references
        }:
            raise WorkflowError("BATCH_EVENT_EVIDENCE: cite only current scoped references.")
        world = DirectorWorldbuildingService(self.conversation.context)
        identity = "world-request:" + str(uuid4())
        scene = batch.scene_id
        try:
            with c.begin_nested():
                packet = world._snapshot(c, gm, scene, view.source.source_id, identity)
                world._save(
                    c,
                    scene,
                    identity,
                    "worldbuilding_request",
                    packet=packet.model_dump(mode="json"),
                )
                result = world._propose(
                    c,
                    gm,
                    scene,
                    identity,
                    WorldbuildingProposal(
                        request_id=identity,
                        action=decision.action,
                        cited_evidence=(
                            "source",
                            "native",
                            *("reference:" + ref for ref in decision.source_refs),
                        ),
                        private_reasoning="Proposed in a scoped Activity batch for human review.",
                    ),
                )
        except WorkflowError:
            return {
                "status": "escalated",
                "reason": "unsupported_world_proposal",
                "source": view.source.source_id,
            }
        return {"status": "world_review", "reason": "proposed_event", "proposal_id": result["id"]}

    @staticmethod
    def _model_decision(
        generate: Callable[[], _Decision], contract: type[_Decision]
    ) -> tuple[_Decision | None, dict[str, str]]:
        try:
            result = generate()
            if not isinstance(result, contract):
                raise TypeError("Provider output did not use the decision contract.")
            return contract.model_validate_json(result.model_dump_json()), {}
        except (TimeoutError, ModelTimeout):
            return None, {"status": "failed", "reason": "model_timeout"}
        except (ValidationError, ModelInvalidResponse, TypeError):
            return None, {"status": "rejected", "reason": "invalid_model_decision"}
        except ModelBudgetExhausted:
            return None, {"status": "failed", "reason": "model_attempt_limit"}
        except (OSError, ModelUnavailable):
            return None, {"status": "failed", "reason": "model_unavailable"}

    @staticmethod
    def _speech_packet(
        packet: ActivityPilotPacket, audience: tuple[PilotListener, ...]
    ) -> ActivityPilotPacket:
        shared = set.intersection(*(set(listener.source_refs) for listener in audience))
        dossier = packet.dossier
        references = tuple(
            ref.model_copy(
                update={
                    "dependencies": tuple(
                        ref_id for ref_id in ref.dependencies if ref_id in shared
                    ),
                    "relations": tuple(
                        link for link in ref.relations if link.reference_id in shared
                    ),
                }
            )
            for ref in dossier.context.references
            if ref.id in shared
        )
        state = dossier.state
        if state and state.terms:
            origins = {ref.origin_reference or ref.id for ref in references}
            addressed = {listener.actor for listener in audience}
            state = state.model_copy(
                update={
                    "terms": tuple(
                        term
                        for term in state.terms
                        if term.subject in addressed
                        and (
                            set(term.knowledge_refs) <= origins
                            or addressed == {term.subject}
                            and set(term.knowledge_refs)
                            <= origins | {source.reference_id for source in term.memory_sources}
                        )
                    )
                }
            )
        return packet.model_copy(
            update={
                "audience": tuple(
                    listener.model_copy(update={"source_refs": ()}) for listener in audience
                ),
                "speech": PilotSpeech(recipients=tuple(listener.actor for listener in audience)),
                "dossier": dossier.model_copy(
                    update={
                        "state": state,
                        "context": dossier.context.model_copy(update={"references": references}),
                        "source_refs": tuple(ref.id for ref in references),
                    }
                ),
                "front_refs": tuple(ref for ref in packet.front_refs if ref in shared),
                "opportunity": packet.opportunity
                if packet.opportunity and set(packet.opportunity.source_refs) <= shared
                else None,
                "scene_details": scene_details(references),
                "received_offers": tuple(
                    item for item in packet.received_offers if item.reference in shared
                ),
                "recent_contributions": tuple(
                    item for item in packet.recent_contributions if item.reference in shared
                ),
            }
        )

    def _pilot_still_current(
        self, gm: GuildViewer, batch: ReviewBatch, view: _PilotProjection
    ) -> None:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._ensure_pending(c, gm, batch)
            if self._pilot_projection(c, batch) != view:
                raise WorkflowError("STALE_CLAIM: current scoped Pilot changed.")

    def _pilot_model(
        self,
        gm: GuildViewer,
        batch: ReviewBatch,
        view: _PilotProjection,
        provider: ActivityPilotProvider,
    ) -> tuple[ActivityPilotDecision | None, dict[str, str]]:
        if not isinstance(provider, ScopedActivityPilotProvider):
            packet = view.packet
            if packet.opportunity and packet.opportunity.tracked:
                packet = packet.model_copy(update={"opportunity": None})
            decision, failure = self._model_decision(
                lambda: provider.decide(packet), ActivityPilotDecision
            )
            if (
                decision
                and isinstance(decision.decision, PilotContribution)
                and decision.decision.access_claim is not None
            ):
                return None, {"status": "rejected", "reason": "mission_access_scope"}
            return decision, failure
        packet = view.packet
        audit: dict[str, str] = {}
        for attempt in range(2):
            selected, failure = self._model_decision(
                partial(provider.select_audience, packet), PilotAudienceDecision
            )
            if selected is None:
                return None, failure | audit
            plan = selected.decision
            if isinstance(plan, (StaySilent, Escalate)):
                return ActivityPilotDecision(decision=plan), audit
            self._pilot_still_current(gm, batch, view)
            intent = plan.intent
            if intent is not None and intent.pressure_id is not None:
                portrayal = packet.dossier.state
                if not any(
                    isinstance(item, DossierPressure)
                    and item.pressure_id == intent.pressure_id
                    and item.pressure.status in ("open", "deferred")
                    for item in (portrayal.pressures if portrayal else ())
                ):
                    return None, {"status": "rejected", "reason": "pilot_intent_scope"} | audit
            draft = packet.model_copy(update={"intent": intent})
            if isinstance(plan, AddressPilotListeners):
                if (
                    intent is not None
                    and intent.move_id is not None
                    and (packet.opportunity is None or intent.move_id != packet.opportunity.id)
                ):
                    return None, {"status": "rejected", "reason": "pilot_intent_scope"} | audit
                eligible = {listener.actor: listener for listener in packet.audience}
                if (
                    len(set(plan.recipients)) != len(plan.recipients)
                    or not set(plan.recipients) <= eligible.keys()
                ):
                    return None, {"status": "rejected", "reason": "ai_pilot_audience"} | audit
                previous = packet.previous_speech
                if (
                    previous
                    and len(plan.recipients) > 1
                    and not set(plan.recipients) <= set(previous.recipients)
                ):
                    return None, {"status": "rejected", "reason": "ai_pilot_audience"} | audit
                draft = self._speech_packet(
                    draft, tuple(eligible[actor] for actor in plan.recipients)
                )
                if intent and intent.move_id and draft.opportunity is None:
                    return None, {"status": "rejected", "reason": "pilot_intent_scope"} | audit
                if intent is None or intent.move_id is None:
                    draft = draft.model_copy(update={"opportunity": None})
                elif (
                    draft.opportunity
                    and draft.opportunity.reply_from
                    and (plan.recipients != (draft.opportunity.reply_from,))
                ):
                    return None, {"status": "rejected", "reason": "pilot_intent_scope"} | audit
            elif attempt:
                return None, {"status": "rejected", "reason": "fiction_intent_only"} | audit
            elif intent and intent.move_id:
                return None, {"status": "rejected", "reason": "pilot_intent_scope"} | audit
            result, failure = self._model_decision(
                partial(provider.decide, draft), ActivityPilotDecision
            )
            if result is None:
                return None, failure | audit
            action = result.decision
            if not isinstance(action, PilotContribution):
                return result, audit
            access = draft.opportunity.mission_access if draft.opportunity else None
            if action.access_claim != access:
                return None, {"status": "rejected", "reason": "mission_access_scope"} | audit
            if isinstance(plan, PrivatePilotIntent):
                if action.kind == "SCENE_OFFER":
                    return result, audit
                return None, {"status": "rejected", "reason": "fiction_intent_only"} | audit
            assert isinstance(plan, AddressPilotListeners)
            intended = action.intended_recipients
            if action.kind != "DIALOGUE" or (
                intended
                and (len(intended) != len(set(intended)) or set(intended) != set(plan.recipients))
            ):
                return None, {"status": "rejected", "reason": "ai_pilot_audience"} | audit
            # The reaction already records its exact source turn. Only remove that turn's ID
            # if it was repeated as a citation and is not an actual evidence reference.
            anchor = draft.report.source_id
            citations = action.source_refs
            if anchor not in view.packet.dossier.source_refs:
                citations = tuple(ref for ref in citations if ref != anchor)
            missing = set(citations) - set(draft.dossier.source_refs)
            if not missing:
                action = action.model_copy(
                    update={"source_refs": citations, "intended_recipients": plan.recipients}
                )
                if draft.opportunity and draft.opportunity.tracked:
                    audit["front_move"] = draft.opportunity.id
                return ActivityPilotDecision(decision=action), audit
            if not missing <= set(view.packet.dossier.source_refs):
                return None, {"status": "rejected", "reason": "reaction_scope"} | audit
            if not attempt:
                self._pilot_still_current(gm, batch, view)
                audit = {"revision": "citation_scope"}
                packet = view.packet.model_copy(
                    update={
                        "revise_for": "citation_scope",
                        "previous_speech": draft.speech,
                        "audience": tuple(
                            listener
                            for listener in view.packet.audience
                            if listener.actor in plan.recipients
                            or missing <= set(listener.source_refs)
                        ),
                    }
                )
        return None, {"status": "rejected", "reason": "npc_delivery_knowledge"} | audit

    def _apply(
        self,
        c: Connection,
        gm: GuildViewer,
        batch: ReviewBatch,
        view: _BatchProjection,
        result: ActivityBatchDecision,
    ) -> dict[str, str]:
        decision = result.decision
        if isinstance(decision, StaySilent):
            return {"status": "wait", "reason": decision.reason}
        if isinstance(decision, Escalate):
            return {
                "status": "escalated",
                "reason": decision.reason,
                "source": view.source.source_id,
            }
        if isinstance(decision, ProposeEvent):
            return self._event(c, gm, batch, view, decision)
        if isinstance(decision, ReviewNativeSignature):
            match = next(
                (item for item in view.packet.native_signatures if item.play == decision.play),
                None,
            )
            if match is None:
                return {"status": "rejected", "reason": "handler_play_trigger"}
            receipt = {
                "status": "native_signature",
                "reason": "owned_native_work",
                "play": match.play,
            }
            if match.control and match.destination:
                receipt.update(
                    control=match.control,
                    destination=match.destination,
                    target=view.source.actor.entity,
                )
            return receipt
        return self._draft(c, batch, view, decision)

    def _record_stale(self, batch: ReviewBatch) -> None:
        runs = t.director["runs"]
        with self.store.transaction() as c:
            changed = c.execute(
                runs.update()
                .where(
                    runs.c.campaign_id == self.store.campaign_id,
                    runs.c.run_id == batch.run_id,
                    runs.c.lease_token == batch.lease_token,
                    runs.c.status.in_(("running", "stale")),
                )
                .values(status="stale")
            ).rowcount
            identity = "activity-readiness:" + batch.run_id
            if changed and not self.conversation._saved(c, identity):
                self.conversation._save_handler_record(
                    c,
                    batch.scene_id,
                    identity,
                    {
                        "record_type": "activity_readiness",
                        "run": batch.run_id,
                        "reason": batch.reason,
                        "frontier": batch.frontier,
                        "consent": batch.consent_generation,
                        "items": [],
                        "model_outcome": {"status": "stale", "reason": "context_changed"},
                    },
                )

    def _save_review(
        self,
        c: Connection,
        gm: GuildViewer,
        batch: ReviewBatch,
        outcome: dict[str, str] | None = None,
        initiative: HandlerInitiative | None = None,
    ) -> None:
        scene = batch.scene_id
        self.conversation._save_handler_record(
            c,
            scene,
            "activity-readiness:" + batch.run_id,
            {
                "record_type": "activity_readiness",
                "run": batch.run_id,
                "reason": batch.reason,
                "frontier": batch.frontier,
                "consent": batch.consent_generation,
                "items": [self._readiness(c, gm, scene, item) for item in batch.inputs],
                **({"initiative": initiative.model_dump(mode="json")} if initiative else {}),
                **({"model_outcome": outcome} if outcome is not None else {}),
            },
        )

    def _model_review(self, gm: GuildViewer, batch: ReviewBatch) -> dict[str, Any]:
        scene = batch.scene_id
        try:
            with self.store.engine.connect() as c:
                c.exec_driver_sql("BEGIN")
                self._ensure_pending(c, gm, batch)
                handler = self.conversation.activity_batch
                provider = self.pilot_provider
                initial = self._projection(c, gm, batch) if handler else None
            result = pilot_result = None
            pilot = None
            outcome = {
                "status": "wait",
                "reason": "no_eligible_handler_source" if handler else "no_eligible_pilot_source",
            }
            if (
                initial
                and initial.packet.response_need is not None
                and (initial.packet.response_need.reason == "pilot_requested_space")
            ):
                outcome = {"status": "wait", "reason": "pilot_requested_space"}
            elif handler and initial:
                result, outcome = self._model_decision(
                    lambda: handler.decide(initial.packet), ActivityBatchDecision
                )
            if provider and (
                outcome.get("status") == "wait"
                or (result is not None and isinstance(result.decision, StaySilent))
            ):
                # Reauthorize after the first call before projecting another role's context.
                with self.store.engine.connect() as c:
                    c.exec_driver_sql("BEGIN")
                    self._ensure_pending(c, gm, batch)
                    pilot = self._pilot_projection(c, batch)
                if pilot is not None:
                    pilot_result, outcome = self._pilot_model(gm, batch, pilot, provider)
            with self.store.transaction() as c:
                self._ensure_pending(c, gm, batch)
                current = self._projection(c, gm, batch) if handler else None
                if current != initial or (
                    pilot is not None and self._pilot_projection(c, batch) != pilot
                ):
                    raise WorkflowError("STALE_CLAIM: current scoped context changed.")
                self.observer.complete_in_transaction(
                    c, batch.run_id, batch.lease_token, success=True
                )
                try:
                    if pilot is not None and pilot_result is not None:
                        outcome = (
                            self._apply_pilot(
                                c,
                                gm,
                                scene,
                                pilot,
                                pilot_result,
                                front_move=outcome.pop("front_move", None),
                            )
                            | outcome
                        )
                    elif pilot is None and result is not None and current is not None:
                        outcome = self._apply(c, gm, batch, current, result)
                except WorkflowError as error:
                    code = str(error).partition(":")[0]
                    reason = code.lower() if re.fullmatch("[A-Z_]+", code) else "invalid"
                    outcome = outcome | {"status": "rejected", "reason": reason}
                if pilot is not None:
                    outcome = outcome | {"pilot": pilot.packet.dossier.actor.token}
                self._save_review(
                    c, gm, batch, outcome, current.packet.initiative if current else None
                )
        except WorkflowError:
            self._record_stale(batch)
            # Reauthorize the caller before returning the stale claim receipt.
            with self.store.engine.connect() as c:
                self._scope(c, gm, scene)
            outcome = {"status": "stale", "reason": "context_changed"}
        return {
            "run": batch.run_id,
            "frontier": batch.frontier,
            "reason": batch.reason,
            "model_outcome": outcome,
        }

    def process(self, gm: GuildViewer, scene: str) -> dict[str, Any] | None:
        model_enabled = (
            self.conversation.activity_batch is not None or self.pilot_provider is not None
        )
        with self.store.engine.connect() as c:
            self._scope(c, gm, scene)
            if model_enabled:
                if self.openings.current(c, self.observer._scene(c, scene)) is None:
                    raise WorkflowError(
                        "SCENE_OPENING_REQUIRED: publish the scene opening before AI review."
                    )
                policy = self.observer._state(c, scene).policy
                if (
                    policy.mode == "shadow"
                    and policy.quiet_seconds != ObservationPolicy().quiet_seconds
                ):
                    raise WorkflowError(
                        "ACTIVITY_BATCH_WINDOW: configure the standard 120-second quiet window."
                    )
        batch = self.observer.claim_review(scene)
        if batch is None:
            return None
        if model_enabled:
            return self._model_review(gm, batch)
        with self.store.transaction() as c:
            self._scope(c, gm, scene)
            # Verifies the frozen claim and current role/consent in the same transaction
            # that saves the review. Failure rolls back the cursor along with the review.
            self.observer.complete_in_transaction(c, batch.run_id, batch.lease_token, success=True)
            self._save_review(c, gm, batch)
        return {"run": batch.run_id, "frontier": batch.frontier, "reason": batch.reason}

    def refer(self, gm: GuildViewer, key: str, scene: str, run_id: str) -> dict[str, Any]:
        """A reviewing human files an already scoped flag to the assigned facilitator."""
        from girlframe.services.p1_facilitator import UNLISTED_ACTION, FacilitatorService

        def scoped_flag(c: Connection) -> tuple[int, int]:
            self._scope(c, gm, scene)
            row = self.observer._scene(c, scene, gm)
            runs = t.director["runs"]
            raw = c.scalar(
                sa.select(runs.c.body_json).where(
                    runs.c.campaign_id == self.store.campaign_id,
                    runs.c.scene_id == scene,
                    runs.c.run_id == run_id,
                    runs.c.status == "reviewed",
                )
            )
            record = self.conversation._saved(c, "activity-readiness:" + run_id) or {}
            outcome = record.get("model_outcome", {})
            if raw and outcome.get("status") == "escalated":
                batch = ReviewBatch.model_validate_json(raw)
                observation = next(
                    (item for item in batch.inputs if item.source_id == outcome.get("source")),
                    None,
                )
                if (
                    batch.consent_generation == self.observer._state(c, scene).consent_generation
                    and observation is not None
                    and observation == self.observer._latest_source(c, observation.source_id)
                ):
                    return int(row["channel_id"]), load_state(c, self.store.campaign_id).revision
            raise WorkflowError("ACTIVITY_REFERRAL_STALE: select a current flagged batch.")

        with self.store.engine.connect() as c:
            channel, revision = scoped_flag(c)

        def require_current(c: Connection) -> None:
            scoped_flag(c)

        return FacilitatorService(self.observer.game).request(
            gm,
            key,
            channel,
            "scene",
            scene,
            UNLISTED_ACTION,
            revision,
            "A reviewed AI batch flagged an unsupported outcome. Review batch " + run_id + ".",
            shared=True,
            source_guard=require_current,
        )

    def records(
        self, gm: GuildViewer, scene: str, *, run_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._scope(c, gm, scene)
            current = self.observer._state(c, scene)
            table, runs = t.director_context["shadow"], t.director["runs"]
            rows = c.execute(
                sa.select(table.c.body_json, runs.c.body_json.label("batch"))
                .join_from(
                    table,
                    runs,
                    sa.and_(
                        table.c.campaign_id == runs.c.campaign_id,
                        table.c.scene_id == runs.c.scene_id,
                        table.c.id == "activity-readiness:" + runs.c.run_id,
                    ),
                )
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    runs.c.status.in_(("reviewed", "stale")),
                    runs.c.run_id == run_id if run_id is not None else sa.true(),
                )
                .order_by(sa.func.json_extract(table.c.body_json, "$.frontier").desc())
                .limit(20)
            )
            result = []
            for row in rows:
                record = json.loads(row.body_json)
                batch = ReviewBatch.model_validate_json(row.batch)
                if batch.consent_generation != current.consent_generation:
                    continue
                if record.get("model_outcome", {}).get("status") == "stale":
                    result.append(record)
                    continue
                for i, item in enumerate(batch.inputs):
                    live = self.observer._latest_source(c, item.source_id)
                    if live != item or not self._same_scope(c, gm, scene, item, record["items"][i]):
                        if record.get("initiative", {}).get("report_id") == item.source_id:
                            record.pop("initiative")
                        record["items"][i] = {
                            "source": item.source_id,
                            "revision": item.source_revision,
                            "sequence": item.sequence,
                            "status": "stale",
                        }
                result.append(record)
            return result

    def _same_scope(
        self,
        c: Connection,
        gm: GuildViewer,
        scene: str,
        item: Observation,
        original: dict[str, Any],
    ) -> bool:
        try:
            return self._readiness(c, gm, scene, item) == original
        except WorkflowError:
            return False
