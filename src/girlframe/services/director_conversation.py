"""Discrete GM/Handler direct-request routes; no spending, rolls or automatic effects."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.conversation import (
    ConversationReply,
    GMProvider,
    GMRequest,
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
    ):
        self.context = context
        self.observations = context.observations
        self.store = context.store
        self.gm = gm if gm is not None else SyntheticGM()
        self.handler = handler if handler is not None else SyntheticHandler()

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
        self, c: Connection, viewer: GuildViewer, scene_id: str, source_id: str, route: Route
    ) -> tuple[GMRequest | HandlerRequest, str]:
        source = self._authorize_source(c, viewer, scene_id, source_id)
        self.observations.game.unpaused(c)
        question = source.text or ""
        if route == "handler":
            role = self.context._handler_for_request(c, viewer, scene_id)
            request: GMRequest | HandlerRequest = HandlerRequest(question=question, context=role)
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
            )
        return request, _digest(request.model_dump(mode="json"))

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
                or saved.get("record_type") != "conversation_exchange"
                or saved.get("owner_id") != str(viewer.user_id)
                or saved.get("scene_id") != scene_id
            ):
                raise WorkflowError("EXCHANGE_UNAVAILABLE: no accessible conversation reply.")
            self._authorize_source(c, viewer, scene_id, saved["source_id"])
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
                expected = SyntheticHandler().respond(request)
            else:
                candidate = self.gm.respond(request)
                expected = SyntheticGM().respond(request)
            reply = ConversationReply.model_validate_json(candidate.model_dump_json())
            if reply != expected or reply.route != route:
                raise ValueError("Unsupported synthetic response")
        except Exception:
            raise WorkflowError(
                "CONVERSATION_UNAVAILABLE: no valid grounded response; retry the same request."
            ) from None

        def authorize(c: Connection) -> None:
            self._authorize_source(c, viewer, scene_id, source_id)

        def operation(c: Connection) -> dict[str, Any]:
            _, current = self._requests(c, viewer, scene_id, source_id, route)
            if current != fingerprint:
                raise WorkflowError("STALE_CONTEXT: no reply committed; refresh and retry.")
            identity = "exchange:" + str(uuid4())
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
            if route == "gm":
                state = self.observations._state(c, scene_id)
                self.observations._save(
                    c, scene_id, state.model_copy(update={"generation": state.generation + 1})
                )
            return {"id": identity, "route": route, "application": "blocked"}

        result = self.store._write(
            viewer, key, "director.conversation", semantic, operation, authorize=authorize
        )
        return self.get(viewer, scene_id, result["id"])

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
        handler = (
            self.respond(
                viewer, key + ":handler", scene_id, source_id, "handler", expected_source_revision
            )
            if addressed_to == "handler"
            else None
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
