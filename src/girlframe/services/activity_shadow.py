"""Private Activity intake review using the existing observation leases and Handler policy."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.conversation import HandlerDecision, HandlerRequest
from girlframe.ai.observation import Observation, ReviewBatch
from girlframe.database import tables as t
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class ActivityShadowReview:
    def __init__(self, conversation: DirectorConversationService):
        self.conversation = conversation
        self.observer, self.store = conversation.observations, conversation.store
        self.knowledge = DirectorKnowledgeService(conversation.context)

    def _scope(self, c: Connection, gm: GuildViewer, scene: str) -> None:
        if not self.observer.activity_shadow or self.conversation.handler_mode != "reviewed":
            raise WorkflowError(
                "ACTIVITY_SHADOW_UNAVAILABLE: use reviewed synthetic Activity mode."
            )
        self.conversation._handler_review_scope(c, gm, scene)

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

    def process(self, gm: GuildViewer, scene: str) -> dict[str, Any] | None:
        with self.store.engine.connect() as c:
            self._scope(c, gm, scene)
        batch = self.observer.claim_review(scene)
        if batch is None:
            return None
        with self.store.transaction() as c:
            self._scope(c, gm, scene)
            # Verifies the frozen claim and current role/consent in the same transaction
            # that saves the review. Failure rolls back the cursor along with the review.
            receipt = self.observer.complete_in_transaction(
                c, batch.run_id, batch.lease_token, success=True
            )
            record = {
                "run": batch.run_id,
                "reason": batch.reason,
                "frontier": receipt.frontier,
                "consent": batch.consent_generation,
                "items": [self._readiness(c, gm, scene, item) for item in batch.inputs],
            }
            self.conversation._save_handler_record(
                c,
                scene,
                "activity-readiness:" + batch.run_id,
                record | {"record_type": "activity_readiness"},
            )
        return {"run": batch.run_id, "frontier": batch.frontier, "reason": batch.reason}

    def records(self, gm: GuildViewer, scene: str) -> list[dict[str, Any]]:
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
                    runs.c.status == "reviewed",
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
                for i, item in enumerate(batch.inputs):
                    live = self.observer._latest_source(c, item.source_id)
                    if live != item or not self._same_scope(c, gm, scene, item, record["items"][i]):
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
