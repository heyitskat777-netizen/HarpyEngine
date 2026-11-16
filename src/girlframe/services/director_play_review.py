"""Source-bound GM triage and real-owner work for every inventoried workflow.

Review notes never finish a native Play, issue a Handler Play, or publish fiction.
"""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import _digest
from girlframe.services.director_play_catalog import PlayCatalog
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorPlayReviewService:
    def __init__(self, context: DirectorContextService, catalog: PlayCatalog | None = None):
        self.context = context
        self.observer = context.observations
        self.store = context.store
        self.game = self.observer.game
        self.catalog = catalog if catalog is not None else PlayCatalog()

    def _scope(self, c: Connection, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        self.observer._scope()
        row = self.observer._scene(c, scene, viewer)
        state = self.observer._state(c, scene)
        if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
            raise WorkflowError("OBSERVATION_DISABLED: current scene consent is required.")
        self.game.unpaused(c)
        return row

    def _source(self, c: Connection, scene: str, identity: str, revision: int) -> Any:
        source = self.observer._latest_source(c, identity)
        inputs = t.director["inputs"]
        if (
            source is None
            or source.kind != "message"
            or source.source_revision != revision
            or not c.scalar(
                sa.select(inputs.c.source_id)
                .where(
                    inputs.c.campaign_id == self.store.campaign_id,
                    inputs.c.scene_id == scene,
                    inputs.c.source_id == identity,
                )
                .limit(1)
            )
        ):
            raise WorkflowError("STALE_REVIEW_SOURCE: recover the current accepted declaration.")
        return source

    def _save(self, c: Connection, value: dict[str, Any]) -> None:
        c.execute(
            t.director_context["shadow"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                scene_id=value["scene_id"],
                id=value["id"],
                body_json=json.dumps(value, sort_keys=True),
            )
        )

    def _capture(
        self, c: Connection, viewer: GuildViewer, scene: str, source_id: str, revision: int
    ) -> str:
        """Called only inside the authenticated conversation's original write transaction."""
        self._scope(c, viewer, scene)
        source = self._source(c, scene, source_id, revision)
        _, _, actual = self.observer._authorize_input(c, viewer, scene, source.actor.kind)
        if source.author_id != str(viewer.user_id) or actual != source.actor:
            raise WorkflowError("REVIEW_NOT_OWNED: retain the actual source author and role.")
        identity = "play-review:" + str(uuid4())
        self._save(
            c,
            {
                "id": identity,
                "record_type": "director_play_review",
                "scene_id": scene,
                "owner_id": str(viewer.user_id),
                "source_id": source_id,
                "source_revision": revision,
                "actor": source.actor.model_dump(mode="json"),
                "catalog_digest": self.catalog.digest,
                "candidates": [
                    r.model_dump(mode="json") for r in self.catalog.recognize(source.text or "")
                ],
            },
        )
        return identity

    def _record(self, c: Connection, scene: str, identity: str) -> dict[str, Any]:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == identity,
            )
        )
        record = json.loads(raw) if raw else None
        if not record or record.get("record_type") != "director_play_review":
            raise WorkflowError("REVIEW_UNAVAILABLE: no accessible review in this scene.")
        return dict(record)

    def _decisions(self, c: Connection, scene: str, identity: str) -> list[dict[str, Any]]:
        table = t.director_context["shadow"]
        return [
            json.loads(raw)
            for raw in c.scalars(
                sa.select(table.c.body_json)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    sa.func.json_extract(table.c.body_json, "$.record_type")
                    == "director_play_review_decision",
                    sa.func.json_extract(table.c.body_json, "$.review_id") == identity,
                )
                .order_by(sa.func.json_extract(table.c.body_json, "$.revision"))
            )
        ]

    def _fingerprint(self, c: Connection, scene: dict[str, Any], record: dict[str, Any]) -> str:
        source = self._source(c, scene["id"], record["source_id"], record["source_revision"])
        return _digest(
            {
                "source": source.model_dump(mode="json"),
                "guard": self.observer._guard(c, scene, self.observer._state(c, scene["id"])),
                "references": [
                    r.model_dump(mode="json") for r in self.context._current(c, scene["id"])
                ],
                "catalog": self.catalog.digest,
            }
        )

    def _work(self, c: Connection, scene: str, viewer: GuildViewer | None) -> dict[str, Any]:
        # Human choice authority comes from native pending_choices, including scoped authors.
        actions = t.m2["m2_actions"]
        ids = set(
            c.scalars(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.scene_id == scene,
                )
            )
        )
        if viewer is None:
            choices = [
                dict(row)
                for row in c.execute(
                    sa.select(t.m2["m2_choices"]).where(
                        t.m2["m2_choices"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_choices"].c.action_id.in_(ids),
                        t.m2["m2_choices"].c.state == "pending",
                    )
                ).mappings()
            ]
        else:
            choices = [x for x in self.game.pending_choices(c, viewer) if x["action_id"] in ids]
        work = t.m3["m3_required_work"]
        latest = {
            row["id"]: dict(row)
            for row in c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id,
                    work.c.scene_id == scene,
                )
                .order_by(work.c.revision)
            ).mappings()
        }
        required = [
            {key: row[key] for key in ("id", "revision", "kind", "state")}
            for row in latest.values()
            if row["state"] != "resolved"
            and (viewer is None or row["owner_id"] == str(viewer.user_id))
        ]
        canon = load_state(c, self.store.campaign_id)
        grants = [
            {
                "id": g.id,
                "state": g.state,
                "selected": g.selected,
                "entrypoint": "HandlerPlayService",
                "source_action": g.source_action,
            }
            for g in canon.handler_plays
            if g.scope.scene_id == scene
            and g.state in ("pending", "awaiting_effect")
            and (viewer is None or g.chooser_controller == viewer.user_id)
        ]
        return {"choices": choices, "required_work": required, "handler_grants": grants}

    def gm(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row = self._scope(c, viewer, scene)
            context = self.context._build(c, viewer, scene, actor=None)
            record = self._record(c, scene, identity)
            fingerprint = self._fingerprint(c, row, record)
            decisions = self._decisions(c, scene, identity)
            source = self._source(c, scene, record["source_id"], record["source_revision"])
            return {
                **record,
                "fingerprint": fingerprint,
                "source": source.model_dump(mode="json"),
                "gm_context": context.model_dump(mode="json"),
                "canonical": load_state(c, self.store.campaign_id).model_dump(mode="json"),
                "work": self._work(c, scene, None),
                "decisions": decisions,
                "current_decision": next(
                    (d for d in reversed(decisions) if d["fingerprint"] == fingerprint), None
                ),
                "mechanics_applied": False,
            }

    def queue(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            self.context._build(c, viewer, scene, actor=None)
            table = t.director_context["shadow"]
            records = [
                json.loads(raw)
                for raw in c.scalars(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        sa.func.json_extract(table.c.body_json, "$.record_type")
                        == "director_play_review",
                    )
                )
            ]
        result = []
        for record in records:
            try:
                result.append(self.gm(viewer, scene, record["id"]))
            except WorkflowError as error:
                if not str(error).startswith("STALE_REVIEW_SOURCE"):
                    raise
                result.append({"id": record["id"], "status": "source_stale"})
        return result

    def review(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        identity: str,
        expected_fingerprint: str,
        play_id: str,
        decision: str,
        private_note: str,
    ) -> dict[str, Any]:
        if (
            decision not in ("native_workflow", "needs_clarification", "manual_review", "blocked")
            or not 1 <= len(private_note) <= 4000
        ):
            raise WorkflowError("INVALID_REVIEW: choose a bounded private routing decision.")
        try:
            selected = self.catalog.get(play_id)
        except ValueError:
            raise WorkflowError(
                "UNKNOWN_REVIEW_PLAY: choose a registered source workflow."
            ) from None

        def authorize(c: Connection) -> None:
            self._scope(c, viewer, scene)
            self.context._build(c, viewer, scene, actor=None)

        def operation(c: Connection) -> dict[str, Any]:
            scene_row = self._scope(c, viewer, scene)
            record = self._record(c, scene, identity)
            if self._fingerprint(c, scene_row, record) != expected_fingerprint:
                raise WorkflowError("STALE_PLAY_REVIEW: refresh the current source and work.")
            if record["candidates"] and selected.play_id not in {
                x["play_id"] for x in record["candidates"]
            }:
                raise WorkflowError("WRONG_REVIEW_PLAY: clarify this actual declaration.")
            if decision == "native_workflow" and selected.adapter not in (
                "structured_native",
                "native_owner_review",
            ):
                raise WorkflowError(
                    "BLOCKED_PLAY_ADAPTER: source review does not implement mechanics."
                )
            value = {
                "id": "play-review-decision:" + str(uuid4()),
                "record_type": "director_play_review_decision",
                "scene_id": scene,
                "review_id": identity,
                "fingerprint": expected_fingerprint,
                "play_id": selected.play_id,
                "decision": decision,
                "private_note": private_note,
                "reviewer_id": str(viewer.user_id),
                "revision": len(self._decisions(c, scene, identity)) + 1,
                "mechanics_applied": False,
            }
            self._save(c, value)
            return {"id": value["id"], "review_id": identity, "mechanics_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.play_triage",
            {
                "scene": scene,
                "id": identity,
                "fingerprint": expected_fingerprint,
                "play": selected.play_id,
                "decision": decision,
                "private_note": private_note,
            },
            operation,
            authorize=authorize,
        )

    def view(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row = self._scope(c, viewer, scene)
            record = self._record(c, scene, identity)
            if record["owner_id"] != str(viewer.user_id):
                raise WorkflowError("REVIEW_NOT_OWNED: private status belongs to its requester.")
            fingerprint = self._fingerprint(c, row, record)
            decisions = self._decisions(c, scene, identity)
            current = next(
                (d for d in reversed(decisions) if d["fingerprint"] == fingerprint), None
            )
            return {
                "id": identity,
                "status": current["decision"] if current else "awaiting_gm_review",
                "candidates": record["candidates"],
                "mechanics_applied": False,
                "text": "Review routing applies no native outcome; "
                "original owner choices remain required.",
            }

    def owner_work(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            result = self._work(c, scene, viewer)
        return {**result, "campaign_owner_inbox": self._owner_inbox(viewer)}

    def _owner_inbox(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        from girlframe.services.inbox import InboxService

        return [
            {
                "id": item.identity,
                "task": item.task,
                "category": item.category,
                "state": item.state,
                "incoming": item.incoming,
                "revision": item.revision,
            }
            for item in InboxService(self.store).items(viewer)
            if item.category
            in ("plays", "playbook", "facilitator", "off_duty", "missions", "world")
        ]

    def gm_work(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        """Also exposes actual pending sources that were opened outside Director chat."""
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            self.context._build(c, viewer, scene, actor=None)
            return self._work(c, scene, None)

    def handler_work(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            context = self.context._handler_for_request(c, viewer, scene)
            if (
                context.actor is None
                or load_state(c, self.store.campaign_id).handler != viewer.user_id
            ):
                raise WorkflowError(
                    "HANDLER_REVIEW_NOT_OWNED: use the actual appointed controller."
                )
            result = {
                "context": context.model_dump(mode="json"),
                "work": self._work(c, scene, viewer),
            }
        # OOC controller coordination: never part of HandlerRequest or fictional knowledge.
        return {**result, "campaign_owner_inbox": self._owner_inbox(viewer)}
