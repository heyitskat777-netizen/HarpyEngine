"""Explicit, actor-owned and recipient-scoped synthetic NPC scene contributions."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import KnowledgeReference
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.director_context import DirectorContextService, next_contribution_ordinal
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_observation import _digest
from girlframe.services.director_reactions import DirectorReactionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class NpcDeliveryService:
    def __init__(self, context: DirectorContextService):
        self.context = context
        self.observer, self.store = context.observations, context.store
        self.knowledge = DirectorKnowledgeService(context)

    def _scope(
        self,
        c: Connection,
        scene: str,
        viewer: GuildViewer | None = None,
        *,
        allow_closed: bool = False,
    ) -> dict[str, Any]:
        self.observer._scope()
        row = self.observer._scene(c, scene, viewer, allow_closed=allow_closed)
        state = self.observer._state(c, scene)
        if (
            state.activity_epoch is None
            or state.policy.mode != "shadow"
            or not self.observer._consented(c, row, state)
        ):
            raise WorkflowError("NPC_DELIVERY_DISABLED: current Activity consent is required.")
        return row

    def _shared_refs(
        self, c: Connection, scene: str, roles: tuple[ActorRef, ...], citations: tuple[str, ...]
    ) -> None:
        current = self.context._current(c, scene)
        if any(
            not set(citations) <= {ref.id for ref in self.context._actor_references(current, actor)}
            for actor in roles
        ):
            raise WorkflowError(
                "NPC_DELIVERY_KNOWLEDGE: review any disclosure through its own route."
            )

    def plan(
        self,
        c: Connection,
        scene: str,
        packet: dict[str, Any],
        proposal: dict[str, Any],
        recipients: tuple[ActorRef, ...],
    ) -> dict[str, Any]:
        actor = ActorRef.model_validate(packet["actor"])
        if actor.kind != "npc" or proposal["kind"] not in {
            "DIALOGUE",
            "REFUSE",
            "COMPROMISE",
            "DELAY",
        }:
            raise WorkflowError("NPC_DELIVERY_REVIEW: use a reviewed dialogue-only NPC reaction.")
        row = self._scope(c, scene)
        actual = {view.ref: view.controller for view in self.knowledge._actor_views(c, row)}
        roles = (actor, *recipients)
        if (
            not recipients
            or len(roles) > 26
            or len(set(roles)) != len(roles)
            or not set(roles) <= actual.keys()
        ):
            raise WorkflowError(
                "NPC_DELIVERY_AUDIENCE: choose distinct listeners in the current cast."
            )
        self._shared_refs(c, scene, roles, tuple(proposal["cited_references"]))
        origin = self.knowledge._source(c, scene, packet["source_id"])
        return {
            "actor": packet["actor"],
            "recipients": [ref.model_dump(mode="json") for ref in recipients],
            "controllers": {ref.token: actual[ref] for ref in roles},
            "consent": self.observer._state(c, scene).consent_generation,
            "source": origin.id,
            "source_revision": origin.revision,
        }

    def _record_authority(
        self, c: Connection, scene: str, record: dict[str, Any], *, allow_closed: bool = False
    ) -> tuple[ActorRef, ...]:
        from girlframe.services.director_worldbuilding import DirectorWorldbuildingService

        row = self._scope(c, scene, allow_closed=allow_closed)
        roles = tuple(ActorRef.model_validate(x) for x in (record["actor"], *record["recipients"]))
        source = self.knowledge._source(c, scene, record["source"], allow_closed=allow_closed)
        if (
            record["consent"] != self.observer._state(c, scene).consent_generation
            or record["source_revision"] != source.revision
            or not DirectorWorldbuildingService(self.context)._disclosure_actors(
                c, row, roles, {"recipient_controllers": record["controllers"]}, allow_closed
            )
        ):
            raise WorkflowError("STALE_NPC_DELIVERY: review the current source and cast again.")
        return roles

    def _record(self, c: Connection, scene: str, identity: str) -> dict[str, Any] | None:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == identity,
            )
        )
        return dict(json.loads(raw)) if raw else None

    def deliver(
        self, controller: GuildViewer, key: str, scene: str, proposal_id: str
    ) -> dict[str, Any]:
        reactions = DirectorReactionService(self.context)
        identity = "npc-delivery:" + proposal_id

        def approved(c: Connection) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            self._scope(c, scene, controller)
            self.observer.game.unpaused(c)
            proposal, packet = reactions._owned(c, controller, scene, proposal_id, fresh=False)
            review = reactions._review_record(c, scene, proposal_id)
            if (
                not review
                or review["decision"] != "approve"
                or not review.get("delivery")
                or review["controller"] != controller.user_id
            ):
                raise WorkflowError(
                    "NPC_DELIVERY_REVIEW: approve the reply and its actual listeners first."
                )
            self._record_authority(c, scene, review["delivery"])
            return proposal["proposal"], packet, review["delivery"]

        def operation(c: Connection) -> dict[str, Any]:
            old = self._record(c, scene, identity)
            if old:
                return {"id": identity, "reference": old["reference"], "effects_applied": False}
            proposal, packet, plan = approved(c)
            reactions._fresh(c, packet, approved_run=True)
            actual = self.plan(
                c,
                scene,
                packet,
                proposal,
                tuple(ActorRef.model_validate(x) for x in plan["recipients"]),
            )
            if actual != plan:
                raise WorkflowError("STALE_NPC_DELIVERY: preserve the exact approved listeners.")
            from girlframe.services.m2_state import load_state
            from girlframe.services.m3_sentinel import require_communication

            require_communication(
                c,
                self.store.campaign_id,
                load_state(c, self.store.campaign_id),
                ActorRef.model_validate(plan["actor"]),
                tuple(ActorRef.model_validate(x) for x in plan["recipients"]),
            )
            episode = "npc-heard-episode:" + _digest(
                {
                    "actor": plan["actor"],
                    "source": plan["source"],
                    "revision": plan["source_revision"],
                }
            )
            if self._record(c, scene, episode):
                raise WorkflowError(
                    "REACTION_ADDRESSED: dialogue was already delivered for this turn."
                )
            if len(self.context._active(c, scene)) >= 100:
                raise WorkflowError("CONTEXT_LIMIT: retire references before delivering dialogue.")
            ref = KnowledgeReference(
                id=str(uuid4()),
                source_id=identity,
                source_revision=1,
                order=len(self.context._references(c, scene)) + 1,
                known_by=tuple(sorted(plan["controllers"])),
                dependencies=tuple(proposal["cited_references"]),
                reported_by=ActorRef.model_validate(plan["actor"]),
                classification="reported_claim",
                text="Reported claim: " + proposal["text"],
            )
            reactions._save(
                c,
                scene,
                identity,
                "npc_delivery",
                reference=ref.id,
                ordinal=next_contribution_ordinal(c, self.store.campaign_id, scene),
                after_sequence=self.observer._state(c, scene).sequence,
                delivered_at=float(self.store.clock()),
                text=proposal["text"],
                dependencies=proposal["cited_references"],
                **plan,
            )
            reactions._save(c, scene, episode, "npc_delivered_episode", delivery=identity)
            c.execute(
                t.director_context["knowledge"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene,
                    id=ref.id,
                    body_json=ref.model_dump_json(),
                )
            )
            return {"id": identity, "reference": ref.id, "effects_applied": False}

        def authorize(c: Connection) -> None:
            approved(c)

        return self.store._write(
            controller,
            key,
            "director.npc_delivered",
            {"scene": scene, "proposal": proposal_id},
            operation,
            authorize=authorize,
        )

    def validate_reference(
        self, c: Connection, scene: str, ref: KnowledgeReference, *, allow_closed: bool
    ) -> None:
        record = self._record(c, scene, ref.source_id)
        if (
            not record
            or record.get("record_type") != "npc_delivery"
            or record["reference"] != ref.id
            or "Reported claim: " + record["text"] != ref.text
            or ref.classification != "reported_claim"
            or ref.source_revision != 1
            or tuple(record["dependencies"]) != ref.dependencies
            or ref.reported_by != ActorRef.model_validate(record["actor"])
            or set(ref.known_by) != set(record["controllers"])
        ):
            raise WorkflowError("STALE_NPC_DELIVERY: recover the original hearing record.")
        self._record_authority(c, scene, record, allow_closed=allow_closed)

    def hearing(self, gm: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        self.store.administrator(gm)
        with self.store.engine.connect() as c:
            self._scope(c, scene, gm, allow_closed=True)
            record = self._record(c, scene, identity)
            if (
                not record
                or record.get("record_type") != "npc_delivery"
                or not any(
                    ref.source_id == identity
                    for ref in self.context._current(c, scene, allow_closed=True)
                )
            ):
                raise WorkflowError("NPC_DELIVERY_UNAVAILABLE: select a current hearing record.")
            return {
                name: record[name]
                for name in ("id", "actor", "recipients", "controllers", "text", "reference")
            }

    def contributions(self, c: Connection, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        if self.observer._state(c, scene).activity_epoch is None:
            return []
        self._scope(c, scene, viewer, allow_closed=True)
        identities = {
            ref.source_id
            for ref in self.context._current(c, scene, allow_closed=True)
            if ref.source_id.startswith("npc-delivery:")
        }
        result = []
        for identity in identities:
            record = self._record(c, scene, identity)
            if record and viewer.user_id in record["controllers"].values():
                result.append(
                    {
                        "id": identity,
                        "actor": record["actor"],
                        "kind": "npc",
                        "sequence": record["after_sequence"],
                        "ordinal": record["ordinal"],
                        "created": record["delivered_at"],
                        "text": record["text"],
                    }
                )
        return result
