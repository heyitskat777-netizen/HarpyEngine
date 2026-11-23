"""Resumable Director session coordination over existing native authorities."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.conversation import RULES_IN_PROSE, HandlerNeedProvider
from girlframe.ai.director_dossiers import HandlerExperienceSelection
from girlframe.ai.knowledge import KnowledgeProvider
from girlframe.ai.observation import AppendSceneInput, Observation
from girlframe.database import tables as t
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_battle_state import Context
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_observation import _digest
from girlframe.services.director_play_review import DirectorPlayReviewService
from girlframe.services.director_timing_review import DirectorTimingReview
from girlframe.services.gm_outcome_compile import CHOICES
from girlframe.services.gm_outcomes import GMOutcomeService, SourceKind
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorSessionService:
    def __init__(
        self,
        context: DirectorContextService,
        *,
        conversation: DirectorConversationService | None = None,
        outcomes: GMOutcomeService | None = None,
        knowledge_provider: KnowledgeProvider | None = None,
        knowledge_gm: GuildViewer | None = None,
        need_provider: HandlerNeedProvider | None = None,
        need_gm: GuildViewer | None = None,
    ):
        self.context, self.observer, self.store = context, context.observations, context.store
        self.game = self.observer.game
        self.conversation = conversation or DirectorConversationService(context)
        self.outcomes = outcomes or GMOutcomeService(
            context, require_response_scope=self.conversation.handler_mode == "reviewed"
        )
        self.reviews = DirectorPlayReviewService(context)
        self.timing_reviews = DirectorTimingReview(self.observer)
        self.responses = self.outcomes.responses
        from girlframe.services.director_knowledge import DirectorKnowledgeService

        self.knowledge = DirectorKnowledgeService(context)
        from girlframe.services.director_worldbuilding import DirectorWorldbuildingService

        self.worldbuilding = DirectorWorldbuildingService(context)
        from girlframe.services.director_dossiers import DirectorDossierService
        from girlframe.services.director_fronts import DirectorFrontService
        from girlframe.services.director_reactions import DirectorReactionService

        self.dossiers = DirectorDossierService(context)
        self.fronts = DirectorFrontService(context)
        self.reactions = DirectorReactionService(context)
        if (knowledge_provider is None) != (knowledge_gm is None):
            raise ValueError("Configure the trusted GM principal and knowledge provider together")
        self.knowledge_provider, self.knowledge_gm = knowledge_provider, knowledge_gm
        if (need_provider is None) != (need_gm is None):
            raise ValueError("Configure the trusted response-need provider and GM together")
        if need_provider is not None and self.conversation.handler_mode != "reviewed":
            raise ValueError("Reviewed response needs require reviewed Handler mode")
        self.need_provider, self.need_gm = need_provider, need_gm

    def submit(self, viewer: GuildViewer, scene: str, command: AppendSceneInput) -> dict[str, Any]:
        """Retry the same command to resume after a saved input or GM-only success."""
        source = self.observer.append_scene_input(viewer, scene, command)
        if source.source_id is None or self.observer.activity_shadow:
            return {"input": source.model_dump(mode="json"), "conversation": None}
        if self.knowledge_provider is not None:
            assert self.knowledge_gm is not None
            self.knowledge.acquire(
                self.knowledge_gm,
                command.command_key + ":knowledge",
                scene,
                source.source_id,
                self.knowledge_provider,
            )
        if self.need_provider is not None:
            assert self.need_gm is not None
            self.conversation.acquire_handler_need(
                self.need_gm,
                command.command_key + ":need",
                scene,
                source.source_id,
                self.need_provider,
            )
        conversation = self.conversation.process_message(
            viewer, command.command_key + ":route", scene, source.source_id, source.source_revision
        )
        return {"input": source.model_dump(mode="json"), "conversation": conversation}

    def timeline(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        """The Activity scene timeline contains persisted, viewer-visible fiction only."""
        self.observer._scope()
        with self.store.engine.connect() as c:
            row = self.observer._scene(c, scene, viewer, allow_closed=True)
            state = self.observer._state(c, scene)
            if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
                raise WorkflowError("OBSERVATION_DISABLED: retain current scene consent.")
            inputs = self.observer._pending(scene, 0, include_handled=True).subquery()
            audience = sa.func.json_each(inputs.c.body_json, "$.audience_ids").table_valued("value")
            observations = (
                Observation.model_validate_json(raw)
                for raw in c.scalars(
                    sa.select(inputs.c.body_json)
                    .where(
                        inputs.c.kind == "message",
                        sa.exists(
                            sa.select(audience.c.value).where(
                                audience.c.value == str(viewer.user_id)
                            )
                        ),
                        sa.or_(
                            inputs.c.owner_id == str(viewer.user_id),
                            sa.func.coalesce(
                                sa.func.json_extract(inputs.c.body_json, "$.fictional_channel"),
                                "scene",
                            )
                            != "private",
                        ),
                    )
                    .order_by(inputs.c.sequence.desc())
                    .limit(75)
                )
            )
            entries = [
                {
                    "id": item.source_id,
                    "revision": item.source_revision,
                    "sequence": item.sequence,
                    "created": item.accepted_at,
                    "ordinal": 0,
                    "actor": item.actor.model_dump(mode="json"),
                    "kind": "input",
                    "channel": item.fictional_channel,
                    "text": item.text,
                    "own_input": item.author_id == str(viewer.user_id),
                }
                for item in observations
                if not item.gm_addressed
            ]
            shadow = t.director_context["shadow"]
            for identity in c.scalars(
                sa.select(shadow.c.id).where(
                    shadow.c.campaign_id == self.store.campaign_id,
                    shadow.c.scene_id == scene,
                    shadow.c.id.like("gm-narration:%"),
                )
            ):
                try:
                    approved = self.context._approved_outcome(c, scene, identity, allow_closed=True)
                except WorkflowError:
                    continue
                if str(viewer.user_id) not in approved["audience_ids"] or RULES_IN_PROSE.search(
                    approved["text"]
                ):
                    continue
                entries.append(
                    {
                        "id": identity,
                        "actor": {"kind": "gm", "entity": "", "incarnation": None},
                        "kind": "gm_narration",
                        "sequence": approved.get("after_sequence", state.sequence),
                        "ordinal": approved.get("ordinal", 0),
                        "created": approved.get("created_at", 0),
                        "text": approved["text"],
                    }
                )
            for entry in self.conversation.delivery._contributions(
                c, viewer, scene, allow_closed=True
            ):
                if RULES_IN_PROSE.search(entry["text"]) or RULES_IN_PROSE.search(
                    entry.get("action") or ""
                ):
                    continue
                entries.append(
                    {
                        "id": entry["id"],
                        "actor": entry["actor"],
                        "kind": "handler",
                        "sequence": entry["after_sequence"]
                        if entry["after_sequence"] is not None
                        else state.sequence,
                        "ordinal": entry["ordinal"],
                        "created": entry["delivered_at"],
                        "text": entry["text"],
                        "action": entry["action"],
                    }
                )
            from girlframe.services.director_npc_delivery import NpcDeliveryService

            entries.extend(NpcDeliveryService(self.context).contributions(c, viewer, scene))
            entries.sort(key=lambda item: (item["sequence"], item["ordinal"]))
            return {
                "scene_id": scene,
                "revision": row["revision"],
                "open": row["open"],
                "entries": entries[-75:],
            }

    def close_scene(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        channel: int,
        expected_revision: int,
        *,
        report_ids: tuple[str, ...] = (),
        experience: HandlerExperienceSelection | None = None,
    ) -> dict[str, Any]:
        """Close the native scene and file its approved Handler report atomically."""
        self.observer._scope()
        return self.game.close_scene(
            viewer,
            key,
            channel,
            director_scene=(scene, expected_revision),
            report_ids=report_ids,
            experience=experience,
        )

    def closeout_options(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        from girlframe.services.director_closeout import closeout_options, commitment_offers

        with self.store.engine.connect() as c:
            self.conversation._handler_review_scope(c, viewer, scene)
            row = self.observer._scene(c, scene, viewer)
            offers = commitment_offers(self.context, c, row)
            return {
                "revision": row["revision"],
                "reports": closeout_options(self.context, c, row),
                **({"offers": offers} if offers else {}),
            }

    def handler_reports(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        from girlframe.services.director_closeout import handler_reports

        self.observer._scope()
        with self.store.engine.connect() as c:
            _, _, actor = self.observer._authorize_input(c, viewer, scene, "handler")
            return {
                "reports": [
                    x.model_dump(mode="json")
                    for x in handler_reports(self.context, c, actor, scene=scene)
                ]
            }

    def work(self, viewer: GuildViewer, scene: str, *, gm: bool = False) -> dict[str, Any]:
        """One current work list; selecting GM scope never grants another owner's choices."""
        with self.store.engine.connect() as c:
            self.outcomes._scope(c, viewer, scene, gm=gm)
            work = self.reviews._work(c, scene, None if gm else viewer)
            table = t.director_context["shadow"]
            records = [
                json.loads(raw)
                for raw in c.scalars(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        sa.or_(table.c.id.like("gm-outcome:%"), table.c.id.like("gm-narration:%")),
                    )
                )
            ]
            proposals = []
            for record in records:
                if record.get("record_type") != "gm_outcome_proposal":
                    continue
                packet, _ = self.outcomes._load(c, scene, record["id"])
                if not gm and packet.owner_id != str(viewer.user_id):
                    continue
                confirmed = (
                    c.scalar(
                        sa.select(t.commands.c.interaction_key)
                        .where(
                            t.commands.c.campaign_id == self.store.campaign_id,
                            t.commands.c.interaction_key.like("gm-outcome:" + record["id"] + ":%"),
                        )
                        .limit(1)
                    )
                    is not None
                )
                status = "confirmed" if confirmed else "awaiting_confirmation"
                if not confirmed:
                    try:
                        self.outcomes._current(c, packet)
                    except (WorkflowError, ValueError):
                        status = "stale_reopen_source"
                proposals.append(
                    {
                        "id": record["id"],
                        "operation": packet.operation,
                        "owner_id": packet.owner_id,
                        "status": status,
                    }
                )
            sources = []
            if gm:
                canon = load_state(c, self.store.campaign_id)
                candidates: list[tuple[SourceKind, str]] = [
                    ("choice", row["id"]) for row in work["choices"] if row["kind"] in CHOICES
                ]
                candidates.extend(
                    ("table", identity)
                    for identity in {
                        row["action_id"]
                        for row in work["choices"]
                        if row["kind"] in ("battle_assault_table", "wyvern_answers_done")
                    }
                )
                seen_battles = set()
                for fact in reversed(canon.facts):
                    if fact.get("kind") == "battle_context":
                        battle = Context.model_validate_json(fact["body"])
                        if battle.id in seen_battles:
                            continue
                        seen_battles.add(battle.id)
                        if battle.scene == scene and battle.state == "proposed":
                            candidates.append(("battle", battle.id))
                # Campaign-scoped grants must still pass the exact scene/target proof.
                candidates.extend(
                    ("handler_grant", g.id) for g in canon.handler_plays if g.state == "pending"
                )
                actions = t.m2["m2_actions"]
                completed = c.scalars(
                    sa.select(actions.c.id).where(
                        actions.c.campaign_id == self.store.campaign_id,
                        actions.c.scene_id == scene,
                        actions.c.state == "complete",
                    )
                )
                narrated = {
                    r["action_id"]
                    for r in records
                    if r.get("record_type") == "gm_outcome_narration"
                }
                candidates.extend(
                    ("completed", identity) for identity in completed if identity not in narrated
                )
                for kind, identity in candidates:
                    try:
                        packet = self.outcomes._snapshot(c, scene, kind, identity, None)
                    except (WorkflowError, ValueError):
                        continue
                    action = packet.native.get("action")
                    sources.append(
                        {
                            "source_kind": kind,
                            "source_id": identity,
                            "action_id": action.get("id") if isinstance(action, dict) else None,
                            "operation": packet.operation,
                            "owner_id": packet.owner_id,
                            "frame_required": packet.operation == "keep",
                        }
                    )
            return {
                "scene_id": scene,
                "scope": "gm" if gm else "own",
                "knowledge_sources": self.knowledge.pending(viewer, scene) if gm else [],
                "handler_drafts": self.conversation.pending_handler(viewer, scene) if gm else [],
                "timing_reviews": self.timing_reviews.pending(c, scene) if gm else [],
                "handler_play_offers": self.conversation.handler_play_offers(viewer, scene),
                "handler_deliveries": self.conversation.delivery.pending(viewer, scene),
                "handler_needs": self.conversation.pending_handler_needs(viewer, scene)
                if gm
                else [],
                "response_requests": self.responses.pending(viewer, scene, gm=gm),
                "worldbuilding": self.worldbuilding.pending(viewer, scene, gm=gm),
                "dossiers": self.dossiers.pending(viewer, scene, gm=gm),
                "reactions": self.reactions.pending(viewer, scene, gm=gm),
                **(
                    {
                        "next_plan": self.fronts.plan_review(
                            c,
                            scene,
                            owner=None if gm else viewer.user_id,
                        )
                    }
                    if self.observer.activity_shadow
                    else {}
                ),
                "front_attention": [
                    {k: value[k] for k in ("id", "title", "version", "status")}
                    for value in self.fronts.view(viewer, scene)["fronts"]
                    if value["status"] == "ready"
                ]
                if gm
                else [],
                "native": work,
                "outcome_sources": sources,
                "decision_routes": [self._decision_route(c, row) for row in work["choices"]],
                "proposals": proposals,
                "declarations": self._declarations(c, viewer, scene, gm=gm),
                "gm_requests": self._gm_requests(c, viewer, scene),
                "publication": "scoped_activity"
                if self.observer.reviewed_activity_trial
                else "synthetic_only",
            }

    def campaign_work(
        self, viewer: GuildViewer, scene: str, *, period_id: str | None = None
    ) -> dict[str, Any]:
        """Recipient-safe OOC lifecycle dashboard; no implicit Handler knowledge."""
        from girlframe.services.m3_mission_control import MissionControlService
        from girlframe.services.m3_missions import MissionService
        from girlframe.services.m3_off_duty import OffDutyService
        from girlframe.services.m3_off_duty_cycle import CycleService

        with self.store.engine.connect() as c:
            self.outcomes._scope(c, viewer, scene)
        missions = MissionService(self.store)
        periods = OffDutyService(missions)
        current = periods.current(viewer)
        selected = period_id or (current["id"] if current else None)
        return {
            "scene_id": scene,
            "missions": MissionControlService(missions).view(viewer),
            "current_period_id": current["id"] if current else None,
            "period": CycleService(periods).review(viewer, selected) if selected else None,
            "required_work": missions.owned_work(viewer),
            "scope": "recipient_ooc",
            "application": "native_services_only",
        }

    def _decision_route(self, c: Connection, choice: dict[str, Any]) -> dict[str, Any]:
        from girlframe.services.m3_princess_sex import decision_author

        action = self.game.action(c, choice["action_id"])
        author = decision_author(
            self.game, c, load_state(c, self.store.campaign_id), action, choice
        )
        return {
            "choice_id": choice["id"],
            "kind": choice["kind"],
            "owner_id": str(author if author is not None else choice["actor_id"]),
            "route": "typed_outcome" if choice["kind"] in CHOICES else "native_owner",
            "operation": CHOICES.get(choice["kind"]),
            "confirmation": "original_owner_required",
        }

    def decision_context(self, viewer: GuildViewer, scene: str, choice_id: str) -> dict[str, Any]:
        """Private GM review of native owner work; never an extra confirmation route."""
        with self.store.engine.connect() as c:
            self.outcomes._scope(c, viewer, scene, gm=True)
            choice = next(
                (x for x in self.reviews._work(c, scene, None)["choices"] if x["id"] == choice_id),
                None,
            )
            if choice is None:
                raise WorkflowError("SOURCE_UNAVAILABLE: reopen the actual pending scene choice.")
            context = self.context._build(c, viewer, scene)
            packet = {
                "scene_id": scene,
                "choice": choice,
                "action": self.game.action(c, choice["action_id"]),
                "context": context.model_dump(mode="json"),
                "canonical_state": load_state(c, self.store.campaign_id).model_dump(mode="json"),
                **self._decision_route(c, choice),
                "application": "blocked",
            }
            return {**packet, "revision": _digest(packet)}

    def _declarations(
        self, c: Connection, viewer: GuildViewer, scene: str, *, gm: bool
    ) -> list[dict[str, Any]]:
        table = t.director_context["shadow"]
        rows = [
            json.loads(raw)
            for raw in c.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    sa.or_(table.c.id.like("play-review:%"), table.c.id.like("action-binding:%")),
                )
            )
        ]
        bindings = {
            r["review_id"]: r for r in rows if r.get("record_type") == "director_action_binding"
        }
        result = []
        for record in rows:
            if record.get("record_type") != "director_play_review" or (
                not gm and record["owner_id"] != str(viewer.user_id)
            ):
                continue
            item = {key: record[key] for key in ("id", "owner_id", "source_id", "candidates")}
            try:
                source = self.reviews._source(
                    c, scene, record["source_id"], record["source_revision"]
                )
                binding = bindings.get(record["id"])
                if binding:
                    action = self.game.action(c, binding["action_id"])
                    item.update(action_id=action["id"], status="native_" + action["state"])
                else:
                    decisions = self.reviews._decisions(c, scene, record["id"])
                    item["status"] = (
                        decisions[-1]["decision"] if decisions else "awaiting_gm_review"
                    )
                    item["decision_current"] = bool(
                        decisions
                        and decisions[-1]["fingerprint"]
                        == self.reviews._fingerprint(c, self.observer._scene(c, scene), record)
                    )
                    if (
                        record["owner_id"] == str(viewer.user_id)
                        and self.reviews.catalog.declared(source.text or "")
                        and {candidate["play_id"] for candidate in record["candidates"]}
                        == {"keep_your_head"}
                        and (not decisions or decisions[-1]["decision"] == "native_workflow")
                    ):
                        sheet = load_state(c, self.store.campaign_id).sheets.get(
                            str(viewer.user_id)
                        )
                        if sheet is not None:
                            item["keep"] = {
                                "intent": source.text,
                                "sheet_revision": sheet.revision,
                                "available_heat": sheet.heat,
                            }
            except WorkflowError:
                item["status"] = "source_stale"
            result.append(item)
        return result

    def _gm_requests(self, c: Connection, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        inputs = self.observer._pending(scene, 0, include_handled=True).subquery()
        sources = (
            Observation.model_validate_json(raw)
            for raw in c.scalars(
                sa.select(inputs.c.body_json)
                .where(inputs.c.owner_id == str(viewer.user_id), inputs.c.kind == "message")
                .order_by(inputs.c.sequence.desc())
                .limit(75)
            )
        )
        table = t.director_context["shadow"]
        replies = {
            (reply["source_id"], reply["source_revision"]): reply["reply"]
            for raw in c.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    sa.func.json_extract(table.c.body_json, "$.route") == "gm",
                    sa.func.json_extract(table.c.body_json, "$.owner_id") == str(viewer.user_id),
                )
            )
            if (reply := json.loads(raw)).get("record_type") == "conversation_exchange"
        }
        requests = []
        for source in sources:
            reply = replies.get((source.source_id, source.source_revision))
            decision = (reply or {}).get("gm_decision") or {}
            if source.gm_addressed or decision.get("action") == "RESPOND":
                requests.append(
                    {
                        "source": source.source_id,
                        "revision": source.source_revision,
                        "text": source.text,
                        "reply": reply["text"] if reply else None,
                    }
                )
            if len(requests) == 15:
                break
        return requests

    def answer_gm(
        self, viewer: GuildViewer, key: str, scene: str, source: str, revision: int
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            actual = self.conversation._authorize_source(c, viewer, scene, source)
            if not actual.gm_addressed:
                raise WorkflowError(
                    "GM_REQUEST: use an explicitly addressed out-of-character request."
                )
        return self.conversation.respond(viewer, key, scene, source, "gm", revision)

    def bind_action(
        self, viewer: GuildViewer, key: str, scene: str, review_id: str, action_id: str
    ) -> dict[str, Any]:
        """Link exact narration to a native Pilot action without applying mechanics."""

        def authorize(c: Connection) -> None:
            self.outcomes._scope(c, viewer, scene, gm=True)

        def operation(c: Connection) -> dict[str, Any]:
            return self._bind_action(c, scene, review_id, action_id)

        return self.store._write(
            viewer,
            key,
            "director.bind_action",
            {"scene": scene, "review": review_id, "action": action_id},
            operation,
            authorize=authorize,
        )

    def _bind_action(
        self, c: Connection, scene: str, review_id: str, action_id: str
    ) -> dict[str, Any]:
        record = self.reviews._record(c, scene, review_id)
        source = self.reviews._source(c, scene, record["source_id"], record["source_revision"])
        action = self.game.action(c, action_id)
        meta = action["data"]
        if (
            source.actor.kind != "pilot"
            or action["scene_id"] != scene
            or action["actor_id"] != source.author_id
            or meta.get("prepared", {}).get("context") != source.text
            or meta.get("play") not in {x["play_id"] for x in record["candidates"]}
            or meta.get("gorgon_play")
            or meta.get("character_ids", {}).get(source.author_id) != source.actor.incarnation
            or meta.get("actor_basic", {}).get("actor", source.actor.model_dump(mode="json"))
            != source.actor.model_dump(mode="json")
        ):
            raise WorkflowError(
                "UNPROVEN_ACTION_BINDING: retain exact declaration, actor and native Play."
            )
        table = t.director_context["shadow"]
        for raw in c.scalars(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id.like("action-binding:%"),
            )
        ):
            old = json.loads(raw)
            if old["review_id"] == review_id or old["action_id"] == action_id:
                if old["review_id"] == review_id and old["action_id"] == action_id:
                    return {"id": old["id"], "mechanics_applied": False}
                raise WorkflowError("ACTION_ALREADY_BOUND: a different source owns that binding.")
        from uuid import uuid4

        value = {
            "id": "action-binding:" + str(uuid4()),
            "record_type": "director_action_binding",
            "scene_id": scene,
            "review_id": review_id,
            "source_id": source.source_id,
            "source_revision": source.source_revision,
            "action_id": action_id,
        }
        self.reviews._save(c, value)
        return {"id": value["id"], "mechanics_applied": False}

    def open_declared_keep(
        self, viewer: GuildViewer, scene: str, review_id: str, sheet_revision: int, heat: int
    ) -> dict[str, Any]:
        """The actual Pilot confirms the prepared declaration and the owned cost."""

        def source_for(c: Connection) -> Observation:
            self.reviews._scope(c, viewer, scene)
            record = self.reviews._record(c, scene, review_id)
            if record["owner_id"] != str(viewer.user_id):
                raise WorkflowError("DECLARATION_OWNER: only the declaring Pilot can open it.")
            source = self.conversation._authorize_source(c, viewer, scene, record["source_id"])
            if (
                source.source_revision != record["source_revision"]
                or source.actor.kind != "pilot"
                or not self.reviews.catalog.declared(source.text or "")
                or {item["play_id"] for item in record["candidates"]} != {"keep_your_head"}
            ):
                raise WorkflowError("STALE_DECLARATION: refresh the exact Keep Your Head call.")
            decisions = self.reviews._decisions(c, scene, review_id)
            if decisions and decisions[-1]["decision"] != "native_workflow":
                raise WorkflowError("DECLARATION_REVIEW: recover the GM's current decision.")
            return source

        with self.store.engine.connect() as c:
            source = source_for(c)
            channel = int(self.observer._scene(c, scene)["channel_id"])
        assert source.text is not None

        def bind(c: Connection, action: str) -> None:
            if source_for(c) != source:
                raise WorkflowError("STALE_DECLARATION: refresh the original message.")
            self._bind_action(c, scene, review_id, action)

        return self.game.begin(
            viewer,
            "declared-keep:" + review_id,
            channel,
            sheet_revision,
            PlayInput(
                play="keep_your_head", context=source.text, trigger_confirmed=True, heat=heat
            ),
            after_begin=bind,
        )

    def contributions(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        """Approved narration plus each caller's native projection; no raw chat/GM log."""
        with self.store.engine.connect() as c:
            self.outcomes._scope(c, viewer, scene)
            table = t.director_context["shadow"]
            ids = list(
                c.scalars(
                    sa.select(table.c.id)
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        table.c.id.like("gm-narration:%"),
                    )
                    .order_by(table.c.id)
                )
            )
        result = []
        for identity in ids:
            try:
                result.append(self.outcomes.contribution(viewer, scene, identity))
            except WorkflowError:
                # Native access loss suppresses optional output, never widens its audience.
                continue
        result.extend(self.conversation.delivery.contributions(viewer, scene))
        return sorted(result, key=lambda x: (x["ordinal"], x["id"]))
