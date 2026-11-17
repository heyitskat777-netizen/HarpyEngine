"""Discrete GM/Handler direct-request routes; no spending, rolls or automatic effects."""

import json
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
    HandlerProvider,
    HandlerRequest,
    Route,
    SyntheticGM,
    SyntheticHandler,
    SyntheticHandlerPolicy,
)
from girlframe.ai.director import DirectorContext
from girlframe.ai.observation import Observation
from girlframe.database import tables as t
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
                ref.id: self._update_key(c, scene_id, role, ref.id)
                for ref in role.references
                if ref.topic in ("briefing", "tactical", "debrief")
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
                question=question, context=role, addressed_update_refs=addressed
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
            )
        return request, _digest(request.model_dump(mode="json"))

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
                    return exchange
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
        # Two distinct transports and schemas; synthetic providers run outside locks.
        try:
            if isinstance(request, HandlerRequest):
                candidate = self.handler.respond(request)
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
            self._validate_handler_draft(request, reply)

        def authorize(c: Connection) -> None:
            self._authorize_source(c, viewer, scene_id, source_id)

        def operation(c: Connection) -> dict[str, Any]:
            _, current = self._requests(c, viewer, scene_id, source_id, route)
            if current != fingerprint:
                raise WorkflowError("STALE_CONTEXT: no reply committed; refresh and retry.")
            identity = "exchange:" + str(uuid4())
            if route == "handler" and self.handler_mode == "reviewed":
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
                        "request": request.model_dump(mode="json"),
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

    def _validate_handler_draft(self, request: HandlerRequest, reply: ConversationReply) -> None:
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
        decision = SyntheticHandlerPolicy().decide(request)
        if decision.action != "RESPOND":
            raise WorkflowError("HANDLER_WAIT: this message has no eligible response.")
        if not set(decision.source_refs) <= refs:
            raise WorkflowError("HANDLER_REQUIRED_REFERENCE: retain the actual response need.")

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
                self._validate_handler_draft(request, reply)
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
        if (
            fingerprint != draft["context_revision"]
            or request.model_dump(mode="json") != draft["request"]
        ):
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
            if decision == "approve":
                request = self._current_handler_draft(c, viewer, scene, draft)
                reply = ConversationReply.model_validate_json(json.dumps(draft["reply"]))
                self._validate_handler_draft(request, reply)
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
                        "publication": "private_reply_only",
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
                },
            )
            return {"id": identity, "status": decision, "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.handler_review",
            {"scene": scene, "draft": identity, "decision": decision, "reason": reason},
            operation,
            authorize=lambda c: self._handler_review_scope(c, viewer, scene),
        )

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
            request, revision = self._requests(c, viewer, scene_id, source_id, "handler")
            assert isinstance(request, HandlerRequest)
            decision = SyntheticHandlerPolicy().decide(request)
            need_key = None
            if decision.reason == "known_update":
                need_key = self._update_key(c, scene_id, request.context, decision.source_refs[0])
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
                "handler_actor": request.context.actor.model_dump(mode="json")
                if request.context.actor
                else None,
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
