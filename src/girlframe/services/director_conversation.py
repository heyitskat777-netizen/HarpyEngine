"""Discrete GM/Handler direct-request routes; no spending, rolls or automatic effects."""

import json
import re
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.ai.conversation import (
    ConversationReply,
    GMDecision,
    GMProvider,
    GMRequest,
    HandlerDecision,
    HandlerNeedPacket,
    HandlerNeedProposal,
    HandlerNeedProvider,
    HandlerPersona,
    HandlerProvider,
    HandlerRequest,
    HeatAnswer,
    PeerResponse,
    Route,
    SyntheticGM,
    SyntheticHandler,
    SyntheticHandlerPolicy,
    handler_updates,
)
from girlframe.ai.director import DirectorContext
from girlframe.ai.observation import Observation
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_character import PROFILES
from girlframe.engine.m3_handler_play_state import BASIC, Play
from girlframe.services.director_closeout import handler_reports
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import _digest
from girlframe.services.director_play_catalog import PlayCatalog
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorConversationService:
    def __init__(
        self,
        context: DirectorContextService,
        *,
        gm: GMProvider | None = None,
        handler: HandlerProvider | None = None,
        handler_mode: Literal["synthetic", "reviewed"] = "synthetic",
    ):
        self.context = context
        self.observations = context.observations
        self.store = context.store
        self.gm = gm if gm is not None else SyntheticGM()
        self.handler = handler if handler is not None else SyntheticHandler()
        if handler_mode not in ("synthetic", "reviewed"):
            raise ValueError("Choose synthetic or reviewed Handler mode")
        if handler_mode == "reviewed" and handler is None:
            raise ValueError("Reviewed Handler mode requires an injected provider")
        self.handler_mode = handler_mode
        self.play_catalog = PlayCatalog()
        from girlframe.services.director_handler_delivery import HandlerDeliveryService

        self.delivery = HandlerDeliveryService(self)

    def _authorize_source(
        self, c: Connection, viewer: GuildViewer, scene_id: str, source_id: str
    ) -> Observation:
        self.observations._scope()
        self.observations._scene(c, scene_id, viewer)
        source = self.observations._latest_source(c, source_id)
        table = t.director["inputs"]
        if (
            source is None
            or source.kind != "message"
            or source.author_id != str(viewer.user_id)
            or not c.scalar(
                sa.select(table.c.source_id)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene_id,
                    table.c.source_id == source_id,
                )
                .limit(1)
            )
        ):
            raise WorkflowError(
                "SOURCE_UNAVAILABLE: address a route using your own actual scene message."
            )
        _, _, actual = self.observations._authorize_input(c, viewer, scene_id, source.actor.kind)
        if actual != source.actor:
            raise WorkflowError("STALE_ACTOR: use the actual current sender.")
        return source

    def _requests(
        self,
        c: Connection,
        viewer: GuildViewer,
        scene_id: str,
        source_id: str,
        route: Route,
        *,
        review_source: Observation | None = None,
    ) -> tuple[GMRequest | HandlerRequest, str]:
        source = review_source or self._authorize_source(c, viewer, scene_id, source_id)
        if review_source is not None and route != "handler":
            raise ValueError("Review source projection is Handler-only")
        self.observations.game.unpaused(c)
        question = source.text or ""
        if route == "handler":
            role = self.context._handler_for_request(c, viewer, scene_id)
            persona = (
                load_state(c, self.store.campaign_id).handler_persona
                if self.handler_mode == "reviewed"
                else None
            )
            playbook = persona.draft.playbook if persona else None
            if source.fictional_channel == "private":
                # Scene membership is OOC access, not in-fiction hearing. Never
                # expose the private narration as the Handler's current question.
                question = "Scene update."
            elif self.handler_mode == "reviewed":
                from girlframe.services.director_knowledge import DirectorKnowledgeService

                assert role.actor is not None
                spoken = DirectorKnowledgeService(self.context).heard(
                    c, scene_id, source_id, role.actor
                )
                question = "\n".join(spoken) or "Scene update."
            keys = {
                ref.id: self._update_key(c, scene_id, role, ref.id) for ref in handler_updates(role)
            }
            table = t.director_context["shadow"]
            decisions = (
                {
                    row.id: row.need_key
                    for row in c.execute(
                        sa.select(
                            table.c.id,
                            sa.func.json_extract(table.c.body_json, "$.need_key").label("need_key"),
                        ).where(
                            table.c.campaign_id == self.store.campaign_id,
                            sa.func.json_extract(table.c.body_json, "$.record_type")
                            == "handler_response_decision",
                            sa.func.json_extract(table.c.body_json, "$.need_key").in_(
                                keys.values()
                            ),
                        )
                    )
                }
                if keys
                else {}
            )
            successful = (
                set(
                    c.scalars(
                        sa.select(
                            sa.func.json_extract(table.c.body_json, "$.handler_decision_id")
                        ).where(
                            table.c.campaign_id == self.store.campaign_id,
                            sa.func.json_extract(table.c.body_json, "$.record_type")
                            == "conversation_exchange",
                            sa.func.json_extract(table.c.body_json, "$.route") == "handler",
                            sa.func.json_extract(table.c.body_json, "$.handler_decision_id").in_(
                                decisions
                            ),
                        )
                    )
                )
                if decisions
                else set()
            )
            delivered = {decisions[identity] for identity in successful}
            addressed = tuple(
                sorted(identity for identity, key in keys.items() if key in delivered)
            )
            request: GMRequest | HandlerRequest = HandlerRequest(
                question=question,
                context=role,
                addressed_update_refs=addressed,
                persona=self._handler_persona(c, scene_id, role)
                if self.handler_mode == "reviewed"
                else None,
                playbook_profile=PROFILES[playbook] if playbook else None,
                open_concerns=self.delivery.open_concerns(
                    c, scene_id, role.actor, source.actor, {ref.id for ref in role.references}
                )
                if self.handler_mode == "reviewed" and role.actor is not None
                else (),
                closed_scene_reports=handler_reports(self.context, c, role.actor)
                if self.handler_mode == "reviewed" and role.actor is not None
                else (),
            )
        else:
            # Trusted internal campaign projection. This broader context is never
            # returned to the caller or passed to the Handler provider.
            scene = self.observations._scene(c, scene_id, viewer)
            state = self.observations._state(c, scene_id)
            references = self.context._current(c, scene_id)
            canonical = load_state(c, self.store.campaign_id).model_dump(mode="json")
            gm_context = DirectorContext(
                campaign_id=self.store.campaign_id,
                scene_id=scene_id,
                audience="gm",
                references=references,
                revision=_digest(
                    {
                        "guard": self.observations._guard(c, scene, state),
                        "references": [x.model_dump(mode="json") for x in references],
                    }
                ),
            )
            recipient = self.context._build(c, viewer, scene_id, actor=source.actor)
            history_query = self.observations._pending(scene_id, 0, include_handled=True)
            history_count = c.scalar(
                sa.select(sa.func.count()).select_from(history_query.subquery())
            )
            history = tuple(
                reversed(
                    tuple(
                        Observation.model_validate_json(row["body_json"])
                        for row in c.execute(
                            history_query.order_by(t.director["inputs"].c.sequence.desc()).limit(
                                100
                            )
                        ).mappings()
                    )
                )
            )
            engine_records = {}
            for name in ("m3_missions", "m3_off_duty", "m3_required_work"):
                table = t.m3[name]
                engine_records[name] = [
                    dict(row)
                    for row in c.execute(
                        sa.select(table).where(table.c.campaign_id == self.store.campaign_id)
                    ).mappings()
                ]
            actions = t.m2["m2_actions"]
            engine_records["scene_actions"] = [
                dict(row)
                for row in c.execute(
                    sa.select(actions).where(
                        actions.c.campaign_id == self.store.campaign_id,
                        actions.c.scene_id == scene_id,
                    )
                ).mappings()
            ]
            for name in ("m2_receipts", "m2_choices"):
                table = t.m2[name]
                engine_records[name] = [
                    dict(row)
                    for row in c.execute(
                        sa.select(table)
                        .join(
                            actions,
                            sa.and_(
                                table.c.campaign_id == actions.c.campaign_id,
                                table.c.action_id == actions.c.id,
                            ),
                        )
                        .where(
                            actions.c.campaign_id == self.store.campaign_id,
                            actions.c.scene_id == scene_id,
                        )
                    ).mappings()
                ]
            request = GMRequest(
                question=question,
                context=gm_context,
                canonical_state=canonical,
                engine_records=engine_records,
                scene_inputs=history,
                scene_inputs_omitted=max(0, (history_count or 0) - len(history)),
                recipient_references=recipient.references,
                play_candidates=self.play_catalog.recognize(question),
                play_declaration=self.play_catalog.declared(question),
                heat_answer=self._heat_question(c, scene_id, source.actor, question),
            )
        return request, _digest(request.model_dump(mode="json"))

    def _heat_question(
        self, c: Connection, scene: str, actor: ActorRef, question: str
    ) -> HeatAnswer | None:
        addressed = re.match(r"^\s*gm\s*[:,]\s*(.*)", question, re.IGNORECASE)
        if addressed is None or not re.search(r"\bheat\b", addressed[1], re.IGNORECASE):
            return None
        text = addressed[1].strip().casefold()
        action = re.fullmatch(r"heat for (?:action\s+)?([a-f0-9-]{36})[?.]?", text)
        if action:
            return self._action_heat(c, scene, actor, action[1])
        if self.play_catalog.declared(question) or (
            re.search(r"\b(?:resolve|roll|run)\b", text) and self.play_catalog.recognize(question)
        ):
            return None
        if re.search(
            r"\b(?:correction|correcting|correct|asking a question)\b", text
        ) and re.search(r"\b(?:costs?|spend|uses?)\b", text):
            return HeatAnswer(status="no_cost", amount=0)
        if re.search(r"\b(?:this|that|last|previous|did|spent|charged|pay)\b", text):
            return HeatAnswer(status="needs_source")
        return HeatAnswer(status="rule")

    def _action_heat(self, c: Connection, scene: str, actor: ActorRef, identity: str) -> HeatAnswer:
        try:
            action = self.observations.game.action(c, identity)
        except WorkflowError:
            return HeatAnswer(status="needs_source")
        data = action["data"]
        prepared = data.get("prepared", {})
        if (
            actor.kind != "pilot"
            or str(action["actor_id"]) != actor.entity
            or action["scene_id"] != scene
            or data.get("character_ids", {}).get(actor.entity) != actor.incarnation
            or prepared.get("play") not in ("keep_your_head", "check_sensors")
            or any(data.get(x) for x in ("m3", "janus", "kicked_puppy", "nightmare_core"))
        ):
            return HeatAnswer(status="needs_source")
        table = t.m2["m2_receipts"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.action_id == action["id"],
            )
        )
        if raw is not None:
            receipt = json.loads(raw)
            return HeatAnswer(
                status="committed",
                action_id=identity,
                amount=receipt["heat"],
                receipt_id=receipt["id"],
            )
        if action["state"] in ("cancelled", "aborted", "complete"):
            return HeatAnswer(status="cancelled", action_id=identity, amount=0)
        return HeatAnswer(status="pending", action_id=identity, amount=prepared["heat"])

    def action_heat(self, viewer: GuildViewer, scene: str, action_id: str) -> HeatAnswer:
        """Read an original Pilot's supported action cost without unlocking the scene."""
        with self.store.engine.connect() as c:
            _, _, actor = self.observations._authorize_input(c, viewer, scene, "pilot")
            return self._action_heat(c, scene, actor, action_id)

    def _handler_persona(
        self, c: Connection, scene: str, role: DirectorContext
    ) -> HandlerPersona | None:
        from girlframe.services.director_dossiers import DirectorDossierService

        assert role.actor is not None
        try:
            own = DirectorDossierService(self.context)._role_packet(c, scene, role.actor)
        except WorkflowError as error:
            # An outdated self dossier cannot expand knowledge or disable normal comms.
            if str(error).startswith(("DOSSIER_UNKNOWN_", "DOSSIER_GOAL_UNAVAILABLE:")):
                return None
            raise
        if own.profile is None or own.state is None:
            return None
        return HandlerPersona(version=own.dossier_version, profile=own.profile, state=own.state)

    def _update_key(
        self, c: Connection, scene_id: str, context: DirectorContext, reference_id: str
    ) -> str:
        ref = next(x for x in context.references if x.id == reference_id)
        scene = self.observations._scene(c, scene_id)
        return _digest(
            {
                "kind": "known_update",
                "scene": ref.origin_scene or scene_id,
                "reference": ref.origin_reference or ref.id,
                "handler": context.actor.model_dump(mode="json") if context.actor else None,
                "audience": sorted(scene["participants"]),
            }
        )

    def _saved(self, c: Connection, key: str) -> dict[str, Any] | None:
        table = t.director_context["shadow"]
        body = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id, table.c.id == key
            )
        )
        return dict(json.loads(body)) if body else None

    def get(self, viewer: GuildViewer, scene_id: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.observations._scene(c, scene_id, viewer)
            saved = self._saved(c, identity)
            if (
                not saved
                or saved.get("record_type") not in ("conversation_exchange", "handler_reply_draft")
                or saved.get("owner_id") != str(viewer.user_id)
                or saved.get("scene_id") != scene_id
            ):
                raise WorkflowError("EXCHANGE_UNAVAILABLE: no accessible conversation reply.")
            self._authorize_source(c, viewer, scene_id, saved["source_id"])
            if saved["record_type"] == "handler_reply_draft":
                review = self._saved(c, identity + ":review")
                if review and review["decision"] == "approve":
                    exchange = self._saved(c, review["exchange_id"])
                    assert exchange is not None
                    saved = exchange
                else:
                    return {
                        "id": identity,
                        "record_type": "handler_reply_draft",
                        "scene_id": scene_id,
                        "route": "handler",
                        "reply": None,
                        "status": "rejected" if review else "awaiting_gm_review",
                        "application": "blocked",
                        "publication": "private_review_only",
                    }
            if saved["route"] == "handler":
                draft_id = str(saved.get("review_id", "")).removesuffix(":review")
                if saved["publication"] == "awaiting_scoped_delivery":
                    delivered = self._saved(c, "handler-delivery:" + draft_id)
                    if delivered is None:
                        return {**saved, "reply": None, "status": "awaiting_delivery"}
                    # Recipients read the single scoped delivery, including on retry.
                    return {
                        **saved,
                        "reply": None,
                        "status": "delivered",
                        "delivery_id": delivered["id"],
                    }
                saved["reply"] = {
                    k: v
                    for k, v in saved["reply"].items()
                    if k not in ("handler_play_offer", "handler_concern")
                }
            return saved

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        source_id: str,
        route: Route,
        expected_source_revision: int,
        *,
        handler_decision_id: str | None = None,
    ) -> dict[str, Any]:
        if type(expected_source_revision) is not int or expected_source_revision < 1:
            raise WorkflowError("STALE_SOURCE: supply the actual positive source revision.")
        if route not in ("gm", "handler"):
            raise WorkflowError("UNSUPPORTED_ROUTE: address gm or handler.")
        if handler_decision_id is not None and route != "handler":
            raise WorkflowError("UNSUPPORTED_ROUTE: Handler decisions cannot address the GM.")
        # The normal command inbox provides the stable semantic key; read cached
        # metadata before invoking a provider, after current source authorization.
        semantic = {
            "scene_id": scene_id,
            "source_id": source_id,
            "route": route,
            "source_revision": expected_source_revision,
            **({"handler_decision_id": handler_decision_id} if handler_decision_id else {}),
        }
        selected_handler_decision = None
        selected_need_key = None
        with self.store.transaction() as c:
            self._authorize_source(c, viewer, scene_id, source_id)
            row = (
                c.execute(
                    sa.select(t.commands).where(
                        t.commands.c.campaign_id == self.store.campaign_id,
                        t.commands.c.interaction_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if row:
                digest = _digest(
                    {"actor": viewer.user_id, "kind": "director.conversation", "payload": semantic}
                )
                if row["request_hash"] != digest:
                    raise WorkflowError("IDEMPOTENCY_CONFLICT: this direct request changed.")
                return self.get(viewer, scene_id, json.loads(row["outcome_json"])["id"])
            source = self._authorize_source(c, viewer, scene_id, source_id)
            if source.source_revision != expected_source_revision:
                raise WorkflowError("STALE_SOURCE: refresh the actual question before routing.")
            request, fingerprint = self._requests(c, viewer, scene_id, source_id, route)
            if (
                route == "handler"
                and self.handler_mode == "reviewed"
                and handler_decision_id is None
            ):
                raise WorkflowError("HANDLER_GATE_REQUIRED: use the persisted RESPOND decision.")
            if handler_decision_id:
                decision = self._saved(c, handler_decision_id)
                if (
                    not decision
                    or decision.get("record_type") != "handler_response_decision"
                    or decision.get("owner_id") != str(viewer.user_id)
                    or decision.get("scene_id") != scene_id
                    or decision.get("source_id") != source_id
                    or decision.get("source_revision") != expected_source_revision
                    or decision.get("context_revision") != fingerprint
                    or decision["decision"]["action"] != "RESPOND"
                ):
                    raise WorkflowError("STALE_HANDLER_DECISION: reconsider the actual message.")
                if self.handler_mode == "reviewed":
                    assert isinstance(request, HandlerRequest)
                    selected_handler_decision, selected_need_key = self._handler_decision(
                        c, scene_id, source, request
                    )
                    if (
                        selected_handler_decision.action != "RESPOND"
                        or selected_handler_decision.model_dump(mode="json") != decision["decision"]
                        or selected_need_key != decision.get("need_key")
                    ):
                        raise WorkflowError(
                            "STALE_HANDLER_DECISION: the actual response need "
                            "is no longer eligible."
                        )
        # Two distinct transports and schemas; synthetic providers run outside locks.
        try:
            if isinstance(request, HandlerRequest):
                provider_request = request.model_copy(
                    update={"response_need": selected_handler_decision}
                )
                candidate = self.handler.respond(provider_request)
                expected = (
                    SyntheticHandler().respond(request)
                    if self.handler_mode == "synthetic"
                    else None
                )
            else:
                candidate = self.gm.respond(request)
                expected = SyntheticGM().respond(request)
            reply = ConversationReply.model_validate_json(candidate.model_dump_json())
            if (expected is not None and reply != expected) or reply.route != route:
                raise ValueError("Unsupported synthetic response")
        except Exception:
            raise WorkflowError(
                "CONVERSATION_UNAVAILABLE: no valid grounded response; retry the same request."
            ) from None
        if route == "handler" and self.handler_mode == "reviewed":
            assert isinstance(request, HandlerRequest)
            self._validate_handler_draft(request, reply, selected_handler_decision)

        def authorize(c: Connection) -> None:
            self._authorize_source(c, viewer, scene_id, source_id)

        def operation(c: Connection) -> dict[str, Any]:
            current_request, current = self._requests(c, viewer, scene_id, source_id, route)
            if current != fingerprint:
                raise WorkflowError("STALE_CONTEXT: no reply committed; refresh and retry.")
            identity = "exchange:" + str(uuid4())
            if route == "handler" and self.handler_mode == "reviewed":
                assert isinstance(current_request, HandlerRequest)
                current_decision, current_need_key = self._handler_decision(
                    c, scene_id, source, current_request
                )
                if (
                    current_decision != selected_handler_decision
                    or current_need_key != selected_need_key
                ):
                    raise WorkflowError(
                        "STALE_HANDLER_DECISION: reconsider the changed response need."
                    )
                identity = "handler-draft:" + str(uuid4())
                self._save_handler_record(
                    c,
                    scene_id,
                    identity,
                    {
                        "id": identity,
                        "record_type": "handler_reply_draft",
                        "scene_id": scene_id,
                        "owner_id": str(viewer.user_id),
                        "source_id": source_id,
                        "source_revision": expected_source_revision,
                        "actor": source.actor.model_dump(mode="json"),
                        "handler_decision_id": handler_decision_id,
                        "context_revision": fingerprint,
                        "request": current_request.model_copy(
                            update={"response_need": current_decision}
                        ).model_dump(mode="json"),
                        "reply": reply.model_dump(mode="json"),
                    },
                )
                return {"id": identity, "route": route, "application": "blocked"}
            result = {
                "id": identity,
                "record_type": "conversation_exchange",
                "scene_id": scene_id,
                "owner_id": str(viewer.user_id),
                "source_id": source_id,
                "source_revision": expected_source_revision,
                "route": route,
                **({"handler_decision_id": handler_decision_id} if handler_decision_id else {}),
                "context_revision": fingerprint,
                "reply": reply.model_dump(mode="json"),
                "external_tokens": 0,
                "external_cost": 0,
                "publication": "private_reply_only",
            }
            if route == "gm":
                state = self.observations._state(c, scene_id)
                self.observations._save(
                    c, scene_id, state.model_copy(update={"generation": state.generation + 1})
                )
                if reply.gm_decision and reply.gm_decision.reason == "play_request":
                    from girlframe.services.director_play_review import DirectorPlayReviewService

                    review = DirectorPlayReviewService(self.context, self.play_catalog)
                    review_id = review._capture(
                        c, viewer, scene_id, source_id, expected_source_revision
                    )
                    # The exchange returns only a stable review ID, never its private notes.
                    result["play_review_id"] = review_id
            c.execute(
                t.director_context["shadow"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    id=identity,
                    body_json=json.dumps(result, sort_keys=True),
                )
            )
            return {"id": identity, "route": route, "application": "blocked"}

        result = self.store._write(
            viewer, key, "director.conversation", semantic, operation, authorize=authorize
        )
        return self.get(viewer, scene_id, result["id"])

    def _save_handler_record(
        self, c: Connection, scene: str, identity: str, record: dict[str, Any]
    ) -> None:
        c.execute(
            t.director_context["shadow"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                scene_id=scene,
                id=identity,
                body_json=json.dumps(record, sort_keys=True),
            )
        )

    def _validate_handler_draft(
        self,
        request: HandlerRequest,
        reply: ConversationReply,
        decision: HandlerDecision | None = None,
    ) -> None:
        if (
            reply.provider != "reviewed-handler-v1"
            or reply.play_id is not None
            or reply.gm_decision is not None
            or reply.route != "handler"
        ):
            raise WorkflowError(
                "HANDLER_AUTHORITY_INVALID: prose cannot supply GM or Play decisions."
            )
        refs = set(reply.source_refs)
        if len(refs) != len(reply.source_refs) or not refs <= {
            x.id for x in request.context.references
        }:
            raise WorkflowError(
                "HANDLER_CITATION_INVALID: cite only actual Handler-known references."
            )
        if reply.disposition == "answer" and not refs:
            raise WorkflowError(
                "HANDLER_CITATION_REQUIRED: factual answers need scoped references."
            )
        decision = decision or SyntheticHandlerPolicy().decide(request)
        if decision.action != "RESPOND":
            raise WorkflowError("HANDLER_WAIT: this message has no eligible response.")
        if not set(decision.source_refs) <= refs:
            raise WorkflowError("HANDLER_REQUIRED_REFERENCE: retain the actual response need.")
        if reply.handler_play_offer and (
            decision.reason
            not in (
                "known_update",
                "reviewed_urgent_report",
                "scope_boundary",
                "reviewed_follow_up",
            )
            or not decision.source_refs
            or (reply.handler_play_offer == "brief" and len(reply.text) > 1200)
        ):
            raise WorkflowError(
                "HANDLER_PLAY_NEED: use a scoped intervention and bounded briefing text."
            )

    def _handler_review_scope(self, c: Connection, viewer: GuildViewer, scene: str) -> None:
        self.store.administrator(viewer)
        self.observations._scope()
        self.observations.game.unpaused(c)
        self.context._build(c, viewer, scene)

    def feedback_handler(
        self, viewer: GuildViewer, scene: str, source_id: str, raw: dict[str, Any]
    ) -> dict[str, Any]:
        """GM-private dry run; no draft, provider call or disclosure is committed."""
        with self.store.engine.connect() as c:
            self._handler_review_scope(c, viewer, scene)
            from girlframe.services.director_knowledge import DirectorKnowledgeService

            DirectorKnowledgeService(self.context)._source(c, scene, source_id)
            source = self.observations._latest_source(c, source_id)
            if source is None:
                raise WorkflowError("SOURCE_UNAVAILABLE: reopen the current message.")
            request, _ = self._requests(
                c, viewer, scene, source_id, "handler", review_source=source
            )
            assert isinstance(request, HandlerRequest)
            try:
                reply = ConversationReply.model_validate_json(json.dumps(raw))
                decision, _ = self._handler_decision(c, scene, source, request)
                self._validate_handler_draft(request, reply, decision)
            except ValidationError:
                return {
                    "valid": False,
                    "errors": [
                        {
                            "code": "INVALID_CONTRACT",
                            "field": "reply",
                            "message": "Use the reviewed Handler reply schema.",
                        }
                    ],
                }
            except WorkflowError as error:
                code = str(error).partition(":")[0]
                return {
                    "valid": False,
                    "errors": [
                        {
                            "code": code,
                            "field": "reply",
                            "message": "Use clarification for unknown information; factual answers "
                            "require real Handler-known citations and the persisted response need.",
                        }
                    ],
                }
            return {"valid": True, "errors": []}

    def _handler_draft(self, c: Connection, scene: str, identity: str) -> dict[str, Any]:
        saved = self._saved(c, identity)
        if (
            not saved
            or saved.get("record_type") != "handler_reply_draft"
            or saved.get("scene_id") != scene
        ):
            raise WorkflowError("HANDLER_DRAFT_UNAVAILABLE: reopen the actual draft.")
        return saved

    def _current_handler_draft(
        self, c: Connection, viewer: GuildViewer, scene: str, draft: dict[str, Any]
    ) -> HandlerRequest:
        from girlframe.services.director_knowledge import DirectorKnowledgeService

        knowledge = DirectorKnowledgeService(self.context)
        knowledge._source(c, scene, draft["source_id"])
        source = self.observations._latest_source(c, draft["source_id"])
        row = self.observations._scene(c, scene)
        if (
            source is None
            or source.source_revision != draft["source_revision"]
            or source.author_id != draft["owner_id"]
            or source.actor.model_dump(mode="json") != draft["actor"]
            or source.actor not in knowledge._actors(c, row)
        ):
            raise WorkflowError("STALE_HANDLER_DRAFT: recover its original source actor.")
        request, fingerprint = self._requests(
            c, viewer, scene, source.source_id, "handler", review_source=source
        )
        if fingerprint != draft["context_revision"] or request.model_dump(mode="json") != {
            name: value for name, value in draft["request"].items() if name != "response_need"
        }:
            raise WorkflowError(
                "STALE_HANDLER_DRAFT: regenerate from current knowledge and speech."
            )
        assert isinstance(request, HandlerRequest)
        return request

    def pending_handler(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        """GM-only discovery metadata; draft prose remains behind private review."""
        with self.store.engine.connect() as c:
            self._handler_review_scope(c, viewer, scene)
            table = t.director_context["shadow"]
            records = [
                json.loads(raw)
                for raw in c.scalars(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        table.c.id.like("handler-draft:%"),
                    )
                )
            ]
            return [
                {
                    "id": row["id"],
                    "source_id": row["source_id"],
                    "owner_id": row["owner_id"],
                    "status": "awaiting_gm_review",
                }
                for row in records
                if row.get("record_type") == "handler_reply_draft"
                and self._saved(c, row["id"] + ":review") is None
            ]

    def private_handler(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        """Only the actual administrative GM can inspect a natural-language draft."""
        with self.store.engine.connect() as c:
            self._handler_review_scope(c, viewer, scene)
            draft = self._handler_draft(c, scene, identity)
            review = self._saved(c, identity + ":review")
            status = review["decision"] if review else "awaiting_gm_review"
            if review is None:
                try:
                    self._current_handler_draft(c, viewer, scene, draft)
                except WorkflowError:
                    status = "stale_reopen_source"
            return {
                "id": identity,
                "request": draft["request"],
                "reply": draft["reply"],
                "status": status,
                "semantic_grounding": "gm_review_required",
                "effects_applied": False,
            }

    def review_handler(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        identity: str,
        decision: Literal["approve", "reject"],
        reason: str,
        *,
        delivery_recipients: tuple[ActorRef, ...] = (),
    ) -> dict[str, Any]:
        """Approve intended prose only; citation validity is not proof of entailment."""
        if decision not in ("approve", "reject") or not reason.strip() or len(reason) > 1200:
            raise WorkflowError(
                "HANDLER_REVIEW_INVALID: give an explicit decision and short reason."
            )

        def operation(c: Connection) -> dict[str, Any]:
            draft = self._handler_draft(c, scene, identity)
            if self._saved(c, identity + ":review"):
                raise WorkflowError("HANDLER_REVIEW_FINAL: the draft already has a decision.")
            exchange_id = None
            offer: dict[str, Any] | None = None
            delivery: dict[str, Any] | None = None
            if decision == "approve":
                request = self._current_handler_draft(c, viewer, scene, draft)
                reply = ConversationReply.model_validate_json(json.dumps(draft["reply"]))
                source = self._need_source(c, scene, draft["source_id"])
                current_decision, _ = self._handler_decision(c, scene, source, request)
                drafted_need = draft["request"].get("response_need")
                if drafted_need is not None and drafted_need != current_decision.model_dump(
                    mode="json"
                ):
                    raise WorkflowError("STALE_HANDLER_DECISION: review the current response need.")
                self._validate_handler_draft(request, reply, current_decision)
                if delivery_recipients:
                    delivery = self.delivery.plan(
                        c, scene, source, request, reply, current_decision, delivery_recipients
                    )
                elif (
                    reply.handler_concern
                    or current_decision.concern_id
                    or current_decision.reason == "reviewed_character_cue"
                ):
                    raise WorkflowError("HANDLER_CONCERN_DELIVERY: select actual scene recipients.")
                if reply.handler_play_offer is not None:
                    assert request.context.actor is not None
                    recipient_refs = self.context._actor_references(
                        self.context._current(c, scene), source.actor
                    )
                    if source.actor.kind != "pilot" or not set(reply.source_refs) <= {
                        ref.id for ref in recipient_refs
                    }:
                        raise WorkflowError(
                            "HANDLER_PLAY_AUDIENCE: use facts shared with the recipient Pilot."
                        )
                    offer = {
                        "play": reply.handler_play_offer,
                        "handler": request.context.actor.model_dump(mode="json"),
                        "binding": self._need_revision(
                            c, scene, source, request, cited_refs=reply.source_refs
                        ),
                    }
                    if reply.handler_play_offer not in dict(BASIC):
                        offer["native_grants"] = self._specialist_grants(
                            c, scene, request.context.actor, source.actor, reply.handler_play_offer
                        )
                        if not offer["native_grants"]:
                            raise WorkflowError(
                                "HANDLER_PLAY_SOURCE: the specialist Play needs an earned grant."
                            )
                exchange_id = "exchange:" + str(uuid4())
                self._save_handler_record(
                    c,
                    scene,
                    exchange_id,
                    {
                        "id": exchange_id,
                        "record_type": "conversation_exchange",
                        "scene_id": scene,
                        "owner_id": draft["owner_id"],
                        "source_id": draft["source_id"],
                        "source_revision": draft["source_revision"],
                        "route": "handler",
                        "handler_decision_id": draft["handler_decision_id"],
                        "context_revision": draft["context_revision"],
                        "reply": draft["reply"],
                        "review_id": identity + ":review",
                        "external_tokens": 0,
                        "external_cost": 0,
                        "publication": "awaiting_scoped_delivery"
                        if delivery
                        else "private_reply_only",
                    },
                )
            self._save_handler_record(
                c,
                scene,
                identity + ":review",
                {
                    "id": identity + ":review",
                    "record_type": "handler_reply_review",
                    "draft_id": identity,
                    "decision": decision,
                    "reason": reason,
                    "reviewer_id": str(viewer.user_id),
                    "exchange_id": exchange_id,
                    **({"play_offer": offer} if offer else {}),
                    **({"delivery": delivery} if delivery else {}),
                },
            )
            return {
                "id": identity,
                "status": decision,
                "effects_applied": False,
                **({"handler_play_offer": offer["play"]} if offer else {}),
                **({"delivery_pending": True} if delivery else {}),
            }

        return self.store._write(
            viewer,
            key,
            "director.handler_review",
            {
                "scene": scene,
                "draft": identity,
                "decision": decision,
                "reason": reason,
                **(
                    {
                        "delivery_recipients": [
                            x.model_dump(mode="json") for x in delivery_recipients
                        ]
                    }
                    if delivery_recipients
                    else {}
                ),
            },
            operation,
            authorize=lambda c: self._handler_review_scope(c, viewer, scene),
        )

    @staticmethod
    def _handler_offer_key(draft_id: str, play: Play) -> str:
        return (
            "director-handler-brief:" if play == "brief" else "director-handler-play:"
        ) + draft_id

    def _specialist_grants(
        self, c: Connection, scene: str, handler: ActorRef, target: ActorRef, play: Play
    ) -> list[str]:
        from girlframe.engine.m3_handler_plays import available_plays
        from girlframe.services.gm_outcomes import GMOutcomeService

        state = load_state(c, self.store.campaign_id)
        outcomes = GMOutcomeService(self.context)
        result = []
        for grant in state.handler_plays:
            if (
                grant.state != "pending"
                or grant.chooser_actor != handler
                or (play != "contaminant_warp" and target not in grant.targets)
                or play not in available_plays(state, grant)
            ):
                continue
            try:
                outcomes._snapshot(c, scene, "handler_grant", grant.id, None)
            except WorkflowError:
                continue
            result.append(grant.id)
        return result

    def _handler_offer(
        self, c: Connection, controller: GuildViewer, scene: str, draft_id: str
    ) -> tuple[Observation, ConversationReply, bool]:
        role = self.context._handler_for_request(c, controller, scene)
        if role.actor is None or role.actor.entity != str(controller.user_id):
            raise WorkflowError("HANDLER_PLAY_OWNER: the original Handler must confirm.")
        draft = self._handler_draft(c, scene, draft_id)
        review = self._saved(c, draft_id + ":review")
        offer = (review.get("play_offer") or review.get("briefing")) if review else None
        if review is None or review["decision"] != "approve" or not offer:
            raise WorkflowError("HANDLER_PLAY_REVIEW: select an approved Play offer.")
        if role.actor.model_dump(mode="json") != offer["handler"]:
            raise WorkflowError("HANDLER_PLAY_OWNER: the original Handler must confirm.")
        source = self._need_source(c, scene, draft["source_id"])
        if source.actor.kind != "pilot" or source.source_revision != draft["source_revision"]:
            raise WorkflowError("HANDLER_PLAY_SOURCE: recover the original pilot source.")
        reply = ConversationReply.model_validate_json(json.dumps(draft["reply"]))
        play = reply.handler_play_offer
        assert play is not None
        started = (
            c.scalar(
                sa.select(t.commands.c.interaction_key).where(
                    t.commands.c.campaign_id == self.store.campaign_id,
                    t.commands.c.interaction_key == self._handler_offer_key(draft_id, play),
                )
            )
            is not None
        )
        if not started:
            request, _ = self._requests(
                c, controller, scene, source.source_id, "handler", review_source=source
            )
            assert isinstance(request, HandlerRequest)
            cited = reply.source_refs if "play_offer" in review else None
            if self._need_revision(c, scene, source, request, cited_refs=cited) != offer["binding"]:
                raise WorkflowError("STALE_HANDLER_PLAY: review the offer from current context.")
        return source, reply, started

    def start_handler_brief(
        self, controller: GuildViewer, scene: str, draft_id: str, expected_game_revision: int
    ) -> dict[str, Any]:
        return self.start_handler_play(
            controller, scene, draft_id, expected_game_revision, expected_play="brief"
        )

    def start_handler_play(
        self,
        controller: GuildViewer,
        scene: str,
        draft_id: str,
        expected_game_revision: int,
        *,
        native_grant: str | None = None,
        expected_play: Play | None = None,
    ) -> dict[str, Any]:
        """Open one ordinary Play or link the already earned specialist grant."""
        from girlframe.services.gm_outcomes import GMOutcomeService
        from girlframe.services.m3_handler_plays import HandlerPlayService

        with self.store.engine.connect() as c:
            source, reply, _ = self._handler_offer(c, controller, scene, draft_id)
        play = reply.handler_play_offer
        assert play is not None
        if expected_play is not None and expected_play != play:
            raise WorkflowError("HANDLER_PLAY_REVIEW: choose the exact approved Play.")
        key = self._handler_offer_key(draft_id, play)

        def guard(c: Connection) -> None:
            current, current_reply, _ = self._handler_offer(c, controller, scene, draft_id)
            if (current, current_reply) != (source, reply):
                raise WorkflowError("HANDLER_PLAY_SOURCE: the original source changed.")

        if play in dict(BASIC):
            if native_grant is not None:
                raise WorkflowError("HANDLER_PLAY_SOURCE: ordinary offers open their own grant.")
            with self.store.source_guard(guard):
                return HandlerPlayService(self.store).start(
                    controller,
                    key,
                    expected_game_revision,
                    (source.actor,),
                    director_brief=(scene, reply.text) if play == "brief" else None,
                    director_offer=(scene, play) if play != "brief" else None,
                )
        if native_grant is None:
            raise WorkflowError("HANDLER_PLAY_SOURCE: select the actual earned specialist grant.")

        def link(c: Connection) -> dict[str, Any]:
            review = self._saved(c, draft_id + ":review")
            if not review or native_grant not in review["play_offer"]["native_grants"]:
                raise WorkflowError("HANDLER_PLAY_SOURCE: select an approved specialist grant.")
            packet = GMOutcomeService(self.context)._snapshot(
                c, scene, "handler_grant", native_grant, None
            )
            grant: Any = packet.native["grant"]
            target = source.actor.model_dump(mode="json")
            if (
                packet.owner_id != str(controller.user_id)
                or packet.native["state_revision"] != expected_game_revision
                or packet.native["allowed_plays"] != [play]
                or (play != "contaminant_warp" and target not in grant["targets"])
            ):
                raise WorkflowError("HANDLER_PLAY_SOURCE: preserve the actual original specialist.")
            return {"id": native_grant, "game_revision": expected_game_revision}

        return self.store._write(
            controller,
            key,
            "director.handler_link_play",
            {"scene": scene, "grant": native_grant, "game_revision": expected_game_revision},
            link,
            authorize=guard,
        )

    def handler_play_offers(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        """Discover unstarted offers without returning the private draft prose."""
        if self.handler_mode != "reviewed":
            return []
        self.store.guild_member(viewer)
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            if state.handler != viewer.user_id:
                return []
            table = t.director_context["shadow"]
            offers = []
            for raw in c.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    sa.or_(
                        sa.func.json_type(table.c.body_json, "$.briefing") == "object",
                        sa.func.json_type(table.c.body_json, "$.play_offer") == "object",
                    ),
                    sa.func.json_extract(table.c.body_json, "$.record_type")
                    == "handler_reply_review",
                )
            ):
                draft_id = json.loads(raw)["draft_id"]
                try:
                    source, reply, started = self._handler_offer(c, viewer, scene, draft_id)
                except WorkflowError:
                    continue
                if not started:
                    review = self._saved(c, draft_id + ":review")
                    approved_grants = (review or {}).get("play_offer", {}).get("native_grants", [])
                    offers.append(
                        {
                            "id": draft_id,
                            "play": reply.handler_play_offer,
                            "target": source.actor.model_dump(mode="json"),
                            "game_revision": state.revision,
                            "requires_native_grant": reply.handler_play_offer not in dict(BASIC),
                            **({"native_grants": approved_grants} if approved_grants else {}),
                        }
                    )
            return offers

    def dispatch(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        source_id: str,
        expected_source_revision: int,
        *,
        addressed_to: Route = "gm",
    ) -> dict[str, Any]:
        """GM first; optional Handler receives original input, never the GM envelope.

        Each role has its own stable outcome. If the second route fails, retrying
        this key reuses the GM outcome and resumes the Handler request safely.
        """
        if addressed_to not in ("gm", "handler"):
            raise WorkflowError("UNSUPPORTED_ROUTE: address gm or handler.")
        gm = self.respond(viewer, key + ":gm", scene_id, source_id, "gm", expected_source_revision)
        handler = None
        if addressed_to == "handler":
            if self.handler_mode == "reviewed":
                gate = self.decide_handler(
                    viewer, key + ":decision", scene_id, source_id, expected_source_revision
                )
                if gate["decision"]["action"] == "RESPOND":
                    handler = self.respond(
                        viewer,
                        key + ":handler",
                        scene_id,
                        source_id,
                        "handler",
                        expected_source_revision,
                        handler_decision_id=gate["id"],
                    )
            else:
                handler = self.respond(
                    viewer,
                    key + ":handler",
                    scene_id,
                    source_id,
                    "handler",
                    expected_source_revision,
                )
        return {"gm": gm, "handler": handler}

    def _need_source(self, c: Connection, scene: str, source_id: str) -> Observation:
        from girlframe.services.director_knowledge import DirectorKnowledgeService

        knowledge = DirectorKnowledgeService(self.context)
        knowledge._source(c, scene, source_id)
        source = self.observations._latest_source(c, source_id)
        if source is None or source.actor not in knowledge._actors(
            c, self.observations._scene(c, scene)
        ):
            raise WorkflowError("STALE_HANDLER_NEED: recover the actual source actor.")
        return source

    def _need_revision(
        self,
        c: Connection,
        scene: str,
        source: Observation,
        request: HandlerRequest,
        *,
        cited_refs: tuple[str, ...] | None = None,
    ) -> str:
        from girlframe.services.handler_setup import HandlerService

        state = self.observations._state(c, scene)
        stable = state.model_copy(update={"generation": 0})
        return _digest(
            {
                "source": source.source_id,
                "source_revision": source.source_revision,
                "actor": source.actor.model_dump(mode="json"),
                "speech": request.question,
                "handler": request.context.actor.model_dump(mode="json")
                if request.context.actor
                else None,
                "references": [
                    x.model_dump(mode="json")
                    for x in request.context.references
                    if cited_refs is None or x.id in cited_refs
                ],
                "guard": self.observations._guard(c, self.observations._scene(c, scene), stable),
                "policy_revision": state.policy_revision,
                "consent_generation": state.consent_generation,
                "consents": state.consents,
                "appointment": HandlerService(self.store).current(c)[0],
                **(
                    {"handler_playbook": request.playbook_profile.playbook}
                    if request.playbook_profile
                    else {}
                ),
                **(
                    {"open_concerns": [x.model_dump(mode="json") for x in request.open_concerns]}
                    if request.open_concerns and cited_refs is None
                    else {}
                ),
            }
        )

    def _need_packet(
        self, c: Connection, viewer: GuildViewer, scene: str, source_id: str, identity: str
    ) -> HandlerNeedPacket:
        self._handler_review_scope(c, viewer, scene)
        if self.handler_mode != "reviewed":
            raise WorkflowError(
                "HANDLER_NEED_MODE: explicit response-need review requires reviewed mode."
            )
        source = self._need_source(c, scene, source_id)
        request, _ = self._requests(c, viewer, scene, source_id, "handler", review_source=source)
        assert isinstance(request, HandlerRequest)
        return HandlerNeedPacket(
            request_id=identity,
            scene_id=scene,
            source_id=source_id,
            source_revision=source.source_revision,
            request=request,
            revision=self._need_revision(c, scene, source, request),
        )

    def _need_record(self, c: Connection, scene: str, identity: str, kind: str) -> dict[str, Any]:
        saved = self._saved(c, identity)
        if not saved or saved.get("record_type") != kind or saved.get("scene_id") != scene:
            raise WorkflowError("HANDLER_NEED_UNAVAILABLE: reopen actual scene response-need work.")
        return saved

    def open_handler_need(
        self, viewer: GuildViewer, key: str, scene: str, source_id: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            identity = "handler-need-request:" + str(uuid4())
            packet = self._need_packet(c, viewer, scene, source_id, identity)
            self._save_handler_record(
                c,
                scene,
                identity,
                {
                    "id": identity,
                    "scene_id": scene,
                    "record_type": "handler_need_request",
                    "packet": packet.model_dump(mode="json"),
                },
            )
            return {"id": identity}

        return self.store._write(
            viewer,
            key,
            "director.handler_need_open",
            {"scene": scene, "source": source_id},
            operation,
            authorize=lambda c: self._handler_review_scope(c, viewer, scene),
        )

    def handler_need_packet(
        self, viewer: GuildViewer, scene: str, identity: str
    ) -> HandlerNeedPacket:
        with self.store.engine.connect() as c:
            self._handler_review_scope(c, viewer, scene)
            saved = self._need_record(c, scene, identity, "handler_need_request")
            return HandlerNeedPacket.model_validate_json(json.dumps(saved["packet"]))

    def _fresh_need(self, c: Connection, viewer: GuildViewer, packet: HandlerNeedPacket) -> None:
        current = self._need_packet(c, viewer, packet.scene_id, packet.source_id, packet.request_id)
        if current.revision != packet.revision:
            raise WorkflowError(
                "STALE_HANDLER_NEED: re-review current speech, knowledge and authority."
            )

    def _validate_need(
        self, c: Connection, packet: HandlerNeedPacket, proposal: HandlerNeedProposal
    ) -> None:
        if proposal.request_id != packet.request_id:
            raise WorkflowError("HANDLER_NEED_SOURCE: preserve the exact source request.")
        refs = {x.id: x for x in packet.request.context.references}
        if not set(proposal.source_refs) <= refs.keys():
            raise WorkflowError("HANDLER_NEED_CITATION: cite only actual Handler-known references.")
        if proposal.kind in ("indirect_request", "follow_up", "character_cue"):
            quote = proposal.speech_quote or ""
            if packet.request.question == "Scene update." or quote not in packet.request.question:
                raise WorkflowError(
                    "HANDLER_NEED_SPEECH: quote actual heard words, not private narration."
                )
        if proposal.kind == "character_cue":
            cue_source = self._need_source(c, packet.scene_id, packet.source_id)
            if cue_source.actor.kind != "pilot":
                raise WorkflowError("HANDLER_NEED_SPEECH: select a cue from an actual Pilot.")
            profile = packet.request.playbook_profile
            if proposal.action == "RESPOND" and proposal.cue not in (
                profile.cues if profile else ("personal",)
            ):
                raise WorkflowError(
                    "HANDLER_PLAYBOOK_CUE: this cue falls outside the sheet's initiative."
                )
            if proposal.peer_response is not None:
                handler = packet.request.context.actor
                assert handler is not None
                if not self._peer_heard(
                    c, packet.scene_id, cue_source, handler, proposal.peer_response
                ):
                    raise WorkflowError(
                        "HANDLER_PEER_RESPONSE: select a later heard reply from another Pilot."
                    )
        if proposal.kind == "follow_up" and proposal.concern_id not in {
            concern.id for concern in packet.request.open_concerns
        }:
            raise WorkflowError("HANDLER_CONCERN_CLOSED: choose the speaker's actual open concern.")
        if proposal.kind in ("urgent_known_report", "follow_up"):
            if packet.request.question == "Scene update.":
                raise WorkflowError(
                    "HANDLER_NEED_REPORT: require an actually heard report from this source."
                )
            for identity in proposal.source_refs:
                ref = refs[identity]
                source = ref.source_id
                if source.startswith("knowledge-acquired:"):
                    event = self._saved(c, source)
                    if not event or event.get("source", {}).get("id") != packet.source_id:
                        raise WorkflowError(
                            "HANDLER_NEED_REPORT: cite a known report from this source."
                        )
                elif source != packet.source_id:
                    raise WorkflowError(
                        "HANDLER_NEED_REPORT: cite a known report from this source."
                    )

    def _peer_heard(
        self, c: Connection, scene: str, source: Observation, handler: ActorRef, proof: PeerResponse
    ) -> bool:
        from girlframe.services.director_knowledge import DirectorKnowledgeService

        try:
            peer = self._need_source(c, scene, proof.source_id)
        except WorkflowError:
            return False
        if (
            peer.kind != "message"
            or peer.actor.kind != "pilot"
            or peer.actor == source.actor
            or peer.author_id == source.author_id
            or peer.source_revision != proof.source_revision
            or not proof.quote.strip()
        ):
            return False
        inputs = t.director["inputs"]
        first = {
            row.source_id: row.first
            for row in c.execute(
                sa.select(inputs.c.source_id, sa.func.min(inputs.c.sequence).label("first"))
                .where(
                    inputs.c.campaign_id == self.store.campaign_id,
                    inputs.c.scene_id == scene,
                    inputs.c.source_id.in_((source.source_id, peer.source_id)),
                )
                .group_by(inputs.c.source_id)
            )
        }
        if first[peer.source_id] <= first[source.source_id]:
            return False
        knowledge = DirectorKnowledgeService(self.context)
        return all(
            any(proof.quote in text for text in knowledge.heard(c, scene, peer.source_id, actor))
            for actor in (source.actor, handler)
        )

    def peer_covered(
        self, c: Connection, scene: str, source: Observation, handler: ActorRef
    ) -> bool:
        """Use a reviewed reply with current listener, order and source proof."""
        table = t.director_context["shadow"]
        for raw in c.scalars(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                sa.func.json_extract(table.c.body_json, "$.record_type") == "handler_need_proposal",
                sa.func.json_extract(table.c.body_json, "$.packet.source_id") == source.source_id,
                sa.func.json_extract(table.c.body_json, "$.packet.source_revision")
                == source.source_revision,
                sa.func.json_type(table.c.body_json, "$.proposal.peer_response") == "object",
            )
        ):
            row = json.loads(raw)
            review = self._saved(c, row["id"] + ":review")
            if (
                review
                and review["decision"] == "approve"
                and row["packet"]["request"]["context"]["actor"] == handler.model_dump(mode="json")
                and self._peer_heard(
                    c,
                    scene,
                    source,
                    handler,
                    PeerResponse.model_validate(row["proposal"]["peer_response"]),
                )
            ):
                return True
        return False

    def _save_need_proposal(
        self,
        c: Connection,
        viewer: GuildViewer,
        scene: str,
        request_id: str,
        proposal: HandlerNeedProposal,
    ) -> dict[str, Any]:
        record = self._need_record(c, scene, request_id, "handler_need_request")
        packet = HandlerNeedPacket.model_validate_json(json.dumps(record["packet"]))
        self._fresh_need(c, viewer, packet)
        self._validate_need(c, packet, proposal)
        table = t.director_context["shadow"]
        count = (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    sa.func.json_extract(table.c.body_json, "$.record_type")
                    == "handler_need_proposal",
                )
            )
            or 0
        )
        identity = "handler-need-proposal:" + str(uuid4())
        self._save_handler_record(
            c,
            scene,
            identity,
            {
                "id": identity,
                "scene_id": scene,
                "record_type": "handler_need_proposal",
                "order": count + 1,
                "packet": packet.model_dump(mode="json"),
                "proposal": proposal.model_dump(mode="json"),
            },
        )
        return {"id": identity, "effects_applied": False}

    def propose_handler_need(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        request_id: str,
        proposal: HandlerNeedProposal,
    ) -> dict[str, Any]:
        proposal = HandlerNeedProposal.model_validate_json(proposal.model_dump_json())
        return self.store._write(
            viewer,
            key,
            "director.handler_need_propose",
            {"scene": scene, "request": request_id, "proposal": proposal.model_dump(mode="json")},
            lambda c: self._save_need_proposal(c, viewer, scene, request_id, proposal),
            authorize=lambda c: self._handler_review_scope(c, viewer, scene),
        )

    def generate_handler_need(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        request_id: str,
        provider: HandlerNeedProvider,
    ) -> dict[str, Any]:
        payload = {"scene": scene, "request": request_id}
        with self.store.engine.connect() as c:
            self._handler_review_scope(c, viewer, scene)
            old = (
                c.execute(
                    sa.select(t.commands).where(
                        t.commands.c.campaign_id == self.store.campaign_id,
                        t.commands.c.interaction_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if old:
                if old["request_hash"] != _digest(
                    {
                        "actor": viewer.user_id,
                        "kind": "director.handler_need_generate",
                        "payload": payload,
                    }
                ):
                    raise WorkflowError("IDEMPOTENCY_CONFLICT: response-need generation changed.")
                return dict(json.loads(old["outcome_json"]))
            saved = self._need_record(c, scene, request_id, "handler_need_request")
            packet = HandlerNeedPacket.model_validate_json(json.dumps(saved["packet"]))
            self._fresh_need(c, viewer, packet)
        try:
            proposal = HandlerNeedProposal.model_validate_json(
                provider.propose(packet).model_dump_json()
            )
        except Exception:
            raise WorkflowError(
                "HANDLER_NEED_PROVIDER_UNAVAILABLE: retry without committing a need."
            ) from None
        return self.store._write(
            viewer,
            key,
            "director.handler_need_generate",
            payload,
            lambda c: self._save_need_proposal(c, viewer, scene, request_id, proposal),
            authorize=lambda c: self._handler_review_scope(c, viewer, scene),
        )

    def private_handler_need(
        self, viewer: GuildViewer, scene: str, identity: str
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._handler_review_scope(c, viewer, scene)
            saved = self._need_record(c, scene, identity, "handler_need_proposal")
            packet = HandlerNeedPacket.model_validate_json(json.dumps(saved["packet"]))
            review = self._saved(c, identity + ":review")
            status = review["decision"] if review else "awaiting_gm_review"
            try:
                self._fresh_need(c, viewer, packet)
            except WorkflowError:
                status = "stale_reopen_source"
            return {
                "id": identity,
                "packet": saved["packet"],
                "proposal": saved["proposal"],
                "status": status,
                "effects_applied": False,
            }

    def pending_handler_needs(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self._handler_review_scope(c, viewer, scene)
            table = t.director_context["shadow"]
            rows = [
                json.loads(raw)
                for raw in c.scalars(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        sa.func.json_extract(table.c.body_json, "$.record_type")
                        == "handler_need_proposal",
                    )
                )
            ]
            return [
                {
                    "id": row["id"],
                    "source_id": row["packet"]["source_id"],
                    "status": "awaiting_gm_review",
                }
                for row in rows
                if self._saved(c, row["id"] + ":review") is None
            ]

    def review_handler_need(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        identity: str,
        decision: Literal["approve", "reject"],
        reason: str,
    ) -> dict[str, Any]:
        if decision not in ("approve", "reject") or not reason.strip() or len(reason) > 1200:
            raise WorkflowError("HANDLER_NEED_REVIEW: give an explicit review and short reason.")

        def operation(c: Connection) -> dict[str, Any]:
            saved = self._need_record(c, scene, identity, "handler_need_proposal")
            if self._saved(c, identity + ":review"):
                raise WorkflowError("HANDLER_NEED_FINAL: this proposal already has a review.")
            if decision == "approve":
                packet = HandlerNeedPacket.model_validate_json(json.dumps(saved["packet"]))
                self._fresh_need(c, viewer, packet)
                self._validate_need(
                    c,
                    packet,
                    HandlerNeedProposal.model_validate_json(json.dumps(saved["proposal"])),
                )
            self._save_handler_record(
                c,
                scene,
                identity + ":review",
                {
                    "id": identity + ":review",
                    "scene_id": scene,
                    "record_type": "handler_need_review",
                    "decision": decision,
                    "reason": reason,
                    "reviewer_id": str(viewer.user_id),
                },
            )
            return {"id": identity, "status": decision, "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.handler_need_review",
            {"scene": scene, "proposal": identity, "decision": decision, "reason": reason},
            operation,
            authorize=lambda c: self._handler_review_scope(c, viewer, scene),
        )

    def acquire_handler_need(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        source_id: str,
        provider: HandlerNeedProvider,
    ) -> dict[str, Any]:
        """Explicitly configured trusted GM worker; no default provider or public approval."""
        request = self.open_handler_need(viewer, key + ":source", scene, source_id)
        proposal = self.generate_handler_need(
            viewer, key + ":proposal", scene, request["id"], provider
        )
        return self.review_handler_need(
            viewer,
            key + ":review",
            scene,
            proposal["id"],
            "approve",
            "Trusted GM provider reviewed this source-bound response need.",
        )

    def _approved_handler_need(
        self, c: Connection, scene: str, source: Observation, request: HandlerRequest
    ) -> tuple[HandlerDecision, str] | None:
        if self.handler_mode != "reviewed":
            return None
        table = t.director_context["shadow"]
        records = [
            json.loads(raw)
            for raw in c.scalars(
                sa.select(table.c.body_json).where(table.c.campaign_id == self.store.campaign_id)
            )
        ]
        candidates = [
            r
            for r in records
            if r.get("record_type") == "handler_need_proposal"
            and r["packet"]["scene_id"] == scene
            and r["packet"]["source_id"] == source.source_id
            and r["packet"]["revision"] == self._need_revision(c, scene, source, request)
        ]
        for row in sorted(candidates, key=lambda r: r["order"], reverse=True):
            review = self._saved(c, row["id"] + ":review")
            if not review or review["decision"] != "approve":
                continue
            proposal = HandlerNeedProposal.model_validate_json(json.dumps(row["proposal"]))
            if proposal.kind == "character_cue":
                handler = request.context.actor
                assert handler is not None
                if self.peer_covered(c, scene, source, handler):
                    return HandlerDecision(action="WAIT", reason="peer_response"), ""
                if proposal.peer_response:
                    continue
            if proposal.action == "WAIT":
                return HandlerDecision(action="WAIT", reason="no_handler_need"), ""
            refs = {x.id: x for x in request.context.references}
            need_key = _digest(
                {
                    "kind": proposal.kind,
                    "handler": request.context.actor.model_dump(mode="json")
                    if request.context.actor
                    else None,
                    "audience": sorted(self.observations._scene(c, scene)["participants"]),
                    "source": (source.source_id, source.source_revision, proposal.speech_quote)
                    if proposal.kind in ("indirect_request", "follow_up")
                    else None,
                    **({"concern": proposal.concern_id} if proposal.concern_id else {}),
                    **(
                        {
                            "cue": proposal.cue,
                            "scene": scene,
                            "speaker": source.actor.token,
                            "words": re.sub(
                                r"[^\w]+", " ", (proposal.speech_quote or "").casefold()
                            ).strip(),
                        }
                        if proposal.kind == "character_cue"
                        else {}
                    ),
                    "refs": [
                        (refs[x].origin_scene or scene, refs[x].origin_reference or x)
                        for x in proposal.source_refs
                        if proposal.kind != "character_cue"
                    ],
                }
            )
            if proposal.kind == "follow_up":
                update = next(
                    (
                        x.id
                        for x in handler_updates(request.context)
                        if x.id in proposal.source_refs
                    ),
                    None,
                )
                if update is not None:
                    need_key = self._update_key(c, scene, request.context, update)
            prior = {
                r["id"]
                for r in records
                if r.get("record_type") == "handler_response_decision"
                and r.get("need_key") == need_key
                and (
                    not proposal.concern_id
                    or r["decision"].get("concern_id") == proposal.concern_id
                )
            }
            delivered = any(
                r.get("record_type") == "conversation_exchange"
                and r.get("route") == "handler"
                and r.get("handler_decision_id") in prior
                for r in records
            )
            if delivered or (
                proposal.kind == "urgent_known_report"
                and set(proposal.source_refs) <= set(request.addressed_update_refs)
            ):
                return HandlerDecision(action="WAIT", reason="need_already_addressed"), need_key
            return HandlerDecision(
                action="RESPOND",
                reason=(
                    "reviewed_follow_up"
                    if proposal.kind == "follow_up"
                    else "reviewed_indirect_request"
                    if proposal.kind == "indirect_request"
                    else "reviewed_character_cue"
                    if proposal.kind == "character_cue"
                    else "reviewed_urgent_report"
                ),
                source_refs=proposal.source_refs,
                concern_id=proposal.concern_id,
                cue=proposal.cue,
            ), need_key
        return None

    def _handler_decision(
        self, c: Connection, scene_id: str, source: Observation, request: HandlerRequest
    ) -> tuple[HandlerDecision, str | None]:
        if self.handler_mode == "reviewed" and source.actor == request.context.actor:
            return HandlerDecision(action="WAIT", reason="no_handler_need"), None
        decision = SyntheticHandlerPolicy().decide(request)
        need_key = None
        if decision.action == "WAIT" and decision.reason != "gm_request":
            proposed = self._approved_handler_need(c, scene_id, source, request)
            if proposed is not None:
                decision, need_key = proposed
        if decision.reason == "known_update":
            need_key = self._update_key(c, scene_id, request.context, decision.source_refs[0])
            if request.open_concerns:
                proposed = self._approved_handler_need(c, scene_id, source, request)
                if (
                    proposed
                    and proposed[1] == need_key
                    and proposed[0].reason == "reviewed_follow_up"
                ):
                    decision = proposed[0]
        if decision.reason == "scope_boundary":
            # Repeat warnings only after a changed scope/role, not every restatement.
            # A saved decision without a successful reply has addressed nothing.
            need_key = _digest(
                {
                    "sender": source.actor.model_dump(mode="json"),
                    "handler": request.context.actor.model_dump(mode="json")
                    if request.context.actor
                    else None,
                    "references": decision.source_refs,
                }
            )
            records = [
                json.loads(raw)
                for raw in c.scalars(
                    sa.select(t.director_context["shadow"].c.body_json).where(
                        t.director_context["shadow"].c.campaign_id == self.store.campaign_id,
                        t.director_context["shadow"].c.scene_id == scene_id,
                    )
                )
            ]
            prior = {
                r["id"]
                for r in records
                if r.get("record_type") == "handler_response_decision"
                and r.get("need_key") == need_key
            }
            if any(
                r.get("record_type") == "conversation_exchange"
                and r.get("route") == "handler"
                and r.get("handler_decision_id") in prior
                for r in records
            ):
                decision = HandlerDecision(
                    action="WAIT",
                    reason="scope_already_addressed",
                    source_refs=decision.source_refs,
                )
        return decision, need_key

    def decide_handler(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        source_id: str,
        expected_source_revision: int,
    ) -> dict[str, Any]:
        """Persist the engine's scoped respond/wait decision, including silent turns."""
        if type(expected_source_revision) is not int or expected_source_revision < 1:
            raise WorkflowError("STALE_SOURCE: supply the actual positive source revision.")

        def authorize(c: Connection) -> None:
            self._authorize_source(c, viewer, scene_id, source_id)

        def operation(c: Connection) -> dict[str, str]:
            source = self._authorize_source(c, viewer, scene_id, source_id)
            if source.source_revision != expected_source_revision:
                raise WorkflowError("STALE_SOURCE: refresh the actual question before routing.")
            try:
                request, revision = self._requests(c, viewer, scene_id, source_id, "handler")
            except WorkflowError as error:
                if not str(error).startswith("HANDLER_UNAVAILABLE:"):
                    raise
                actor, revision, need_key = None, None, None
                decision = HandlerDecision(action="WAIT", reason="handler_absent")
            else:
                assert isinstance(request, HandlerRequest)
                decision, need_key = self._handler_decision(c, scene_id, source, request)
                actor = (
                    request.context.actor.model_dump(mode="json") if request.context.actor else None
                )
            identity = "handler-decision:" + str(uuid4())
            record = {
                "id": identity,
                "record_type": "handler_response_decision",
                "owner_id": str(viewer.user_id),
                "scene_id": scene_id,
                "source_id": source_id,
                "source_revision": expected_source_revision,
                "context_revision": revision,
                "decision": decision.model_dump(mode="json"),
                "need_key": need_key,
                "handler_actor": actor,
            }
            c.execute(
                t.director_context["shadow"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    id=identity,
                    body_json=json.dumps(record, sort_keys=True),
                )
            )
            return {"id": identity}

        result = self.store._write(
            viewer,
            key,
            "director.handler_decision",
            {
                "scene_id": scene_id,
                "source_id": source_id,
                "source_revision": expected_source_revision,
            },
            operation,
            authorize=authorize,
        )
        with self.store.engine.connect() as c:
            self._authorize_source(c, viewer, scene_id, source_id)
            saved = self._saved(c, result["id"])
            if not saved or saved.get("owner_id") != str(viewer.user_id):
                raise WorkflowError("DECISION_UNAVAILABLE: no accessible Handler decision.")
            return saved

    def process_message(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        source_id: str,
        expected_source_revision: int,
    ) -> dict[str, Any]:
        """GM processes input; the engine independently decides whether Handler speaks."""
        gm = self.respond(viewer, key + ":gm", scene_id, source_id, "gm", expected_source_revision)
        decision = self.decide_handler(
            viewer, key + ":decision", scene_id, source_id, expected_source_revision
        )
        handler = None
        if decision["decision"]["action"] == "RESPOND":
            handler = self.respond(
                viewer,
                key + ":handler",
                scene_id,
                source_id,
                "handler",
                expected_source_revision,
                handler_decision_id=decision["id"],
            )
        return {"gm": gm, "handler_decision": decision, "handler": handler}

    def review_play(
        self, viewer: GuildViewer, key: str, scene_id: str, action_id: str
    ) -> dict[str, Any]:
        """GM readback after proved native Keep completion; never resolves a Play."""

        def authorize(c: Connection) -> None:
            _, _, action, _, _, actor = self.observations._prove_committed_play(
                c, scene_id, action_id
            )
            _, _, sender = self.observations._authorize_input(c, viewer, scene_id, "pilot")
            if str(action["actor_id"]) != str(viewer.user_id) or sender != actor:
                raise WorkflowError("PLAY_REVIEW_UNAVAILABLE: use your own actual completed Play.")

        with self.store.engine.connect() as c:
            authorize(c)
        source = self.observations.observe_committed_play(scene_id, action_id)
        source_id = source.source_id
        if source_id is None:
            raise WorkflowError("UNPROVEN_PLAY: completion has no actual source reference.")

        def operation(c: Connection) -> dict[str, str]:
            _, state, action, receipt, event, _ = self.observations._prove_committed_play(
                c, scene_id, action_id
            )
            result = action["data"]["result"]
            # Total/tier/receipt are the ordinary participant-safe projection.
            # Private Handler outcome text, PC choices and raw state stay out.
            public = {
                "action_id": action_id,
                "receipt_id": receipt["id"],
                "event_id": event["id"],
                "faces": json.loads(receipt["body_json"])["faces"],
                "total": result["total"],
                "tier": result["tier"],
            }
            accepted = None
            outcomes = t.director_context["shadow"]
            for body in c.scalars(
                sa.select(outcomes.c.body_json).where(
                    outcomes.c.campaign_id == self.store.campaign_id,
                    outcomes.c.scene_id == scene_id,
                    sa.func.json_extract(outcomes.c.body_json, "$.record_type")
                    == "gm_adjudication",
                    sa.func.json_extract(outcomes.c.body_json, "$.action_id") == action_id,
                    sa.func.json_extract(outcomes.c.body_json, "$.owner_id") == str(viewer.user_id),
                )
            ):
                candidate = json.loads(body)
                proposal = candidate["proposal"]
                response = c.scalar(
                    sa.select(t.m2["m2_responses"].c.answer_json).where(
                        t.m2["m2_responses"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_responses"].c.choice_id == candidate["pending_choice_id"],
                    )
                )
                original = self.observations._latest_source(c, candidate["source_id"])
                if (
                    response
                    and original
                    and original.source_revision == candidate["source_revision"]
                    and proposal["enough"] is not None
                    and result.get("enough") == proposal["enough"]
                    and json.loads(response).get("text")
                    == proposal["reasoning"] + "\n" + proposal["narration"]
                    and action["data"]["prepared"]["context"] == original.text
                ):
                    accepted = candidate
                    break
            confirmed_text = (
                (
                    " Confirmed GM ruling: "
                    + accepted["proposal"]["reasoning"]
                    + " "
                    + accepted["proposal"]["narration"]
                )
                if accepted
                else ""
            )
            reply = ConversationReply(
                route="gm",
                disposition="answer",
                play_id="keep_your_head",
                gm_decision=GMDecision(action="RESPOND", reason="completed_play"),
                source_refs=(source_id,),
                text=f"The engine completed Keep Your Head: total {public['total']}, "
                f"{public['tier']} tier, receipt {public['receipt_id']}. "
                "The original Pilot's printed choices and original Handler's required ruling "
                "are committed. A tier alone does not establish mission success, access, "
                "or cancellation of another Play; no further outcome is invented here."
                + confirmed_text,
            )
            identity = "play-review:" + str(uuid4())
            record = {
                "id": identity,
                "record_type": "gm_play_review",
                "route": "gm",
                "scene_id": scene_id,
                "owner_id": str(viewer.user_id),
                "source_id": source.source_id,
                "source_revision": source.source_revision,
                "proof": public,
                **(
                    {"adjudication_id": accepted["id"], "verdict": accepted["proposal"]["verdict"]}
                    if accepted
                    else {}
                ),
                "reply": reply.model_dump(mode="json"),
                "publication": "private_reply_only",
                "external_tokens": 0,
                "external_cost": 0,
            }
            c.execute(
                t.director_context["shadow"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    id=identity,
                    body_json=json.dumps(record, sort_keys=True),
                )
            )
            self.observations._save(
                c, scene_id, state.model_copy(update={"generation": state.generation + 1})
            )
            return {"id": identity}

        result = self.store._write(
            viewer,
            key,
            "director.play_review",
            {"scene_id": scene_id, "action_id": action_id},
            operation,
            authorize=authorize,
        )
        return self.get_play_review(viewer, scene_id, result["id"])

    def get_play_review(self, viewer: GuildViewer, scene_id: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.observations._scope()
            self.observations._scene(c, scene_id, viewer)
            _, _, actor = self.observations._authorize_input(c, viewer, scene_id, "pilot")
            saved = self._saved(c, identity)
            if (
                not saved
                or saved.get("record_type") != "gm_play_review"
                or saved.get("owner_id") != str(viewer.user_id)
                or saved.get("scene_id") != scene_id
            ):
                raise WorkflowError("PLAY_REVIEW_UNAVAILABLE: no accessible GM Play review.")
            source = self.observations._latest_source(c, saved["source_id"])
            if source is None or source.kind != "completed_play" or source.actor != actor:
                raise WorkflowError("PLAY_REVIEW_UNAVAILABLE: retain the actual original actor.")
            return saved
