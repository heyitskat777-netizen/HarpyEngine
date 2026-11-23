"""Facilitator-linked outcomes of a Handler promise accepted in a closed scene."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import KnowledgeReference
from girlframe.ai.director_dossiers import HandlerExperience
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.activity_fiction import ActivityFiction
from girlframe.services.director_closeout import handler_experiences
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_worldbuilding import DirectorWorldbuildingService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class HandlerCommitments:
    def __init__(self, context: DirectorContextService):
        self.context, self.store = context, context.store
        self.world = DirectorWorldbuildingService(context)

    def _accepted(
        self, c: Connection, scene: str, handler: ActorRef
    ) -> tuple[HandlerExperience, ...]:
        row = self.context.observations._scene(c, scene)
        cast = self.world.knowledge._actors(c, row)
        if handler not in cast:
            return ()
        return tuple(
            item
            for item in handler_experiences(self.context, c, handler, cast, limit=None)
            if item.kind == "accepted_help" and item.offer_reference
        )

    def _results(self, c: Connection, scene: str) -> dict[str, KnowledgeReference]:
        return {
            ref.id: ref
            for ref in self.context._current(c, scene)
            if ref.classification == "established_world"
            and ref.origin_scene is None
            and ref.source_id.startswith("world-disclosure:")
        }

    def _linked(self, c: Connection, close_event: str) -> bool:
        table = t.director_context["shadow"]
        return (
            c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == "handler-commitment:" + close_event,
                )
            )
            is not None
        )

    def _matches(
        self,
        c: Connection,
        scene: str,
        handler: ActorRef,
        item: HandlerExperience,
        result: KnowledgeReference,
    ) -> bool:
        if not {handler.token, item.pilot.token} <= set(result.known_by):
            return False
        disclosure = self.world._record(c, scene, result.source_id, "worldbuilding_disclosure")
        committed = self.world._record(c, scene, disclosure["commit_id"], "worldbuilding_commit")
        packet, proposal = self.world._load(c, scene, committed["proposal_id"])
        return any(
            ref.origin_scene == item.scene
            and ref.origin_reference == item.reference_id
            and "reference:" + ref.id in proposal.cited_evidence
            for ref in packet.context.references
        )

    def work(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.world._scope(c, viewer, scene, gm=True, native_access=False)
            handler = active_handler(load_state(c, self.store.campaign_id))
            if handler is None:
                return []
            results = self._results(c, scene)
            return [
                {
                    "id": item.close_event,
                    "offer": item.offer_text,
                    "choice": item.reported_text,
                    "results": [
                        {"id": ref.id, "text": ref.text}
                        for ref in results.values()
                        if self._matches(c, scene, handler, item, ref)
                    ],
                }
                for item in self._accepted(c, scene, handler)
                if not self._linked(c, item.close_event)
            ]

    def link(
        self, viewer: GuildViewer, key: str, scene: str, commitment: str, reference: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            identity = "handler-commitment:" + commitment
            handler = active_handler(load_state(c, self.store.campaign_id))
            item = (
                next(
                    (x for x in self._accepted(c, scene, handler) if x.close_event == commitment),
                    None,
                )
                if handler
                else None
            )
            result = self._results(c, scene).get(reference)
            if (
                handler is None
                or item is None
                or result is None
                or not self._matches(c, scene, handler, item, result)
                or self._linked(c, commitment)
            ):
                raise WorkflowError(
                    "HANDLER_COMMITMENT_UNAVAILABLE: select an accepted offer and reviewed result."
                )
            self.world._save(c, scene, identity, "handler_commitment_result", reference=reference)
            return {"id": identity, "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.handler_commitment_result",
            {"scene": scene, "commitment": commitment, "reference": reference},
            operation,
            authorize=lambda c: self.world._scope(c, viewer, scene, gm=True, native_access=False),
            auto_audit=False,
        )

    def ready(
        self, c: Connection, scene: str, handler: ActorRef, pilot: ActorRef
    ) -> KnowledgeReference | None:
        table = t.director_context["shadow"]
        if not c.scalar(
            sa.select(table.c.id)
            .where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id.like("handler-commitment:%"),
            )
            .limit(1)
        ):
            return None
        accepted = [item for item in self._accepted(c, scene, handler) if item.pilot == pilot]
        if not accepted:
            return None
        results = self._results(c, scene)
        if not results:
            return None
        told = {
            citation
            for row in ActivityFiction(self.context)._delivered(c, scene, handler)
            if pilot.model_dump(mode="json") in row["recipients"]
            for citation in row.get("citations", ())
        }
        for item in accepted:
            record = self.world._saved(c, scene, "handler-commitment:" + item.close_event)
            if not record or record["reference"] in told:
                continue
            result = results.get(record["reference"])
            if result and self._matches(c, scene, handler, item, result):
                return result
        return None
