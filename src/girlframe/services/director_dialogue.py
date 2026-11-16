"""Controller-requested synthetic NPC/Handler drafts, never human Pilot speech."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.director_context import DirectorContextService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorDialogueService:
    def __init__(self, context: DirectorContextService):
        self.context = context
        self.store = context.store

    def draft(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        actor: ActorRef,
        expected_context: str,
        source_refs: tuple[str, ...],
    ) -> dict[str, Any]:
        if actor.kind not in ("npc", "handler"):
            raise WorkflowError("PLAYER_AGENCY: Director dialogue cannot portray a human Pilot.")

        def authorize(c: Connection) -> None:
            self.context._build(c, viewer, scene_id, actor=actor)

        def operation(c: Connection) -> dict[str, Any]:
            self.context.observations.game.unpaused(c)
            context = self.context._build(c, viewer, scene_id, actor=actor)
            if context.revision != expected_context:
                raise WorkflowError("STALE_CONTEXT: refresh this actual role’s knowledge.")
            refs = {x.id: x for x in context.references}
            if (
                not source_refs
                or len(set(source_refs)) != len(source_refs)
                or not set(source_refs) <= refs.keys()
            ):
                raise WorkflowError(
                    "UNKNOWN_KNOWLEDGE: select actual references known by this role."
                )
            identity = "dialogue:" + str(uuid4())
            result = {
                "id": identity,
                "scene_id": scene_id,
                "actor": actor.model_dump(mode="json"),
                "owner_id": str(viewer.user_id),
                "context_revision": context.revision,
                "source_refs": list(source_refs),
                "kind": "NPC_DIALOGUE",
                "text": "Reports available to me:\n"
                + "\n".join(json.dumps(refs[x].text, ensure_ascii=False) for x in source_refs),
                "status": "draft",
                "scope": "private_unperformed_draft",
                "application": "blocked",
                "publication": "blocked",
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
            return {
                "id": identity,
                "status": "draft",
                "scope": "private_unperformed_draft",
                "application": "blocked",
                "publication": "blocked",
            }

        return self.store._write(
            viewer,
            key,
            "director.dialogue_draft",
            {
                "scene_id": scene_id,
                "actor": actor.model_dump(mode="json"),
                "source_refs": source_refs,
            },
            operation,
            authorize=authorize,
        )

    def get(self, viewer: GuildViewer, scene_id: str, identity: str) -> dict[str, Any]:
        with self.store.transaction() as c:
            return self._owned(c, viewer, scene_id, identity)

    def _owned(
        self, c: Connection, viewer: GuildViewer, scene_id: str, identity: str
    ) -> dict[str, Any]:
        self.context.observations._scene(c, scene_id, viewer)
        table = t.director_context["shadow"]
        body = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene_id,
                table.c.id == identity,
            )
        )
        if not body:
            raise WorkflowError("DIALOGUE_UNAVAILABLE: no accessible draft.")
        result = dict(json.loads(body))
        if result.get("owner_id") != str(viewer.user_id) or not identity.startswith("dialogue:"):
            raise WorkflowError("DIALOGUE_UNAVAILABLE: no accessible draft.")
        actor = ActorRef.model_validate_json(json.dumps(result["actor"]))
        self.context._build(c, viewer, scene_id, actor=actor)
        return result

    def review(
        self, viewer: GuildViewer, key: str, scene_id: str, identity: str, *, decision: str
    ) -> dict[str, Any]:
        if decision not in ("approve", "reject"):
            raise WorkflowError("INVALID_REVIEW: choose approve or reject.")

        def authorize(c: Connection) -> None:
            self._owned(c, viewer, scene_id, identity)

        def operation(c: Connection) -> dict[str, Any]:
            draft = self._owned(c, viewer, scene_id, identity)
            actor = ActorRef.model_validate_json(json.dumps(draft["actor"]))
            current = self.context._build(c, viewer, scene_id, actor=actor)
            if decision == "approve":
                self.context.observations.game.unpaused(c)
                if current.revision != draft["context_revision"]:
                    raise WorkflowError("STALE_CONTEXT: regenerate this role’s draft.")
            table = t.director_context["shadow"]
            review_id = identity + ":review"
            if c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == self.store.campaign_id, table.c.id == review_id
                )
            ):
                raise WorkflowError("REVIEW_FINAL: this draft already has an immutable review.")
            result = {
                "id": review_id,
                "owner_id": str(viewer.user_id),
                "actor": draft["actor"],
                "decision": decision,
                "application": "blocked",
                "publication": "blocked",
            }
            c.execute(
                table.insert().values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    id=review_id,
                    body_json=json.dumps(result, sort_keys=True),
                )
            )
            return result

        return self.store._write(
            viewer,
            key,
            "director.dialogue_review",
            {"scene_id": scene_id, "id": identity, "decision": decision},
            operation,
            authorize=authorize,
        )
